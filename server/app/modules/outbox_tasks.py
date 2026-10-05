"""Transactional outbox 的 Celery 入口。"""

import redis.asyncio as redis

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.outbox_dispatcher import publish_pending_events
from app.core.task_loop import run_task
from app.db.session import session_factory


async def _publish_pending(limit: int) -> dict[str, int]:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)

    async def publish(fields: dict[str, str]) -> None:
        await client.xadd(settings.outbox_stream, fields, maxlen=10000, approximate=True)

    try:
        async with session_factory() as db:
            return await publish_pending_events(db, publish, limit=limit)
    finally:
        await client.aclose()


@celery_app.task(name="outbox.publish_pending")
def publish_outbox(limit: int = 50) -> dict[str, int]:
    return run_task(_publish_pending(limit))
