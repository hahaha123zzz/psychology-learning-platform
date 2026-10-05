import asyncio

from sqlalchemy import select

from app.core.outbox import (
    append_event,
    claim_pending_events,
    mark_failed,
    mark_published,
    record_consumer_success,
)
from app.core.outbox_dispatcher import event_fields, publish_pending_events
from app.db.models import OutboxEvent
from app.db.session import session_factory


def test_outbox_append_claim_publish_and_consumer_idempotency() -> None:
    async def _run() -> None:
        async with session_factory() as session:
            event = await append_event(
                session,
                event_type="test.event",
                payload={"value": 1},
                producer="tests",
                trace_id="trace-test",
            )
            await session.commit()
            event_id = event.id

        async with session_factory() as session:
            events = await claim_pending_events(session)
            claimed = next(item for item in events if item.id == event_id)
            assert claimed.attempt_count == 1
            await mark_failed(session, claimed, "temporary")
            await mark_published(session, claimed)
            assert await record_consumer_success(
                session, event_id=event_id, consumer_name="test-consumer"
            )
            assert not await record_consumer_success(
                session, event_id=event_id, consumer_name="test-consumer"
            )
            await session.commit()

        async with session_factory() as session:
            stored = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
            assert stored is not None
            assert stored.published_at is not None
            assert stored.last_error is None

    asyncio.run(_run())


def test_outbox_dispatcher_retries_failed_publish_and_serializes_fields() -> None:
    async def _run() -> None:
        async with session_factory() as session:
            event = await append_event(
                session,
                event_type="test.dispatch",
                payload={"text": "中文"},
                producer="tests",
                trace_id="trace-dispatch",
            )
            await session.commit()
            event_id = event.id

        attempts = 0
        published: list[dict[str, str]] = []

        async def publisher(fields: dict[str, str]) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("redis unavailable")
            published.append(fields)

        async with session_factory() as session:
            first = await publish_pending_events(session, publisher)
            assert first["failed"] >= 1
            assert first["published"] == 0

        async with session_factory() as session:
            second = await publish_pending_events(session, publisher)
            assert second["published"] >= 1

        assert published[0]["event_id"] == event_id
        assert published[0]["event_type"] == "test.dispatch"
        assert '"text":"中文"' in published[0]["payload"]
        assert set(event_fields(event)) >= {"event_id", "payload"}

    asyncio.run(_run())
