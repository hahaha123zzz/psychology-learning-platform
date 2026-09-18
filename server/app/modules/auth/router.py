from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import CourseMember, User
from app.db.session import get_db_session
from app.modules.auth import service
from app.modules.auth.dependencies import REFRESH_COOKIE, get_current_user
from app.modules.auth.rate_limit import LoginRateLimiter
from app.modules.auth.schemas import (
    LoginRequest,
    MeCourseMembership,
    MeResponse,
    RefreshResponse,
)
from app.modules.auth.service import invalid_credentials

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _set_cookies(response: Response, cookies: list[str]) -> None:
    for cookie in cookies:
        response.headers.append("Set-Cookie", cookie)


@router.post("/auth/login", response_model=None)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    ip = _client_ip(request)
    redis_client = service.get_redis_client()
    try:
        limiter = LoginRateLimiter(redis_client)
        if await limiter.is_blocked(body.email, ip):
            raise ApiError(
                status_code=429,
                code="LOGIN_RATE_LIMITED",
                message="登录失败次数过多，请稍后再试",
                retryable=True,
            )
        result = await db.execute(
            select(User).where(User.email == body.email.lower()).limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None or not service.verify_user_password(user, body.password):
            await limiter.record_failure(body.email, ip)
            raise invalid_credentials()
        if user.status != "active":
            raise ApiError(
                status_code=403,
                code="ACCOUNT_DISABLED",
                message="账号已被停用，请联系管理员",
            )
        await limiter.clear(body.email, ip)
        access_token, refresh_token, expires_at = await service.create_session(
            db,
            user,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        return service.build_login_response(
            request,
            user,
            access_token,
            refresh_token,
            expires_at,
        )
    finally:
        await redis_client.aclose()


@router.post("/auth/refresh", response_model=None)
async def refresh(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="登录状态已失效")
    session = await service.find_active_session(db, refresh_token)
    if session is None:
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="登录状态已失效")
    user_result = await db.execute(
        select(User).where(User.id == session.user_id).limit(1)
    )
    user = user_result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise ApiError(status_code=401, code="UNAUTHENTICATED", message="登录状态已失效")
    access_token, new_refresh_token, expires_at = await service.rotate_session(db, session)
    await db.commit()
    response = ok(
        request,
        RefreshResponse(session_expires_at=expires_at).model_dump(mode="json"),
    )
    _set_cookies(response, service.build_login_cookies(access_token, new_refresh_token))
    return response


@router.post("/auth/logout", response_model=None)
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        await service.revoke_session_by_token(db, refresh_token)
        await db.commit()
    response = ok(request, {"logged_out": True})
    _set_cookies(response, service.build_logout_cookies())
    return response


@router.get("/me", response_model=None)
async def me(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    memberships_result = await db.execute(
        select(CourseMember).where(
            CourseMember.user_id == user.id, CourseMember.status == "active"
        )
    )
    memberships = [
        MeCourseMembership(course_id=m.course_id, role=m.role, status=m.status)
        for m in memberships_result.scalars()
    ]
    payload = MeResponse(
        id=user.id,
        display_name=user.display_name,
        platform_roles=service.platform_roles(user),
        course_memberships=memberships,
    )
    return ok(request, payload.model_dump(mode="json"))
