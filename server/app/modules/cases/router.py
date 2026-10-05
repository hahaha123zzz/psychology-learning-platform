from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import CaseSession, LearningEvent, User
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.cases import schemas

router = APIRouter()

PUBLIC_SNAPSHOT_KEYS = frozenset(
    {"title", "prompt", "options", "knowledge_point", "case_kind"}
)

CASE_CATALOG = {
    "confound-basic": {
        "title": "照明与反应时：找出混淆变量",
        "prompt": (
            "研究者比较两组被试在不同背景音乐下的反应时，但实验组同时使用了更亮的屏幕。"
            "请识别最关键的混淆变量，并提出一个可执行的设计调整。"
        ),
        "options": [
            {"key": "screen_brightness", "label": "屏幕亮度"},
            {"key": "sample_size", "label": "样本量"},
            {"key": "response_scale", "label": "反应时记录单位"},
        ],
        "expected_confound": "screen_brightness",
        "knowledge_point": "实验设计中的混淆变量",
    },
    "experiment-decomposer": {
        "title": "从研究问题拆解实验变量",
        "prompt": (
            "研究者想检验睡眠时长是否影响注意任务表现。"
            "请先识别最应操纵的变量，并说明如何测量结果。"
        ),
        "options": [
            {"key": "sleep_duration", "label": "睡眠时长（自变量）"},
            {"key": "attention_score", "label": "注意任务得分（因变量）"},
            {"key": "room_color", "label": "房间颜色（无关变量）"},
        ],
        "expected_confound": "sleep_duration",
        "knowledge_point": "实验变量与操作化",
        "case_kind": "experiment_decomposer",
    },
    "design-board": {
        "title": "把设计方案变成可执行步骤",
        "prompt": (
            "两组被试要比较不同提示方式对延迟回忆的影响。"
            "请选择最关键的控制策略，并说明实施步骤。"
        ),
        "options": [
            {"key": "random_assignment", "label": "随机分配并保持测验流程一致"},
            {"key": "change_everything", "label": "同时改变提示、时长和测验难度"},
            {"key": "remove_baseline", "label": "不设置基线测量"},
        ],
        "expected_confound": "random_assignment",
        "knowledge_point": "实验设计与控制",
        "case_kind": "design_board",
    },
    "result-interpreter": {
        "title": "解释交互结果而不越过证据",
        "prompt": (
            "结果显示两种提示方式在短延迟时差异很小、长延迟时差异变大。"
            "请选择最稳妥的解释方向，并指出仍需的验证。"
        ),
        "options": [
            {"key": "interaction_effect", "label": "提示方式与延迟共同影响回忆表现"},
            {"key": "causal_certainty", "label": "已经证明提示方式必然导致记忆提升"},
            {"key": "ignore_delay", "label": "忽略延迟条件，只比较总体平均"},
        ],
        "expected_confound": "interaction_effect",
        "knowledge_point": "结果解释与证据边界",
        "case_kind": "result_interpreter",
    },
    "critique": {
        "title": "批判性检查实验结论",
        "prompt": (
            "研究只招募一个班级的志愿者，并把一次测验的高分解释为长期掌握。"
            "请选择最需要指出的问题，并提出补救。"
        ),
        "options": [
            {"key": "sampling_and_retention", "label": "样本代表性和延迟保持都不足"},
            {"key": "font_choice", "label": "只调整报告字体即可解决问题"},
            {"key": "more_confidence", "label": "提高结论措辞的确定性"},
        ],
        "expected_confound": "sampling_and_retention",
        "knowledge_point": "研究批判与迁移验证",
        "case_kind": "critique",
    },
}


def _out(item: CaseSession) -> dict:
    public_snapshot = {
        key: value
        for key, value in item.case_snapshot.items()
        if key in PUBLIC_SNAPSHOT_KEYS
    }
    return schemas.CaseOut(
        id=item.id,
        course_id=item.course_id,
        case_key=item.case_key,
        status=item.status,
        case_snapshot=public_snapshot,
        response=item.response,
        outcome=item.outcome,
        version=item.version,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    ).model_dump(mode="json")


async def _owned(db: AsyncSession, session_id: str, user: User) -> CaseSession:
    item = await db.scalar(select(CaseSession).where(CaseSession.id == session_id))
    if item is None or item.user_id != user.id:
        raise ApiError(
            status_code=404,
            code="CASE_SESSION_NOT_FOUND",
            message="案例会话不存在或无权访问",
        )
    await require_course_role(item.course_id, user, db, roles={"student"})
    return item


@router.get("/student/cases", response_model=None)
async def list_cases(
    request: Request,
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"student"})
    rows = (
        await db.execute(
            select(CaseSession)
            .where(CaseSession.user_id == user.id, CaseSession.course_id == course_id)
            .order_by(CaseSession.updated_at.desc(), CaseSession.id.desc())
            .limit(20)
        )
    ).scalars()
    return ok(request, [_out(item) for item in rows], has_more=False)


@router.get("/student/cases/catalog", response_model=None)
async def case_catalog(
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    del user
    return ok(
        request,
        [
            {
                "case_key": key,
                "title": value["title"],
                "case_kind": value.get("case_kind", "find_confound"),
                "knowledge_point": value["knowledge_point"],
            }
            for key, value in CASE_CATALOG.items()
        ],
        has_more=False,
    )


@router.post("/student/cases", response_model=None)
async def create_case(
    body: schemas.CaseCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(body.course_id, user, db, roles={"student"})
    snapshot = CASE_CATALOG.get(body.case_key)
    if snapshot is None:
        raise ApiError(status_code=404, code="CASE_NOT_FOUND", message="案例不存在")
    item = CaseSession(
        user_id=user.id,
        course_id=body.course_id,
        case_key=body.case_key,
        case_snapshot=snapshot,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item), status_code=201)


@router.get("/student/cases/{session_id}", response_model=None)
async def get_case(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    return ok(request, _out(await _owned(db, session_id, user)))


@router.post("/student/cases/{session_id}/respond", response_model=None)
async def respond_case(
    session_id: str,
    body: schemas.CaseResponse,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _owned(db, session_id, user)
    if item.version != body.version:
        raise ApiError(status_code=409, code="RESOURCE_VERSION_CONFLICT", message="案例会话已变化")
    if item.status == "completed":
        return ok(request, _out(item))
    if item.status != "active":
        raise ApiError(
            status_code=409, code="CASE_SESSION_INVALID_STATE", message="案例会话不能作答"
        )
    options = item.case_snapshot["options"]
    selected_option = next(
        (option for option in options if option["key"] == body.selected_confound), None
    )
    if body.selected_confound and selected_option is None:
        raise ApiError(status_code=422, code="CASE_OPTION_INVALID", message="请选择案例提供的选项")

    if body.draft:
        item.response = body.model_dump(exclude={"version", "draft"})
        item.version += 1
        await db.commit()
        await db.refresh(item)
        return ok(request, _out(item))

    if (
        not body.selected_confound
        or not body.reasoning.strip()
        or not body.design_change.strip()
    ):
        raise ApiError(
            status_code=422,
            code="CASE_RESPONSE_INCOMPLETE",
            message="请完成结构化选择、文字理由和设计调整后再提交",
        )

    reasoning_complete = len(body.reasoning.strip()) >= 20
    design_complete = len(body.design_change.strip()) >= 20
    selection_points = int(bool(selected_option))
    reasoning_points = int(reasoning_complete)
    design_completion_points = int(design_complete)
    score = selection_points + reasoning_points + design_completion_points
    item.response = body.model_dump(exclude={"version", "draft"})
    item.outcome = {
        "score_band": "complete" if score == 3 else "needs_revision",
        "points": score,
        "max_points": 3,
        "components": {
            "selection_points": selection_points,
            "reasoning_completion_points": reasoning_points,
            "design_completion_points": design_completion_points,
        },
        "score_basis": "response_completeness",
        "feedback": "此结果仅反映是否填写了选择、理由和设计调整，不判断答案正确性或推理质量。",
        "qualification_status": "pending",
    }
    item.status = "completed"
    item.version += 1
    db.add(
        LearningEvent(
            event_key=f"case:{item.id}:respond",
            user_id=user.id,
            course_id=item.course_id,
            event_type="answer_submitted",
            source_type="practice",
            source_ref=item.id,
            payload={"case_key": item.case_key, "points": score, "max_points": 3},
            occurred_at=datetime.now(UTC),
        )
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))
