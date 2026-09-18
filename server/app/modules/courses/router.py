from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import Course, CourseMember, User
from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    get_current_user,
    require_course_role,
)
from app.modules.courses import service
from app.modules.courses.schemas import (
    CourseCreate,
    CourseUpdate,
    MemberAdd,
    MemberOut,
    MemberRoleUpdate,
)

router = APIRouter()

COURSE_LIST_PAGE_SIZE = 50
COURSES_CREATE_ENDPOINT = "POST:/api/v1/courses"


@router.post("/courses", response_model=None)
async def create_course(
    body: CourseCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not (user.is_platform_admin or user.is_teacher):
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="仅教师或管理员可创建课程",
        )
    payload: dict[str, Any] = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)

    if idempotency_key:
        previous = await service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=COURSES_CREATE_ENDPOINT,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(
                request,
                previous["body"]["data"],
                status_code=previous["status"],
            )

    course = await service.create_course_with_membership(
        db,
        creator=user,
        title=body.title,
        term=body.term,
        description=body.description,
        timezone=body.timezone,
    )
    body_data = service.course_out(course)

    if idempotency_key:
        try:
            await service.save_idempotent_response(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=COURSES_CREATE_ENDPOINT,
                request_hash=request_hash,
                status=201,
                body={"data": body_data},
            )
            await db.commit()
        except IntegrityError:
            await db.rollback()
            previous = await service.find_idempotent_response(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=COURSES_CREATE_ENDPOINT,
                request_hash=request_hash,
            )
            if previous is None:
                raise
            return ok(request, previous["body"]["data"], status_code=previous["status"])
    else:
        await db.commit()

    return ok(request, body_data, status_code=201)


@router.get("/courses", response_model=None)
async def list_courses(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=COURSE_LIST_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    query = select(Course).where(Course.status == "active").order_by(Course.id.desc())
    if not user.is_platform_admin:
        member_courses = select(CourseMember.course_id).where(
            CourseMember.user_id == user.id,
            CourseMember.status == "active",
        )
        query = query.where(Course.id.in_(member_courses))
    if cursor:
        query = query.where(Course.id < cursor)
    result = await db.execute(query.limit(limit + 1))
    courses = list(result.scalars())
    has_more = len(courses) > limit
    items = [service.course_out(c) for c in courses[:limit]]
    next_cursor = courses[:limit][-1].id if has_more and courses else None
    return ok(request, items, next_cursor=next_cursor, has_more=has_more)


@router.get("/courses/{course_id}", response_model=None)
async def get_course(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    course = await service.get_course_or_404(db, course_id)
    if not user.is_platform_admin:
        membership = await service.get_active_membership(
            db, course_id=course.id, user_id=user.id
        )
        if membership is None:
            raise ApiError(
                status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问"
            )
    return ok(request, service.course_out(course))


@router.patch("/courses/{course_id}", response_model=None)
async def update_course(
    course_id: str,
    body: CourseUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    course = await service.get_course_or_404(db, course_id)
    if course.status == "archived" and body.status != "active":
        raise ApiError(status_code=409, code="COURSE_ARCHIVED", message="课程已归档")
    if course.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="课程已被其他人修改，请刷新后重试",
            details={"expected_version": body.version, "actual_version": course.version},
        )
    updates = body.model_dump(exclude={"version"}, exclude_none=True)
    for field, value in updates.items():
        setattr(course, field, value)
    course.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.updated",
        resource_type="course",
        resource_id=course.id,
        course_id=course.id,
        detail={"fields": sorted(updates), "new_version": course.version},
    )
    await db.commit()
    await db.refresh(course)
    return ok(request, service.course_out(course))


@router.post("/courses/{course_id}/members", response_model=None)
async def add_member(
    course_id: str,
    body: MemberAdd,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    course = await service.get_course_or_404(db, course_id)
    target_result = await db.execute(
        select(User).where(User.id == body.user_id).limit(1)
    )
    target = target_result.scalar_one_or_none()
    if target is None:
        raise ApiError(status_code=404, code="USER_NOT_FOUND", message="用户不存在")
    if target.status != "active":
        raise ApiError(
            status_code=409, code="USER_DISABLED", message="不能添加已停用的账号"
        )
    existing = await service.get_active_membership(
        db, course_id=course.id, user_id=body.user_id
    )
    if existing is not None:
        raise ApiError(
            status_code=409,
            code="MEMBER_ALREADY_EXISTS",
            message="该用户已是课程成员",
        )
    existing_row_result = await db.execute(
        select(CourseMember).where(
            CourseMember.course_id == course.id,
            CourseMember.user_id == body.user_id,
        )
    )
    existing_row = existing_row_result.scalar_one_or_none()
    if existing_row is not None:
        existing_row.status = "active"
        existing_row.role = body.role
        existing_row.version += 1
        member = existing_row
    else:
        member = CourseMember(
            course_id=course.id,
            user_id=body.user_id,
            role=body.role,
            status="active",
        )
        db.add(member)
    await db.flush()
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.member_added",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course.id,
        detail={"target_user_id": body.user_id, "role": body.role},
    )
    await db.commit()
    data = MemberOut(
        id=member.id,
        user_id=member.user_id,
        display_name=target.display_name,
        role=member.role,
        status=member.status,
        joined_at=member.created_at,
    ).model_dump(mode="json")
    return ok(request, data, status_code=201)


@router.patch("/courses/{course_id}/members/{member_id}", response_model=None)
async def update_member_role(
    course_id: str,
    member_id: str,
    body: MemberRoleUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    member = await service.get_member_or_404(db, course_id=course_id, member_id=member_id)
    if member.status != "active":
        raise ApiError(status_code=409, code="MEMBER_NOT_ACTIVE", message="成员已不在课程中")
    if member.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="成员信息已被修改，请刷新后重试",
            details={"expected_version": body.version, "actual_version": member.version},
        )
    old_role = member.role
    member.role = body.role
    member.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.member_role_changed",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course_id,
        detail={"old_role": old_role, "new_role": body.role},
    )
    await db.commit()
    return ok(
        request,
        {
            "id": member.id,
            "user_id": member.user_id,
            "role": member.role,
            "version": member.version,
        },
    )


@router.delete("/courses/{course_id}/members/{member_id}", response_model=None)
async def remove_member(
    course_id: str,
    member_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    member = await service.get_member_or_404(db, course_id=course_id, member_id=member_id)
    if member.status == "removed":
        raise ApiError(status_code=409, code="MEMBER_NOT_ACTIVE", message="成员已移除")
    member.status = "removed"
    member.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.member_removed",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course_id,
        detail={"target_user_id": member.user_id},
    )
    await db.commit()
    return ok(request, {"id": member.id, "status": member.status})


@router.get("/courses/{course_id}/members", response_model=None)
async def list_members(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant", "student"})
    result = await db.execute(
        select(CourseMember, User.display_name)
        .join(User, User.id == CourseMember.user_id)
        .where(CourseMember.course_id == course_id, CourseMember.status == "active")
        .order_by(CourseMember.created_at.asc())
    )
    items = [
        MemberOut(
            id=member.id,
            user_id=member.user_id,
            display_name=display_name,
            role=member.role,
            status=member.status,
            joined_at=member.created_at,
        ).model_dump(mode="json")
        for member, display_name in result.all()
    ]
    return ok(request, items, has_more=False)
