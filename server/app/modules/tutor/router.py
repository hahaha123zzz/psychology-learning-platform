import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    ChatSession,
    ChatTurn,
    CourseMember,
    CurrentLearningTask,
    LearningEpisode,
    LearningEvent,
    LearningSession,
    ReviewTask,
    TeachingSession,
    User,
    UserPreference,
)
from app.db.session import get_db_session
from app.modules.assessments.policy import ensure_ai_support_available
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.tutor import service as tutor_service
from app.modules.tutor.planner import plan_next_step
from app.modules.tutor.policy import load_effective_policy

router = APIRouter()


def _sse_frame(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def _replay_saved_turn(tutor_turn: ChatTurn):
    """只从已提交的 TutorTurn 重放完整回答，不重新调用模型或写回业务数据。"""
    citations = tutor_turn.citations or []
    verification = tutor_turn.verification if isinstance(tutor_turn.verification, dict) else {}
    object_context = verification.get("object_context")
    table_context = (
        isinstance(object_context, dict)
        and object_context.get("type") == "table"
        and isinstance(object_context.get("evidence_pointer_id"), str)
        and isinstance(object_context.get("material_version_id"), str)
        and isinstance(object_context.get("publication_snapshot_id"), str)
        and isinstance(object_context.get("index_job_id"), str)
        and any(
            isinstance(citation, dict)
            and citation.get("evidence_pointer_id") == object_context["evidence_pointer_id"]
            and citation.get("material_version_id") == object_context["material_version_id"]
            and citation.get("publication_snapshot_id")
            == object_context["publication_snapshot_id"]
            and citation.get("index_job_id") == object_context["index_job_id"]
            for citation in citations
        )
    )
    safety = tutor_turn.finish_reason == "safety"
    if safety:
        yield _sse_frame("state", {"stage": "safety", "replayed": True})
    else:
        yield _sse_frame("state", {"stage": "retrieving", "replayed": True})
        yield _sse_frame(
            "state",
            {
                "stage": "generating",
                "evidence_count": len(citations),
                "warnings": [],
                "replayed": True,
            },
        )
        if table_context:
            yield _sse_frame(
                "state",
                {
                    "stage": "explaining_object",
                    "object_type": "table",
                    "evidence_pointer_id": object_context["evidence_pointer_id"],
                },
            )
        for citation in citations:
            yield _sse_frame(
                "citation",
                {
                    "evidence_id": citation.get("evidence_id"),
                    "evidence_pointer_id": citation.get("evidence_pointer_id"),
                    "label": citation.get("label", "教材证据"),
                },
            )
        yield _sse_frame("state", {"stage": "verifying", "replayed": True})

    for sequence, offset in enumerate(range(0, len(tutor_turn.content), 24)):
        yield _sse_frame(
            "delta",
            {"sequence": sequence, "text": tutor_turn.content[offset : offset + 24]},
        )

    done = {
        "turn_id": tutor_turn.id,
        "finish_reason": tutor_turn.finish_reason or "stop",
        "saved": True,
        "refusal": tutor_turn.refusal,
        "replayed": True,
    }
    if verification:
        unsupported_count = verification.get("unsupported_count")
        if isinstance(unsupported_count, int):
            done["unsupported_count"] = unsupported_count
    yield _sse_frame("done", done)


class ChatSessionCreate(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    mode: str = Field(default="course_qa", pattern="^(course_qa|tutor|question_coach|review)$")
    chapter_object_id: str | None = Field(default=None, min_length=26, max_length=26)
    question_version_id: str | None = Field(default=None, min_length=26, max_length=26)
    title: str | None = Field(default=None, max_length=200)


EvidencePointerId = Annotated[str, Field(min_length=26, max_length=26)]


class TurnCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    client_turn_id: str = Field(min_length=8, max_length=64)
    selected_evidence_ids: list[str] | None = None
    selected_evidence_pointer_ids: list[EvidencePointerId] | None = Field(
        default=None, max_length=1
    )


class LearningSessionCreate(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    material_version_id: str = Field(min_length=26, max_length=26)
    chapter_object_id: str | None = Field(default=None, min_length=26, max_length=26)


class LearningResponse(BaseModel):
    state_version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=2000)
    action: str = Field(default="respond_task", pattern="^respond_task$")


class LearningTransition(BaseModel):
    state_version: int = Field(ge=1)


async def _get_owned_session(
    db: AsyncSession, session_id: str, user: User
) -> ChatSession:
    session_row = (
        await db.execute(select(ChatSession).where(ChatSession.id == session_id).limit(1))
    ).scalar_one_or_none()
    if session_row is None or session_row.user_id != user.id:
        raise ApiError(
            status_code=404, code="CHAT_SESSION_NOT_FOUND", message="会话不存在或无权访问"
        )
    await tutor_service.authorize_chat_session_release_scope(
        db, session_row=session_row, user_id=user.id
    )
    return session_row


def _turn_selected_pointer_ids(turn: ChatTurn) -> list[str]:
    if turn.role != "student" or not isinstance(turn.citations, list):
        return []
    return [
        citation["evidence_pointer_id"]
        for citation in turn.citations
        if isinstance(citation, dict)
        and isinstance(citation.get("evidence_pointer_id"), str)
    ]


def _turn_idempotency_matches(
    turn: ChatTurn, *, content: str, selected_pointer_ids: list[str]
) -> bool:
    return (
        turn.role == "student"
        and turn.content == content
        and _turn_selected_pointer_ids(turn) == selected_pointer_ids
    )


def _learning_allowed_actions(*, state: str, status: str) -> list[str]:
    """只向前端暴露服务端认可的下一步动作。"""
    if status == "paused":
        return ["RESUME"]
    if status != "active" or state == "completed":
        return ["REVIEW"]
    return ["RESPOND_TASK"]


def _learning_workspace(
    learning: LearningSession,
    *,
    action_override: str | None = None,
    runtime: dict | None = None,
    display_message: str | None = None,
) -> dict:
    allowed_actions = _learning_allowed_actions(
        state=learning.state, status=learning.status
    )
    action = action_override or (
        "complete"
        if learning.state == "completed"
        else "resume"
        if learning.status == "paused"
        else "wait_for_student"
    )
    return {
        "id": learning.id,
        "task_id": learning.id,
        "course_id": learning.course_id,
        "material_version_id": learning.material_version_id,
        "chapter_object_id": learning.chapter_object_id,
        "state": learning.state,
        "status": learning.status,
        "state_version": learning.version,
        "task_version": learning.version,
        "tutor_message": (
            learning.tutor_message if display_message is None else display_message
        ),
        "action": action,
        "hint_level": learning.hint_level,
        "allowed_actions": allowed_actions,
        "context_refs": {
            "course_id": learning.course_id,
            "material_version_id": learning.material_version_id,
            "chapter_object_id": learning.chapter_object_id,
        },
        "completion": {
            "status": "completed" if learning.state == "completed" else "in_progress",
            "activity_completed": learning.state == "completed",
        },
        "runtime": runtime or {"current_task_id": learning.id, "episode_id": None},
        "blocks": tutor_service.build_learning_blocks(
            session_id=learning.id,
            state=learning.state,
            state_version=learning.version,
            message=(
                learning.tutor_message if display_message is None else display_message
            ),
            action=action,
            hint_level=learning.hint_level,
        ),
    }


async def _runtime_view(db: AsyncSession, learning: LearningSession) -> dict | None:
    row = (
        await db.execute(
            select(CurrentLearningTask, TeachingSession, LearningEpisode)
            .join(TeachingSession, TeachingSession.task_id == CurrentLearningTask.id)
            .join(LearningEpisode, LearningEpisode.task_id == CurrentLearningTask.id)
            .where(CurrentLearningTask.legacy_session_id == learning.id)
        )
    ).one_or_none()
    if row is None:
        return None
    task, teaching, episode = row
    return {
        "current_task_id": task.id,
        "teaching_session_id": teaching.id,
        "episode_id": episode.id,
        "episode_no": episode.episode_no,
        "episode_turn_count": episode.turn_count,
        "goal": task.goal,
        "completion": task.completion,
        "release_snapshot": task.release_snapshot,
    }


async def _create_runtime_aggregates(
    db: AsyncSession, learning: LearningSession
) -> None:
    task = CurrentLearningTask(
        id=learning.id,
        user_id=learning.user_id,
        course_id=learning.course_id,
        legacy_session_id=learning.id,
        material_version_id=learning.material_version_id,
        chapter_object_id=learning.chapter_object_id,
        goal={"type": "guided_learning", "target": "complete_learning_session"},
        release_snapshot={"material_version_id": learning.material_version_id},
        completion={"status": "in_progress", "activity_completed": False},
    )
    teaching = TeachingSession(
        task_id=task.id,
        state=learning.state,
        status=learning.status,
        state_version=learning.version,
        context={
            "course_id": learning.course_id,
            "material_version_id": learning.material_version_id,
            "chapter_object_id": learning.chapter_object_id,
        },
        hint_budget=max(0, 3 - learning.hint_level),
    )
    db.add(task)
    await db.flush()
    db.add(teaching)
    await db.flush()
    db.add(LearningEpisode(task_id=task.id, teaching_session_id=teaching.id))


async def _sync_runtime_aggregates(db: AsyncSession, learning: LearningSession) -> None:
    task = await db.scalar(
        select(CurrentLearningTask).where(CurrentLearningTask.legacy_session_id == learning.id)
    )
    if task is None:
        return
    teaching = await db.scalar(select(TeachingSession).where(TeachingSession.task_id == task.id))
    episode = await db.scalar(select(LearningEpisode).where(LearningEpisode.task_id == task.id))
    task.status = "completed" if learning.state == "completed" else learning.status
    task.version = learning.version
    task.completion = {
        "status": "completed" if learning.state == "completed" else "in_progress",
        "activity_completed": learning.state == "completed",
    }
    if teaching is not None:
        teaching.state = learning.state
        teaching.status = "closed" if learning.state == "completed" else learning.status
        teaching.state_version = learning.version
        teaching.version = learning.version
        teaching.hint_budget = max(0, 3 - learning.hint_level)
    if episode is not None:
        episode.status = "completed" if learning.state == "completed" else learning.status
        episode.turn_count += 1
        if learning.state == "completed":
            episode.ended_at = datetime.now(UTC)


async def _get_owned_learning_session(
    db: AsyncSession, session_id: str, user: User
) -> LearningSession:
    learning = (
        await db.execute(
            select(LearningSession).where(LearningSession.id == session_id).limit(1)
        )
    ).scalar_one_or_none()
    if learning is None or learning.user_id != user.id:
        raise ApiError(
            status_code=404,
            code="LEARNING_SESSION_NOT_FOUND",
            message="学习会话不存在或无权访问",
        )
    await require_course_role(
        learning.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    return learning


@router.post("/chat/sessions", response_model=None)
async def create_chat_session(
    body: ChatSessionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    role = await require_course_role(
        body.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if body.mode in ("tutor", "review") and body.chapter_object_id is None:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="教学模式必须指定章节上下文",
        )
    await ensure_ai_support_available(db, user_id=user.id)
    assignment_id = release_id = None
    if role == "student":
        assignment_id, release_id = await tutor_service.resolve_chat_session_release_binding(
            db, user_id=user.id, course_id=body.course_id
        )
    await load_effective_policy(
        db,
        user_id=user.id,
        course_id=body.course_id,
        course_release_id=release_id,
    )
    session_row = ChatSession(
        course_id=body.course_id,
        course_release_assignment_id=assignment_id,
        course_release_id=release_id,
        user_id=user.id,
        mode=body.mode,
        chapter_object_id=body.chapter_object_id,
        question_version_id=body.question_version_id,
        title=body.title,
    )
    db.add(session_row)
    await db.commit()
    await db.refresh(session_row, attribute_names=["id", "created_at"])
    return ok(
        request,
        {
            "id": session_row.id,
            "course_id": session_row.course_id,
            "mode": session_row.mode,
            "status": session_row.status,
            "created_at": session_row.created_at.isoformat(),
        },
        status_code=201,
    )


@router.get("/chat/sessions", response_model=None)
async def list_chat_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await ensure_ai_support_available(db, user_id=user.id)
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    items = [
        {
            "id": s.id,
            "course_id": s.course_id,
            "mode": s.mode,
            "title": s.title,
            "status": s.status,
            "updated_at": s.updated_at.isoformat(),
        }
        for s in result.scalars()
    ]
    return ok(request, items, has_more=False)


@router.get("/chat/sessions/{session_id}", response_model=None)
async def get_chat_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session_row = await _get_owned_session(db, session_id, user)
    await require_course_role(
        session_row.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    await ensure_ai_support_available(db, user_id=user.id)
    turns = (
        await db.execute(
            select(ChatTurn)
            .where(ChatTurn.session_id == session_id)
            .order_by(ChatTurn.created_at.asc())
        )
    ).scalars()
    return ok(
        request,
        {
            "id": session_row.id,
            "course_id": session_row.course_id,
            "mode": session_row.mode,
            "status": session_row.status,
            "turns": [
                {
                    "id": t.id,
                    "role": t.role,
                    "content": t.content,
                    "citations": t.citations,
                    "verification": t.verification,
                    "refusal": t.refusal,
                    "created_at": t.created_at.isoformat(),
                }
                for t in turns
            ],
        },
    )


@router.post("/chat/sessions/{session_id}/turns", response_model=None)
async def create_turn(
    session_id: str,
    body: TurnCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session_row = await _get_owned_session(db, session_id, user)
    await require_course_role(
        session_row.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    await ensure_ai_support_available(db, user_id=user.id)
    effective_policy = await load_effective_policy(
        db,
        user_id=user.id,
        course_id=session_row.course_id,
        course_release_id=session_row.course_release_id,
    )
    preference_row = await db.scalar(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    preferences = (preference_row.preferences or {}) if preference_row else {}
    response_length = preferences.get("response_length", "BALANCED")
    example_order = preferences.get("example_order", "CONCEPT_FIRST")
    if not set(effective_policy["allowed_actions"]) - {"pause", "handoff"}:
        raise ApiError(
            status_code=403,
            code="TEACHING_POLICY_RESTRICTED",
            message="当前策略不允许内容型教学支持。",
            details={
                "policy_version": effective_policy["version"],
                "policy_hash": effective_policy["hash"],
            },
        )
    if session_row.status != "active":
        raise ApiError(
            status_code=409, code="SESSION_CLOSED", message="会话已结束"
        )
    selected_pointer_ids = body.selected_evidence_pointer_ids or []
    if any(len(pointer_id) != 26 for pointer_id in selected_pointer_ids):
        raise ApiError(404, "EVIDENCE_NOT_FOUND", "证据不存在或已撤回")
    selected_pointer = None
    if selected_pointer_ids:
        selected_pointer = await tutor_service.authorize_selected_table_pointer(
            db,
            session_row=session_row,
            user_id=user.id,
            pointer_id=selected_pointer_ids[0],
        )
    duplicate = (
        await db.execute(
            select(ChatTurn).where(
                ChatTurn.session_id == session_id,
                ChatTurn.client_turn_id == body.client_turn_id,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        if not _turn_idempotency_matches(
            duplicate,
            content=body.content,
            selected_pointer_ids=selected_pointer_ids,
        ):
            raise ApiError(
                status_code=409,
                code="TURN_IDEMPOTENCY_CONFLICT",
                message="该 client_turn_id 已用于不同的回合内容",
            )
        saved_tutor_turn = await db.scalar(
            select(ChatTurn).where(
                ChatTurn.session_id == session_id,
                ChatTurn.client_turn_id == f"{body.client_turn_id}:tutor",
                ChatTurn.role == "tutor",
            )
        )
        if saved_tutor_turn is None:
            raise ApiError(
                status_code=409,
                code="TURN_IN_PROGRESS",
                message="该回合尚无已保存的 Tutor 回答，请保留输入后稍后重试",
                retryable=True,
            )
        return StreamingResponse(
            _replay_saved_turn(saved_tutor_turn),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if selected_pointer is not None and selected_pointer.pointer.object_type == "table":
        await tutor_service.authorize_table_pointer_index_job(
            db,
            selected=selected_pointer,
            domain_release_id=selected_pointer.domain_release_id,
        )

    async def event_stream():
        turn_stream = tutor_service.run_turn_stream(
            db,
            session_row=session_row,
            student_turn_id=body.client_turn_id,
            client_turn_id=body.client_turn_id,
            content=body.content,
            purpose=session_row.mode,
            effective_policy=effective_policy,
            organization_id=user.organization_id,
            response_length=response_length,
            example_order=example_order,
            selected_evidence_context=selected_pointer,
        )
        try:
            async for event in turn_stream:
                yield _sse_frame(event["event"], event["data"])
        finally:
            await turn_stream.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/learning-sessions", response_model=None)
async def create_learning_session(
    body: LearningSessionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    role = await require_course_role(
        body.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    from app.modules.materials import service as materials_service

    version, material = await materials_service.get_version_with_material_or_404(
        db, body.material_version_id
    )
    if material.course_id != body.course_id:
        raise ApiError(
            status_code=404,
            code="MATERIAL_VERSION_NOT_FOUND",
            message="资料版本不存在或无权访问",
        )
    if role == "student" and (
        material.visibility != "published" or material.status != "active"
    ):
        raise ApiError(
            status_code=404,
            code="MATERIAL_VERSION_NOT_FOUND",
            message="资料版本不存在或无权访问",
        )
    if role == "student":
        await ensure_ai_support_available(db, user_id=user.id)
    if version.status != "parsed":
        raise ApiError(
            status_code=409,
            code="MATERIAL_NOT_PARSED",
            message="资料必须解析成功后才能学习",
            details={"status": version.status},
        )
    assignment_id = release_id = None
    if role == "student":
        assignment_id, release_id = await tutor_service.resolve_learning_release_binding(
            db,
            user_id=user.id,
            course_id=body.course_id,
            material_id=material.id,
            material_version_id=version.id,
        )
    effective_policy = await load_effective_policy(
        db,
        user_id=user.id,
        course_id=body.course_id,
        course_release_id=release_id,
    )
    if "teach" not in effective_policy["allowed_actions"]:
        raise ApiError(
            status_code=403,
            code="TEACHING_ACTION_NOT_ALLOWED",
            message="当前教学策略不允许开始讲解。",
            details={
                "policy_version": effective_policy["version"],
                "action": "teach",
            },
        )
    tutor_message = await tutor_service.start_learning_session(
        db,
        material_version_id=body.material_version_id,
        chapter_object_id=body.chapter_object_id,
    )
    learning = LearningSession(
        user_id=user.id,
        course_id=body.course_id,
        course_release_assignment_id=assignment_id,
        course_release_id=release_id,
        material_version_id=body.material_version_id,
        chapter_object_id=body.chapter_object_id,
        state="diagnose",
        tutor_message=tutor_message,
    )
    db.add(learning)
    await db.flush()
    await _create_runtime_aggregates(db, learning)
    await db.commit()
    await db.refresh(learning, attribute_names=["id", "version"])
    return ok(
        request,
        _learning_workspace(learning, runtime=await _runtime_view(db, learning)),
        status_code=201,
    )


@router.get("/learning-sessions/{session_id}", response_model=None)
async def get_learning_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    learning = await _get_owned_learning_session(db, session_id, user)
    return ok(request, _learning_workspace(learning, runtime=await _runtime_view(db, learning)))


@router.get("/student/learning/tasks/{task_id}", response_model=None)
async def get_current_learning_task(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """可刷新恢复的学生学习工作区投影；不创建任务，也不写长期学习状态。"""
    learning = await _get_owned_learning_session(db, task_id, user)
    return ok(request, _learning_workspace(learning, runtime=await _runtime_view(db, learning)))


@router.get("/student/home", response_model=None)
async def get_student_home(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """学生首页投影：只聚合本人且当前仍有课程 Scope 的学习任务。"""
    sessions = (
        await db.execute(
            select(LearningSession)
            .join(
                CourseMember,
                (CourseMember.course_id == LearningSession.course_id)
                & (CourseMember.user_id == LearningSession.user_id),
            )
            .where(
                LearningSession.user_id == user.id,
                CourseMember.role == "student",
                CourseMember.status == "active",
            )
            .order_by(desc(LearningSession.updated_at), desc(LearningSession.created_at))
            .limit(20)
        )
    ).scalars().all()
    visible: list[LearningSession] = []
    for session_row in sessions:
        try:
            await require_course_role(
                session_row.course_id,
                user,
                db,
                roles={"teacher", "assistant", "student"},
            )
        except ApiError:
            continue
        visible.append(session_row)
    resumable = [item for item in visible if item.status in ("active", "paused")]
    current = next((item for item in resumable if item.status == "active"), None)
    if current is None:
        current = next((item for item in resumable if item.status == "paused"), None)

    now = datetime.now(UTC)
    review_rows = (
        await db.execute(
            select(ReviewTask)
            .where(
                ReviewTask.user_id == user.id,
                ReviewTask.status == "pending",
                ReviewTask.due_at <= now,
            )
            .order_by(ReviewTask.due_at.asc(), ReviewTask.id.asc())
            .limit(50)
        )
    ).scalars().all()
    due_reviews: list[ReviewTask] = []
    for review in review_rows:
        try:
            await require_course_role(review.course_id, user, db, roles={"student"})
        except ApiError:
            continue
        due_reviews.append(review)

    due_review_count = len(due_reviews)
    planner_course_id = (
        current.course_id if current else (due_reviews[0].course_id if due_reviews else None)
    )
    if planner_course_id:
        progress = await plan_next_step(
            db,
            user_id=user.id,
            course_id=planner_course_id,
            task_status=(
                current.status
                if current and current.course_id == planner_course_id
                else None
            ),
            task_state=(
                current.state
                if current and current.course_id == planner_course_id
                else None
            ),
        )
    else:
        progress = {
            "decision": "continue",
            "reason": "没有已授权的当前任务或到期复习候选。",
            "budget": 1,
            "candidates": [],
            "candidate_budget": 5,
            "source_refs": [],
            "fallback": "continue",
            "fallback_reason": "候选数据不足，不改变任何学习状态。",
            "policy_version": "planner.v1",
        }
    recent_activity = [
        {
            "task_id": item.id,
            "course_id": item.course_id,
            "state": item.state,
            "status": item.status,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in visible[:5]
    ]
    next_actions: list[str] = []
    if due_reviews:
        next_actions.append("COMPLETE_DUE_REVIEW")
    if current is not None and len(next_actions) < 2:
        next_actions.append("RESPOND_TASK" if current.status == "active" else "RESUME_TASK")
    elif current is None and not due_reviews:
        next_actions.append("START_LEARNING")

    return ok(
        request,
        {
            "current_task": (
                _learning_workspace(current, runtime=await _runtime_view(db, current))
                if current
                else None
            ),
            "task_queue": [
                {
                    "task_id": item.id,
                    "course_id": item.course_id,
                    "status": item.status,
                    "state": item.state,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in resumable[:20]
            ],
            "due_reviews": [
                {
                    "id": item.id,
                    "course_id": item.course_id,
                    "reason": item.reason,
                    "due_at": item.due_at.isoformat(),
                }
                for item in due_reviews[:10]
            ],
            "next_actions": next_actions[:2],
            "progress_decision": progress,
            "attention_item": (
                [
                    {
                        "type": "due_reviews",
                        "count": due_review_count,
                        "course_id": due_reviews[0].course_id,
                    }
                ]
                if due_reviews
                else []
            ),
            "recent_activity": recent_activity,
        },
    )


@router.post("/learning-sessions/{session_id}/responses", response_model=None)
async def respond_learning_session(
    session_id: str,
    body: LearningResponse,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    learning = await _get_owned_learning_session(db, session_id, user)
    await ensure_ai_support_available(db, user_id=user.id)
    effective_policy = await load_effective_policy(
        db,
        user_id=user.id,
        course_id=learning.course_id,
        course_release_id=learning.course_release_id,
    )
    if learning.status != "active":
        raise ApiError(
            status_code=409, code="SESSION_CLOSED", message="学习会话已结束"
        )
    if learning.version != body.state_version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="学习状态已更新，请刷新后重试",
            details={
                "expected_version": body.state_version,
                "actual_version": learning.version,
            },
        )
    response_state = learning.state
    result = await tutor_service.respond_learning_session(
        db, learning, body.content, effective_policy=effective_policy
    )
    preference_row = await db.scalar(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    preferences = (preference_row.preferences or {}) if preference_row else {}
    display_message = tutor_service.apply_presentation_preferences(
        result["message"],
        response_length=preferences.get("response_length", "BALANCED"),
        example_order=preferences.get("example_order", "CONCEPT_FIRST"),
        query=body.content,
        include_evidence_prefix=False,
    )
    result["message"] = display_message
    await _sync_runtime_aggregates(db, learning)
    db.add(
        LearningEvent(
            event_key=f"learning-session-response:{learning.id}:{body.state_version}",
            user_id=user.id,
            course_id=learning.course_id,
            event_type="tutor_responded",
            source_type="tutor",
            source_ref=learning.id,
            payload={
                "state_version": learning.version,
                "state": result.get("state"),
                "response_state": response_state,
                "action": result.get("action"),
                "correct": result.get("correct"),
                "hint_level": result.get("hint_level", learning.hint_level),
                "teaching_action": result.get("teaching_action"),
                "policy_version": effective_policy["version"],
                "policy_hash": effective_policy["hash"],
                "policy_sources": effective_policy["sources"],
            },
            occurred_at=datetime.now(UTC),
        )
    )
    await db.commit()
    return ok(
        request,
        {
            **_learning_workspace(
                learning,
                action_override=result.get("action"),
                runtime=await _runtime_view(db, learning),
                display_message=display_message,
            ),
            **result,
        },
    )


@router.post("/student/learning/tasks/{task_id}/respond", response_model=None)
async def respond_current_learning_task(
    task_id: str,
    body: LearningResponse,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """规范化的单回合动作入口；动作白名单由 LearningResponse 强制约束。"""
    return await respond_learning_session(
        task_id, body, request, user=user, db=db
    )


async def _transition_learning_session(
    *,
    session_id: str,
    body: LearningTransition,
    request: Request,
    user: User,
    db: AsyncSession,
    target_status: str,
) -> Response:
    learning = await _get_owned_learning_session(db, session_id, user)
    expected_status = "active" if target_status == "paused" else "paused"
    if learning.status != expected_status:
        raise ApiError(
            status_code=409,
            code="INVALID_SESSION_TRANSITION",
            message=(
                "只有进行中的学习会话可以暂停"
                if target_status == "paused"
                else "只有已暂停的学习会话可以恢复"
            ),
            details={"status": learning.status, "expected_status": expected_status},
        )
    if target_status == "active":
        await ensure_ai_support_available(db, user_id=user.id)
    if learning.version != body.state_version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="学习状态已更新，请刷新后重试",
            details={
                "expected_version": body.state_version,
                "actual_version": learning.version,
            },
        )
    learning.status = target_status
    learning.version += 1
    await _sync_runtime_aggregates(db, learning)
    await db.commit()
    return ok(request, _learning_workspace(learning, runtime=await _runtime_view(db, learning)))


@router.post("/student/learning/tasks/{task_id}/pause", response_model=None)
async def pause_current_learning_task(
    task_id: str,
    body: LearningTransition,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    return await _transition_learning_session(
        session_id=task_id,
        body=body,
        request=request,
        user=user,
        db=db,
        target_status="paused",
    )


@router.post("/student/learning/tasks/{task_id}/resume", response_model=None)
async def resume_current_learning_task(
    task_id: str,
    body: LearningTransition,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    return await _transition_learning_session(
        session_id=task_id,
        body=body,
        request=request,
        user=user,
        db=db,
        target_status="active",
    )
