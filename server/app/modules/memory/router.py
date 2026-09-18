from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    Attempt,
    AuditLog,
    LearningEvidence,
    MasteryState,
    MemoryItem,
    ModelCallLog,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.memory import service as memory_service

router = APIRouter()


@router.get("/me/memory", response_model=None)
async def get_memory_summary(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    summary = await memory_service.memory_summary(db, user_id=user.id)
    await db.commit()
    return ok(request, summary)


@router.get("/me/memory/items", response_model=None)
async def get_memory_items(
    request: Request,
    layer: str | None = Query(default=None, pattern="^(L1|L2|L3)$"),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    items = await memory_service.memory_items_detail(
        db, user_id=user.id, layer=layer, limit=limit
    )
    await db.commit()
    return ok(request, items, has_more=False)


@router.get("/me/mastery", response_model=None)
async def get_my_mastery(
    request: Request,
    course_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    states = (
        await db.execute(
            select(MasteryState)
            .where(
                MasteryState.user_id == user.id,
                MasteryState.course_id == course_id,
            )
            .order_by(MasteryState.correct_ratio.asc())
        )
    ).scalars()
    items = [
        {
            "knowledge_point": s.knowledge_point,
            "state": s.state,
            "evidence_count": s.evidence_count,
            "correct_ratio": s.correct_ratio,
            "weight_score": s.weight_score,
            "updated_at": s.updated_at.isoformat(),
        }
        for s in states
    ]
    return ok(request, items, has_more=False)


@router.post("/me/privacy/delete-request", response_model=None)
async def request_data_deletion(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """隐私删除请求：停用账号、撤销会话、记忆全部标记过时（可审计不物理删除）。"""
    user.status = "disabled"
    user.display_name = f"已注销用户-{user.id[-6:]}"
    user.version += 1
    memories = (
        await db.execute(select(MemoryItem).where(MemoryItem.user_id == user.id))
    ).scalars()
    for item in memories:
        item.stale = True
    await db.commit()
    return ok(
        request,
        {"status": "scheduled", "note": "账号已停用，学习记忆已隐藏，删除流程按学校制度执行"},
    )


@router.get("/admin/health", response_model=None)
async def admin_health(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not user.is_platform_admin:
        raise ApiError(status_code=403, code="FORBIDDEN", message="仅管理员可访问")
    counts = {}
    for name, model in (
        ("users", User),
        ("learning_evidences", LearningEvidence),
        ("mastery_states", MasteryState),
        ("memory_items", MemoryItem),
        ("model_call_logs", ModelCallLog),
    ):
        counts[name] = (
            await db.execute(select(func.count(model.id)))
        ).scalar_one()
    recent_calls = (
        await db.execute(
            select(
                ModelCallLog.purpose,
                ModelCallLog.status,
                func.count(ModelCallLog.id),
            )
            .group_by(ModelCallLog.purpose, ModelCallLog.status)
        )
    ).all()
    in_progress_attempts = (
        await db.execute(
            select(func.count(Attempt.id)).where(Attempt.status == "in_progress")
        )
    ).scalar_one()
    return ok(
        request,
        {
            "database": "ok",
            "counts": counts,
            "model_calls": [
                {"purpose": p, "status": s, "count": c} for p, s, c in recent_calls
            ],
            "attempts_in_progress": in_progress_attempts,
            "server_time": datetime.now(UTC).isoformat(),
        },
    )


@router.get("/admin/audit-logs", response_model=None)
async def query_audit_logs(
    request: Request,
    course_id: str | None = Query(default=None, max_length=26),
    action: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not user.is_platform_admin:
        raise ApiError(status_code=403, code="FORBIDDEN", message="仅管理员可访问")
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if course_id:
        query = query.where(AuditLog.course_id == course_id)
    if action:
        query = query.where(AuditLog.action == action)
    rows = (await db.execute(query)).scalars()
    return ok(
        request,
        [
            {
                "id": log.id,
                "actor_id": log.actor_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "course_id": log.course_id,
                "created_at": log.created_at.isoformat(),
            }
            for log in rows
        ],
        has_more=False,
    )
