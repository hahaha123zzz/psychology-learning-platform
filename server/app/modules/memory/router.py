import base64
import hashlib
import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.response import ok
from app.core.security import hash_password
from app.core.task_dispatcher import dispatch_embed_job, dispatch_parse_job
from app.db.models import (
    Assessment,
    Attempt,
    AuditLog,
    AuthSession,
    Course,
    IdempotencyRecord,
    Job,
    LearningEvidence,
    MasteryState,
    Material,
    MaterialVersion,
    MemoryItem,
    ModelCallLog,
    PrivacyDeletionRequest,
    ReviewTask,
    RoleAssignment,
    User,
)
from app.db.session import get_db_session
from app.modules.auth import schemas as auth_schemas
from app.modules.auth.dependencies import get_current_user, has_course_scope, require_course_role
from app.modules.courses import service as course_service
from app.modules.memory import service as memory_service

router = APIRouter()


class PrivacyDeletionReceipt(BaseModel):
    request_id: str
    status: Literal["queued", "running", "failed", "completed_with_retention"]
    processed_counts: dict[str, int]
    retained_categories: list[str]
    note: str
    attempt_count: int
    retryable: bool
    last_error_code: str | None
    status_credential: str = Field(
        description="调用方预先生成的高熵状态凭证；仅保存哈希，不可恢复账号登录"
    )
    status_credential_expires_at: datetime = Field(description="查询凭证到期时间；当前为 30 天")


class PrivacyDeletionRequestBody(BaseModel):
    request_id: str = Field(pattern=r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
    status_credential: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class PrivacyDeletionStatusQuery(BaseModel):
    request_id: str = Field(min_length=26, max_length=26)
    status_credential: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class PrivacyDeletionStatusReceipt(BaseModel):
    request_id: str
    status: Literal["queued", "running", "failed", "completed_with_retention"]
    processed_counts: dict[str, int]
    retained_categories: list[str]
    requested_at: datetime
    completed_at: datetime | None
    attempt_count: int
    retryable: bool
    last_error_code: str | None


class PrivacyDeletionResponseMeta(BaseModel):
    request_id: str | None
    server_time: str


class PrivacyDeletionResponse(BaseModel):
    data: PrivacyDeletionReceipt
    meta: PrivacyDeletionResponseMeta


class PrivacyDeletionStatusResponse(BaseModel):
    data: PrivacyDeletionStatusReceipt
    meta: PrivacyDeletionResponseMeta


ROLE_ASSIGNMENT_GRANT_ENDPOINT = "POST:/api/v1/admin/role-assignments"
ROLE_ASSIGNMENT_REVOKE_ENDPOINT = "POST:/api/v1/admin/role-assignments/{id}/revoke"
ADMIN_JOB_RETRY_ENDPOINT = "POST:/api/v1/admin/jobs/{id}/retry"
ADMIN_RECOVERABLE_JOB_KINDS = ("material_parse", "material_embed")
ADMIN_JOB_MAX_ATTEMPTS = 5


def _encode_admin_cursor(created_at: datetime, row_id: str) -> str:
    timestamp = created_at.astimezone(UTC).isoformat()
    payload = f"{timestamp}|{row_id}".encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_admin_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8")
        timestamp_text, row_id = raw.split("|", maxsplit=1)
        timestamp = datetime.fromisoformat(timestamp_text)
        if timestamp.tzinfo is None or len(row_id) != 26:
            raise ValueError("invalid cursor fields")
        return timestamp.astimezone(UTC), row_id
    except (ValueError, UnicodeDecodeError):
        raise ApiError(
            status_code=400,
            code="INVALID_CURSOR",
            message="列表游标无效，请从第一页重新加载",
        ) from None


def _cursor_predicate(model, cursor: tuple[datetime, str]):
    created_at, row_id = cursor
    return or_(
        model.created_at < created_at,
        and_(model.created_at == created_at, model.id < row_id),
    )


async def _memory_course_scopes(db: AsyncSession, *, user_id: str) -> list[str | None]:
    """用户级记忆端点要聚合该用户各课程与全局 Scope。"""
    scopes = set(
        (
            await db.execute(
                select(MemoryItem.course_id).where(MemoryItem.user_id == user_id).distinct()
            )
        ).scalars()
    )
    scopes.add(None)
    return sorted(scopes, key=lambda value: (value is not None, value or ""))


class EvidenceInvalidationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _require_admin(user: User) -> None:
    if not user.is_platform_admin:
        raise ApiError(status_code=403, code="FORBIDDEN", message="仅管理员可访问")


@router.get("/me/memory", response_model=None)
async def get_memory_summary(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    summary_counts: dict[str, int] = defaultdict(int)
    stale_hidden = 0
    for course_id in await _memory_course_scopes(db, user_id=user.id):
        scope_summary = await memory_service.memory_summary(
            db, user_id=user.id, course_id=course_id
        )
        for key, count in scope_summary["summary"].items():
            summary_counts[key] += count
        stale_hidden += scope_summary["stale_hidden"]
    summary = {
        "summary": dict(sorted(summary_counts.items())),
        "stale_hidden": stale_hidden,
    }
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
    items_by_id: dict[str, dict] = {}
    for course_id in await _memory_course_scopes(db, user_id=user.id):
        scoped_items = await memory_service.memory_items_detail(
            db,
            user_id=user.id,
            layer=layer,
            limit=limit,
            course_id=course_id,
        )
        items_by_id.update({item["id"]: item for item in scoped_items})
    items = sorted(
        items_by_id.values(),
        key=lambda item: (item["confidence"], item["updated_at"], item["id"]),
        reverse=True,
    )[:limit]
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
            "context_count": s.context_count,
            "independent_evidence_count": s.independent_evidence_count,
            "algorithm_version": s.algorithm_version,
            "state_reason": s.state_reason,
            "updated_at": s.updated_at.isoformat(),
        }
        for s in states
    ]
    return ok(request, items, has_more=False)


@router.post(
    "/courses/{course_id}/learning-evidence/{evidence_id}/invalidate",
    response_model=None,
)
async def invalidate_learning_evidence(
    course_id: str,
    evidence_id: str,
    body: EvidenceInvalidationRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    evidence = await db.scalar(
        select(LearningEvidence).where(
            LearningEvidence.id == evidence_id,
            LearningEvidence.course_id == course_id,
        )
    )
    if evidence is None:
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="学习证据不存在")
    if evidence.quality_status == "invalidated":
        return ok(
            request,
            {
                "evidence_id": evidence.id,
                "quality_status": evidence.quality_status,
                "mastery_recomputed": True,
            },
            idempotent_replay=True,
        )
    evidence.quality_status = "invalidated"
    evidence.invalidated_reason = body.reason
    await memory_service.recompute_mastery(db, user_id=evidence.user_id, course_id=course_id)
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="learning_evidence.invalidated",
        resource_type="learning_evidence",
        resource_id=evidence.id,
        course_id=course_id,
        detail={"student_id": evidence.user_id, "reason": body.reason},
    )
    await db.commit()
    return ok(
        request,
        {
            "evidence_id": evidence.id,
            "quality_status": evidence.quality_status,
            "mastery_recomputed": True,
        },
    )


def _growth_next_step(state: str, review_count: int) -> str:
    if review_count > 0:
        return "完成一次独立提取并检查反馈"
    if state in ("needs_consolidation", "learning"):
        return "继续一次不同情境的练习"
    if state == "mastered":
        return "安排延迟复习以验证保持"
    return "先完成一项有依据的学习活动"


async def _latest_valid_growth_evidence_metadata(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    states: list[MasteryState],
) -> dict[str, dict[str, object]]:
    """读取这些掌握点的最新有效证据 metadata，不读取答题正文或正确性。"""
    knowledge_points = {state.knowledge_point for state in states if state.last_evidence_id}
    if not knowledge_points:
        return {}
    rows = (
        await db.execute(
            select(
                LearningEvidence.id,
                LearningEvidence.knowledge_point,
                LearningEvidence.source_type,
                LearningEvidence.created_at,
                LearningEvidence.dimension,
                LearningEvidence.independence_status,
            )
            .where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.quality_status == "valid",
                LearningEvidence.knowledge_point.in_(knowledge_points),
            )
            .order_by(
                LearningEvidence.knowledge_point.asc(),
                LearningEvidence.created_at.desc(),
                LearningEvidence.id.desc(),
            )
        )
    ).all()
    latest: dict[str, dict[str, object]] = {}
    for row in rows:
        if row.knowledge_point in latest:
            continue
        latest[row.knowledge_point] = {
            "evidence_id": row.id,
            "source_type": row.source_type,
            "created_at": row.created_at.isoformat(),
            "dimension": row.dimension,
            "independence_status": row.independence_status,
        }
    return latest


def _growth_last_evidence(
    state: MasteryState, latest_by_knowledge_point: dict[str, dict[str, object]]
) -> dict[str, object] | None:
    latest = latest_by_knowledge_point.get(state.knowledge_point)
    if latest is None or latest["evidence_id"] != state.last_evidence_id:
        return None
    return latest


async def _growth_hint_support_summary(
    db: AsyncSession, *, user_id: str, course_id: str
) -> dict[str, int]:
    """按有效作答 attempt 去重汇总提示支持程度，不返回作答内容或比例。"""
    supported_attempt = func.max(
        case(
            (
                or_(
                    LearningEvidence.independence_status == "supported",
                    LearningEvidence.hints_used > 0,
                ),
                1,
            ),
            else_=0,
        )
    )
    all_independent_without_hints = func.min(
        case(
            (
                and_(
                    LearningEvidence.independence_status == "independent",
                    LearningEvidence.hints_used == 0,
                ),
                1,
            ),
            else_=0,
        )
    )
    rows = (
        await db.execute(
            select(
                supported_attempt.label("supported_attempt"),
                all_independent_without_hints.label("independent_attempt"),
            )
            .where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.quality_status == "valid",
                LearningEvidence.attempt_id.is_not(None),
            )
            .group_by(LearningEvidence.attempt_id)
        )
    ).all()
    summary = {
        "attempt_count": len(rows),
        "supported_attempt_count": 0,
        "independent_attempt_count": 0,
        "other_attempt_count": 0,
    }
    for row in rows:
        if row.supported_attempt:
            summary["supported_attempt_count"] += 1
        elif row.independent_attempt:
            summary["independent_attempt_count"] += 1
        else:
            summary["other_attempt_count"] += 1
    return summary


@router.get("/student/growth/overview", response_model=None)
async def get_growth_overview(
    request: Request,
    course_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not await has_course_scope(user, course_id, db):
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    states = list(
        (
            await db.execute(
                select(MasteryState)
                .where(MasteryState.user_id == user.id, MasteryState.course_id == course_id)
                .order_by(MasteryState.updated_at.desc(), MasteryState.id.desc())
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    review_count = int(
        (
            await db.execute(
                select(func.count(ReviewTask.id)).where(
                    ReviewTask.user_id == user.id,
                    ReviewTask.course_id == course_id,
                    ReviewTask.status == "pending",
                    ReviewTask.due_at <= now,
                )
            )
        ).scalar_one()
    )
    state_summary: dict[str, int] = {}
    for state in states:
        state_summary[state.state] = state_summary.get(state.state, 0) + 1
    focus = next(
        (state for state in states if state.state in ("needs_consolidation", "learning")),
        states[0] if states else None,
    )
    evidence_states = states[:20]
    if focus is not None and all(item.id != focus.id for item in evidence_states):
        evidence_states.append(focus)
    latest_evidence_by_knowledge_point = await _latest_valid_growth_evidence_metadata(
        db, user_id=user.id, course_id=course_id, states=evidence_states
    )
    return ok(
        request,
        {
            "course_id": course_id,
            "freshness": {"status": "fresh", "generated_at": now.isoformat()},
            "focus": (
                {
                    "knowledge_point": focus.knowledge_point,
                    "state": focus.state,
                    "state_reason": focus.state_reason,
                    "next_step": _growth_next_step(focus.state, review_count),
                    "last_evidence": _growth_last_evidence(
                        focus, latest_evidence_by_knowledge_point
                    ),
                }
                if focus
                else None
            ),
            "state_summary": state_summary,
            "attention": {
                "due_review_count": review_count,
                "message": "有到期复习任务" if review_count else None,
            },
            "explainability_refs": [
                {
                    "knowledge_point": state.knowledge_point,
                    "state": state.state,
                    "evidence_count": state.evidence_count,
                    "state_reason": state.state_reason,
                    "algorithm_version": state.algorithm_version,
                    "updated_at": state.updated_at.isoformat(),
                    "last_evidence": _growth_last_evidence(
                        state, latest_evidence_by_knowledge_point
                    ),
                }
                for state in states[:20]
            ],
        },
    )


@router.get("/student/growth/knowledge", response_model=None)
async def list_growth_knowledge(
    request: Request,
    course_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not await has_course_scope(user, course_id, db):
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    states = (
        await db.execute(
            select(MasteryState)
            .where(MasteryState.user_id == user.id, MasteryState.course_id == course_id)
            .order_by(MasteryState.knowledge_point.asc())
        )
    ).scalars()
    return ok(
        request,
        [
            {
                "knowledge_point": state.knowledge_point,
                "state": state.state,
                "evidence_count": state.evidence_count,
                "state_reason": state.state_reason,
                "algorithm_version": state.algorithm_version,
                "next_step": _growth_next_step(state.state, 0),
                "updated_at": state.updated_at.isoformat(),
            }
            for state in states
        ],
        has_more=False,
    )


@router.get("/student/growth/tabs", response_model=None)
async def get_growth_tabs(
    request: Request,
    course_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """返回成长四视图的可解释投影，不暴露原始正确率。"""
    if not await has_course_scope(user, course_id, db):
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    states = list(
        (
            await db.execute(
                select(MasteryState)
                .where(MasteryState.user_id == user.id, MasteryState.course_id == course_id)
                .order_by(MasteryState.updated_at.desc(), MasteryState.id.desc())
            )
        ).scalars()
    )
    latest_evidence_by_knowledge_point = await _latest_valid_growth_evidence_metadata(
        db, user_id=user.id, course_id=course_id, states=states
    )
    hint_support_summary = await _growth_hint_support_summary(
        db, user_id=user.id, course_id=course_id
    )
    memories = list(
        (
            await db.execute(
                select(MemoryItem)
                .where(
                    *memory_service.effective_memory_conditions(
                        user_id=user.id,
                        course_id=course_id,
                        now=datetime.now(UTC),
                    ),
                    MemoryItem.kind.in_(("weakness", "strength")),
                )
                .order_by(MemoryItem.updated_at.desc(), MemoryItem.id.desc())
                .limit(100)
            )
        ).scalars()
    )
    evidences = list(
        (
            await db.execute(
                select(LearningEvidence)
                .where(
                    LearningEvidence.user_id == user.id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.quality_status == "valid",
                )
                .order_by(LearningEvidence.created_at.asc(), LearningEvidence.id.asc())
                .limit(500)
            )
        ).scalars()
    )
    trajectory: dict[str, dict[str, object]] = defaultdict(
        lambda: {"evidence_count": 0, "knowledge_points": set()}
    )
    for evidence in evidences:
        day = evidence.created_at.date().isoformat()
        item = trajectory[day]
        item["evidence_count"] = int(item["evidence_count"]) + 1
        points = item["knowledge_points"]
        assert isinstance(points, set)
        points.add(evidence.knowledge_point)
    return ok(
        request,
        {
            "course_id": course_id,
            "freshness": {"status": "fresh", "generated_at": datetime.now(UTC).isoformat()},
            "hint_support_summary": hint_support_summary,
            "knowledge": [
                {
                    "knowledge_point": state.knowledge_point,
                    "state": state.state,
                    "evidence_count": state.evidence_count,
                    "state_reason": state.state_reason,
                    "algorithm_version": state.algorithm_version,
                    "next_step": _growth_next_step(state.state, 0),
                    "updated_at": state.updated_at.isoformat(),
                    "last_evidence": _growth_last_evidence(
                        state, latest_evidence_by_knowledge_point
                    ),
                }
                for state in states
            ],
            # 知识点掌握证据不能被重命名为领域技能证据；在独立
            # DomainSkillState 来源接入前，明确返回空集合。
            "skills": [],
            "misconceptions": [
                {
                    "knowledge_point": item.content.removeprefix("对“").split("”", 1)[0]
                    if "”" in item.content
                    else item.kind,
                    "status": "待验证",
                    "explanation": item.content,
                    "confidence": item.confidence,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in memories
                if item.kind == "weakness"
            ],
            "trajectory": [
                {
                    "date": day,
                    "evidence_count": int(item["evidence_count"]),
                    "knowledge_points": sorted(item["knowledge_points"]),
                }
                for day, item in sorted(trajectory.items())
            ],
        },
    )


def _privacy_deletion_status(deletion: PrivacyDeletionRequest) -> dict[str, object]:
    return {
        "request_id": deletion.id,
        "status": deletion.status,
        "processed_counts": deletion.processed_counts,
        "retained_categories": deletion.retained_categories,
        "requested_at": deletion.requested_at.isoformat(),
        "completed_at": deletion.completed_at.isoformat() if deletion.completed_at else None,
        "attempt_count": deletion.attempt_count,
        "retryable": deletion.retryable,
        "last_error_code": deletion.last_error_code,
    }


def _privacy_deletion_note(status: str) -> str:
    if status == "completed_with_retention":
        return (
            "账号已停用并去标识化；个人学习上下文已清除。正式测评作答/成绩、"
            "审计及课程资产历史依保留边界保留，不能视为全部数据删除完成。"
        )
    if status == "failed":
        return "账号已停用并去标识化；删除工作单未完成，可使用回执编号和查询凭证重试。"
    return "账号已停用并去标识化；个人学习数据删除任务尚未完成，请稍后核验状态。"


def _privacy_deletion_response_data(
    deletion: PrivacyDeletionRequest, status_credential: str
) -> dict[str, object]:
    return {
        **_privacy_deletion_status(deletion),
        "status_credential": status_credential,
        "status_credential_expires_at": deletion.status_credential_expires_at.isoformat()
        if deletion.status_credential_expires_at
        else None,
        "note": _privacy_deletion_note(deletion.status),
    }


async def _mark_deletion_dispatch_failed(db: AsyncSession, request_id: str) -> None:
    await db.execute(
        update(PrivacyDeletionRequest)
        .where(
            PrivacyDeletionRequest.id == request_id,
            PrivacyDeletionRequest.status == "queued",
        )
        .values(status="failed", retryable=True, last_error_code="dispatch_failed")
    )
    await db.commit()


@router.post(
    "/me/privacy/delete-request",
    response_model=PrivacyDeletionResponse,
    responses={202: {"model": PrivacyDeletionResponse}},
)
async def request_data_deletion(
    request: Request,
    body: PrivacyDeletionRequestBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """停用账号并建立可由调用方凭证恢复的持久删除工作单。"""
    from app.modules.auth import service as auth_service
    from app.modules.memory.deletion import RETAINED_CATEGORIES
    from app.modules.memory.tasks import dispatch_privacy_deletion

    credential_hash = hashlib.sha256(body.status_credential.encode("ascii")).hexdigest()
    existing = await db.get(PrivacyDeletionRequest, body.request_id)
    if existing is not None:
        if not secrets.compare_digest(existing.status_credential_hash or "", credential_hash):
            raise ApiError(
                status_code=404,
                code="PRIVACY_DELETION_STATUS_NOT_FOUND",
                message="删除状态凭证无效或已过期",
            )
        response = ok(
            request,
            _privacy_deletion_response_data(existing, body.status_credential),
            status_code=202 if existing.status != "completed_with_retention" else 200,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
        for cookie in auth_service.build_logout_cookies():
            response.headers.append("Set-Cookie", cookie)
        return response

    # Redis 中邮箱散列限流键不参与事务，故清理成功后才提交账号停用与工作单。
    rate_limiter = auth_service.get_redis_client()
    old_email_hash = hashlib.sha256(user.email.strip().lower().encode("utf-8")).hexdigest()[:24]
    try:
        rate_limit_keys = [
            key async for key in rate_limiter.scan_iter(match=f"login_fail:{old_email_hash}:*")
        ]
        if rate_limit_keys:
            await rate_limiter.delete(*rate_limit_keys)
    except Exception as exc:
        await db.rollback()
        raise ApiError(
            status_code=503,
            code="PRIVACY_DELETE_RETRYABLE",
            message="暂时无法清理登录安全缓存，删除请求未受理，请稍后重试",
            retryable=True,
        ) from exc
    finally:
        await rate_limiter.aclose()

    auth_sessions = await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    user.status = "disabled"
    user.email = f"deleted-{user.id}@invalid.invalid"
    user.display_name = "已注销账号"
    user.password_hash = hash_password(secrets.token_urlsafe(48))
    user.version += 1

    now = datetime.now(UTC)
    status_credential_expires_at = now + timedelta(days=30)
    deletion = PrivacyDeletionRequest(
        id=body.request_id,
        subject_user_id=user.id,
        status="queued",
        processed_counts={
            "auth_sessions": max(auth_sessions.rowcount or 0, 0),
            "login_rate_limit_keys": len(rate_limit_keys),
        },
        retained_categories=RETAINED_CATEGORIES,
        requested_at=now,
        attempt_count=0,
        retryable=True,
        last_error_code=None,
        status_credential_hash=credential_hash,
        status_credential_expires_at=status_credential_expires_at,
        completed_at=None,
    )
    db.add(deletion)
    db.add(
        AuditLog(
            actor_id=user.id,
            action="privacy.deletion.requested",
            resource_type="privacy_deletion_request",
            resource_id=deletion.id,
            detail={"status": "queued"},
        )
    )
    await db.commit()

    try:
        dispatch_privacy_deletion(deletion.id)
    except Exception:  # noqa: BLE001 - don't leak broker details to a deleted user
        await _mark_deletion_dispatch_failed(db, deletion.id)
    await db.refresh(deletion)
    response = ok(
        request,
        _privacy_deletion_response_data(deletion, body.status_credential),
        status_code=202 if deletion.status != "completed_with_retention" else 200,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    for cookie in auth_service.build_logout_cookies():
        response.headers.append("Set-Cookie", cookie)
    return response


@router.post(
    "/privacy/deletion-status",
    response_model=PrivacyDeletionStatusResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["request_id", "status_credential"],
                        "properties": {
                            "request_id": {
                                "type": "string",
                                "minLength": 26,
                                "maxLength": 26,
                            },
                            "status_credential": {
                                "type": "string",
                                "pattern": "^[A-Za-z0-9_-]{43}$",
                                "description": (
                                    "调用方预生成的 30 天有效随机凭证；服务端仅保存其哈希"
                                ),
                            },
                        },
                    }
                }
            },
        }
    },
)
async def query_privacy_deletion_status(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """允许已注销用户凭短期随机凭证核验删除回执，不恢复任何账户访问权。"""
    try:
        body = PrivacyDeletionStatusQuery.model_validate(await request.json())
    except (TypeError, ValueError) as exc:
        # Pydantic 的原始校验详情可能包含 input；凭证属于 Bearer secret，不能回显。
        raise ApiError(
            status_code=404,
            code="PRIVACY_DELETION_STATUS_NOT_FOUND",
            message="删除状态凭证无效或已过期",
        ) from exc
    credential_hash = hashlib.sha256(body.status_credential.encode("ascii")).hexdigest()
    now = datetime.now(UTC)
    deletion = await db.scalar(
        select(PrivacyDeletionRequest).where(
            PrivacyDeletionRequest.id == body.request_id,
            PrivacyDeletionRequest.status_credential_hash == credential_hash,
            PrivacyDeletionRequest.status_credential_expires_at > now,
        )
    )
    if deletion is None:
        raise ApiError(
            status_code=404,
            code="PRIVACY_DELETION_STATUS_NOT_FOUND",
            message="删除状态凭证无效或已过期",
        )
    response = ok(
        request,
        PrivacyDeletionStatusReceipt(
            **_privacy_deletion_status(deletion),
        ).model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    return response


@router.post(
    "/privacy/deletion-status/retry",
    response_model=PrivacyDeletionStatusResponse,
    responses={202: {"model": PrivacyDeletionStatusResponse}},
)
async def retry_privacy_deletion(
    request: Request,
    body: PrivacyDeletionStatusQuery,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """凭同一状态凭证重派发 queued/failed 工作单；重复派发由 Worker 幂等处理。"""
    from app.modules.memory.tasks import dispatch_privacy_deletion

    credential_hash = hashlib.sha256(body.status_credential.encode("ascii")).hexdigest()
    deletion = await db.scalar(
        select(PrivacyDeletionRequest)
        .where(
            PrivacyDeletionRequest.id == body.request_id,
            PrivacyDeletionRequest.status_credential_hash == credential_hash,
            PrivacyDeletionRequest.status_credential_expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if deletion is None:
        raise ApiError(
            status_code=404,
            code="PRIVACY_DELETION_STATUS_NOT_FOUND",
            message="删除状态凭证无效或已过期",
        )
    if deletion.status == "completed_with_retention":
        return ok(
            request,
            _privacy_deletion_status(deletion),
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
    if deletion.status == "running":
        await db.commit()
        return ok(
            request,
            _privacy_deletion_status(deletion),
            status_code=202,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
    if not deletion.retryable:
        raise ApiError(
            status_code=409,
            code="PRIVACY_DELETION_NOT_RETRYABLE",
            message="当前删除工作单不可重试",
        )
    if deletion.status == "failed":
        deletion.status = "queued"
        deletion.last_error_code = None
    await db.commit()
    try:
        dispatch_privacy_deletion(deletion.id)
    except Exception:  # noqa: BLE001 - keep safe retry state without exposing broker details
        await _mark_deletion_dispatch_failed(db, deletion.id)
    await db.refresh(deletion)
    return ok(
        request,
        _privacy_deletion_status(deletion),
        status_code=202 if deletion.status != "completed_with_retention" else 200,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.get("/admin/health", response_model=None)
async def admin_health(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_admin(user)
    organization_user_ids = select(User.id).where(
        User.organization_id == user.organization_id
    )
    organization_course_ids = select(Course.id).where(
        Course.organization_id == user.organization_id
    )
    counts = {
        "users": (
            await db.execute(
                select(func.count(User.id)).where(User.organization_id == user.organization_id)
            )
        ).scalar_one()
    }
    # Detached model-call logs cannot be attributed to an institution and are excluded.
    for name, model in (
        ("learning_evidences", LearningEvidence),
        ("mastery_states", MasteryState),
        ("memory_items", MemoryItem),
        ("model_call_logs", ModelCallLog),
    ):
        counts[name] = (
            await db.execute(
                select(func.count(model.id)).where(model.user_id.in_(organization_user_ids))
            )
        ).scalar_one()
    recent_calls = (
        await db.execute(
            select(
                ModelCallLog.purpose,
                ModelCallLog.status,
                func.count(ModelCallLog.id),
            )
            .where(ModelCallLog.user_id.in_(organization_user_ids))
            .group_by(ModelCallLog.purpose, ModelCallLog.status)
        )
    ).all()
    in_progress_attempts = (
        await db.execute(
            select(func.count(Attempt.id))
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(
                Attempt.status == "in_progress",
                Assessment.course_id.in_(organization_course_ids),
            )
        )
    ).scalar_one()
    return ok(
        request,
        {
            "database": "ok",
            "counts": counts,
            "model_calls": [{"purpose": p, "status": s, "count": c} for p, s, c in recent_calls],
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
    cursor: str | None = Query(default=None, max_length=256),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not user.is_platform_admin:
        raise ApiError(status_code=403, code="FORBIDDEN", message="仅管理员可访问")
    organization_course_ids = select(Course.id).where(
        Course.organization_id == user.organization_id
    )
    organization_actor_ids = select(User.id).where(
        User.organization_id == user.organization_id
    )
    query = (
        select(AuditLog)
        .where(
            or_(
                AuditLog.course_id.in_(organization_course_ids),
                and_(
                    AuditLog.course_id.is_(None),
                    AuditLog.actor_id.in_(organization_actor_ids),
                ),
            )
        )
    )
    if course_id:
        query = query.where(AuditLog.course_id == course_id)
    if action:
        query = query.where(AuditLog.action == action)
    decoded_cursor = _decode_admin_cursor(cursor)
    if decoded_cursor is not None:
        query = query.where(_cursor_predicate(AuditLog, decoded_cursor))
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
    rows = list((await db.execute(query)).scalars())
    has_more = len(rows) > limit
    page = rows[:limit]
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
            for log in page
        ],
        next_cursor=(
            _encode_admin_cursor(page[-1].created_at, page[-1].id)
            if has_more and page
            else None
        ),
        has_more=has_more,
    )


@router.get("/admin/role-assignment-targets", response_model=None)
async def search_role_assignment_targets(
    request: Request,
    q: str = Query(min_length=3, max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """只返回同机构的必要账号标识，供管理员授权目标选择使用。"""
    _require_admin(user)
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    result = await db.execute(
        select(User)
        .where(
            User.organization_id == user.organization_id,
            User.status == "active",
            (
                User.email.ilike(f"%{escaped}%", escape="\\")
                | User.display_name.ilike(f"%{escaped}%", escape="\\")
            ),
        )
        .order_by(User.display_name.asc(), User.id.asc())
        .limit(30)
    )
    return ok(
        request,
        [
            auth_schemas.RoleAssignmentTargetOut(
                id=target.id,
                email=target.email,
                display_name=target.display_name,
            ).model_dump(mode="json")
            for target in result.scalars()
        ],
        has_more=False,
    )


@router.get("/admin/role-assignment-courses", response_model=None)
async def list_role_assignment_courses(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """只暴露同机构课程的授权 Scope 选择项，不返回课程内容。"""
    _require_admin(user)
    result = await db.execute(
        select(Course)
        .where(
            Course.organization_id == user.organization_id,
            Course.status == "active",
        )
        .order_by(Course.title.asc(), Course.id.asc())
        .limit(200)
    )
    return ok(
        request,
        [
            {"id": course.id, "title": course.title, "term": course.term}
            for course in result.scalars()
        ],
        has_more=False,
    )


@router.get("/admin/role-assignments", response_model=None)
async def list_role_assignments(
    request: Request,
    user_id: str | None = Query(default=None, min_length=26, max_length=26),
    scope_type: str | None = Query(default=None, pattern="^(platform|course|class)$"),
    scope_id: str | None = Query(default=None, min_length=26, max_length=26),
    status: str = Query(default="active", pattern="^(active|revoked|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """只读授权审计列表，不返回课程正文或学生学习数据。"""
    _require_admin(user)
    query = (
        select(RoleAssignment, User.email, User.display_name)
        .join(User, User.id == RoleAssignment.user_id)
        .where(User.organization_id == user.organization_id)
        .order_by(RoleAssignment.created_at.desc(), RoleAssignment.id.desc())
    )
    if user_id:
        query = query.where(RoleAssignment.user_id == user_id)
    if scope_type:
        query = query.where(RoleAssignment.scope_type == scope_type)
    if scope_id:
        query = query.where(RoleAssignment.scope_id == scope_id)
    if status != "all":
        query = query.where(RoleAssignment.status == status)
    decoded_cursor = _decode_admin_cursor(cursor)
    if decoded_cursor is not None:
        query = query.where(_cursor_predicate(RoleAssignment, decoded_cursor))
    rows = list((await db.execute(query.limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return ok(
        request,
        [
            auth_schemas.RoleAssignmentOut(
                id=item.id,
                user_id=item.user_id,
                user_email=email,
                user_display_name=display_name,
                role=item.role,
                scope_type=item.scope_type,
                scope_id=item.scope_id,
                status=item.status,
                version=item.version,
                granted_by=item.granted_by,
                created_at=item.created_at,
                updated_at=item.updated_at,
            ).model_dump(mode="json")
            for item, email, display_name in page
        ],
        next_cursor=(
            _encode_admin_cursor(page[-1][0].created_at, page[-1][0].id)
            if has_more and page
            else None
        ),
        has_more=has_more,
    )


def _role_assignment_data(assignment: RoleAssignment, target: User) -> dict:
    return auth_schemas.RoleAssignmentOut(
        id=assignment.id,
        user_id=target.id,
        user_email=target.email,
        user_display_name=target.display_name,
        role=assignment.role,
        scope_type=assignment.scope_type,
        scope_id=assignment.scope_id,
        status=assignment.status,
        version=assignment.version,
        granted_by=assignment.granted_by,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    ).model_dump(mode="json")


@router.post("/admin/role-assignments", response_model=None)
async def grant_role_assignment(
    body: auth_schemas.RoleAssignmentCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_admin(user)
    if body.scope_type == "class":
        raise ApiError(
            status_code=422,
            code="ROLE_ASSIGNMENT_SCOPE_UNSUPPORTED",
            message="班级授权请通过班级成员或任课教师分配流程办理",
        )
    if body.scope_type == "platform" and body.scope_id is not None:
        raise ApiError(
            status_code=422,
            code="ROLE_ASSIGNMENT_SCOPE_INVALID",
            message="平台授权不能设置 scope_id",
        )
    if body.scope_type == "platform" and body.role not in {
        "assistant",
        "course_designer",
        "course_publisher",
    }:
        raise ApiError(
            status_code=422,
            code="ROLE_ASSIGNMENT_SCOPE_INVALID",
            message="该角色不支持平台级授权",
        )
    if body.scope_type == "course" and body.scope_id is None:
        raise ApiError(
            status_code=422,
            code="ROLE_ASSIGNMENT_SCOPE_INVALID",
            message="课程授权必须设置 scope_id",
        )
    payload = body.model_dump(mode="json")
    request_hash = course_service.canonical_request_hash(payload)
    previous = await course_service.find_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=ROLE_ASSIGNMENT_GRANT_ENDPOINT,
        request_hash=request_hash,
    )
    if previous is not None:
        return ok(
            request,
            previous["body"]["data"],
            status_code=previous["status"],
            idempotent_replay=True,
        )

    target = await db.scalar(
        select(User).where(
            User.id == body.user_id,
            User.organization_id == user.organization_id,
            User.status == "active",
        )
    )
    if target is None:
        raise ApiError(status_code=404, code="USER_NOT_FOUND", message="同机构有效账号不存在")
    if target.id == user.id:
        raise ApiError(
            status_code=409,
            code="ROLE_SELF_ASSIGNMENT_FORBIDDEN",
            message="管理员不能为自己新增授权",
        )
    course_id: str | None = None
    if body.scope_type == "course":
        course_id = body.scope_id
        course = await db.scalar(
            select(Course).where(
                Course.id == body.scope_id,
                Course.organization_id == user.organization_id,
            )
        )
        if course is None:
            raise ApiError(
                status_code=404,
                code="COURSE_NOT_FOUND",
                message="同机构课程不存在",
            )

    assignment = await db.scalar(
        select(RoleAssignment)
        .where(
            RoleAssignment.user_id == target.id,
            RoleAssignment.role == body.role,
            RoleAssignment.scope_type == body.scope_type,
            RoleAssignment.scope_id.is_(None)
            if body.scope_id is None
            else RoleAssignment.scope_id == body.scope_id,
        )
        .with_for_update()
    )
    previous = await course_service.find_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=ROLE_ASSIGNMENT_GRANT_ENDPOINT,
        request_hash=request_hash,
    )
    if previous is not None:
        return ok(
            request,
            previous["body"]["data"],
            status_code=previous["status"],
            idempotent_replay=True,
        )
    if assignment is not None and assignment.status == "active":
        raise ApiError(
            status_code=409,
            code="ROLE_ASSIGNMENT_EXISTS",
            message="该账号已拥有相同 Scope 的有效授权",
        )
    if assignment is None:
        assignment = RoleAssignment(
            user_id=target.id,
            role=body.role,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            status="active",
            granted_by=user.id,
        )
        db.add(assignment)
    else:
        assignment.status = "active"
        assignment.granted_by = user.id
        assignment.version += 1
    await db.flush()
    data = _role_assignment_data(assignment, target)
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="admin.role_assignment.granted",
        resource_type="role_assignment",
        resource_id=assignment.id,
        course_id=course_id,
        detail={
            "user_id": target.id,
            "role": body.role,
            "scope_type": body.scope_type,
            "scope_id": body.scope_id,
            "reason": body.reason,
            "version": assignment.version,
        },
    )
    await course_service.save_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=ROLE_ASSIGNMENT_GRANT_ENDPOINT,
        request_hash=request_hash,
        status=201,
        body={"data": data},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=ROLE_ASSIGNMENT_GRANT_ENDPOINT,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(
                request,
                previous["body"]["data"],
                status_code=previous["status"],
                idempotent_replay=True,
            )
        raise ApiError(
            status_code=409,
            code="ROLE_ASSIGNMENT_CONFLICT",
            message="授权状态已被其他管理员变更，请刷新后重试",
        ) from exc
    return ok(request, data, status_code=201)


@router.post("/admin/role-assignments/{assignment_id}/revoke", response_model=None)
async def revoke_role_assignment(
    assignment_id: str,
    body: auth_schemas.RoleAssignmentRevoke,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_admin(user)
    payload = body.model_dump(mode="json")
    request_hash = course_service.canonical_request_hash(payload)
    previous = await course_service.find_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=ROLE_ASSIGNMENT_REVOKE_ENDPOINT.format(id=assignment_id),
        request_hash=request_hash,
    )
    if previous is not None:
        return ok(request, previous["body"]["data"], idempotent_replay=True)
    row = await db.execute(
        select(RoleAssignment, User)
        .join(User, User.id == RoleAssignment.user_id)
        .where(
            RoleAssignment.id == assignment_id,
            User.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    assignment, target = row.one_or_none() or (None, None)
    if assignment is None or target is None:
        raise ApiError(status_code=404, code="ROLE_ASSIGNMENT_NOT_FOUND", message="授权记录不存在")
    if assignment.version != body.version:
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=ROLE_ASSIGNMENT_REVOKE_ENDPOINT.format(id=assignment_id),
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(request, previous["body"]["data"], idempotent_replay=True)
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="授权记录已变更，请刷新后重试",
            details={"expected_version": body.version, "actual_version": assignment.version},
        )
    was_already_revoked = assignment.status == "revoked"
    if not was_already_revoked:
        assignment.status = "revoked"
        assignment.version += 1
        await course_service.write_audit(
            db,
            actor_id=user.id,
            action="admin.role_assignment.revoked",
            resource_type="role_assignment",
            resource_id=assignment.id,
            course_id=assignment.scope_id if assignment.scope_type == "course" else None,
            detail={
                "user_id": target.id,
                "role": assignment.role,
                "scope_type": assignment.scope_type,
                "scope_id": assignment.scope_id,
                "reason": body.reason,
                "version": assignment.version,
            },
        )
    data = _role_assignment_data(assignment, target)
    await course_service.save_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=ROLE_ASSIGNMENT_REVOKE_ENDPOINT.format(id=assignment_id),
        request_hash=request_hash,
        status=200,
        body={"data": data},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=ROLE_ASSIGNMENT_REVOKE_ENDPOINT.format(id=assignment_id),
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(request, previous["body"]["data"], idempotent_replay=True)
        raise ApiError(
            status_code=409,
            code="ROLE_ASSIGNMENT_CONFLICT",
            message="授权状态已被其他管理员变更，请刷新后重试",
        ) from exc
    return ok(request, data, idempotent_replay=was_already_revoked)


@router.get("/admin/jobs", response_model=None)
async def list_admin_jobs(
    request: Request,
    status: str = Query(default="all", pattern="^(all|queued|running|failed|succeeded|cancelled)$"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """列出同机构教材解析/索引任务的最小状态，不返回任务 payload 或错误正文。"""
    _require_admin(user)
    query = (
        select(Job, Course.id)
        .join(
            MaterialVersion,
            Job.payload["material_version_id"].as_string() == MaterialVersion.id,
        )
        .join(Material, MaterialVersion.material_id == Material.id)
        .join(Course, Material.course_id == Course.id)
        .where(
            Course.organization_id == user.organization_id,
            Job.kind.in_(ADMIN_RECOVERABLE_JOB_KINDS),
        )
    )
    if status != "all":
        query = query.where(Job.status == status)
    decoded_cursor = _decode_admin_cursor(cursor)
    if decoded_cursor is not None:
        query = query.where(_cursor_predicate(Job, decoded_cursor))
    query = query.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1)
    rows = list((await db.execute(query)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return ok(
        request,
        [
            auth_schemas.AdminJobOut(
                id=job.id,
                kind=job.kind,
                status=job.status,
                stage=job.stage,
                progress=job.progress,
                retryable=job.retryable,
                attempt_count=job.attempt_count,
                version=job.version,
                course_id=course_id,
                has_error=job.error is not None,
                created_at=job.created_at,
                updated_at=job.updated_at,
            ).model_dump(mode="json")
            for job, course_id in page
        ],
        next_cursor=(
            _encode_admin_cursor(page[-1][0].created_at, page[-1][0].id)
            if has_more and page
            else None
        ),
        has_more=has_more,
    )


@router.post("/admin/jobs/{job_id}/retry", response_model=None)
async def retry_admin_job(
    job_id: str,
    body: auth_schemas.AdminJobRetryRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """受控重派发同机构内可安全恢复的最新教材任务。"""
    _require_admin(user)
    endpoint = ADMIN_JOB_RETRY_ENDPOINT.format(id=job_id)
    payload = body.model_dump(mode="json")
    request_hash = course_service.canonical_request_hash(payload)
    previous = await course_service.find_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=endpoint,
        request_hash=request_hash,
    )
    if previous is not None:
        return ok(
            request,
            previous["body"]["data"],
            status_code=previous["status"],
            idempotent_replay=True,
        )

    row = await db.execute(
        select(Job, MaterialVersion, Material, Course)
        .join(
            MaterialVersion,
            Job.payload["material_version_id"].as_string() == MaterialVersion.id,
        )
        .join(Material, MaterialVersion.material_id == Material.id)
        .join(Course, Material.course_id == Course.id)
        .where(
            Job.id == job_id,
            Job.kind.in_(ADMIN_RECOVERABLE_JOB_KINDS),
            Course.organization_id == user.organization_id,
        )
        .with_for_update(of=(Job, MaterialVersion))
    )
    job, version, material, course = row.one_or_none() or (None, None, None, None)
    if job is None:
        raise ApiError(status_code=404, code="JOB_NOT_FOUND", message="同机构可恢复任务不存在")
    if job.version != body.version:
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(
                request,
                previous["body"]["data"],
                status_code=previous["status"],
                idempotent_replay=True,
            )
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="任务状态已更新，请刷新后重试",
            details={"expected_version": body.version, "actual_version": job.version},
        )
    if job.status != "failed" or not job.retryable:
        raise ApiError(
            status_code=409,
            code="JOB_NOT_RETRYABLE",
            message="仅可重试明确标记为可重试的失败任务",
        )
    if job.attempt_count >= ADMIN_JOB_MAX_ATTEMPTS:
        raise ApiError(
            status_code=409,
            code="JOB_RETRY_LIMIT_REACHED",
            message="任务已达到人工重试次数上限，请先排查失败原因",
        )
    version_id = version.id
    latest_job_id = await db.scalar(
        select(Job.id)
        .where(
            Job.kind == job.kind,
            Job.payload["material_version_id"].as_string() == version_id,
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    if latest_job_id != job.id:
        raise ApiError(
            status_code=409,
            code="JOB_SUPERSEDED",
            message="该任务已有更新版本，请从最新任务查看状态",
        )
    active_job_id = await db.scalar(
        select(Job.id).where(
            Job.kind == job.kind,
            Job.payload["material_version_id"].as_string() == version_id,
            Job.status.in_(("queued", "running")),
        )
    )
    if active_job_id is not None:
        raise ApiError(
            status_code=409,
            code="JOB_ALREADY_ACTIVE",
            message="该教材版本已有进行中的同类任务",
            details={"job_id": active_job_id},
        )
    if job.kind == "material_parse" and material.visibility != "draft":
        raise ApiError(
            status_code=409,
            code="PUBLISHED_VERSION_IMMUTABLE",
            message="已发布教材不能通过管理员重试原地重新解析",
        )

    old_version = job.version
    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    job.retryable = False
    job.error = None
    job.started_at = None
    job.finished_at = None
    job.last_heartbeat_at = None
    job.worker_backend = get_settings().task_backend
    job.checkpoint = {
        "stage": "queued",
        "admin_retry_from_version": old_version,
    }
    job.version += 1
    data = auth_schemas.AdminJobRetryOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        stage=job.stage,
        retryable=job.retryable,
        attempt_count=job.attempt_count,
        version=job.version,
    ).model_dump(mode="json")
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="admin.job.retry_requested",
        resource_type="job",
        resource_id=job.id,
        course_id=course.id,
        detail={
            "kind": job.kind,
            "version_from": old_version,
            "version_to": job.version,
            "attempt_count": job.attempt_count,
            "reason": body.reason,
        },
    )
    await course_service.save_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=endpoint,
        request_hash=request_hash,
        status=202,
        body={"data": data},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(
                request,
                previous["body"]["data"],
                status_code=previous["status"],
                idempotent_replay=True,
            )
        raise ApiError(
            status_code=409,
            code="JOB_RETRY_CONFLICT",
            message="任务已被其他管理员更新，请刷新状态后重试",
        ) from exc

    try:
        if job.kind == "material_parse":
            dispatch_parse_job(job.id, version_id)
        else:
            dispatch_embed_job(job.id, version_id)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        failed_job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if failed_job is not None and failed_job.status == "queued":
            failed_job.status = "failed"
            failed_job.stage = "dispatch_failed"
            failed_job.retryable = True
            failed_job.error = "任务派发失败，请稍后重试"
            failed_job.finished_at = datetime.now(UTC)
            failed_job.version += 1
            failed_job.checkpoint = {
                "stage": "dispatch_failed",
                "admin_retry_from_version": body.version,
            }
            replay_record = await db.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.idempotency_key == idempotency_key,
                    IdempotencyRecord.user_id == user.id,
                    IdempotencyRecord.endpoint == endpoint,
                )
            )
            if replay_record is not None:
                replay_data = auth_schemas.AdminJobRetryOut(
                    id=failed_job.id,
                    kind=failed_job.kind,
                    status=failed_job.status,
                    stage=failed_job.stage,
                    retryable=failed_job.retryable,
                    attempt_count=failed_job.attempt_count,
                    version=failed_job.version,
                ).model_dump(mode="json")
                replay_record.response_body = {"data": replay_data}
            await db.commit()
        raise ApiError(
            status_code=503,
            code="JOB_DISPATCH_FAILED",
            message="任务已记录，但暂时无法派发；可刷新后再次重试",
            retryable=True,
        ) from exc
    return ok(request, data, status_code=202)
