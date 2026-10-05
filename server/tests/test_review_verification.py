import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

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

    from app.db.models import ReviewTask
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

    verified = client.post(
        f"/api/v1/review-tasks/{task['id']}/verify",
        json={
            "version": task["version"],
            "response": {"selected_keys": ["A"]},
        },
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["pending_qualification"] is True

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
