"""陈旧教材任务恢复：Worker 崩溃或重启后，把失去心跳的任务安全重派发。

解析与索引任务都以不可变源文件为输入，且索引替换采用"全部成功后原子提交"，
因此重派发不会产生半成品状态；幂等键保证同一任务不会被重复排队。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.task_dispatcher import dispatch_embed_job, dispatch_parse_job
from app.db.models import Job

RECOVERABLE_KINDS = ("material_parse", "material_embed")


async def find_stale_jobs(db: AsyncSession, *, older_than: datetime) -> list[Job]:
    result = await db.execute(
        select(Job).where(
            Job.kind.in_(RECOVERABLE_KINDS),
            Job.status == "running",
            (Job.last_heartbeat_at.is_(None)) | (Job.last_heartbeat_at < older_than),
        )
    )
    return list(result.scalars())


async def requeue_stale_jobs(db: AsyncSession) -> list[str]:
    """把心跳超时的 running 任务重置为 queued 并重新派发；返回受影响任务 ID。"""
    stale_seconds = get_settings().task_stale_seconds
    older_than = datetime.now(UTC) - timedelta(seconds=stale_seconds)
    stale_jobs = await find_stale_jobs(db, older_than=older_than)
    recovered: list[str] = []
    for job in stale_jobs:
        version_id = job.payload.get("material_version_id")
        if not version_id:
            continue
        job.status = "queued"
        job.stage = "queued"
        job.progress = 0
        job.error = None
        job.retryable = False
        job.started_at = None
        job.last_heartbeat_at = None
        recovered.append(job.id)
    await db.commit()
    for job_id in recovered:
        job = await db.get(Job, job_id)
        if job is None:
            continue
        version_id = job.payload["material_version_id"]
        if job.kind == "material_parse":
            dispatch_parse_job(job_id, version_id)
        else:
            dispatch_embed_job(job_id, version_id)
    return recovered
