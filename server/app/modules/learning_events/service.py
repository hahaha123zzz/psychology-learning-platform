from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import (
    DomainRelease,
    EvidencePointer,
    Job,
    LearningEvent,
    Material,
    MaterialVersion,
    PublicationSnapshot,
)


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
    qualification_status: str = "pending",
    qualification_reason: str | None = None,
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
        qualification_status=qualification_status,
        qualification_reason=qualification_reason,
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


async def derive_resource_open_event(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    pointer_id: str,
) -> dict[str, str]:
    """Validate the current assigned release and return identifier-only event payload."""
    from app.modules.courses.service import resolve_active_student_course_release

    pointer = await db.get(EvidencePointer, pointer_id)
    if pointer is None or pointer.course_id != course_id:
        raise ApiError(404, "EVIDENCE_NOT_FOUND", "教材引用不存在或无权访问")

    resolved = await resolve_active_student_course_release(
        db, user_id=user_id, course_id=course_id
    )
    if resolved is None:
        raise ApiError(404, "COURSE_RELEASE_ASSIGNMENT_NOT_FOUND", "当前课程没有有效材料指派")
    assignment, release = resolved
    manifest = release.manifest if isinstance(release.manifest, dict) else {}
    materials = manifest.get("materials")
    versions = manifest.get("material_version_ids")
    pins = manifest.get("publication_snapshots")
    if (
        not isinstance(materials, list)
        or not isinstance(versions, list)
        or not isinstance(pins, list)
        or any(not isinstance(value, str) or not value for value in materials)
        or any(not isinstance(value, str) or not value for value in versions)
        or len(set(materials)) != len(materials)
        or len(set(versions)) != len(versions)
        or release.domain_release_id is None
    ):
        raise ApiError(409, "COURSE_RELEASE_ASSIGNMENT_INVALID", "课程材料指派快照不可用")
    if len(materials) != len(versions) or len(materials) != len(pins):
        raise ApiError(409, "COURSE_RELEASE_ASSIGNMENT_INVALID", "课程材料指派快照不可用")
    matching_indexes = [
        index
        for index, (material_id, version_id) in enumerate(
            zip(materials, versions, strict=True)
        )
        if material_id == pointer.material_id and version_id == pointer.material_version_id
    ]
    if len(matching_indexes) != 1:
        raise ApiError(404, "EVIDENCE_NOT_FOUND", "教材引用不属于当前课程版本")
    pin = pins[matching_indexes[0]]
    required = {
        "material_id",
        "material_version_id",
        "publication_snapshot_id",
        "index_job_id",
        "embedding_version",
        "domain_release_id",
    }
    if (
        not isinstance(pin, dict)
        or set(pin) != required
        or any(not isinstance(pin.get(key), str) or not pin[key] for key in required)
        or pin["domain_release_id"] != release.domain_release_id
        or pointer.publication_snapshot_id is None
        or pointer.index_job_id is None
        or pointer.domain_release_id is None
        or pointer.material_id != pin["material_id"]
        or pointer.material_version_id != pin["material_version_id"]
        or pointer.publication_snapshot_id != pin["publication_snapshot_id"]
        or pointer.index_job_id != pin["index_job_id"]
        or pointer.domain_release_id != pin["domain_release_id"]
    ):
        raise ApiError(409, "EVIDENCE_PIN_INVALID", "教材引用没有与当前课程版本一致的固定发布")

    material = await db.get(Material, pointer.material_id)
    version = await db.get(MaterialVersion, pointer.material_version_id)
    snapshot = await db.get(PublicationSnapshot, pointer.publication_snapshot_id)
    index_job = await db.get(Job, pointer.index_job_id)
    domain_release = await db.get(DomainRelease, pointer.domain_release_id)
    job_payload = index_job.payload if index_job and isinstance(index_job.payload, dict) else {}
    if (
        material is None
        or material.course_id != course_id
        or material.status != "active"
        or material.visibility != "published"
        or version is None
        or version.material_id != material.id
        or version.status != "parsed"
        or snapshot is None
        or snapshot.material_id != material.id
        or snapshot.material_version_id != version.id
        or snapshot.embedding_version != pin["embedding_version"]
        or index_job is None
        or snapshot.index_job_id != index_job.id
    ):
        raise ApiError(409, "EVIDENCE_PIN_INVALID", "教材引用对应的发布快照已不可用")
    if (
        index_job is None
        or index_job.kind != "material_embed"
        or index_job.status != "succeeded"
        or job_payload.get("material_version_id") != version.id
        or job_payload.get("domain_release_id") != pointer.domain_release_id
        or snapshot.domain_release_id != pointer.domain_release_id
        or domain_release is None
        or domain_release.course_id != course_id
        or domain_release.status not in {"published", "deprecated"}
        or release.domain_release_id != pointer.domain_release_id
    ):
        raise ApiError(409, "EVIDENCE_PIN_INVALID", "教材引用对应的发布索引或课程版本已不可用")

    return {
        "evidence_pointer_id": pointer.id,
        "material_id": material.id,
        "material_version_id": version.id,
        "course_release_assignment_id": assignment.id,
        "course_release_id": release.id,
        "publication_snapshot_id": snapshot.id,
        "index_job_id": index_job.id,
        "domain_release_id": domain_release.id,
    }
