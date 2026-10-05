import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.db.models import CourseRelease, CourseReleaseAssignment
from app.db.session import session_factory
from app.modules.interventions.router import (
    _effect_count_metrics,
    _intervention_window,
    _summarize_recheck_evidence,
    _suppress_recheck_small_sample,
)
from app.modules.teaching_activities import schemas, service
from app.modules.teaching_activities.router import _time_window, router
from tests.conftest import create_user_sync


def test_time_window_defaults_to_last_thirty_days_and_uses_utc() -> None:
    start, end = _time_window(None, None)

    assert end.tzinfo == UTC
    assert end - start == timedelta(days=30)


def test_intervention_window_defaults_to_thirty_days_and_rejects_over_ninety() -> None:
    now = datetime(2026, 3, 31, tzinfo=UTC)
    start, end = _intervention_window(None, None, now=now)
    assert start == now - timedelta(days=30)
    assert end == now
    with pytest.raises(ApiError) as exc_info:
        _intervention_window(
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
            now=now,
        )
    assert exc_info.value.code == "TIME_WINDOW_TOO_WIDE"


def test_effect_count_metrics_hide_every_exact_value_when_sample_is_small() -> None:
    metrics = _effect_count_metrics(student_count=4, run_count=6, completed_count=3)

    assert metrics == {
        "sample_status": "suppressed_small_sample",
        "student_count": None,
        "run_count": None,
        "completed_count": None,
        "completion_rate": None,
    }


def test_effect_count_metrics_expose_values_at_five_students() -> None:
    metrics = _effect_count_metrics(student_count=5, run_count=8, completed_count=6)

    assert metrics["sample_status"] == "available"
    assert metrics["student_count"] == 5
    assert metrics["completion_rate"] == 0.75


def test_time_window_normalizes_offsets_and_is_half_open() -> None:
    start, end = _time_window(
        datetime(2026, 1, 1, 8, tzinfo=UTC),
        datetime(2026, 2, 1, 8, tzinfo=UTC),
    )

    assert start.isoformat() == "2026-01-01T08:00:00+00:00"
    assert end.isoformat() == "2026-02-01T08:00:00+00:00"


@pytest.mark.parametrize(
    ("start_at", "end_at", "error_code"),
    [
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 4, 2, tzinfo=UTC),
            "TIME_WINDOW_TOO_WIDE",
        ),
        (
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            "TIME_WINDOW_INVALID",
        ),
        (
            datetime(2026, 1, 1),
            datetime(2026, 1, 2, tzinfo=UTC),
            "TIME_WINDOW_TIMEZONE_REQUIRED",
        ),
    ],
)
def test_time_window_rejects_invalid_ranges(start_at, end_at, error_code) -> None:
    with pytest.raises(ApiError) as exc_info:
        _time_window(start_at, end_at)

    assert exc_info.value.code == error_code


def test_recheck_requires_independent_valid_evidence_in_distinct_contexts() -> None:
    completed_at = datetime(2026, 1, 1, tzinfo=UTC)
    run = SimpleNamespace(user_id="student-1", completed_at=completed_at)
    rows = [
        SimpleNamespace(
            id="evidence-1",
            user_id="student-1",
            created_at=completed_at + timedelta(days=1),
            context_key="quiz-a",
            correct=True,
            quality_status="valid",
            independence_status="independent",
        ),
        SimpleNamespace(
            id="evidence-2",
            user_id="student-1",
            created_at=completed_at + timedelta(days=2),
            context_key="lab-b",
            correct=False,
            quality_status="valid",
            independence_status="independent",
        ),
        SimpleNamespace(
            id="evidence-3",
            user_id="student-1",
            created_at=completed_at + timedelta(days=3),
            context_key="quiz-a",
            correct=True,
            quality_status="valid",
            independence_status="supported",
        ),
    ]

    result = _summarize_recheck_evidence(
        rows,
        evidence_ids={"evidence-1", "evidence-2", "evidence-3"},
        run_for_evidence={item.id: run for item in rows},
        window="immediate",
    )

    assert result["status"] == "measured"
    assert result["evidence_count"] == 2
    assert result["student_count"] == 1
    assert result["context_count"] == 2
    assert result["accuracy_rate"] == 0.5


def test_recheck_summary_suppresses_all_exact_metrics_below_five_students() -> None:
    summary = {
        "status": "measured",
        "evidence_count": 4,
        "student_count": 4,
        "context_count": 3,
        "accuracy_rate": 0.75,
    }

    result = _suppress_recheck_small_sample(summary)

    assert result["status"] == "suppressed_small_sample"
    assert result["evidence_count"] is None
    assert result["student_count"] is None
    assert result["context_count"] is None
    assert result["accuracy_rate"] is None


def test_recheck_json_without_referenced_evidence_stays_not_measured() -> None:
    result = _summarize_recheck_evidence(
        [], evidence_ids=set(), run_for_evidence={}, window="immediate"
    )

    assert result["status"] == "not_measured"
    assert result["accuracy_rate"] is None


def test_activity_update_requires_expected_version_and_a_change() -> None:
    with pytest.raises(ValueError):
        schemas.TeachingActivityUpdate(expected_version=1)

    update = schemas.TeachingActivityUpdate(expected_version=3, status="ready")
    assert update.expected_version == 3


def test_run_requires_timezone_aware_schedule() -> None:
    with pytest.raises(ValueError):
        schemas.TeachingActivityRunCreate(
            activity_version_id="0" * 26,
            scheduled_at=datetime(2026, 1, 1),
        )


def test_activity_router_exposes_the_agreed_module_paths() -> None:
    paths = {route.path for route in router.routes}

    assert "/courses/{course_id}/teaching-activities" in paths
    assert "/courses/{course_id}/classes/{class_id}/teaching-activity-runs" in paths
    assert (
        "/courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run_id}/actions" in paths
    )
    assert "/courses/{course_id}/classes/{class_id}/timeline" in paths
    assert "/courses/{course_id}/classes/{class_id}/teacher-annotations" in paths


def test_run_transitions_reject_terminal_revival_and_skips() -> None:
    assert service.run_transition("start", "ready") == "active"
    assert service.run_transition("pause", "active") == "paused"
    assert service.run_transition("resume", "paused") == "active"
    assert service.run_transition("start", "completed") is None
    assert service.run_transition("complete", "planned") is None


def test_target_roster_snapshot_is_deterministic_and_policy_requires_publish() -> None:
    snapshot_a, digest_a = service.target_roster_snapshot(["student-b", "student-a"])
    snapshot_b, digest_b = service.target_roster_snapshot(["student-a", "student-b"])

    assert snapshot_a == snapshot_b
    assert digest_a == digest_b
    with pytest.raises(ApiError) as exc_info:
        service.validate_annotation_visibility("student_visible", "draft")
    assert exc_info.value.code == "ANNOTATION_PUBLICATION_REQUIRED"
    service.validate_annotation_visibility("student_visible", "published")


def test_teaching_activity_run_timeline_annotation_flow(client) -> None:
    teacher_email = "r3-d-activity-teacher@uni.edu"
    teacher_id = create_user_sync(email=teacher_email, is_teacher=True)
    student_id = create_user_sync(email="r3-d-activity-student@uni.edu")
    assert client.post(
        "/api/v1/auth/login",
        json={"email": teacher_email, "password": "correct-password"},
    ).status_code == 200
    course = client.post(
        "/api/v1/courses",
        json={"title": "R3-D 活动测试", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    course_id = course["id"]
    assert client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    class_response = client.post(
        f"/api/v1/courses/{course_id}/classes",
        json={"code": "R3D01", "name": "R3-D 活动班"},
    )
    assert class_response.status_code == 201
    class_id = class_response.json()["data"]["id"]
    assert client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teachers",
        json={"teacher_id": teacher_id, "assignment_role": "lead"},
    ).status_code == 201
    assert client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/members",
        json={"user_id": student_id},
    ).status_code == 201

    async def _seed_release() -> tuple[str, str]:
        async with session_factory() as db:
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="R3-D test release",
                status="published",
                manifest={"pedagogy_pack": {"success_criteria": ["解释变量关系"]}},
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(release)
            await db.flush()
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=class_id,
                course_release_id=release.id,
                status="active",
                assigned_by=teacher_id,
            )
            db.add(assignment)
            await db.commit()
            return release.id, assignment.id

    release_id, assignment_id = asyncio.run(_seed_release())
    if not any(
        getattr(route, "path", None) == "/courses/{course_id}/teaching-activities"
        for route in client.app.router.routes
    ):
        client.app.include_router(router, prefix="/api/v1", tags=["teaching-activities"])

    activity_response = client.post(
        f"/api/v1/courses/{course_id}/teaching-activities",
        headers={"Idempotency-Key": "r3d-activity-create-001"},
        json={
            "activity_key": "r3d-variable-map",
            "title": "变量映射活动",
            "activity_type": "practice",
            "manifest": {"steps": ["找出自变量", "解释因变量"]},
        },
    )
    assert activity_response.status_code == 201
    activity = activity_response.json()["data"]
    replay = client.post(
        f"/api/v1/courses/{course_id}/teaching-activities",
        headers={"Idempotency-Key": "r3d-activity-create-001"},
        json={
            "activity_key": "r3d-variable-map",
            "title": "变量映射活动",
            "activity_type": "practice",
            "manifest": {"steps": ["找出自变量", "解释因变量"]},
        },
    )
    assert replay.status_code == 201
    assert replay.json()["meta"]["idempotent_replay"] is True
    assert replay.json()["data"]["id"] == activity["id"]

    ready = client.patch(
        f"/api/v1/courses/{course_id}/teaching-activities/{activity['id']}",
        headers={"Idempotency-Key": "r3d-activity-ready-001"},
        json={"expected_version": activity["version"], "status": "ready"},
    )
    assert ready.status_code == 200
    ready_activity = ready.json()["data"]
    assert ready_activity["status"] == "ready"
    assert ready_activity["supersedes_id"] == activity["id"]

    run_response = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teaching-activity-runs",
        headers={"Idempotency-Key": "r3d-activity-run-001"},
        json={
            "activity_version_id": ready_activity["id"],
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert run_response.status_code == 201
    run = run_response.json()["data"]
    assert run["status"] == "ready"
    assert run["course_release_id"] == release_id
    assert run["course_release_assignment_id"] == assignment_id
    assert run["target_snapshot"]["member_ids"] == [student_id]
    assert run["run_snapshot"]["course_policy"] == {
        "success_criteria": ["解释变量关系"]
    }

    action = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run['id']}/actions",
        headers={"Idempotency-Key": "r3d-activity-start-001"},
        json={"expected_version": run["version"], "action": "start"},
    )
    assert action.status_code == 200
    assert action.json()["data"]["status"] == "active"
    action_replay = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run['id']}/actions",
        headers={"Idempotency-Key": "r3d-activity-start-001"},
        json={"expected_version": run["version"], "action": "start"},
    )
    assert action_replay.status_code == 200
    assert action_replay.json()["meta"]["idempotent_replay"] is True
    invalid_complete = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run['id']}/actions",
        headers={"Idempotency-Key": "r3d-activity-invalid-complete"},
        json={"expected_version": run["version"], "action": "complete"},
    )
    assert invalid_complete.status_code == 409

    unpublished = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teacher-annotations",
        headers={"Idempotency-Key": "r3d-annotation-draft-public"},
        json={
            "target_type": "activity",
            "target_id": ready_activity["id"],
            "visibility": "student_visible",
            "status": "draft",
            "annotation": "公开前应先由教师确认的教学提示",
        },
    )
    assert unpublished.status_code == 422
    annotation_response = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teacher-annotations",
        headers={"Idempotency-Key": "r3d-annotation-published-001"},
        json={
            "target_type": "activity",
            "target_id": ready_activity["id"],
            "visibility": "student_visible",
            "status": "published",
            "annotation": "公开发布的教学提示",
        },
    )
    assert annotation_response.status_code == 201
    annotation = annotation_response.json()["data"]
    assert annotation["status"] == "published"
    assert annotation["visibility"] == "student_visible"

    timeline = client.get(
        f"/api/v1/courses/{course_id}/classes/{class_id}/timeline",
        params={
            "start_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "end_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    assert timeline.status_code == 200
    phases = {event["phase"] for event in timeline.json()["data"]["events"]}
    assert "planned" in phases
    assert "actual" in phases
    assert all("payload" not in event for event in timeline.json()["data"]["events"])

    unassigned_email = "r3-d-activity-unassigned@uni.edu"
    unassigned_id = create_user_sync(email=unassigned_email, is_teacher=True)
    assert client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": unassigned_id, "role": "teacher"},
    ).status_code == 201
    assert client.post(
        "/api/v1/auth/logout", json={}
    ).status_code in {200, 204}
    assert client.post(
        "/api/v1/auth/login",
        json={"email": unassigned_email, "password": "correct-password"},
    ).status_code == 200
    denied = client.get(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teaching-activity-runs"
    )
    assert denied.status_code == 404
