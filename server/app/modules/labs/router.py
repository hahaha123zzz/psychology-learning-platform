import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import LearningEvent, MiniLabSession, User
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.labs import schemas

router = APIRouter()

LAB_CATALOG: dict[str, dict] = {
    "attention-cue-basic": {
        "id": "attention-cue-basic",
        "title": "注意线索与反应时：一次可重复的 Mini Lab",
        "intro": "这是一个确定性教学实验，用来观察线索是否改变反应时。请按阶段完成记录。",
        "prediction": {
            "prompt": "如果线索有效，哪一种条件下反应会更快？",
            "choices": ["有线索条件", "无线索条件", "两者一定相同"],
        },
        "run": {
            "prompt": "根据演示结果，哪项描述最符合当前记录？",
            "choices": ["线索条件更快", "无线索条件更快", "当前记录不足以判断"],
        },
        "inspect": "比较两种条件的反应时，并注意样本量和随机波动。",
        "explanation": "解释时应区分观察到的差异与可以推广的因果结论。",
        "summary": "完成预测、观察、解释和迁移总结后，系统才会生成一条 transfer 证据。",
        "knowledge_point": "注意线索实验与证据边界",
        "source_status": "engineering_fixture",
        "source_note": "当前为工程验证用自编 fixture，不对应已获准教材，也不代表科学效度验收。",
    }
}


def _out(item: MiniLabSession) -> dict:
    return schemas.MiniLabOut(
        id=item.id,
        course_id=item.course_id,
        lab_key=item.lab_key,
        definition_snapshot=item.definition_snapshot,
        status=item.status,
        phase=item.phase,
        trial_data=item.trial_data,
        derived_measure=item.derived_measure,
        version=item.version,
        started_at=item.started_at.isoformat(),
        completed_at=item.completed_at.isoformat() if item.completed_at else None,
        invalidation_reason=item.invalidation_reason,
        invalidated_at=item.invalidated_at.isoformat() if item.invalidated_at else None,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    ).model_dump(mode="json")


async def _owned(
    db: AsyncSession, session_id: str, user: User, *, lock: bool = False
) -> MiniLabSession:
    statement = select(MiniLabSession).where(MiniLabSession.id == session_id)
    if lock:
        statement = statement.with_for_update()
    item = await db.scalar(statement)
    if item is None or item.user_id != user.id:
        raise ApiError(
            status_code=404,
            code="MINI_LAB_NOT_FOUND",
            message="实验会话不存在或无权访问",
        )
    await require_course_role(item.course_id, user, db, roles={"student"})
    return item


def _validate_trials(trials: list[schemas.MiniLabTrial]) -> list[dict]:
    expected = ["intro", "predict", "run", "inspect", "explain", "summary"]
    phases = [trial.phase for trial in trials]
    if phases != expected[: len(phases)]:
        raise ApiError(
            status_code=422,
            code="MINI_LAB_TRIAL_SEQUENCE_INVALID",
            message="实验阶段记录必须按顺序追加",
        )
    return [trial.model_dump(mode="json") for trial in trials]


def _validated_definition(definition: dict) -> dict:
    try:
        return schemas.MiniLabDefinition.model_validate(definition).model_dump(mode="json")
    except ValidationError as exc:
        raise ApiError(
            status_code=500,
            code="MINI_LAB_DEFINITION_INVALID",
            message="实验定义不符合安全文本模板",
        ) from exc


def _validate_responses(item: MiniLabSession, trial_data: list[dict]) -> None:
    choices = item.definition_snapshot.get("prediction", {}).get("choices", [])
    run_choices = item.definition_snapshot.get("run", {}).get("choices", [])
    if not isinstance(choices, list) or not isinstance(run_choices, list):
        raise ApiError(
            status_code=500, code="MINI_LAB_DEFINITION_INVALID", message="实验定义不可用"
        )
    for trial in trial_data:
        choice_count = (
            len(choices if trial["phase"] == "predict" else run_choices)
            if trial["phase"] in {"predict", "run"}
            else 1
        )
        if trial["response"] is not None and trial["response"] >= choice_count:
            raise ApiError(
                status_code=422,
                code="MINI_LAB_RESPONSE_INVALID",
                message="实验响应超出选项范围",
            )


@router.get("/student/labs/active", response_model=None)
async def get_active_lab(
    request: Request,
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """优先返回运行中会话；否则返回最近终态，供页面恢复已知状态。"""
    await require_course_role(course_id, user, db, roles={"student"})
    item = await db.scalar(
        select(MiniLabSession)
        .where(
            MiniLabSession.user_id == user.id,
            MiniLabSession.course_id == course_id,
            MiniLabSession.status.in_({"running", "completed", "invalidated"}),
        )
        .order_by(
            case((MiniLabSession.status == "running", 0), else_=1),
            MiniLabSession.updated_at.desc(),
            MiniLabSession.created_at.desc(),
        )
        .limit(1)
    )
    return ok(request, _out(item) if item else None)


@router.get("/student/labs/catalog", response_model=None)
async def list_catalog(
    request: Request,
    course_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if course_id:
        await require_course_role(course_id, user, db, roles={"student"})
    return ok(
        request,
        [
            {**_validated_definition(value), "lab_key": key}
            for key, value in LAB_CATALOG.items()
        ],
        has_more=False,
    )


@router.post("/student/labs", response_model=None)
async def create_lab(
    body: schemas.MiniLabCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(body.course_id, user, db, roles={"student"})
    definition = LAB_CATALOG.get(body.lab_key)
    if definition is None:
        raise ApiError(status_code=404, code="MINI_LAB_NOT_FOUND", message="实验不存在")
    definition = _validated_definition(definition)
    # 锁定当前用户行，串行化同一用户并发创建，避免刷新/重复点击遗留多个活动会话。
    await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    active = await db.scalar(
        select(MiniLabSession)
        .where(
            MiniLabSession.user_id == user.id,
            MiniLabSession.course_id == body.course_id,
            MiniLabSession.status == "running",
        )
        .order_by(MiniLabSession.updated_at.desc(), MiniLabSession.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if active is not None:
        if active.lab_key == body.lab_key:
            return ok(request, _out(active))
        raise ApiError(
            status_code=409,
            code="MINI_LAB_SESSION_ACTIVE",
            message="已有未完成实验，请先恢复或完成当前会话",
            details={"session_id": active.id},
        )
    item = MiniLabSession(
        user_id=user.id,
        course_id=body.course_id,
        lab_key=body.lab_key,
        definition_snapshot=dict(definition),
        status="running",
        phase="intro",
        trial_data=[],
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item), status_code=201)


@router.get("/student/labs/{session_id}", response_model=None)
async def get_lab(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    return ok(request, _out(await _owned(db, session_id, user)))


@router.post("/student/labs/{session_id}/trials", response_model=None)
async def save_lab_progress(
    session_id: str,
    body: schemas.MiniLabProgress,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _owned(db, session_id, user, lock=True)
    if item.status != "running":
        raise ApiError(
            status_code=409, code="MINI_LAB_INVALID_STATE", message="实验会话不能继续记录"
        )
    incoming = _validate_trials(body.trial_data)
    _validate_responses(item, incoming)
    saved = item.trial_data or []

    # 完全重复或较早的重试只返回当前快照；不会覆盖已持久化的后续 trial。
    if incoming == saved or (len(incoming) < len(saved) and saved[: len(incoming)] == incoming):
        return ok(request, _out(item))
    if body.version != item.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="实验会话已变化，请恢复最新保存的阶段后继续",
        )
    # 只有对已保存前缀的追加才可合并；不同答案/不同阶段顺序必须显式解决冲突。
    if incoming[: len(saved)] != saved:
        raise ApiError(
            status_code=409,
            code="MINI_LAB_TRIAL_CONFLICT",
            message="实验记录与服务端已保存阶段不一致，请恢复最新会话",
        )
    if body.version > item.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="实验会话已变化"
        )

    item.trial_data = incoming
    phases = ["intro", "predict", "run", "inspect", "explain", "summary"]
    item.phase = phases[len(incoming)] if len(incoming) < len(phases) else "summary"
    item.version += 1
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))


@router.post(
    "/student/labs/{session_id}/invalidate", response_model=schemas.MiniLabResponse
)
async def invalidate_lab(
    session_id: str,
    body: schemas.MiniLabInvalidate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _owned(db, session_id, user, lock=True)
    payload_hash = hashlib.sha256(
        json.dumps(
            {"expected_version": body.expected_version, "reason": body.reason},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    # 幂等重放先于状态/版本检查；同 key 的不同请求体不得复用旧回执。
    if item.invalidation_key == body.idempotency_key:
        if item.invalidation_payload_hash != payload_hash:
            raise ApiError(
                status_code=409,
                code="IDEMPOTENCY_KEY_REUSED",
                message="作废幂等键已用于不同请求内容",
            )
        return ok(request, _out(item))
    if item.status != "running":
        raise ApiError(
            status_code=409,
            code="MINI_LAB_INVALID_STATE",
            message="只有进行中的实验会话可以作废",
        )
    if item.version != body.expected_version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="实验会话已变化，请恢复最新保存阶段后再作废",
        )

    item.status = "invalidated"
    item.version += 1
    item.invalidation_key = body.idempotency_key
    item.invalidation_payload_hash = payload_hash
    item.invalidated_by_user_id = user.id
    item.invalidated_at = datetime.now(UTC)
    item.invalidation_reason = body.reason
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))


@router.post("/student/labs/{session_id}/result", response_model=None)
async def submit_result(
    session_id: str,
    body: schemas.MiniLabResult,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _owned(db, session_id, user, lock=True)
    submitted_trials = [trial.model_dump(mode="json") for trial in body.trial_data]
    if item.status == "completed":
        if submitted_trials == item.trial_data:
            return ok(request, _out(item))
        raise ApiError(
            status_code=409,
            code="MINI_LAB_RESULT_CONFLICT",
            message="该实验已完成，不能用不同记录覆盖",
        )
    if item.version != body.version:
        raise ApiError(status_code=409, code="RESOURCE_VERSION_CONFLICT", message="实验会话已变化")
    if item.status != "running":
        raise ApiError(
            status_code=409, code="MINI_LAB_INVALID_STATE", message="实验会话不能提交"
        )
    if body.definition_id != item.definition_snapshot.get("id"):
        raise ApiError(
            status_code=422,
            code="MINI_LAB_DEFINITION_MISMATCH",
            message="实验定义不匹配",
        )
    trial_data = _validate_trials(body.trial_data)
    if len(trial_data) != 6:
        raise ApiError(
            status_code=422,
            code="MINI_LAB_TRIAL_SEQUENCE_INVALID",
            message="实验阶段记录不完整或顺序错误",
        )
    _validate_responses(item, trial_data)
    saved = item.trial_data or []
    if trial_data[: len(saved)] != saved:
        raise ApiError(
            status_code=409,
            code="MINI_LAB_TRIAL_CONFLICT",
            message="提交结果与服务端已保存阶段不一致，请恢复最新会话",
        )
    explanation_complete = trial_data[4]["response"] is not None
    transfer_complete = trial_data[5]["response"] is not None
    rts = [trial["rt"] for trial in trial_data if isinstance(trial["rt"], int)]
    item.trial_data = trial_data
    item.phase = "summary"
    item.status = "completed"
    item.version += 1
    item.completed_at = datetime.now(UTC)
    item.derived_measure = {
        "trial_count": len(trial_data),
        "explanation_complete": explanation_complete,
        "transfer_complete": transfer_complete,
        "rt_summary": {
            "count": len(rts),
            "mean_ms": round(sum(rts) / len(rts), 2) if rts else None,
        },
        "qualification_status": "pending",
    }
    db.add(
        LearningEvent(
            event_key=f"lab:{item.id}:completed",
            user_id=user.id,
            course_id=item.course_id,
            event_type="lab_trial_completed",
            source_type="lab",
            source_ref=item.id,
            payload={
                "lab_key": item.lab_key,
                "session_id": item.id,
                "trial_count": len(trial_data),
                "explanation_complete": explanation_complete,
                "transfer_complete": transfer_complete,
            },
            occurred_at=datetime.now(UTC),
        )
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))
