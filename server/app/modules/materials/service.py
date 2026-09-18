import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import Course, Job, Material, MaterialVersion
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
    return ValidatedUpload(
        content_type=content_type, sha256=digest.hexdigest(), size_bytes=size
    )


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
        raise ApiError(
            status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问"
        )
    return course


# ---- 解析任务 ----

PARSE_STAGES: list[tuple[str, int]] = [
    ("download", 15),
    ("render", 35),
    ("parse", 60),
    ("normalize", 80),
    ("quality", 95),
    ("persist", 100),
]

_background_tasks: set[asyncio.Task] = set()


async def find_active_parse_job(
    db: AsyncSession, version_id: str
) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.kind == "material_parse",
            Job.status.in_(("queued", "running")),
            Job.payload["material_version_id"].as_string() == version_id,
        )
    )
    return result.scalar_one_or_none()


async def find_parse_job_by_idempotency_key(
    db: AsyncSession, key: str
) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.kind == "material_parse",
            Job.idempotency_key == key,
        )
    )
    return result.scalar_one_or_none()


async def run_parse_job(job_id: str, version_id: str) -> None:
    """后台执行解析。阶段进度只增不减；异常时版本回退为 failed。"""
    settings = get_settings()
    stage_sleep = max(settings.parse_simulate_seconds, 0.1) / len(PARSE_STAGES)
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        version = await session.get(MaterialVersion, version_id)
        if job is None or version is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.stage = "download"
        version.status = "parsing"
        await session.commit()
        try:
            for stage, progress in PARSE_STAGES:
                await asyncio.sleep(stage_sleep)
                job.stage = stage
                job.progress = max(job.progress, progress)
                await session.commit()
            version.status = "parsed"
            job.status = "succeeded"
            job.stage = "done"
            job.progress = 100
            job.finished_at = datetime.now(UTC)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            version.status = "failed"
            job.status = "failed"
            job.error = str(exc)[:500]
            job.retryable = True
            job.finished_at = datetime.now(UTC)
            await session.commit()


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
