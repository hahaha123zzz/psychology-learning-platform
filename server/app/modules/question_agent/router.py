import hashlib
import json
import unicodedata
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.base import new_ulid
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
from app.modules.assessments.policy import ensure_ai_support_available
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.learning_events import service as learning_event_service
from app.modules.question_agent import service as agent_service
from app.modules.tutor.policy import load_effective_policy
from app.modules.tutor.service import authorize_chat_session_release_scope

router = APIRouter()


class GenerationJobCreate(BaseModel):
    chapter_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=lambda: ["single"])
    count: int = Field(default=5, ge=1, le=20)
    difficulty_distribution: dict | None = None
    special_requirements: str | None = Field(default=None, max_length=1000)


class ReviewTaskVerify(BaseModel):
    version: int = Field(ge=1)
    response: dict = Field(min_length=1)


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
    merge_key: str = Field(min_length=8, max_length=128)
    confirmed: bool

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("合并说明不能为空")
        return normalized


@router.post("/chat/sessions/{session_id}/branches", response_model=None)
async def create_branch(
    session_id: str,
    body: BranchCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await ensure_ai_support_available(db, user_id=user.id)
    parent = (
        await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one_or_none()
    if parent is None or parent.user_id != user.id:
        raise ApiError(
            status_code=404, code="CHAT_SESSION_NOT_FOUND", message="会话不存在或无权访问"
        )
    await require_course_role(parent.course_id, user, db, roles={"teacher", "assistant", "student"})
    await authorize_chat_session_release_scope(db, session_row=parent, user_id=user.id)
    policy = await load_effective_policy(db, user_id=user.id, course_id=parent.course_id)
    if not set(policy["allowed_actions"]) - {"pause", "handoff"}:
        raise ApiError(
            status_code=403,
            code="TEACHING_POLICY_RESTRICTED",
            message="当前策略不允许创建教学分支。",
        )
    source_turn = await db.scalar(
        select(ChatTurn).where(
            ChatTurn.id == body.source_turn_id,
            ChatTurn.session_id == parent.id,
            ChatTurn.role == "student",
        )
    )
    if source_turn is None or body.selection not in source_turn.content:
        raise ApiError(status_code=404, code="BRANCH_SOURCE_NOT_FOUND", message="选区来源不存在")
    branch = ChatSession(
        course_id=parent.course_id,
        user_id=user.id,
        mode=parent.mode,
        title=body.title or f"分支：{body.selection[:30]}",
        parent_session_id=parent.id,
        is_branch=True,
        branch_source_turn_id=body.source_turn_id,
        branch_selection=body.selection,
        course_release_assignment_id=parent.course_release_assignment_id,
        course_release_id=parent.course_release_id,
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
    await ensure_ai_support_available(db, user_id=user.id)
    branch = (
        await db.execute(select(ChatSession).where(ChatSession.id == branch_id))
    ).scalar_one_or_none()
    if branch is None or branch.user_id != user.id or branch.parent_session_id != session_id:
        raise ApiError(status_code=404, code="BRANCH_NOT_FOUND", message="分支不存在或无权访问")
    if not body.confirmed:
        raise ApiError(
            status_code=422,
            code="BRANCH_MERGE_CONFIRMATION_REQUIRED",
            message="合并前必须由学生明确确认",
        )
    branch = await db.scalar(
        select(ChatSession).where(ChatSession.id == branch_id).with_for_update()
    )
    parent = await db.scalar(select(ChatSession).where(ChatSession.id == session_id))
    if (
        branch is None
        or parent is None
        or branch.user_id != user.id
        or parent.user_id != user.id
        or branch.parent_session_id != parent.id
        or branch.course_id != parent.course_id
        or branch.mode != parent.mode
        or not branch.is_branch
    ):
        raise ApiError(status_code=404, code="BRANCH_NOT_FOUND", message="分支不存在或无权访问")
    await require_course_role(parent.course_id, user, db, roles={"teacher", "assistant", "student"})
    if (
        branch.course_release_assignment_id != parent.course_release_assignment_id
        or branch.course_release_id != parent.course_release_id
    ):
        raise ApiError(status_code=404, code="BRANCH_NOT_FOUND", message="分支不存在或无权访问")
    await authorize_chat_session_release_scope(db, session_row=parent, user_id=user.id)
    await authorize_chat_session_release_scope(db, session_row=branch, user_id=user.id)
    policy = await load_effective_policy(db, user_id=user.id, course_id=parent.course_id)
    if not set(policy["allowed_actions"]) - {"pause", "handoff"}:
        raise ApiError(
            status_code=403,
            code="TEACHING_POLICY_RESTRICTED",
            message="当前策略不允许合并教学内容。",
        )
    source_turn = await db.scalar(
        select(ChatTurn).where(
            ChatTurn.id == branch.branch_source_turn_id,
            ChatTurn.session_id == parent.id,
            ChatTurn.role == "student",
        )
    )
    if (
        source_turn is None
        or not branch.branch_selection
        or branch.branch_selection not in source_turn.content
    ):
        raise ApiError(
            status_code=409,
            code="BRANCH_SOURCE_CHANGED",
            message="分支来源已变化，无法安全合并。",
        )
    merge_payload = {
        "branch_id": branch.id,
        "parent_session_id": parent.id,
        "course_id": parent.course_id,
        "mode": parent.mode,
        "source_turn_id": source_turn.id,
        "selection": unicodedata.normalize("NFC", branch.branch_selection),
        "student_text": unicodedata.normalize("NFC", body.note.strip()),
    }
    payload_hash = hashlib.sha256(
        json.dumps(
            merge_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if branch.branch_merge_key is not None:
        if (
            branch.branch_merge_key == body.merge_key
            and branch.branch_merge_payload_hash == payload_hash
        ):
            merged_at = branch.branch_merged_at
            return ok(
                request,
                {
                    "branch_id": branch.id,
                    "merged_into": parent.id,
                    "status": branch.status,
                    "result_turn_id": branch.branch_merge_result_turn_id,
                    "merge_key": branch.branch_merge_key,
                    "merged_at": merged_at.isoformat() if merged_at else None,
                    "replayed": True,
                },
            )
        raise ApiError(
            status_code=409,
            code="BRANCH_MERGE_CONFLICT",
            message="分支已用不同合并请求提交。",
        )
    if branch.status != "active":
        raise ApiError(
            status_code=409,
            code="BRANCH_ALREADY_CLOSED",
            message="分支已关闭，无法合并。",
        )
    merged_at = datetime.now(UTC)
    merge_note = (
        f"学生确认带回的选区：\n{branch.branch_selection}"
        f"\n\n学生补充：\n{body.note.strip()}"
    )
    parent_turn = ChatTurn(
        id=new_ulid(),
        session_id=parent.id,
        client_turn_id=f"merge-{branch.id}",
        role="student",
        content=merge_note,
        citations=[],
        verification={
            "branch_id": branch.id,
            "source_turn_id": source_turn.id,
            "effective_policy": {
                "version": policy["version"],
                "hash": policy["hash"],
                "sources": policy["sources"],
            },
        },
        finish_reason="branch_merge_student_note",
    )
    db.add(parent_turn)
    await db.flush()
    branch.status = "closed"
    branch.merge_note = body.note.strip()
    branch.branch_merge_key = body.merge_key
    branch.branch_merge_payload_hash = payload_hash
    branch.branch_merge_result_turn_id = parent_turn.id
    branch.branch_merged_at = merged_at
    await db.commit()
    return ok(
        request,
        {
            "branch_id": branch.id,
            "merged_into": parent.id,
            "status": branch.status,
            "result_turn_id": parent_turn.id,
            "merge_key": body.merge_key,
            "merged_at": merged_at.isoformat(),
            "replayed": False,
        },
    )


# ---- 复习任务 ----

@router.get("/review-tasks", response_model=None)
async def list_review_tasks(
    request: Request,
    due_only: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await ensure_ai_support_available(db, user_id=user.id)
    query = (
        select(ReviewTask, QuestionVersion)
        .join(QuestionVersion, QuestionVersion.id == ReviewTask.question_version_id)
        .where(ReviewTask.user_id == user.id)
    )
    if due_only:
        query = query.where(
            ReviewTask.due_at <= datetime.now(UTC),
            ReviewTask.status == "pending",
        )
    else:
        query = query.where(ReviewTask.status == "pending")
    rows = (await db.execute(query.order_by(ReviewTask.due_at.asc()).limit(100))).all()
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
                "qualification_status": t.qualification_status,
                "qualification_reason": t.qualification_reason,
                "version": t.version,
                "question": {
                    "type": q.type,
                    "stem": q.stem,
                    "options": q.options or [],
                },
            }
            for t, q in rows
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
    await ensure_ai_support_available(db, user_id=user.id)
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


@router.post("/review-tasks/{task_id}/verify", response_model=None)
async def verify_review_task(
    task_id: str,
    body: ReviewTaskVerify,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await ensure_ai_support_available(db, user_id=user.id)
    task = await db.scalar(
        select(ReviewTask)
        .where(ReviewTask.id == task_id, ReviewTask.user_id == user.id)
        .with_for_update()
    )
    if task is None:
        raise ApiError(status_code=404, code="REVIEW_TASK_NOT_FOUND", message="复习任务不存在")
    if task.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="复习任务已变化，请刷新后重试",
        )
    if task.status != "pending":
        raise ApiError(
            status_code=409,
            code="REVIEW_TASK_NOT_PENDING",
            message="任务已完成或已忽略",
        )
    if task.due_at > datetime.now(UTC):
        raise ApiError(status_code=409, code="REVIEW_TASK_NOT_DUE", message="复习任务尚未到期")
    question = await db.scalar(
        select(QuestionVersion).where(QuestionVersion.id == task.question_version_id)
    )
    if question is None:
        raise ApiError(
            status_code=409,
            code="REVIEW_QUESTION_NOT_FOUND",
            message="复习题目版本不可用",
        )
    event, replay = await learning_event_service.append_event(
        db,
        user_id=user.id,
        course_id=task.course_id,
        event_key=f"review:{task.id}:verify",
        event_type="answer_submitted",
        source_type="review",
        source_ref=task.id,
        payload={"question_version_id": question.id, "response": body.response},
        occurred_at=datetime.now(UTC),
    )
    if not replay:
        task.status = "done"
        task.completed_at = datetime.now(UTC)
        task.version += 1
    await db.commit()
    return ok(
        request,
        {
            "id": task.id,
            "status": task.status,
            "qualification_status": task.qualification_status,
            "event_id": event.id,
            "pending_qualification": event.qualification_status == "pending",
        },
        idempotent_replay=replay,
    )
