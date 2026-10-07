import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from tests.test_mastery_memory import _prepare_published
from tests.test_materials import _login


def test_due_review_verification_generates_retention_evidence(client) -> None:
    course_id, _student_id, _version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts").json()["data"]
    question = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]["items"][0]
    assert client.put(
        f"/api/v1/attempts/{attempt['attempt_id']}/answers/{question['question_version_id']}",
        json={"answer_version": 1, "response": {"selected_keys": ["C"]}},
    ).status_code == 200
    assert client.post(f"/api/v1/attempts/{attempt['attempt_id']}/submit").status_code == 200

    from app.db.models import LearningEvent, LearningEvidence, MasteryState, ReviewTask
    from app.db.session import session_factory

    async def _make_due() -> None:
        async with session_factory() as db:
            await db.execute(
                update(ReviewTask)
                .where(ReviewTask.course_id == course_id)
                .values(due_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await db.commit()

    asyncio.run(_make_due())
    tasks = client.get("/api/v1/review-tasks?due_only=true")
    assert tasks.status_code == 200
    task = tasks.json()["data"][0]
    assert task["question"]["options"]

    body = {"version": task["version"], "response": {"selected_keys": ["A"]}}
    verify_url = f"/api/v1/review-tasks/{task['id']}/verify"

    async def _set_review_status(status: str) -> None:
        async with session_factory() as db:
            stored_task = await db.scalar(select(ReviewTask).where(ReviewTask.id == task["id"]))
            assert stored_task is not None
            stored_task.status = status
            await db.commit()

    # A completed task alone is not evidence that a verify event was committed.
    asyncio.run(_set_review_status("done"))
    missing_event = client.post(verify_url, json=body)
    assert missing_event.status_code == 409
    assert missing_event.json()["error"]["code"] == "REVIEW_TASK_NOT_PENDING"
    asyncio.run(_set_review_status("pending"))

    verified = client.post(verify_url, json=body)
    assert verified.status_code == 200
    assert verified.json()["data"]["pending_qualification"] is True
    original_data = verified.json()["data"]
    event_key = f"review:{task['id']}:verify"

    async def _side_effect_snapshot() -> tuple:
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.user_id == _student_id, LearningEvent.event_key == event_key)
            )
            evidence_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvidence)
                .where(
                    LearningEvidence.user_id == _student_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.source_type == "review",
                    LearningEvidence.attempt_id == task["id"],
                )
            )
            review_task_count = await db.scalar(
                select(func.count())
                .select_from(ReviewTask)
                .where(ReviewTask.user_id == _student_id, ReviewTask.course_id == course_id)
            )
            mastery_rows = list(
                (
                    await db.execute(
                        select(MasteryState)
                        .where(
                            MasteryState.user_id == _student_id,
                            MasteryState.course_id == course_id,
                        )
                        .order_by(MasteryState.knowledge_point)
                    )
                ).scalars()
            )
            mastery_snapshot = tuple(
                (row.knowledge_point, row.version, row.state, row.evidence_count)
                for row in mastery_rows
            )
            return event_count, evidence_count, review_task_count, mastery_snapshot

    before_replays = asyncio.run(_side_effect_snapshot())
    replayed = client.post(verify_url, json=body)
    assert replayed.status_code == 200
    assert replayed.json()["data"] == original_data
    assert replayed.json()["meta"]["idempotent_replay"] is True
    assert asyncio.run(_side_effect_snapshot()) == before_replays

    changed_answer = client.post(
        verify_url,
        json={"version": task["version"], "response": {"selected_keys": ["B"]}},
    )
    assert changed_answer.status_code == 409
    assert changed_answer.json()["error"]["code"] == "LEARNING_EVENT_KEY_CONFLICT"
    assert asyncio.run(_side_effect_snapshot()) == before_replays

    from app.modules.learning_events.qualification import qualify_pending_events

    async def _qualify() -> dict[str, int]:
        async with session_factory() as db:
            return await qualify_pending_events(db, limit=20)

    counts = asyncio.run(_qualify())
    assert counts["qualified"] >= 1

    async def _read_task() -> ReviewTask | None:
        async with session_factory() as db:
            return await db.scalar(select(ReviewTask).where(ReviewTask.id == task["id"]))

    stored = asyncio.run(_read_task())
    assert stored is not None
    assert stored.qualification_status == "qualified"

    # Qualification changes separately; a later HTTP retry still replays the original response.
    after_qualification = asyncio.run(_side_effect_snapshot())
    qualified_replay = client.post(verify_url, json=body)
    assert qualified_replay.status_code == 200
    assert qualified_replay.json()["data"] == original_data
    assert qualified_replay.json()["meta"]["idempotent_replay"] is True
    assert asyncio.run(_side_effect_snapshot()) == after_qualification

    changed_after_qualification = client.post(
        verify_url,
        json={"version": task["version"], "response": {"selected_keys": ["B"]}},
    )
    assert changed_after_qualification.status_code == 409
    assert changed_after_qualification.json()["error"]["code"] == "LEARNING_EVENT_KEY_CONFLICT"
    assert asyncio.run(_side_effect_snapshot()) == after_qualification
