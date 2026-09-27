import asyncio
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import (
    Course,
    Job,
    KnowledgeChunk,
    KnowledgeObject,
    Material,
    MaterialVersion,
    ObjectAsset,
    ObjectRelation,
    ParsedPage,
    ParseReviewIssue,
    RetrievalIndexEntry,
    RetrievalUnit,
)
from app.db.session import session_factory

ALLOWED_TYPES: dict[str, tuple[str, str | None]] = {
    # 扩展名: (服务端检测的Content-Type, 必需的文件签名前缀)
    "pdf": ("application/pdf", b"%PDF-"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"PK\x03\x04",
    ),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        b"PK\x03\x04",
    ),
    "md": ("text/markdown", None),
    "txt": ("text/plain", None),
}

CHUNK_SIZE = 1024 * 1024


@dataclass
class ValidatedUpload:
    content_type: str
    sha256: str
    size_bytes: int


def validate_file_name(filename: str | None) -> str:
    if not filename:
        raise ApiError(
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
            message="缺少文件名或文件类型不支持",
        )
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_TYPES:
        raise ApiError(
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
            message="仅支持 PDF、DOCX、PPTX、Markdown 和 TXT 文件",
            details={"extension": extension},
        )
    return extension


async def validate_and_hash(file: UploadFile) -> ValidatedUpload:
    extension = validate_file_name(file.filename)
    content_type, magic = ALLOWED_TYPES[extension]
    settings = get_settings()
    max_bytes = settings.upload_max_mb * 1024 * 1024

    head = await file.read(8)
    if not head:
        raise ApiError(status_code=422, code="EMPTY_FILE", message="文件内容为空")
    if magic is not None and not head.startswith(magic):
        raise ApiError(
            status_code=415,
            code="FILE_SIGNATURE_MISMATCH",
            message="文件内容与声明的类型不一致",
            details={"extension": extension},
        )

    digest = hashlib.sha256()
    digest.update(head)
    size = len(head)
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise ApiError(
                status_code=413,
                code="FILE_TOO_LARGE",
                message=f"文件超过大小上限 {settings.upload_max_mb}MB",
                details={"max_bytes": max_bytes},
            )
        digest.update(chunk)
    await file.seek(0)
    return ValidatedUpload(content_type=content_type, sha256=digest.hexdigest(), size_bytes=size)


async def check_course_quota(db: AsyncSession, course_id: str, incoming: int) -> None:
    settings = get_settings()
    quota_bytes = settings.course_storage_quota_gb * 1024 * 1024 * 1024
    result = await db.execute(
        select(func.coalesce(func.sum(MaterialVersion.size_bytes), 0)).where(
            MaterialVersion.material_id.in_(
                select(Material.id).where(Material.course_id == course_id)
            ),
            MaterialVersion.status.in_(("uploading", "uploaded")),
        )
    )
    used = int(result.scalar_one())
    if used + incoming > quota_bytes:
        raise ApiError(
            status_code=413,
            code="COURSE_STORAGE_QUOTA_EXCEEDED",
            message="课程存储空间已满",
            details={"used_bytes": used, "quota_bytes": quota_bytes},
        )


async def find_duplicate(
    db: AsyncSession, *, course_id: str, sha256: str
) -> MaterialVersion | None:
    result = await db.execute(
        select(MaterialVersion)
        .join(Material, Material.id == MaterialVersion.material_id)
        .where(
            Material.course_id == course_id,
            MaterialVersion.sha256 == sha256,
            MaterialVersion.status.in_(("uploading", "uploaded")),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def next_version_no(db: AsyncSession, material_id: str) -> int:
    result = await db.execute(
        select(func.max(MaterialVersion.version_no)).where(
            MaterialVersion.material_id == material_id
        )
    )
    current = result.scalar_one()
    return (current or 0) + 1


def material_object_key(
    *, course_id: str, material_id: str, version_id: str, extension: str
) -> str:
    return f"courses/{course_id}/materials/{material_id}/{version_id}.{extension}"


async def get_course_or_404(db: AsyncSession, course_id: str) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id).limit(1))
    course = result.scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    return course


# ---- 解析任务 ----

_background_tasks: set[asyncio.Task] = set()


async def find_active_parse_job(db: AsyncSession, version_id: str) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.kind == "material_parse",
            Job.status.in_(("queued", "running")),
            Job.payload["material_version_id"].as_string() == version_id,
        )
    )
    return result.scalar_one_or_none()


async def find_parse_job_by_idempotency_key(db: AsyncSession, key: str) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.kind == "material_parse",
            Job.idempotency_key == key,
        )
    )
    return result.scalar_one_or_none()


async def run_parse_job(job_id: str, version_id: str) -> None:
    """后台执行解析：按页持久化，重试时保留已完成页面。"""
    from app.core.storage import get_object_bytes, put_object
    from app.modules.materials.parsers.base import get_parser

    current_page: int | None = None
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        version = await session.get(MaterialVersion, version_id)
        if job is None or version is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.last_heartbeat_at = job.started_at
        job.attempt_count += 1
        job.stage = "download"
        job.checkpoint = {"stage": "download", "attempt": job.attempt_count}
        version.status = "parsing"
        await session.commit()
        try:
            if not version.object_key:
                raise RuntimeError("版本缺少对象键，无法解析")
            data = await get_object_bytes(version.object_key)
            job.progress = max(job.progress, 30)
            job.stage = "parse"
            job.last_heartbeat_at = datetime.now(UTC)
            job.checkpoint = {"stage": "parse", "source": "downloaded"}
            await session.commit()

            parser = get_parser(version.content_type)
            result = await asyncio.to_thread(parser.parse, data, version.content_type or "")
            completed_rows = list(
                (
                    await session.execute(
                        select(ParsedPage).where(
                            ParsedPage.material_version_id == version_id,
                            ParsedPage.parser_version == parser.version,
                            ParsedPage.status == "completed",
                        )
                    )
                ).scalars()
            )
            completed_pages = {row.physical_page for row in completed_rows}
            if not completed_pages:
                await _clear_parse_outputs(session, version_id)
                await session.commit()

            objects_by_page: dict[int, list] = {}
            for parsed_object in result.objects:
                objects_by_page.setdefault(parsed_object.physical_page, []).append(parsed_object)

            completed_object_count = sum(row.object_count for row in completed_rows)
            completed_asset_count = sum(row.asset_count for row in completed_rows)
            for page_no in range(1, result.page_count + 1):
                if page_no in completed_pages:
                    continue
                current_page = page_no
                page_objects = objects_by_page.get(page_no, [])
                rows = [
                    KnowledgeObject(
                        material_version_id=version_id,
                        type=parsed.type,
                        title=parsed.title,
                        chapter_path=parsed.chapter_path,
                        physical_page=parsed.physical_page,
                        printed_page=parsed.printed_page,
                        reading_order=parsed.reading_order,
                        bbox=parsed.bbox,
                        raw_content=parsed.raw_content,
                        parser=parser.name,
                        parser_version=parser.version,
                        confidence=parsed.confidence,
                        review_status="pending",
                    )
                    for parsed in page_objects
                ]
                session.add_all(rows)
                await session.flush()
                asset_count = 0
                for parsed, row in zip(page_objects, rows, strict=True):
                    if not parsed.asset_bytes:
                        continue
                    digest = hashlib.sha256(parsed.asset_bytes).hexdigest()
                    key = layout_asset_key(
                        version_id=version_id,
                        parser_version=parser.version,
                        physical_page=page_no,
                        object_id=row.id,
                        sha256=digest,
                    )
                    await put_object(
                        key=key,
                        data=io.BytesIO(parsed.asset_bytes),
                        length=len(parsed.asset_bytes),
                        content_type=parsed.asset_mime_type or "application/octet-stream",
                    )
                    session.add(
                        ObjectAsset(
                            material_version_id=version_id,
                            knowledge_object_id=row.id,
                            asset_type="object_crop",
                            object_key=key,
                            mime_type=parsed.asset_mime_type or "application/octet-stream",
                            sha256=digest,
                            physical_page=page_no,
                            bbox=parsed.bbox,
                            width=parsed.asset_width,
                            height=parsed.asset_height,
                            render_version=parser.version,
                            status="ready",
                        )
                    )
                    asset_count += 1
                page_hash = _parsed_page_hash(page_objects)
                session.add(
                    ParsedPage(
                        material_version_id=version_id,
                        parser_version=parser.version,
                        physical_page=page_no,
                        status="completed",
                        object_count=len(rows),
                        asset_count=asset_count,
                        content_hash=page_hash,
                    )
                )
                completed_pages.add(page_no)
                completed_object_count += len(rows)
                completed_asset_count += asset_count
                job.progress = max(job.progress, 30 + int(50 * page_no / max(result.page_count, 1)))
                job.stage = "parse_pages"
                job.last_heartbeat_at = datetime.now(UTC)
                job.checkpoint = {
                    "stage": "parse_pages",
                    "parser_version": parser.version,
                    "completed_pages": len(completed_pages),
                    "total_pages": result.page_count,
                    "last_page": page_no,
                    "object_count": completed_object_count,
                    "asset_count": completed_asset_count,
                }
                await session.commit()

            job.progress = max(job.progress, 85)
            job.stage = "quality"
            job.last_heartbeat_at = datetime.now(UTC)
            job.checkpoint = {
                "stage": "quality",
                "parser_version": parser.version,
                "completed_pages": len(completed_pages),
                "total_pages": result.page_count,
                "object_count": completed_object_count,
                "asset_count": completed_asset_count,
            }
            await session.commit()

            empty_pages = result.page_count - len(
                {page for page, entries in objects_by_page.items() if entries}
            )
            low_confidence = sum(1 for o in result.objects if o.confidence < 0.5)
            quality_report = {
                "parser": parser.name,
                "parser_version": parser.version,
                "page_count": result.page_count,
                "object_count": len(result.objects),
                "empty_pages": empty_pages,
                "low_confidence_objects": low_confidence,
                "issues": result.issues,
            }

            job.stage = "persist"
            all_rows = list(
                (
                    await session.execute(
                        select(KnowledgeObject)
                        .where(KnowledgeObject.material_version_id == version_id)
                        .order_by(KnowledgeObject.reading_order.asc())
                    )
                ).scalars()
            )
            session.add_all(_sequence_relations(all_rows))
            blocking_codes = {"no_text_extracted", "parser_unavailable"}
            review_issues = [
                ParseReviewIssue(
                    material_version_id=version_id,
                    severity="blocking" if code in blocking_codes else "warning",
                    code=code,
                    detail={"source": "parser"},
                )
                for code in sorted(set(result.issues))
            ]
            if empty_pages:
                review_issues.append(
                    ParseReviewIssue(
                        material_version_id=version_id,
                        severity="warning",
                        code="empty_pages_detected",
                        detail={"count": empty_pages},
                    )
                )
            if low_confidence:
                review_issues.append(
                    ParseReviewIssue(
                        material_version_id=version_id,
                        severity="warning",
                        code="low_confidence_objects",
                        detail={"count": low_confidence, "threshold": 0.5},
                    )
                )
            session.add_all(review_issues)
            version.page_count = result.page_count
            version.quality_report = quality_report
            version.quality_gate_status = (
                "blocked"
                if any(issue.severity == "blocking" for issue in review_issues)
                else "pending"
            )
            version.status = "parsed"
            job.progress = 100
            job.stage = "done"
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            job.last_heartbeat_at = job.finished_at
            job.checkpoint = {
                "stage": "done",
                "parser_version": parser.version,
                "completed_pages": len(completed_pages),
                "total_pages": result.page_count,
                "object_count": completed_object_count,
                "asset_count": completed_asset_count,
            }
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            job = await session.get(Job, job_id)
            version = await session.get(MaterialVersion, version_id)
            if job is not None and version is not None:
                version.status = "failed"
                version.quality_gate_status = "blocked"
                job.status = "failed"
                job.error = str(exc)[:500]
                job.retryable = True
                job.finished_at = datetime.now(UTC)
                job.last_heartbeat_at = job.finished_at
                job.checkpoint = {
                    **(job.checkpoint or {}),
                    "stage": "failed",
                    "failed_page": current_page,
                    "error": str(exc)[:500],
                }
                await session.commit()


def _pages_with_objects(objects) -> int:
    return len({o.physical_page for o in objects if o.raw_content})


def layout_asset_key(
    *, version_id: str, parser_version: str, physical_page: int, object_id: str, sha256: str
) -> str:
    """版面派生产物使用教材版本范围内不可变键，避免覆盖历史资产。"""
    return (
        f"material-layout/{version_id}/{parser_version}/pages/{physical_page}/"
        f"objects/{object_id}-{sha256[:16]}"
    )


def _parsed_page_hash(objects) -> str:
    digest = hashlib.sha256()
    for object_row in objects:
        digest.update(object_row.type.encode())
        digest.update(object_row.raw_content.encode())
        digest.update(repr(object_row.bbox).encode())
        if object_row.asset_bytes:
            digest.update(hashlib.sha256(object_row.asset_bytes).digest())
    return digest.hexdigest()


async def _clear_parse_outputs(session: AsyncSession, version_id: str) -> None:
    """新解析起始时失效旧对象和索引；断点重试不会调用本函数。"""
    version_object_ids = select(KnowledgeObject.id).where(
        KnowledgeObject.material_version_id == version_id
    )
    await session.execute(
        delete(ObjectRelation).where(
            or_(
                ObjectRelation.source_object_id.in_(version_object_ids),
                ObjectRelation.target_object_id.in_(version_object_ids),
            )
        )
    )
    await session.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.material_version_id == version_id)
    )
    await session.execute(
        delete(RetrievalIndexEntry).where(
            RetrievalIndexEntry.retrieval_unit_id.in_(
                select(RetrievalUnit.id).where(RetrievalUnit.material_version_id == version_id)
            )
        )
    )
    await session.execute(
        delete(RetrievalUnit).where(RetrievalUnit.material_version_id == version_id)
    )
    await session.execute(
        delete(ObjectAsset).where(ObjectAsset.material_version_id == version_id)
    )
    await session.execute(
        delete(KnowledgeObject).where(KnowledgeObject.material_version_id == version_id)
    )
    await session.execute(
        delete(ParseReviewIssue).where(ParseReviewIssue.material_version_id == version_id)
    )


def _sequence_relations(objects: list[KnowledgeObject]) -> list[ObjectRelation]:
    """从确定的阅读顺序构建同章节相邻对象关系，供最小证据闭包使用。"""
    content_objects = [
        object
        for object in sorted(objects, key=lambda item: item.reading_order)
        if object.type != "chapter"
    ]
    relations: list[ObjectRelation] = []
    for previous, current in zip(content_objects, content_objects[1:], strict=False):
        if previous.chapter_path != current.chapter_path:
            continue
        relations.extend(
            (
                ObjectRelation(
                    source_object_id=previous.id,
                    target_object_id=current.id,
                    relation_type="next",
                    source="parser:reading-order",
                    confidence=1.0,
                    review_status="approved",
                ),
                ObjectRelation(
                    source_object_id=current.id,
                    target_object_id=previous.id,
                    relation_type="previous",
                    source="parser:reading-order",
                    confidence=1.0,
                    review_status="approved",
                ),
            )
        )
    return relations


def spawn_parse_job(job_id: str, version_id: str) -> None:
    task = asyncio.create_task(run_parse_job(job_id, version_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def job_out(job: Job) -> dict:
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "last_heartbeat_at": job.last_heartbeat_at.isoformat() if job.last_heartbeat_at else None,
        "attempt_count": job.attempt_count,
        "checkpoint": job.checkpoint,
        "worker_backend": job.worker_backend,
        "error": job.error,
        "retryable": job.retryable,
    }


async def get_version_with_material_or_404(
    db: AsyncSession, version_id: str
) -> tuple[MaterialVersion, Material]:
    result = await db.execute(
        select(MaterialVersion, Material)
        .join(Material, Material.id == MaterialVersion.material_id)
        .where(MaterialVersion.id == version_id)
        .limit(1)
    )
    row = result.first()
    if row is None:
        raise ApiError(
            status_code=404,
            code="MATERIAL_VERSION_NOT_FOUND",
            message="资料版本不存在或无权访问",
        )
    return row[0], row[1]


async def get_object_or_404(db: AsyncSession, object_id: str) -> KnowledgeObject:
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == object_id).limit(1)
    )
    object_row = result.scalar_one_or_none()
    if object_row is None:
        raise ApiError(
            status_code=404,
            code="KNOWLEDGE_OBJECT_NOT_FOUND",
            message="知识对象不存在或无权访问",
        )
    return object_row


async def get_parse_review_issue_or_404(db: AsyncSession, issue_id: str) -> ParseReviewIssue:
    issue = await db.get(ParseReviewIssue, issue_id)
    if issue is None:
        raise ApiError(
            status_code=404,
            code="PARSE_REVIEW_ISSUE_NOT_FOUND",
            message="解析审核问题不存在或无权访问",
        )
    return issue


async def build_outline(db: AsyncSession, version_id: str, page_count: int | None) -> list[dict]:
    result = await db.execute(
        select(KnowledgeObject)
        .where(
            KnowledgeObject.material_version_id == version_id,
            KnowledgeObject.type == "chapter",
        )
        .order_by(KnowledgeObject.reading_order.asc())
    )
    chapters = list(result.scalars())

    count_result = await db.execute(
        select(KnowledgeObject.chapter_path, func.count(KnowledgeObject.id))
        .where(KnowledgeObject.material_version_id == version_id)
        .group_by(KnowledgeObject.chapter_path)
    )
    counts = {path: count for path, count in count_result.all()}

    outline: list[dict] = []
    for index, chapter in enumerate(chapters):
        start_page = chapter.physical_page
        next_page = chapters[index + 1].physical_page if index + 1 < len(chapters) else None
        end_page = (next_page - 1) if next_page else (page_count or start_page)
        outline.append(
            {
                "id": chapter.id,
                "title": chapter.title or (chapter.normalized_content or "")[:50] or "未命名",
                "level": len([p for p in chapter.chapter_path.split("/") if p]),
                "parent_id": chapter.parent_id,
                "start_page": start_page,
                "end_page": end_page,
                "review_status": chapter.review_status,
                "object_count": counts.get(chapter.chapter_path, 0),
            }
        )
    return outline
