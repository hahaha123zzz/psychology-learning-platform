"""Transactional outbox 投递器。

业务事务只写入数据库；Worker 再把已提交事件写入 Redis Stream，成功后才标记
``published_at``。重复投递由事件 id 和消费者账本保证幂等，Redis 暂时不可用时
保留未发布事件并记录错误，下一轮可以继续重试。
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.outbox import claim_pending_events, mark_failed, mark_published
from app.db.models import OutboxEvent

PublishEvent = Callable[[dict[str, str]], Awaitable[Any]]


def event_fields(event: OutboxEvent) -> dict[str, str]:
    """将数据库事件转换为 Redis Stream 的稳定字段。"""
    return {
        "event_id": event.id,
        "event_type": event.event_type,
        "event_version": str(event.event_version),
        "occurred_at": event.occurred_at.isoformat(),
        "producer": event.producer,
        "trace_id": event.trace_id,
        "payload": json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
    }


async def publish_pending_events(
    db,
    publisher: PublishEvent,
    *,
    limit: int = 50,
) -> dict[str, int]:
    """投递一批事件；单条失败不会阻塞同批其它事件。"""
    events = await claim_pending_events(db, limit=limit)
    published = 0
    failed = 0
    for event in events:
        try:
            await publisher(event_fields(event))
        except Exception as exc:  # noqa: BLE001 - 失败必须留账并让下一轮重试
            await mark_failed(db, event, str(exc))
            failed += 1
        else:
            await mark_published(db, event)
            published += 1
    await db.commit()
    return {"claimed": len(events), "published": published, "failed": failed}
