from datetime import UTC, datetime, timedelta

import redis.asyncio as redis
from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.db.models import AuthSession, CourseMember, RoleAssignment, User

ACCESS_COOKIE = "pl_access"
REFRESH_COOKIE = "pl_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


async def create_session(
    db: AsyncSession, user: User, *, ip: str | None, user_agent: str | None
) -> tuple[str, str, datetime]:
    """创建认证会话，返回 (access_token, refresh_token, 过期时间)。"""
    settings = get_settings()
    refresh_token = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=expires_at,
        last_ip=ip,
        user_agent=(user_agent or "")[:255],
    )
    db.add(session)
    await db.flush()
    access_token = create_access_token(user.id, session.id)
    return access_token, refresh_token, expires_at


def _serialize_cookie(
    name: str, value: str, *, max_age: int, path: str = "/"
) -> str:
    settings = get_settings()
    parts = [
        f"{name}={value}",
        f"Path={path}",
        f"Max-Age={max_age}",
        "HttpOnly",
        "SameSite=lax",
    ]
    if settings.app_env == "production":
        parts.append("Secure")
    return "; ".join(parts)


def build_login_cookies(access_token: str, refresh_token: str) -> list[str]:
    settings = get_settings()
    return [
        _serialize_cookie(
            ACCESS_COOKIE,
            access_token,
            max_age=settings.access_token_minutes * 60,
        ),
        _serialize_cookie(
            REFRESH_COOKIE,
            refresh_token,
            max_age=settings.refresh_token_days * 86400,
            path=REFRESH_COOKIE_PATH,
        ),
    ]


def build_logout_cookies() -> list[str]:
    return [
        _serialize_cookie(ACCESS_COOKIE, "", max_age=0),
        _serialize_cookie(REFRESH_COOKIE, "", max_age=0, path=REFRESH_COOKIE_PATH),
    ]


async def revoke_session_by_token(db: AsyncSession, refresh_token: str) -> bool:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        update(AuthSession)
        .where(
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return bool(result.rowcount)


async def rotate_session(
    db: AsyncSession, session: AuthSession
) -> tuple[str, str, datetime]:
    settings = get_settings()
    refresh_token = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    session.refresh_token_hash = hash_refresh_token(refresh_token)
    session.expires_at = expires_at
    await db.flush()
    access_token = create_access_token(session.user_id, session.id)
    return access_token, refresh_token, expires_at


async def find_active_session(db: AsyncSession, refresh_token: str) -> AuthSession | None:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        select(AuthSession)
        .where(
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(
        settings.redis_url, socket_connect_timeout=1, socket_timeout=1
    )


def invalid_credentials() -> ApiError:
    return ApiError(
        status_code=401,
        code="INVALID_CREDENTIALS",
        message="邮箱或密码不正确",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_user_password(user: User, password: str) -> bool:
    from app.core.security import verify_password

    return verify_password(password, user.password_hash)


def build_login_response(
    request: Request,
    user: User,
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
) -> Response:
    from app.core.response import ok
    from app.modules.auth.schemas import LoginResponse, UserInfo

    payload = LoginResponse(
        user=UserInfo(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
        ),
        platform_roles=platform_roles(user),
        session_expires_at=expires_at,
    )
    response = ok(request, payload.model_dump(mode="json"))
    for cookie in build_login_cookies(access_token, refresh_token):
        response.headers.append("Set-Cookie", cookie)
    return response


def platform_roles(user: User) -> list[str]:
    roles = ["student"]
    if user.is_teacher:
        roles.append("teacher")
    if user.is_platform_admin:
        roles.append("admin")
    return roles


async def effective_platform_roles(db: AsyncSession, user: User) -> list[str]:
    """返回用户当前有效的平台角色；课程级授权不提升为平台工作区角色。"""
    roles = platform_roles(user)
    result = await db.execute(
        select(RoleAssignment.role).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.scope_type == "platform",
            RoleAssignment.scope_id.is_(None),
            RoleAssignment.status == "active",
            RoleAssignment.role.in_({"assistant", "course_designer", "course_publisher"}),
        )
    )
    for role in result.scalars():
        if role not in roles:
            roles.append(role)
    return roles


async def effective_capabilities(db: AsyncSession, user: User) -> dict[str, bool]:
    """把角色映射为不越过课程 Scope 的导航与动作能力。"""
    memberships = list(
        (
            await db.execute(
                select(CourseMember.role).where(
                    CourseMember.user_id == user.id,
                    CourseMember.status == "active",
                )
            )
        ).scalars()
    )
    scoped_roles = list(
        (
            await db.execute(
                select(RoleAssignment.role).where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.status == "active",
                )
            )
        ).scalars()
    )
    available = set(memberships) | set(scoped_roles) | set(await effective_platform_roles(db, user))
    return {
        "student_learning": "student" in available,
        "teacher_teaching": bool({"teacher", "assistant"} & available),
        "course_design": "course_designer" in available,
        "course_publish": "course_publisher" in available or "teacher" in available,
        "admin_audit": user.is_platform_admin,
    }
