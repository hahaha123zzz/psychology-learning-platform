from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from app.core.errors import ApiError
from app.db.models import CourseRelease, CourseReleaseAssignment, TeachingActivity


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiError(
            status_code=422,
            code="TIME_WINDOW_TIMEZONE_REQUIRED",
            message="时间必须包含时区",
        )
    return value.astimezone(UTC)


def time_window(start_at: datetime | None, end_at: datetime | None) -> tuple[datetime, datetime]:
    end = as_utc(end_at) if end_at is not None else utc_now()
    start = as_utc(start_at) if start_at is not None else end - timedelta(days=30)
    if start >= end:
        raise ApiError(
            status_code=422,
            code="TIME_WINDOW_INVALID",
            message="start_at 必须早于 end_at",
        )
    if end - start > timedelta(days=90):
        raise ApiError(
            status_code=422,
            code="TIME_WINDOW_TOO_WIDE",
            message="统计时间范围不能超过 90 天",
        )
    return start, end


def target_roster_snapshot(target_user_ids: list[str]) -> tuple[dict[str, Any], str]:
    targets = sorted(set(target_user_ids))
    digest = sha256("\n".join(targets).encode("utf-8")).hexdigest()
    return (
        {"member_ids": targets, "member_count": len(targets), "sha256": digest},
        digest,
    )


def build_run_snapshot(
    *,
    activity: TeachingActivity,
    release: CourseRelease,
    assignment: CourseReleaseAssignment,
    created_by: str,
    target_sha256: str,
) -> dict[str, Any]:
    manifest = release.manifest if isinstance(release.manifest, dict) else {}
    activity_snapshot = {
        "id": activity.id,
        "activity_key": activity.activity_key,
        "version_no": activity.version_no,
        "title": activity.title,
        "activity_type": activity.activity_type,
        "manifest": deepcopy(activity.manifest),
    }
    return {
        "activity": activity_snapshot,
        "course_policy": deepcopy(manifest.get("pedagogy_pack", {})),
        "release": {"id": release.id, "version_no": release.version_no},
        "assignment": {
            "id": assignment.id,
            "assigned_at": assignment.assigned_at.isoformat(),
        },
        "created_by": created_by,
        "target_sha256": target_sha256,
    }


def run_transition(action: str, status: str) -> str | None:
    transitions = {
        "start": {"ready": "active"},
        "pause": {"active": "paused"},
        "resume": {"paused": "active"},
        "complete": {"active": "completed", "paused": "completed"},
        "cancel": {
            "planned": "cancelled",
            "ready": "cancelled",
            "active": "cancelled",
            "paused": "cancelled",
        },
    }
    return transitions.get(action, {}).get(status)


def validate_annotation_visibility(visibility: str, status: str) -> None:
    if visibility == "student_visible" and status != "published":
        raise ApiError(
            status_code=422,
            code="ANNOTATION_PUBLICATION_REQUIRED",
            message="学生可见注释必须显式发布",
        )
