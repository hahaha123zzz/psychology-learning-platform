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


def _prepare_resource_open_pointer(client) -> tuple[str, str, str]:
    from tests.test_search import _create_student_search_release, _prepare

    course_id, student_id, version_id = _prepare(client, publish=True)
    _login(client, "mt@uni.edu")
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]
    from app.db.base import new_ulid

    _create_student_search_release(
        client,
        course_id=course_id,
        student_id=student_id,
        teacher_id=teacher_id,
        version_id=version_id,
        domain_release_id=new_ulid(),
    )
    _login(client, "ms@uni.edu")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "independent variable validity"},
    )
    assert search.status_code == 200, search.text
    pointer_id = search.json()["data"]["items"][0]["evidence_pointer_id"]
    return course_id, student_id, pointer_id


def test_resource_open_event_is_exact_pinned_non_evidence_and_idempotent(client) -> None:
    from app.db.base import new_ulid
    from app.db.models import (
        CourseMember,
        EvidencePointer,
        LearningEvent,
        LearningEvidence,
        LearningQualification,
        MasteryState,
    )
    from app.db.session import session_factory
    from app.modules.learning_events.service import derive_resource_open_event

    course_id, student_id, pointer_id = _prepare_resource_open_pointer(client)
    body = {
        "event_key": "resource-open-001",
        "course_id": course_id,
        "evidence_pointer_id": pointer_id,
    }
    first = client.post("/api/v1/learning-events", json=body)
    assert first.status_code == 201, first.text
    event = first.json()["data"]
    assert event["event_type"] == "RESOURCE_OPENED"
    assert event["source_type"] == "resource"
    assert event["source_ref"] == pointer_id
    assert event["qualification_status"] == "rejected"
    assert event["qualification_reason"] == "resource_usage_non_evidence"
    assert set(event["payload"]) == {
        "evidence_pointer_id",
        "material_id",
        "material_version_id",
        "course_release_assignment_id",
        "course_release_id",
        "publication_snapshot_id",
        "index_job_id",
        "domain_release_id",
    }
    assert "excerpt" not in event["payload"]
    replay = client.post("/api/v1/learning-events", json=body)
    assert replay.status_code == 200
    assert replay.json()["data"]["id"] == event["id"]
    assert replay.json()["meta"]["idempotent_replay"] is True

    async def clone_pointer() -> str:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            duplicate = EvidencePointer(
                id=new_ulid(),
                course_id=pointer.course_id,
                material_id=pointer.material_id,
                material_version_id=pointer.material_version_id,
                publication_snapshot_id=pointer.publication_snapshot_id,
                index_job_id=pointer.index_job_id,
                domain_release_id=pointer.domain_release_id,
                source_object_id=pointer.source_object_id,
                retrieval_unit_id=pointer.retrieval_unit_id,
                material_title=pointer.material_title,
                excerpt=pointer.excerpt,
                excerpt_sha256=pointer.excerpt_sha256,
                chapter_path=pointer.chapter_path,
                physical_page=pointer.physical_page,
                reading_order=pointer.reading_order,
                object_type=pointer.object_type,
                coordinate_space=pointer.coordinate_space,
                bbox=pointer.bbox,
                anchors=pointer.anchors,
            )
            db.add(duplicate)
            await db.commit()
            return duplicate.id

    second_pointer_id = asyncio.run(clone_pointer())
    conflict = client.post(
        "/api/v1/learning-events",
        json={**body, "evidence_pointer_id": second_pointer_id},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "LEARNING_EVENT_KEY_CONFLICT"

    async def assert_only_usage_event() -> None:
        async with session_factory() as db:
            row = await db.get(LearningEvent, event["id"])
            assert row is not None
            assert row.qualification_status == "rejected"
            assert row.qualification_reason == "resource_usage_non_evidence"
            assert await db.scalar(
                select(func.count()).select_from(LearningQualification).where(
                    LearningQualification.event_id == event["id"]
                )
            ) == 0
            assert await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            ) == 0
            assert await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            ) == 0
            derived = await derive_resource_open_event(
                db, user_id=student_id, course_id=course_id, pointer_id=pointer_id
            )
            assert set(derived) == set(row.payload)

    asyncio.run(assert_only_usage_event())

    async def revoke_course_membership() -> None:
        async with session_factory() as db:
            membership = await db.scalar(
                select(CourseMember).where(
                    CourseMember.user_id == student_id,
                    CourseMember.course_id == course_id,
                )
            )
            assert membership is not None
            membership.status = "removed"
            await db.commit()

    asyncio.run(revoke_course_membership())
    denied_after_revocation = client.post(
        "/api/v1/learning-events",
        json={**body, "event_key": "resource-open-after-revocation"},
    )
    assert denied_after_revocation.status_code == 404
    assert denied_after_revocation.json()["error"]["code"] == "COURSE_NOT_FOUND"

    from app.modules.memory.deletion import delete_personal_learning_data

    async def delete_usage_event() -> None:
        async with session_factory() as db:
            counts = await delete_personal_learning_data(db, user_id=student_id)
            await db.commit()
            assert counts["learning_events"] == 1
            assert await db.get(LearningEvent, event["id"]) is None

    asyncio.run(delete_usage_event())


def test_resource_open_event_rejects_unpinned_pointer_and_extra_fields(client) -> None:
    from app.core.errors import ApiError
    from app.db.models import EvidencePointer
    from app.db.session import session_factory
    from app.modules.learning_events.service import derive_resource_open_event

    course_id, student_id, pointer_id = _prepare_resource_open_pointer(client)

    async def make_legacy_pointer() -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            pointer.publication_snapshot_id = None
            pointer.index_job_id = None
            pointer.domain_release_id = None
            await db.commit()

    asyncio.run(make_legacy_pointer())
    rejected = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-legacy",
            "course_id": course_id,
            "evidence_pointer_id": pointer_id,
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "EVIDENCE_PIN_INVALID"

    extra = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-extra",
            "course_id": course_id,
            "evidence_pointer_id": pointer_id,
            "excerpt": "must not be accepted",
        },
    )
    assert extra.status_code == 422

    async def wrong_scope_pointer() -> None:
        async with session_factory() as db:
            with pytest.raises(ApiError) as error:
                await derive_resource_open_event(
                    db,
                    user_id=student_id,
                    course_id=course_id,
                    pointer_id="01M00000000000000000000000",
                )
            assert error.value.status_code == 404

    asyncio.run(wrong_scope_pointer())


def test_resource_open_event_rejects_pointer_after_assignment_release_rotation(client) -> None:
    from app.db.models import CourseRelease, CourseReleaseAssignment
    from app.db.session import session_factory

    course_id, _student_id, pointer_id = _prepare_resource_open_pointer(client)

    async def rotate_to_empty_release() -> None:
        async with session_factory() as db:
            assignment = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert assignment is not None
            old_release = await db.get(CourseRelease, assignment.course_release_id)
            assert old_release is not None
            current = CourseRelease(
                course_id=course_id,
                version_no=old_release.version_no + 1,
                name="合成空资料新版",
                status="published",
                manifest={
                    "materials": [],
                    "material_version_ids": [],
                    "publication_snapshots": [],
                },
                domain_release_id=old_release.domain_release_id,
                created_by=old_release.created_by,
                published_by=old_release.published_by,
                published_at=old_release.published_at,
            )
            db.add(current)
            await db.flush()
            assignment.course_release_id = current.id
            await db.commit()

    asyncio.run(rotate_to_empty_release())
    _login(client, "ms@uni.edu")
    stale_pointer = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-stale-pin",
            "course_id": course_id,
            "evidence_pointer_id": pointer_id,
        },
    )
    assert stale_pointer.status_code == 404
    assert stale_pointer.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_resource_open_event_enforces_student_scope_unique_assignment_and_release_state(
    client,
) -> None:
    from app.db.base import new_ulid
    from app.db.models import (
        ClassMember,
        CourseClass,
        CourseReleaseAssignment,
        EvidencePointer,
        Material,
        MaterialVersion,
    )
    from app.db.session import session_factory

    course_id, student_id, pointer_id = _prepare_resource_open_pointer(client)
    _login(client, "mt@uni.edu")
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]
    foreign_course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    assert client.post(
        f"/api/v1/courses/{foreign_course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    denied_staff = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-staff",
            "course_id": course_id,
            "evidence_pointer_id": pointer_id,
        },
    )
    assert denied_staff.status_code == 404

    async def create_unassigned_legacy_pointer() -> str:
        async with session_factory() as db:
            material = Material(
                course_id=foreign_course["id"],
                title="合成未指派资料",
                material_type="slides",
                visibility="published",
                status="active",
                created_by=teacher_id,
            )
            db.add(material)
            await db.flush()
            version = MaterialVersion(
                material_id=material.id,
                version_no=1,
                status="parsed",
                created_by=teacher_id,
                page_count=1,
            )
            db.add(version)
            await db.flush()
            material.current_version_id = version.id
            pointer = EvidencePointer(
                course_id=foreign_course["id"],
                material_id=material.id,
                material_version_id=version.id,
                material_title=material.title,
                excerpt="合成片段",
                excerpt_sha256="0" * 64,
                object_type="paragraph",
                publication_snapshot_id=None,
                index_job_id=None,
                domain_release_id=None,
            )
            db.add(pointer)
            await db.commit()
            return pointer.id

    unassigned_pointer_id = asyncio.run(create_unassigned_legacy_pointer())
    _login(client, "ms@uni.edu")
    legacy_unassigned = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-never-assigned",
            "course_id": foreign_course["id"],
            "evidence_pointer_id": unassigned_pointer_id,
        },
    )
    assert legacy_unassigned.status_code == 404
    assert legacy_unassigned.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_NOT_FOUND"

    async def add_second_assignment() -> None:
        async with session_factory() as db:
            original = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert original is not None
            other_class = CourseClass(
                course_id=course_id,
                code=f"SRC-{new_ulid()[:10]}",
                name="合成歧义班级",
                created_by=teacher_id,
            )
            db.add(other_class)
            await db.flush()
            db.add_all(
                [
                    CourseReleaseAssignment(
                        course_id=course_id,
                        class_id=other_class.id,
                        course_release_id=original.course_release_id,
                        status="active",
                        assigned_by=teacher_id,
                    ),
                    ClassMember(class_id=other_class.id, user_id=student_id),
                ]
            )
            await db.commit()

    asyncio.run(add_second_assignment())
    ambiguous = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-ambiguous",
            "course_id": course_id,
            "evidence_pointer_id": pointer_id,
        },
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS"

    foreign = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-foreign",
            "course_id": foreign_course["id"],
            "evidence_pointer_id": pointer_id,
        },
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"

    async def close_assignments() -> None:
        async with session_factory() as db:
            assignments = (
                await db.scalars(
                    select(CourseReleaseAssignment).where(
                        CourseReleaseAssignment.course_id == course_id,
                        CourseReleaseAssignment.status == "active",
                    )
                )
            ).all()
            assert len(assignments) == 2
            for assignment in assignments:
                assignment.status = "closed"
            await db.commit()

    asyncio.run(close_assignments())
    no_assignment = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "resource-open-no-assignment",
            "course_id": course_id,
            "evidence_pointer_id": pointer_id,
        },
    )
    assert no_assignment.status_code == 404
    assert no_assignment.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_NOT_FOUND"


def test_learning_event_is_pending_and_idempotent(client) -> None:
    create_user_sync(email="event-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="event-student@uni.edu")
    other_student_id = create_user_sync(email="event-other-student@uni.edu")
    _login(client, "event-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    added = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert added.status_code == 201
    other_added = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": other_student_id, "role": "student"},
    )
    assert other_added.status_code == 201

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

    _login(client, "event-other-student@uni.edu")
    other_event = client.post(
        "/api/v1/learning-events",
        json={**body, "event_key": "turn-other-001", "payload": {"block_count": 1}},
    )
    assert other_event.status_code == 201

    _login(client, "event-student@uni.edu")
    listed = client.get(f"/api/v1/me/learning-events?course_id={course['id']}")
    assert listed.status_code == 200
    assert [item["event_key"] for item in listed.json()["data"]] == ["turn-001"]

    _login(client, "event-teacher@uni.edu")
    denied_teacher = client.get(f"/api/v1/me/learning-events?course_id={course['id']}")
    assert denied_teacher.status_code == 404


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
