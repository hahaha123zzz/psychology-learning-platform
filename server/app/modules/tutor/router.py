import json

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    ChatSession,
    ChatTurn,
    LearningSession,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.tutor import service as tutor_service

router = APIRouter()


class ChatSessionCreate(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    mode: str = Field(default="course_qa", pattern="^(course_qa|tutor|question_coach|review)$")
    chapter_object_id: str | None = Field(default=None, min_length=26, max_length=26)
    question_version_id: str | None = Field(default=None, min_length=26, max_length=26)
    title: str | None = Field(default=None, max_length=200)


class TurnCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    client_turn_id: str = Field(min_length=8, max_length=64)
    selected_evidence_ids: list[str] | None = None


class LearningSessionCreate(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    material_version_id: str = Field(min_length=26, max_length=26)
    chapter_object_id: str | None = Field(default=None, min_length=26, max_length=26)


class LearningResponse(BaseModel):
    state_version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=2000)


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
    return session_row


@router.post("/chat/sessions", response_model=None)
async def create_chat_session(
    body: ChatSessionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        body.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if body.mode in ("tutor", "review") and body.chapter_object_id is None:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="教学模式必须指定章节上下文",
        )
    session_row = ChatSession(
        course_id=body.course_id,
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
    if session_row.status != "active":
        raise ApiError(
            status_code=409, code="SESSION_CLOSED", message="会话已结束"
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
        raise ApiError(
            status_code=409,
            code="TURN_DUPLICATE",
            message="该回合已提交过，请勿重复发送",
        )

    async def event_stream():
        async for event in tutor_service.run_turn_stream(
            db,
            session_row=session_row,
            student_turn_id=body.client_turn_id,
            client_turn_id=body.client_turn_id,
            content=body.content,
            purpose=session_row.mode,
        ):
            payload = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event['event']}\ndata: {payload}\n\n"

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
    if version.status != "parsed":
        raise ApiError(
            status_code=409,
            code="MATERIAL_NOT_PARSED",
            message="资料必须解析成功后才能学习",
            details={"status": version.status},
        )
    tutor_message = await tutor_service.start_learning_session(
        db,
        material_version_id=body.material_version_id,
        chapter_object_id=body.chapter_object_id,
    )
    learning = LearningSession(
        user_id=user.id,
        course_id=body.course_id,
        material_version_id=body.material_version_id,
        chapter_object_id=body.chapter_object_id,
        state="diagnose",
        tutor_message=tutor_message,
    )
    db.add(learning)
    await db.commit()
    await db.refresh(learning, attribute_names=["id", "version"])
    return ok(
        request,
        {
            "id": learning.id,
            "state": learning.state,
            "state_version": learning.version,
            "tutor_message": learning.tutor_message,
            "action": "wait_for_student",
            "hint_level": learning.hint_level,
        },
        status_code=201,
    )


@router.get("/learning-sessions/{session_id}", response_model=None)
async def get_learning_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    learning = (
        await db.execute(select(LearningSession).where(LearningSession.id == session_id).limit(1))
    ).scalar_one_or_none()
    if learning is None or learning.user_id != user.id:
        raise ApiError(
            status_code=404,
            code="LEARNING_SESSION_NOT_FOUND",
            message="学习会话不存在或无权访问",
        )
    return ok(
        request,
        {
            "id": learning.id,
            "state": learning.state,
            "state_version": learning.version,
            "tutor_message": learning.tutor_message,
            "hint_level": learning.hint_level,
            "status": learning.status,
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
    learning = (
        await db.execute(select(LearningSession).where(LearningSession.id == session_id).limit(1))
    ).scalar_one_or_none()
    if learning is None or learning.user_id != user.id:
        raise ApiError(
            status_code=404,
            code="LEARNING_SESSION_NOT_FOUND",
            message="学习会话不存在或无权访问",
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
    result = await tutor_service.respond_learning_session(db, learning, body.content)
    await db.commit()
    return ok(request, {**result, "state_version": learning.version})
