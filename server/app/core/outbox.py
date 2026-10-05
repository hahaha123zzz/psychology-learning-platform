from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxConsumerReceipt, OutboxEvent


def utc_now() -> datetime:
    return datetime.now(UTC)


async def append_event(
    db: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    producer: str,
    trace_id: str,
    event_version: int = 1,
) -> OutboxEvent:
    """在当前事务中追加事件；调用方提交业务事务时一并提交。"""
    event = OutboxEvent(
        event_type=event_type,
        event_version=event_version,
        occurred_at=utc_now(),
        producer=producer,
        trace_id=trace_id,
        payload=payload,
    )
    db.add(event)
    await db.flush()
    return event


async def claim_pending_events(db: AsyncSession, *, limit: int = 50) -> list[OutboxEvent]:
    """锁定一批未发布事件；锁在投递完成或事务结束前保持。"""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    result = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.occurred_at.asc(), OutboxEvent.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())
    for event in events:
        event.attempt_count += 1
    return events


async def mark_published(db: AsyncSession, event: OutboxEvent) -> None:
    event.published_at = utc_now()
    event.last_error = None


async def mark_failed(db: AsyncSession, event: OutboxEvent, error: str) -> None:
    event.last_error = error[:2000]


async def record_consumer_success(
    db: AsyncSession, *, event_id: str, consumer_name: str
) -> bool:
    """记录消费成功；重复事件返回 False，调用方不应重复产生业务副作用。"""
    existing = await db.scalar(
        select(OutboxConsumerReceipt).where(
            OutboxConsumerReceipt.event_id == event_id,
            OutboxConsumerReceipt.consumer_name == consumer_name,
        )
    )
    if existing is not None:
        return False
    db.add(OutboxConsumerReceipt(event_id=event_id, consumer_name=consumer_name))
    await db.flush()
    return True
