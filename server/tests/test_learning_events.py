import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from tests.conftest import create_user_sync

COURSE_BODY = {"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"}


@pytest.mark.parametrize(
    ("current_version", "post_version", "predecessor", "expected_reason"),
    [
        (8, 6, 5, None),
        (4, 6, 4, "tutor_session_version_mismatch"),
        (8, True, 0, "tutor_session_version_mismatch"),
        (8, 0, -1, "tutor_session_version_mismatch"),
        (8, 6, 4, "tutor_session_version_mismatch"),
    ],
)
def test_tutor_response_version_chain_allows_delay_but_fails_closed_without_database(
    current_version: int,
    post_version: int,
    predecessor: int,
    expected_reason: str | None,
) -> None:
    from app.modules.learning_events.qualification import (
        tutor_response_version_rejection_reason,
    )

    reason = tutor_response_version_rejection_reason(
        session_id="synthetic-session",
        current_session_version=current_version,
        event_key=f"learning-session-response:synthetic-session:{predecessor}",
        event_payload={"state_version": post_version},
    )
    assert reason == expected_reason


def test_tutor_response_version_chain_rejects_malformed_version_without_database() -> None:
    from app.modules.learning_events.qualification import (
        tutor_response_version_rejection_reason,
    )

    reason = tutor_response_version_rejection_reason(
        session_id="synthetic-session",
        current_session_version="8",
        event_key="learning-session-response:synthetic-session:4",
        event_payload={"state_version": 6},
    )
    assert reason == "tutor_session_version_mismatch"


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
        "event_type": "feedback_submitted",
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


@pytest.mark.parametrize(
    ("has_scope", "expected_status", "expected_code"),
    [
        (True, 403, "LEARNING_EVENT_SERVER_OWNED"),
        (False, 404, "COURSE_NOT_FOUND"),
    ],
)
def test_public_tutor_response_event_requires_server_owner_without_database(
    monkeypatch, has_scope: bool, expected_status: int, expected_code: str
) -> None:
    import importlib
    from types import SimpleNamespace

    from fastapi import Request

    from app.core.errors import ApiError
    from app.modules.learning_events.schemas import LearningEventCreate

    router = importlib.import_module("app.modules.learning_events.router")
    scope_checks: list[tuple[str, str]] = []

    async def fake_has_course_scope(user, course_id, _db):
        scope_checks.append((user.id, course_id))
        return has_scope

    async def unexpected_append(**_kwargs):
        raise AssertionError("server-owned tutor event must not be appended from the route")

    monkeypatch.setattr(router, "has_course_scope", fake_has_course_scope)
    monkeypatch.setattr(router.service, "append_event", unexpected_append)
    body = LearningEventCreate(
        event_key="forged-tutor-turn",
        course_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        event_type="tutor_responded",
        source_type="tutor",
        source_ref="01ARZ3NDEKTSV4RRFFQ69G5FAW",
        payload={"state_version": 4, "response_state": "check", "correct": True},
    )
    request = Request(
        {"type": "http", "method": "POST", "path": "/api/v1/learning-events", "headers": []}
    )

    with pytest.raises(ApiError) as error:
        asyncio.run(
            router.append_learning_event(
                body, request, SimpleNamespace(id="synthetic-student"), object()
            )
        )

    assert scope_checks == [("synthetic-student", body.course_id)]
    assert error.value.status_code == expected_status
    assert error.value.code == expected_code


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


def test_client_cannot_forge_tutor_event_or_bypass_formal_assessment(client) -> None:
    from app.db.models import (
        Assessment,
        Attempt,
        LearningEvent,
        LearningEvidence,
        LearningSession,
        MasteryState,
    )
    from app.db.session import session_factory

    teacher_id = create_user_sync(email="event-owned-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="event-owned-student@uni.edu")
    create_user_sync(email="event-owned-outsider@uni.edu")
    _login(client, "event-owned-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    course_id = course["id"]
    assert client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201

    async def _seed_learning_session() -> tuple[str, int]:
        async with session_factory() as db:
            learning = LearningSession(
                user_id=student_id,
                course_id=course_id,
                material_version_id="synthetic-material-version",
                state="check",
                tutor_message="合成检查题",
            )
            db.add(learning)
            await db.commit()
            await db.refresh(learning)
            return learning.id, learning.version

    learning_id, learning_version = asyncio.run(_seed_learning_session())
    forged = {
        "event_key": "forged-tutor-check",
        "course_id": course_id,
        "event_type": "tutor_responded",
        "source_type": "tutor",
        "source_ref": learning_id,
        "payload": {
            "state_version": learning_version,
            "response_state": "check",
            "correct": True,
            "hint_level": 0,
        },
    }
    _login(client, "event-owned-student@uni.edu")
    denied = client.post("/api/v1/learning-events", json=forged)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "LEARNING_EVENT_SERVER_OWNED"

    async def _seed_formal_attempt() -> None:
        async with session_factory() as db:
            assessment = Assessment(
                course_id=course_id,
                title="合成正式测评隔离",
                status="published",
                purpose="formal",
                result_visibility_policy="after_close",
                created_by=teacher_id,
            )
            db.add(assessment)
            await db.flush()
            db.add(Attempt(assessment_id=assessment.id, user_id=student_id))
            await db.commit()

    asyncio.run(_seed_formal_attempt())
    formal_denied = client.post(
        "/api/v1/learning-events", json={**forged, "event_key": "formal-tutor-bypass"}
    )
    assert formal_denied.status_code == 403
    assert formal_denied.json()["error"]["code"] == "LEARNING_EVENT_SERVER_OWNED"

    async def _assert_no_qualification_side_effects() -> None:
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count()).select_from(LearningEvent).where(
                    LearningEvent.user_id == student_id,
                    LearningEvent.event_key.in_([forged["event_key"], "formal-tutor-bypass"]),
                )
            )
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            assert (event_count, evidence_count, mastery_count) == (0, 0, 0)

    asyncio.run(_assert_no_qualification_side_effects())

    _login(client, "event-owned-outsider@uni.edu")
    out_of_scope = client.post("/api/v1/learning-events", json=forged)
    assert out_of_scope.status_code == 404
    assert out_of_scope.json()["error"]["code"] == "COURSE_NOT_FOUND"


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
