"""陈旧教材任务恢复：心跳超时的 running 任务可被安全重置并重派发。"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.job_recovery import find_stale_jobs, requeue_stale_jobs
from app.db.models import Job, User
from app.db.session import session_factory
from tests.conftest import create_user_sync


def _find_creator() -> str | None:
    async def find() -> str | None:
        async with session_factory() as db:
            return (
                await db.execute(select(User.id).where(User.email == "jr@uni.edu"))
            ).scalar_one_or_none()

    return asyncio.run(find())


def _ensure_creator() -> str:
    existing = _find_creator()
    if existing is not None:
        return existing
    create_user_sync(email="jr@uni.edu", is_teacher=True)
    creator_id = _find_creator()
    assert creator_id is not None
    return creator_id


def _insert_job(status: str, *, heartbeat_age_seconds: int | None, kind: str) -> str:
    creator_id = _ensure_creator()

    async def insert() -> str:
        async with session_factory() as db:
            job = Job(
                kind=kind,
                status=status,
                stage="parse",
                progress=40,
                payload={"material_version_id": "01J0000000000000000000TEST"},
                created_by=creator_id,
            )
            if heartbeat_age_seconds is not None:
                job.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=heartbeat_age_seconds)
            db.add(job)
            await db.commit()
            await db.refresh(job)
            return job.id

    return asyncio.run(insert())


def test_stale_running_jobs_are_requeued_and_fresh_are_kept(client) -> None:
    stale_parse = _insert_job("running", heartbeat_age_seconds=3600, kind="material_parse")
    fresh_embed = _insert_job("running", heartbeat_age_seconds=0, kind="material_embed")
    no_heartbeat = _insert_job("running", heartbeat_age_seconds=None, kind="material_embed")
    _insert_job("succeeded", heartbeat_age_seconds=3600, kind="material_parse")

    async def recover() -> list[str]:
        async with session_factory() as db:
            return await requeue_stale_jobs(db)

    recovered = asyncio.run(recover())

    assert stale_parse in recovered
    assert no_heartbeat in recovered
    assert fresh_embed not in recovered

    async def verify() -> dict[str, Job]:
        async with session_factory() as db:
            return {
                job_id: await db.get(Job, job_id)
                for job_id in (stale_parse, fresh_embed, no_heartbeat)
            }

    jobs = asyncio.run(verify())
    assert jobs[stale_parse].status == "queued"
    assert jobs[stale_parse].progress == 0
    assert jobs[stale_parse].stage == "queued"
    assert jobs[stale_parse].last_heartbeat_at is None
    assert jobs[no_heartbeat].status == "queued"
    assert jobs[fresh_embed].status == "running"
    assert jobs[fresh_embed].progress == 40
    # 测试环境固定 in_process：重派发立即在本进程执行，验证派发路径可用。
    assert get_settings().task_backend == "in_process"


def test_find_stale_jobs_ignores_other_kinds(client) -> None:
    _insert_job("running", heartbeat_age_seconds=3600, kind="question_generate")

    async def scan() -> list[str]:
        async with session_factory() as db:
            threshold = datetime.now(UTC) - timedelta(seconds=get_settings().task_stale_seconds)
            stale = await find_stale_jobs(db, older_than=threshold)
            return [job.id for job in stale]

    assert asyncio.run(scan()) == []
