import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from tests.conftest import create_user_sync

COURSE_BODY = {"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"}


@pytest.mark.parametrize("qualification_status", ["qualified", "rejected", None])
def test_mini_lab_qualification_requires_pending_measure_without_database(
    qualification_status,
) -> None:
    from app.modules.learning_events.qualification import _qualify_lab_result

    measure = {
        "trial_count": 6,
        "explanation_complete": True,
        "transfer_complete": True,
        "qualification_status": qualification_status,
    }
    session = SimpleNamespace(
        id="synthetic-session-id",
        user_id="synthetic-user-id",
        course_id="synthetic-course-id",
        status="completed",
        derived_measure=measure,
        trial_data=[
            {"phase": phase, "response": 0}
            for phase in ("intro", "predict", "run", "inspect", "explain", "summary")
        ],
    )
    event = SimpleNamespace(
        source_ref=session.id,
        user_id=session.user_id,
        course_id=session.course_id,
        payload={key: value for key, value in measure.items() if key != "qualification_status"},
    )

    class FakeDatabase:
        async def scalar(self, _statement):
            return session

    evidence_ids, reason = asyncio.run(_qualify_lab_result(FakeDatabase(), event))
    assert evidence_ids == []
    assert reason == "mini_lab_result_not_pending"


def test_mini_lab_button_only_explain_and_summary_are_not_qualified_without_database() -> None:
    from app.modules.learning_events.qualification import _qualify_lab_result

    measure = {
        "trial_count": 6,
        "explanation_complete": False,
        "transfer_complete": False,
        "qualification_status": "pending",
    }
    session = SimpleNamespace(
        id="synthetic-session-id",
        user_id="synthetic-user-id",
        course_id="synthetic-course-id",
        status="completed",
        derived_measure=measure,
        trial_data=[
            {"phase": phase, "response": 0}
            for phase in ("intro", "predict", "run", "inspect", "explain", "summary")
        ],
        lab_key="synthetic-lab",
    )
    event = SimpleNamespace(
        source_ref=session.id,
        user_id=session.user_id,
        course_id=session.course_id,
        payload={key: value for key, value in measure.items() if key != "qualification_status"},
    )

    class FakeDatabase:
        async def scalar(self, _statement):
            return session

    evidence_ids, reason = asyncio.run(_qualify_lab_result(FakeDatabase(), event))
    assert evidence_ids == []
    assert reason == "mini_lab_explanation_or_transfer_unverified"


def test_mini_lab_legacy_true_flags_do_not_qualify_button_only_response() -> None:
    from app.modules.learning_events.qualification import _qualify_lab_result

    measure = {
        "trial_count": 6,
        "explanation_complete": True,
        "transfer_complete": True,
        "qualification_status": "pending",
    }
    session = SimpleNamespace(
        id="synthetic-legacy-session-id",
        user_id="synthetic-user-id",
        course_id="synthetic-course-id",
        status="completed",
        derived_measure=measure,
        trial_data=[
            {"phase": phase, "response": 0}
            for phase in ("intro", "predict", "run", "inspect", "explain", "summary")
        ],
        lab_key="synthetic-lab",
    )
    event = SimpleNamespace(
        source_ref=session.id,
        user_id=session.user_id,
        course_id=session.course_id,
        payload={key: value for key, value in measure.items() if key != "qualification_status"},
    )

    class FakeDatabase:
        async def scalar(self, _statement):
            return session

    evidence_ids, reason = asyncio.run(_qualify_lab_result(FakeDatabase(), event))
    assert evidence_ids == []
    assert reason == "mini_lab_explanation_or_transfer_unverified"


@pytest.mark.parametrize("missing_phase", ["predict", "run"])
def test_mini_lab_missing_required_phase_response_is_rejected_without_database(
    missing_phase: str,
) -> None:
    from app.modules.learning_events.qualification import _qualify_lab_result

    measure = {
        "trial_count": 6,
        "explanation_complete": False,
        "transfer_complete": False,
        "qualification_status": "pending",
    }
    trial_data = [
        {"phase": phase, "response": None if phase == missing_phase else 0}
        for phase in ("intro", "predict", "run", "inspect", "explain", "summary")
    ]
    session = SimpleNamespace(
        id="synthetic-session-id",
        user_id="synthetic-user-id",
        course_id="synthetic-course-id",
        status="completed",
        derived_measure=measure,
        trial_data=trial_data,
        lab_key="synthetic-lab",
    )
    event = SimpleNamespace(
        source_ref=session.id,
        user_id=session.user_id,
        course_id=session.course_id,
        payload={key: value for key, value in measure.items() if key != "qualification_status"},
    )

    class FakeDatabase:
        async def scalar(self, _statement):
            return session

    evidence_ids, reason = asyncio.run(_qualify_lab_result(FakeDatabase(), event))
    assert evidence_ids == []
    assert reason == "mini_lab_required_response_missing"


def _login(client, email: str, password: str = "correct-password") -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200


def test_learning_event_is_pending_and_idempotent(client) -> None:
    create_user_sync(email="event-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="event-student@uni.edu")
    _login(client, "event-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    added = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert added.status_code == 201

    _login(client, "event-student@uni.edu")
    body = {
        "event_key": "turn-001",
        "course_id": course["id"],
        "event_type": "tutor_responded",
        "source_type": "tutor",
        "source_ref": "session-001",
        "payload": {"block_count": 3},
    }
    first = client.post("/api/v1/learning-events", json=body)
    assert first.status_code == 201
    assert first.json()["data"]["qualification_status"] == "pending"
    assert first.json()["meta"]["idempotent_replay"] is False

    replay = client.post("/api/v1/learning-events", json=body)
    assert replay.status_code == 200
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert replay.json()["meta"]["idempotent_replay"] is True

    listed = client.get(f"/api/v1/me/learning-events?course_id={course['id']}")
    assert listed.status_code == 200
    assert [item["event_key"] for item in listed.json()["data"]] == ["turn-001"]


def test_learning_event_key_conflict_and_course_scope(client) -> None:
    create_user_sync(email="event-owner@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="event-member@uni.edu")
    outsider_id = create_user_sync(email="event-outsider@uni.edu")
    _login(client, "event-owner@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    assert client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201

    _login(client, "event-member@uni.edu")
    body = {
        "event_key": "answer-001",
        "course_id": course["id"],
        "event_type": "answer_submitted",
        "source_type": "assessment",
        "payload": {"question_version_id": "qv-1", "answer": "B"},
    }
    assert client.post("/api/v1/learning-events", json=body).status_code == 201
    conflict = client.post(
        "/api/v1/learning-events",
        json={**body, "payload": {"question_version_id": "qv-1", "answer": "C"}},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "LEARNING_EVENT_KEY_CONFLICT"

    _login(client, "event-outsider@uni.edu")
    denied = client.get(f"/api/v1/me/learning-events?course_id={course['id']}")
    assert denied.status_code == 404
    assert outsider_id


def test_pending_learning_event_worker_rejects_non_evidence_event(client) -> None:
    create_user_sync(email="worker-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="worker-student@uni.edu")
    _login(client, "worker-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    assert client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    _login(client, "worker-student@uni.edu")
    created = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "view-001",
            "course_id": course["id"],
            "event_type": "task_viewed",
            "source_type": "tutor",
            "payload": {"task_id": "task-1"},
        },
    )
    assert created.status_code == 201

    from app.db.models import LearningEvent, LearningQualification
    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_pending_events

    async def _run_worker():
        async with session_factory() as session:
            counts = await qualify_pending_events(session, limit=10)
            row = await session.execute(
                select(LearningEvent, LearningQualification)
                .join(LearningQualification, LearningQualification.event_id == LearningEvent.id)
                .where(LearningEvent.event_key == "view-001")
            )
            return counts, row.one()

    counts, (event, qualification) = asyncio.run(_run_worker())
    assert counts["rejected"] == 1
    assert event.qualification_status == "rejected"
    assert qualification.reason == "event_type_not_evidence_bearing"
