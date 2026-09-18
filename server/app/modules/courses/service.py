import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import AuditLog, Course, CourseMember, IdempotencyRecord, User
from app.modules.courses.schemas import CourseOut


def canonical_request_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def course_out(course: Course) -> dict[str, Any]:
    return CourseOut(
        id=course.id,
        title=course.title,
        term=course.term,
        description=course.description,
        timezone=course.timezone,
        status=course.status,
        version=course.version,
        created_by=course.created_by,
        created_at=course.created_at,
        updated_at=course.updated_at,
    ).model_dump(mode="json")


async def find_idempotent_response(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.endpoint == endpoint,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="该幂等键已用于不同内容的请求",
        )
    return {"status": record.response_status, "body": record.response_body}


async def save_idempotent_response(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
    status: int,
    body: dict[str, Any],
) -> None:
    db.add(
        IdempotencyRecord(
            idempotency_key=key,
            user_id=user_id,
            endpoint=endpoint,
            request_hash=request_hash,
            response_status=status,
            response_body=body,
        )
    )


async def write_audit(
    db: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    course_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            course_id=course_id,
            detail=detail,
        )
    )


async def get_course_or_404(db: AsyncSession, course_id: str) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id).limit(1))
    course = result.scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    return course


async def create_course_with_membership(
    db: AsyncSession,
    *,
    creator: User,
    title: str,
    term: str,
    description: str | None,
    timezone: str,
) -> Course:
    course = Course(
        organization_id=get_settings().default_organization_id,
        title=title,
        term=term,
        description=description,
        timezone=timezone,
        created_by=creator.id,
    )
    db.add(course)
    await db.flush()
    db.add(
        CourseMember(
            course_id=course.id,
            user_id=creator.id,
            role="teacher",
            status="active",
        )
    )
    await write_audit(
        db,
        actor_id=creator.id,
        action="course.created",
        resource_type="course",
        resource_id=course.id,
        course_id=course.id,
        detail={"title": title, "term": term},
    )
    return course


async def get_active_membership(
    db: AsyncSession, *, course_id: str, user_id: str
) -> CourseMember | None:
    result = await db.execute(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == user_id,
            CourseMember.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def get_member_or_404(
    db: AsyncSession, *, course_id: str, member_id: str
) -> CourseMember:
    result = await db.execute(
        select(CourseMember).where(
            CourseMember.id == member_id, CourseMember.course_id == course_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise ApiError(status_code=404, code="MEMBER_NOT_FOUND", message="成员不存在")
    return member
