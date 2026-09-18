from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    ChatSession,
    ChatTurn,
    Job,
    Question,
    QuestionVersion,
    ReviewTask,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.question_agent import service as agent_service

router = APIRouter()


class GenerationJobCreate(BaseModel):
    chapter_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=lambda: ["single"])
    count: int = Field(default=5, ge=1, le=20)
    difficulty_distribution: dict | None = None
    special_requirements: str | None = Field(default=None, max_length=1000)


@router.post(
    "/courses/{course_id}/question-generation-jobs", response_model=None
)
async def create_generation_job(
    course_id: str,
    body: GenerationJobCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    job = Job(
        kind="question_generation",
        status="queued",
        stage="queued",
        payload={
            "course_id": course_id,
            "chapter_ids": body.chapter_ids,
            "knowledge_point_ids": body.knowledge_point_ids,
            "question_types": body.question_types,
            "count": body.count,
            "difficulty_distribution": body.difficulty_distribution,
            "special_requirements": body.special_requirements,
        },
        created_by=user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job, attribute_names=["id"])
    agent_service.spawn_generation_job(job.id, job.payload)
    return ok(request, {"job_id": job.id, "status": "queued"}, status_code=202)


@router.get(
    "/courses/{course_id}/question-generation-jobs/{job_id}/drafts",
    response_model=None,
)
async def list_generation_drafts(
    course_id: str,
    job_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.kind == "question_generation"))
    ).scalar_one_or_none()
    if job is None or (job.payload or {}).get("course_id") != course_id:
        raise ApiError(status_code=404, code="JOB_NOT_FOUND", message="任务不存在")
    rows = (
        await db.execute(
            select(Question, QuestionVersion)
            .join(
                QuestionVersion,
                QuestionVersion.id == Question.current_version_id,
            )
            .where(
                Question.course_id == course_id,
                Question.origin == "agent",
                Question.created_at >= job.created_at,
            )
            .order_by(Question.created_at.asc())
        )
    ).all()
    items = [
        {
            "question_id": q.id,
            "status": q.status,
            "version_id": v.id,
            "type": v.type,
            "stem": v.stem,
            "options": v.options,
            "explanation": v.explanation,
            "difficulty": v.difficulty,
            "evidence_ids": v.evidence_ids,
        }
        for q, v in rows
    ]
    return ok(request, {"job_status": job.status, "drafts": items})


# ---- 分支追问 ----

class BranchCreate(BaseModel):
    source_turn_id: str = Field(min_length=26, max_length=26)
    selection: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=200)


class BranchMerge(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


@router.post("/chat/sessions/{session_id}/branches", response_model=None)
async def create_branch(
    session_id: str,
    body: BranchCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    parent = (
        await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one_or_none()
    if parent is None or parent.user_id != user.id:
        raise ApiError(
            status_code=404, code="CHAT_SESSION_NOT_FOUND", message="会话不存在或无权访问"
        )
    branch = ChatSession(
        course_id=parent.course_id,
        user_id=user.id,
        mode=parent.mode,
        title=body.title or f"分支：{body.selection[:30]}",
        parent_session_id=parent.id,
        is_branch=True,
        branch_source_turn_id=body.source_turn_id,
        branch_selection=body.selection,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch, attribute_names=["id"])
    return ok(
        request,
        {
            "id": branch.id,
            "parent_session_id": parent.id,
            "selection": body.selection,
        },
        status_code=201,
    )



@router.post(
    "/chat/sessions/{session_id}/branches/{branch_id}/merge", response_model=None
)
async def merge_branch(
    session_id: str,
    branch_id: str,
    body: BranchMerge,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    branch = (
        await db.execute(select(ChatSession).where(ChatSession.id == branch_id))
    ).scalar_one_or_none()
    if branch is None or branch.user_id != user.id or branch.parent_session_id != session_id:
        raise ApiError(status_code=404, code="BRANCH_NOT_FOUND", message="分支不存在或无权访问")
    if branch.status != "active":
        raise ApiError(status_code=409, code="BRANCH_ALREADY_MERGED", message="分支已关闭")

    tutor_turns = (
        await db.execute(
            select(ChatTurn)
            .where(ChatTurn.session_id == branch.id, ChatTurn.role == "tutor")
            .order_by(ChatTurn.created_at.asc())
        )
    ).scalars()
    conclusions = [t.content for t in tutor_turns if t.refusal is False]
    merge_note = "分支结论（用户确认）：\n" + (
        "\n".join(conclusions[-2:]) or body.note
    )
    parent_turn = ChatTurn(
        session_id=session_id,
        client_turn_id=f"merge-{branch.id}",
        role="tutor",
        content=merge_note,
        citations=[],
        finish_reason="branch_merge",
    )
    db.add(parent_turn)
    branch.status = "closed"
    branch.merge_note = body.note
    await db.commit()
    return ok(
        request,
        {"branch_id": branch.id, "merged_into": session_id, "status": branch.status},
    )


# ---- 复习任务 ----

@router.get("/review-tasks", response_model=None)
async def list_review_tasks(
    request: Request,
    due_only: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    query = select(ReviewTask).where(ReviewTask.user_id == user.id)
    if due_only:
        query = query.where(
            ReviewTask.due_at <= datetime.now(UTC),
            ReviewTask.status == "pending",
        )
    else:
        query = query.where(ReviewTask.status == "pending")
    rows = (
        await db.execute(query.order_by(ReviewTask.due_at.asc()).limit(100))
    ).scalars()
    return ok(
        request,
        [
            {
                "id": t.id,
                "course_id": t.course_id,
                "question_version_id": t.question_version_id,
                "reason": t.reason,
                "due_at": t.due_at.isoformat(),
                "status": t.status,
            }
            for t in rows
        ],
        has_more=False,
    )


@router.post("/review-tasks/{task_id}/complete", response_model=None)
async def complete_review_task(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    task = (
        await db.execute(select(ReviewTask).where(ReviewTask.id == task_id).limit(1))
    ).scalar_one_or_none()
    if task is None or task.user_id != user.id:
        raise ApiError(
            status_code=404, code="REVIEW_TASK_NOT_FOUND", message="复习任务不存在"
        )
    if task.status != "pending":
        raise ApiError(
            status_code=409, code="REVIEW_TASK_NOT_PENDING", message="任务已完成或已忽略"
        )
    task.status = "done"
    task.completed_at = datetime.now(UTC)
    await db.commit()
    return ok(request, {"id": task.id, "status": task.status})
