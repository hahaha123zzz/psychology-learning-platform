"""可恢复教材上传会话。

浏览器只把分片上传至 MinIO 的预签名地址；服务端仅保存会话、ETag 与最终
校验结果。因此刷新页面、跳转到其他页面或网络短暂中断都不会丢失已完成分片。
"""

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.storage import (
    abort_multipart_upload,
    complete_multipart_upload,
    copy_object,
    create_multipart_upload,
    delete_object,
    ensure_bucket,
    object_sha256,
    presign_upload_part,
)
from app.db.models import Material, MaterialVersion, UploadPart, UploadSession
from app.modules.materials import service as materials_service

ACTIVE_UPLOAD_STATUSES = ("created", "uploading", "uploaded", "verifying")


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower()


def _expected_part_size(session: UploadSession, part_number: int) -> int:
    start = (part_number - 1) * session.part_size_bytes
    return min(session.part_size_bytes, session.size_bytes - start)


def total_parts(session: UploadSession) -> int:
    return ceil(session.size_bytes / session.part_size_bytes)


async def reserve_upload_quota(db: AsyncSession, course_id: str, incoming: int) -> None:
    """把已落库资料和未完成上传会话一起纳入课程容量计算。"""
    settings = get_settings()
    quota_bytes = settings.course_storage_quota_gb * 1024 * 1024 * 1024
    material_used = await db.scalar(
        select(func.coalesce(func.sum(MaterialVersion.size_bytes), 0)).where(
            MaterialVersion.material_id.in_(
                select(Material.id).where(Material.course_id == course_id)
            ),
            MaterialVersion.status != "failed",
        )
    )
    reserved = await db.scalar(
        select(func.coalesce(func.sum(UploadSession.size_bytes), 0)).where(
            UploadSession.course_id == course_id,
            UploadSession.status.in_(ACTIVE_UPLOAD_STATUSES),
        )
    )
    used = int(material_used or 0) + int(reserved or 0)
    if used + incoming > quota_bytes:
        raise ApiError(
            status_code=413,
            code="COURSE_STORAGE_QUOTA_EXCEEDED",
            message="课程存储空间已满，无法创建上传任务",
            details={"used_bytes": used, "quota_bytes": quota_bytes},
        )


async def create_session(
    db: AsyncSession,
    *,
    course_id: str,
    title: str,
    material_type: str,
    filename: str,
    size_bytes: int,
    created_by: str,
) -> UploadSession:
    extension = materials_service.validate_file_name(filename)
    settings = get_settings()
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if size_bytes <= 0:
        raise ApiError(status_code=422, code="EMPTY_FILE", message="文件内容为空")
    if size_bytes > max_bytes:
        raise ApiError(
            status_code=413,
            code="FILE_TOO_LARGE",
            message=f"文件超过大小上限 {settings.upload_max_mb}MB",
            details={"max_bytes": max_bytes},
        )
    await reserve_upload_quota(db, course_id, size_bytes)
    content_type = materials_service.ALLOWED_TYPES[extension][0]
    now = datetime.now(UTC)
    session = UploadSession(
        course_id=course_id,
        title=title,
        material_type=material_type,
        original_filename=filename[:255],
        content_type=content_type,
        size_bytes=size_bytes,
        part_size_bytes=settings.upload_part_size_mb * 1024 * 1024,
        object_key="pending",
        multipart_upload_id="pending",
        status="created",
        expires_at=now + timedelta(hours=settings.upload_session_ttl_hours),
        created_by=created_by,
    )
    db.add(session)
    await db.flush()
    session.object_key = f"courses/{course_id}/uploads/{session.id}/source.{extension}"
    try:
        await ensure_bucket()
        session.multipart_upload_id = await create_multipart_upload(
            key=session.object_key, content_type=content_type
        )
    except Exception as exc:  # noqa: BLE001
        session.status = "failed"
        raise ApiError(
            status_code=502,
            code="STORAGE_UNAVAILABLE",
            message="对象存储暂时不可用，请稍后重试",
            retryable=True,
        ) from exc
    session.status = "uploading"
    return session


async def get_session_or_404(db: AsyncSession, session_id: str) -> UploadSession:
    session = await db.get(UploadSession, session_id)
    if session is None:
        raise ApiError(status_code=404, code="UPLOAD_SESSION_NOT_FOUND", message="上传任务不存在")
    return session


async def expire_if_needed(db: AsyncSession, session: UploadSession) -> None:
    if session.status not in ACTIVE_UPLOAD_STATUSES or session.expires_at > datetime.now(UTC):
        return
    try:
        await abort_multipart_upload(key=session.object_key, upload_id=session.multipart_upload_id)
    except Exception:  # noqa: BLE001
        # 会话已失效，即使对象存储清理稍后执行也不能继续使用。
        pass
    session.status = "expired"


async def require_uploading(db: AsyncSession, session: UploadSession) -> None:
    await expire_if_needed(db, session)
    if session.status == "expired":
        raise ApiError(
            status_code=409,
            code="UPLOAD_SESSION_EXPIRED",
            message="上传任务已过期，请重新选择文件开始上传",
        )
    if session.status != "uploading":
        raise ApiError(
            status_code=409,
            code="UPLOAD_SESSION_NOT_ACTIVE",
            message="当前上传任务不可继续",
            details={"status": session.status},
        )


async def get_part_url(db: AsyncSession, session: UploadSession, part_number: int) -> dict:
    await require_uploading(db, session)
    count = total_parts(session)
    if part_number < 1 or part_number > count:
        raise ApiError(
            status_code=422,
            code="UPLOAD_PART_OUT_OF_RANGE",
            message="分片序号超出文件范围",
            details={"total_parts": count},
        )
    url = await presign_upload_part(
        key=session.object_key, upload_id=session.multipart_upload_id, part_number=part_number
    )
    return {
        "part_number": part_number,
        "size_bytes": _expected_part_size(session, part_number),
        "upload_url": url,
    }


async def record_part(
    db: AsyncSession, session: UploadSession, *, part_number: int, etag: str, size_bytes: int
) -> UploadPart:
    await require_uploading(db, session)
    if part_number < 1 or part_number > total_parts(session):
        raise ApiError(
            status_code=422, code="UPLOAD_PART_OUT_OF_RANGE", message="分片序号超出文件范围"
        )
    expected = _expected_part_size(session, part_number)
    if size_bytes != expected:
        raise ApiError(
            status_code=422,
            code="UPLOAD_PART_SIZE_MISMATCH",
            message="分片大小与会话声明不一致",
            details={"expected_bytes": expected, "received_bytes": size_bytes},
        )
    normalized_etag = etag.strip().strip('"')
    if not normalized_etag:
        raise ApiError(status_code=422, code="UPLOAD_PART_ETAG_REQUIRED", message="缺少分片 ETag")
    part = await db.get(UploadPart, {"upload_session_id": session.id, "part_number": part_number})
    if part is None:
        part = UploadPart(
            upload_session_id=session.id,
            part_number=part_number,
            etag=normalized_etag,
            size_bytes=size_bytes,
        )
        db.add(part)
    else:
        part.etag = normalized_etag
        part.size_bytes = size_bytes
    return part


async def complete_session(
    db: AsyncSession, session: UploadSession, created_by: str
) -> tuple[Material, MaterialVersion]:
    await require_uploading(db, session)
    parts = list(
        (
            await db.execute(
                select(UploadPart)
                .where(UploadPart.upload_session_id == session.id)
                .order_by(UploadPart.part_number)
            )
        ).scalars()
    )
    expected_numbers = list(range(1, total_parts(session) + 1))
    if [part.part_number for part in parts] != expected_numbers:
        raise ApiError(
            status_code=409,
            code="UPLOAD_PARTS_INCOMPLETE",
            message="仍有文件分片未上传完成",
            details={
                "completed_parts": [part.part_number for part in parts],
                "total_parts": total_parts(session),
            },
        )
    session.status = "verifying"
    await db.flush()
    try:
        await complete_multipart_upload(
            key=session.object_key,
            upload_id=session.multipart_upload_id,
            parts=[{"PartNumber": part.part_number, "ETag": part.etag} for part in parts],
        )
        sha256, actual_size = await object_sha256(session.object_key)
    except Exception as exc:  # noqa: BLE001
        # 分片仍完整保留在 MinIO；回滚到 uploading 后可直接重试完成操作。
        raise ApiError(
            status_code=502,
            code="UPLOAD_FINALIZATION_FAILED",
            message="文件已上传但服务端校验未完成，可稍后重试完成操作",
            retryable=True,
        ) from exc
    if actual_size != session.size_bytes:
        session.status = "failed"
        # 确定性失败必须持久化，否则异常回滚会让教师误以为仍可继续上传。
        await db.commit()
        raise ApiError(
            status_code=422,
            code="UPLOAD_SIZE_MISMATCH",
            message="合并后的文件大小与原始文件不一致",
            details={"expected_bytes": session.size_bytes, "actual_bytes": actual_size},
        )
    duplicate = await materials_service.find_duplicate(
        db, course_id=session.course_id, sha256=sha256
    )
    if duplicate is not None:
        session.status = "failed"
        await db.commit()
        raise ApiError(
            status_code=409,
            code="DUPLICATE_MATERIAL",
            message="课程中已存在内容相同的文件，可直接复用",
            details={"material_id": duplicate.material_id, "version_id": duplicate.id},
        )
    material = Material(
        course_id=session.course_id,
        title=session.title,
        material_type=session.material_type,
        visibility="draft",
        created_by=created_by,
    )
    db.add(material)
    await db.flush()
    version = MaterialVersion(
        material_id=material.id,
        version_no=1,
        status="uploaded",
        original_filename=session.original_filename,
        sha256=sha256,
        size_bytes=actual_size,
        content_type=session.content_type,
        object_key=materials_service.material_object_key(
            course_id=session.course_id,
            material_id=material.id,
            version_id="pending",
            extension=_extension(session.original_filename),
        ),
        created_by=created_by,
    )
    db.add(version)
    await db.flush()
    final_key = materials_service.material_object_key(
        course_id=session.course_id,
        material_id=material.id,
        version_id=version.id,
        extension=_extension(session.original_filename),
    )
    try:
        await copy_object(
            source_key=session.object_key,
            destination_key=final_key,
            content_type=session.content_type,
        )
        await delete_object(session.object_key)
    except Exception as exc:  # noqa: BLE001
        # 归档属可重试失败：回滚到 uploading，教师重试完成后重新复制。
        raise ApiError(
            status_code=502,
            code="STORAGE_FINALIZE_COPY_FAILED",
            message="教材归档失败，可稍后重新上传",
            retryable=True,
        ) from exc
    version.object_key = final_key
    material.current_version_id = version.id
    session.sha256 = sha256
    session.material_id = material.id
    session.material_version_id = version.id
    session.status = "completed"
    return material, version


async def cancel_session(db: AsyncSession, session: UploadSession) -> None:
    await expire_if_needed(db, session)
    if session.status in ("completed", "cancelled", "expired"):
        raise ApiError(
            status_code=409,
            code="UPLOAD_SESSION_NOT_CANCELLABLE",
            message="当前上传任务不能取消",
            details={"status": session.status},
        )
    try:
        await abort_multipart_upload(key=session.object_key, upload_id=session.multipart_upload_id)
    except Exception:  # noqa: BLE001
        pass
    session.status = "cancelled"


def session_out(session: UploadSession, parts: list[UploadPart] | None = None) -> dict:
    return {
        "upload_session_id": session.id,
        "status": session.status,
        "title": session.title,
        "original_filename": session.original_filename,
        "size_bytes": session.size_bytes,
        "part_size_bytes": session.part_size_bytes,
        "total_parts": total_parts(session),
        "completed_parts": [part.part_number for part in parts or []],
        "expires_at": session.expires_at.isoformat(),
        "material_id": session.material_id,
        "material_version_id": session.material_version_id,
        "sha256": session.sha256,
    }
