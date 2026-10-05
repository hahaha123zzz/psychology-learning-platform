import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.db.models import CourseMember, RoleAssignment, User
from app.db.session import get_db_session

ACCESS_COOKIE = "pl_access"
REFRESH_COOKIE = "pl_refresh"


async def get_optional_user(
    request: Request, db: AsyncSession = Depends(get_db_session)
) -> User | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    result = await db.execute(select(User).where(User.id == payload["sub"]).limit(1))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        return None
    return user


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db_session)
) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="请先登录")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="登录状态已失效") from None
    result = await db.execute(select(User).where(User.id == payload["sub"]).limit(1))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="登录状态已失效")
    return user


def platform_roles(user: User) -> list[str]:
    roles = ["student"]
    if user.is_teacher:
        roles.append("teacher")
    if user.is_platform_admin:
        roles.append("admin")
    return roles


async def require_course_role(
    course_id: str,
    user: User,
    db: AsyncSession,
    *,
    roles: set[str],
) -> str:
    """校验用户在指定课程中的角色；无权时返回404以避免资源枚举。"""
    result = await db.execute(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == user.id,
            CourseMember.status == "active",
            CourseMember.role.in_(roles),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is not None:
        return membership.role
    scoped = await db.execute(
        select(RoleAssignment.role).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.role.in_(roles),
            RoleAssignment.scope_type == "course",
            RoleAssignment.scope_id == course_id,
            RoleAssignment.status == "active",
        ).limit(1)
    )
    role = scoped.scalar_one_or_none()
    if role is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    return role


async def has_course_scope(user: User, course_id: str, db: AsyncSession) -> bool:
    """课程列表/详情使用的只读 Scope 检查；平台管理员不自动穿透课程边界。"""
    membership = await db.scalar(
        select(CourseMember.id).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == user.id,
            CourseMember.status == "active",
        ).limit(1)
    )
    if membership is not None:
        return True
    assignment = await db.scalar(
        select(RoleAssignment.id).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.scope_type == "course",
            RoleAssignment.scope_id == course_id,
            RoleAssignment.status == "active",
        ).limit(1)
    )
    return assignment is not None
