from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import LearningEvent


async def append_event(
    db: AsyncSession,
    *,
    user_id: str,
    event_key: str,
    course_id: str,
    event_type: str,
    source_type: str,
    source_ref: str | None,
    payload: dict[str, Any],
    occurred_at: datetime | None,
) -> tuple[LearningEvent, bool]:
    existing = await db.scalar(
        select(LearningEvent).where(
            LearningEvent.user_id == user_id,
            LearningEvent.event_key == event_key,
        )
    )
    if existing is not None:
        same = (
            existing.course_id == course_id
            and existing.event_type == event_type
            and existing.source_type == source_type
            and existing.source_ref == source_ref
            and existing.payload == payload
        )
        if not same:
            raise ApiError(
                status_code=409,
                code="LEARNING_EVENT_KEY_CONFLICT",
                message="事件幂等键已用于不同内容",
            ) from None
        return existing, True
    now = datetime.now(UTC)
    event_time = occurred_at or now
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=UTC)
    if event_time > now + timedelta(minutes=5) or event_time < now - timedelta(days=30):
        raise ApiError(
            status_code=422,
            code="LEARNING_EVENT_TIME_INVALID",
            message="学习事件时间超出允许范围",
        )
    event = LearningEvent(
        event_key=event_key,
        user_id=user_id,
        course_id=course_id,
        event_type=event_type,
        source_type=source_type,
        source_ref=source_ref,
        payload=payload,
        occurred_at=event_time,
    )
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        # 并发请求可能同时通过预检查；唯一约束仍是最终幂等裁决。
        await db.rollback()
        existing = await db.scalar(
            select(LearningEvent).where(
                LearningEvent.user_id == user_id,
                LearningEvent.event_key == event_key,
            )
        )
        if existing is None:
            raise
        same = (
            existing.course_id == course_id
            and existing.event_type == event_type
            and existing.source_type == source_type
            and existing.source_ref == source_ref
            and existing.payload == payload
        )
        if not same:
            raise ApiError(
                status_code=409,
                code="LEARNING_EVENT_KEY_CONFLICT",
                message="事件幂等键已用于不同内容",
            ) from None
        return existing, True
    return event, False
