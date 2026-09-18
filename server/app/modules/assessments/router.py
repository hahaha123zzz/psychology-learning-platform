from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    Assessment,
    AssessmentItem,
    Attempt,
    AttemptAnswer,
    Question,
    QuestionVersion,
    ReviewTask,
    User,
)
from app.db.session import get_db_session
from app.modules.assessments.schemas import (
    AnswerSave,
    AssessmentCreate,
    QuestionCreate,
    QuestionReview,
)
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service

router = APIRouter()

OBJECTIVE_TYPES = {"single", "multiple", "true_false"}


# ---- 题库 ----

def _validate_question_body(body: QuestionCreate) -> None:
    if body.type == "single":
        options = body.options or []
        correct = [o for o in options if o.is_correct]
        if len(options) < 2 or len(correct) != 1:
            raise ApiError(
                status_code=422,
                code="QUESTION_INVALID",
                message="单选题必须恰有一个正确选项且至少两个选项",
            )
    if body.type == "multiple":
        options = body.options or []
        correct = [o for o in options if o.is_correct]
        if len(options) < 3 or len(correct) < 1:
            raise ApiError(
                status_code=422,
                code="QUESTION_INVALID",
                message="多选题至少三个选项且至少一个正确选项",
            )
    if body.type in ("short_answer", "essay") and not (body.rubric or "").strip():
        raise ApiError(
            status_code=422,
            code="QUESTION_INVALID",
            message="主观题必须提供评分规则（rubric）",
        )


def question_out(question: Question, version: QuestionVersion | None) -> dict:
    data = {
        "id": question.id,
        "course_id": question.course_id,
        "status": question.status,
        "origin": question.origin,
        "version": question.version,
        "created_at": question.created_at.isoformat(),
    }
    if version is not None:
        data.update(
            {
                "current_version": {
                    "id": version.id,
                    "version_no": version.version_no,
                    "type": version.type,
                    "stem": version.stem,
                    "options": version.options,
                    "answer": version.answer,
                    "rubric": version.rubric,
                    "explanation": version.explanation,
                    "difficulty": version.difficulty,
                    "knowledge_point_ids": version.knowledge_point_ids,
                    "evidence_ids": version.evidence_ids,
                }
            }
        )
    return data


async def get_question_or_404(
    db: AsyncSession, question_id: str, user: User
) -> Question:
    question = (
        await db.execute(select(Question).where(Question.id == question_id).limit(1))
    ).scalar_one_or_none()
    if question is None:
        raise ApiError(
            status_code=404, code="QUESTION_NOT_FOUND", message="题目不存在或无权访问"
        )
    await require_course_role(
        question.course_id, user, db, roles={"teacher"}
    )
    return question


@router.post("/courses/{course_id}/questions", response_model=None)
async def create_question(
    course_id: str,
    body: QuestionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    _validate_question_body(body)
    question = Question(course_id=course_id, created_by=user.id, status="draft")
    db.add(question)
    await db.flush()
    version = QuestionVersion(
        question_id=question.id,
        version_no=1,
        type=body.type,
        stem=body.stem,
        options=[o.model_dump() for o in body.options] if body.options else None,
        answer=body.answer
        or (
            {"correct_keys": [o.key for o in body.options if o.is_correct]}
            if body.options
            else None
        ),
        rubric=body.rubric,
        explanation=body.explanation,
        difficulty=body.difficulty,
        knowledge_point_ids=body.knowledge_point_ids,
        evidence_ids=body.evidence_ids,
        created_by=user.id,
    )
    db.add(version)
    await db.flush()
    question.current_version_id = version.id
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="question.created",
        resource_type="question",
        resource_id=question.id,
        course_id=course_id,
        detail={"type": body.type, "difficulty": body.difficulty},
    )
    await db.commit()
    await db.refresh(question, attribute_names=["id", "created_at"])
    return ok(request, question_out(question, version), status_code=201)


@router.get("/courses/{course_id}/questions", response_model=None)
async def list_questions(
    course_id: str,
    request: Request,
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    query = (
        select(Question, QuestionVersion)
        .outerjoin(
            QuestionVersion, Question.current_version_id == QuestionVersion.id
        )
        .where(Question.course_id == course_id)
        .order_by(Question.created_at.desc())
    )
    if status:
        query = query.where(Question.status == status)
    if type:
        query = query.where(QuestionVersion.type == type)
    rows = (await db.execute(query)).all()
    items = [question_out(q, v) for q, v in rows]
    return ok(request, items, has_more=False)


@router.get("/questions/{question_id}", response_model=None)
async def get_question(
    question_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    question = (
        await db.execute(select(Question).where(Question.id == question_id).limit(1))
    ).scalar_one_or_none()
    if question is None:
        raise ApiError(
            status_code=404, code="QUESTION_NOT_FOUND", message="题目不存在或无权访问"
        )
    await require_course_role(
        question.course_id, user, db, roles={"teacher", "assistant"}
    )
    version = (
        await db.get(QuestionVersion, question.current_version_id)
        if question.current_version_id
        else None
    )
    return ok(request, question_out(question, version))


@router.post("/questions/{question_id}/review", response_model=None)
async def review_question(
    question_id: str,
    body: QuestionReview,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    question = (
        await db.execute(select(Question).where(Question.id == question_id).limit(1))
    ).scalar_one_or_none()
    if question is None:
        raise ApiError(
            status_code=404, code="QUESTION_NOT_FOUND", message="题目不存在或无权访问"
        )
    await require_course_role(
        question.course_id, user, db, roles={"teacher"}
    )
    if question.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="题目状态已被修改，请刷新后重试",
            details={"expected_version": body.version, "actual_version": question.version},
        )
    if body.action in ("reject", "request_changes") and not (body.comment or "").strip():
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="驳回或退回修改时必须填写理由",
        )
    mapping = {
        "approve": "approved",
        "reject": "rejected",
        "request_changes": "draft",
    }
    if question.status == "draft" and body.action == "approve":
        question.status = "approved"
    elif question.status in ("approved", "published") and body.action == "approve":
        raise ApiError(
            status_code=409, code="INVALID_REVIEW_ACTION", message="当前状态无需审核"
        )
    else:
        question.status = mapping[body.action]
    question.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action=f"question.review_{body.action}",
        resource_type="question",
        resource_id=question.id,
        course_id=question.course_id,
        detail={"comment": body.comment},
    )
    await db.commit()
    return ok(request, {"id": question.id, "status": question.status})


@router.post("/questions/{question_id}/publish", response_model=None)
async def publish_question(
    question_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    question = (
        await db.execute(select(Question).where(Question.id == question_id).limit(1))
    ).scalar_one_or_none()
    if question is None:
        raise ApiError(
            status_code=404, code="QUESTION_NOT_FOUND", message="题目不存在或无权访问"
        )
    await require_course_role(
        question.course_id, user, db, roles={"teacher"}
    )
    version = (
        await db.get(QuestionVersion, question.current_version_id)
        if question.current_version_id
        else None
    )
    if question.status != "approved" or version is None:
        raise ApiError(
            status_code=409,
            code="QUESTION_NOT_APPROVED",
            message="题目必须先审核通过才能发布",
            details={"status": question.status},
        )
    if not (version.evidence_ids or []):
        raise ApiError(
            status_code=409,
            code="QUESTION_EVIDENCE_MISSING",
            message="发布题必须绑定教材证据",
        )
    question.status = "published"
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="question.published",
        resource_type="question",
        resource_id=question.id,
        course_id=question.course_id,
        detail=None,
    )
    await db.commit()
    return ok(request, {"id": question.id, "status": question.status})


# ---- 测验 ----

@router.post("/courses/{course_id}/assessments", response_model=None)
async def create_assessment(
    course_id: str,
    body: AssessmentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    versions: list[QuestionVersion] = []
    for question_id in body.question_ids:
        question = (
            await db.execute(
                select(Question).where(
                    Question.id == question_id, Question.course_id == course_id
                )
            )
        ).scalar_one_or_none()
        if question is None or question.status != "published":
            raise ApiError(
                status_code=409,
                code="QUESTION_NOT_PUBLISHED",
                message="只能使用已发布题目组卷",
                details={"question_id": question_id},
            )
        version = await db.get(QuestionVersion, question.current_version_id)
        if version is None:
            raise ApiError(
                status_code=409,
                code="QUESTION_NOT_PUBLISHED",
                message="题目缺少可用版本",
                details={"question_id": question_id},
            )
        versions.append(version)
    assessment = Assessment(
        course_id=course_id,
        title=body.title,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
        ai_policy=body.ai_policy,
        created_by=user.id,
    )
    db.add(assessment)
    await db.flush()
    for order_no, version in enumerate(versions, start=1):
        db.add(
            AssessmentItem(
                assessment_id=assessment.id,
                question_version_id=version.id,
                points=body.points_per_question,
                order_no=order_no,
            )
        )
    await db.commit()
    await db.refresh(assessment, attribute_names=["id"])
    return ok(request, {"id": assessment.id, "status": assessment.status}, status_code=201)


@router.post("/assessments/{assessment_id}/publish", response_model=None)
async def publish_assessment(
    assessment_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    assessment = await _get_assessment_or_404(db, assessment_id, user)
    if assessment.status != "draft":
        raise ApiError(
            status_code=409, code="INVALID_ASSESSMENT_STATUS", message="当前状态不能发布"
        )
    assessment.status = "published"
    await db.commit()
    return ok(request, {"id": assessment.id, "status": assessment.status})


async def _get_assessment_or_404(
    db: AsyncSession, assessment_id: str, user: User, *, staff: bool = True
) -> Assessment:
    assessment = (
        await db.execute(
            select(Assessment).where(Assessment.id == assessment_id).limit(1)
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise ApiError(
            status_code=404,
            code="ASSESSMENT_NOT_FOUND",
            message="测验不存在或无权访问",
        )
    await require_course_role(
        assessment.course_id,
        user,
        db,
        roles={"teacher", "assistant"} if staff else {"teacher", "assistant", "student"},
    )
    return assessment


@router.get("/assessments/{assessment_id}", response_model=None)
async def get_assessment(
    assessment_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    assessment = await _get_assessment_or_404(db, assessment_id, user, staff=False)
    role = await require_course_role(
        assessment.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    staff = role in ("teacher", "assistant") or user.is_platform_admin
    rows = (
        await db.execute(
            select(AssessmentItem, QuestionVersion)
            .join(QuestionVersion, QuestionVersion.id == AssessmentItem.question_version_id)
            .where(AssessmentItem.assessment_id == assessment_id)
            .order_by(AssessmentItem.order_no.asc())
        )
    ).all()
    items = []
    for item, version in rows:
        entry = {
            "question_version_id": version.id,
            "order_no": item.order_no,
            "points": item.points,
            "type": version.type,
            "stem": version.stem,
            "options": [
                {"key": o["key"], "text": o["text"]} for o in (version.options or [])
            ]
            or None,
        }
        if staff:
            entry["answer"] = version.answer
            entry["rubric"] = version.rubric
            entry["explanation"] = version.explanation
            entry["evidence_ids"] = version.evidence_ids
        items.append(entry)
    data = {
        "id": assessment.id,
        "title": assessment.title,
        "status": assessment.status,
        "ai_policy": assessment.ai_policy,
        "opens_at": assessment.opens_at.isoformat() if assessment.opens_at else None,
        "closes_at": assessment.closes_at.isoformat() if assessment.closes_at else None,
        "items": items,
    }
    return ok(request, data)


# ---- 作答 ----

@router.post("/assessments/{assessment_id}/attempts", response_model=None)
async def start_attempt(
    assessment_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    assessment = await _get_assessment_or_404(db, assessment_id, user, staff=False)
    if assessment.status != "published":
        raise ApiError(
            status_code=409, code="ASSESSMENT_NOT_OPEN", message="测验未开放"
        )
    now = datetime.now(UTC)
    if assessment.opens_at and now < assessment.opens_at:
        raise ApiError(status_code=409, code="ASSESSMENT_NOT_OPEN", message="测验尚未开始")
    if assessment.closes_at and now > assessment.closes_at:
        raise ApiError(status_code=409, code="ASSESSMENT_CLOSED", message="测验已结束")
    existing = (
        await db.execute(
            select(Attempt).where(
                Attempt.assessment_id == assessment_id,
                Attempt.user_id == user.id,
                Attempt.status == "in_progress",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return ok(
            request, {"attempt_id": existing.id, "resumed": True}, status_code=200
        )
    attempt = Attempt(assessment_id=assessment_id, user_id=user.id)
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt, attribute_names=["id"])
    return ok(request, {"attempt_id": attempt.id, "resumed": False}, status_code=201)


async def _get_owned_attempt(
    db: AsyncSession, attempt_id: str, user: User
) -> Attempt:
    attempt = (
        await db.execute(select(Attempt).where(Attempt.id == attempt_id).limit(1))
    ).scalar_one_or_none()
    if attempt is None or attempt.user_id != user.id:
        raise ApiError(
            status_code=404, code="ATTEMPT_NOT_FOUND", message="作答记录不存在或无权访问"
        )
    return attempt


@router.put("/attempts/{attempt_id}/answers/{question_version_id}", response_model=None)
async def save_answer(
    attempt_id: str,
    question_version_id: str,
    body: AnswerSave,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    attempt = await _get_owned_attempt(db, attempt_id, user)
    if attempt.status != "in_progress":
        raise ApiError(
            status_code=409, code="ATTEMPT_SUBMITTED", message="已提交，不能修改答案"
        )
    item = (
        await db.execute(
            select(AssessmentItem).where(
                AssessmentItem.assessment_id == attempt.assessment_id,
                AssessmentItem.question_version_id == question_version_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise ApiError(
            status_code=404, code="QUESTION_NOT_IN_ASSESSMENT", message="题目不在本测验中"
        )
    answer = (
        await db.execute(
            select(AttemptAnswer).where(
                AttemptAnswer.attempt_id == attempt_id,
                AttemptAnswer.question_version_id == question_version_id,
            )
        )
    ).scalar_one_or_none()
    if answer is None:
        if body.answer_version != 1:
            raise ApiError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="答案版本冲突",
                details={"expected_version": body.answer_version, "actual_version": 0},
            )
        answer = AttemptAnswer(
            attempt_id=attempt_id,
            question_version_id=question_version_id,
            response=body.response,
            client_saved_at=body.client_saved_at,
        )
        db.add(answer)
    else:
        if answer.version != body.answer_version:
            raise ApiError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="答案已被更新，请刷新后重试",
                details={
                    "expected_version": body.answer_version,
                    "actual_version": answer.version,
                },
            )
        answer.response = body.response
        answer.client_saved_at = body.client_saved_at
        answer.version += 1
    await db.commit()
    return ok(
        request,
        {"answer_version": answer.version, "server_saved_at": datetime.now(UTC).isoformat()},
    )


def _grade_objective(version: QuestionVersion, response: dict | None) -> bool | None:
    if version.type not in OBJECTIVE_TYPES:
        return None
    answer = version.answer or {}
    correct_keys = set(answer.get("correct_keys") or [])
    given = response.get("selected_keys") if response else None
    if version.type == "true_false":
        expected = answer.get("correct")
        return isinstance(given, bool) and given == expected
    if not isinstance(given, list):
        return False
    return set(map(str, given)) == correct_keys


@router.post("/attempts/{attempt_id}/submit", response_model=None)
async def submit_attempt(
    attempt_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    attempt = await _get_owned_attempt(db, attempt_id, user)
    if attempt.status in ("submitted", "graded"):
        return ok(
            request,
            {
                "attempt_id": attempt.id,
                "submitted_at": attempt.submitted_at.isoformat()
                if attempt.submitted_at
                else None,
                "score": attempt.score,
                "grading_status": attempt.grading_status,
                "idempotent_replay": True,
            },
        )
    assessment = await db.get(Assessment, attempt.assessment_id)
    now = datetime.now(UTC)
    if assessment and assessment.closes_at and now > assessment.closes_at:
        raise ApiError(status_code=409, code="ASSESSMENT_CLOSED", message="测验已结束")

    rows = (
        await db.execute(
            select(AssessmentItem, QuestionVersion, AttemptAnswer)
            .join(
                QuestionVersion,
                QuestionVersion.id == AssessmentItem.question_version_id,
            )
            .outerjoin(
                AttemptAnswer,
                (AttemptAnswer.question_version_id == AssessmentItem.question_version_id)
                & (AttemptAnswer.attempt_id == attempt_id),
            )
            .where(AssessmentItem.assessment_id == attempt.assessment_id)
            .order_by(AssessmentItem.order_no.asc())
        )
    ).all()

    total_score = 0.0
    has_subjective = False
    wrong_versions: list[tuple[float, str]] = []
    for item, version, answer in rows:
        correctness = _grade_objective(version, answer.response if answer else None)
        if correctness is None:
            has_subjective = True
            continue
        if answer:
            answer.is_correct = correctness
            answer.points_earned = item.points if correctness else 0.0
        if correctness:
            total_score += item.points
        else:
            wrong_versions.append((item.points, version.id))

    attempt.status = "graded" if not has_subjective else "submitted"
    attempt.score = total_score
    attempt.grading_status = "graded" if not has_subjective else "pending_teacher"
    attempt.submitted_at = now
    if assessment is not None:
        from app.modules.memory import service as memory_service

        hints_by_default = 0
        for _item, version, answer in rows:
            correctness = None
            if answer is not None:
                correctness = answer.is_correct
            if correctness is None:
                continue
            knowledge_points = [
                kp for kp in (version.knowledge_point_ids or []) if isinstance(kp, str)
            ][:5] or [f"{version.stem[:30]}"]
            await memory_service.record_evidence(
                db,
                user_id=attempt.user_id,
                course_id=assessment.course_id,
                knowledge_points=knowledge_points,
                question_version_id=version.id,
                attempt_id=attempt.id,
                source_type="formal_quiz",
                hints_used=hints_by_default,
                correct=correctness,
            )
        await memory_service.recompute_mastery(
            db, user_id=attempt.user_id, course_id=assessment.course_id
        )
        await memory_service.update_memory_after_submit(
            db,
            user_id=attempt.user_id,
            course_id=assessment.course_id,
            attempt_id=attempt.id,
        )
        await memory_service.promote_weakness_if_mastered(
            db, user_id=attempt.user_id, course_id=assessment.course_id
        )
        for _points, version_id in wrong_versions:
            db.add(
                ReviewTask(
                    user_id=attempt.user_id,
                    course_id=assessment.course_id,
                    question_version_id=version_id,
                    source_attempt_id=attempt.id,
                    reason="wrong_answer",
                    due_at=now + timedelta(days=1),
                )
            )
    await db.commit()
    return ok(
        request,
        {
            "attempt_id": attempt.id,
            "submitted_at": attempt.submitted_at.isoformat(),
            "score": attempt.score,
            "grading_status": attempt.grading_status,
        },
    )


@router.get("/attempts/{attempt_id}/result", response_model=None)
async def get_attempt_result(
    attempt_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    attempt = await _get_owned_attempt(db, attempt_id, user)
    assessment = await db.get(Assessment, attempt.assessment_id)
    rows = (
        await db.execute(
            select(AssessmentItem, QuestionVersion, AttemptAnswer)
            .join(
                QuestionVersion,
                QuestionVersion.id == AssessmentItem.question_version_id,
            )
            .outerjoin(
                AttemptAnswer,
                (AttemptAnswer.question_version_id == AssessmentItem.question_version_id)
                & (AttemptAnswer.attempt_id == attempt_id),
            )
            .where(AssessmentItem.assessment_id == attempt.assessment_id)
            .order_by(AssessmentItem.order_no.asc())
        )
    ).all()
    after_submit = assessment is not None and assessment.ai_policy == "full_after_submit"
    items = []
    for item, version, answer in rows:
        entry = {
            "question_version_id": version.id,
            "type": version.type,
            "stem": version.stem,
            "response": answer.response if answer else None,
            "points": item.points,
            "points_earned": answer.points_earned if answer else None,
            "is_correct": answer.is_correct if answer else None,
        }
        if after_submit or attempt.status == "graded":
            entry["explanation"] = version.explanation
        items.append(entry)
    return ok(
        request,
        {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "score": attempt.score,
            "grading_status": attempt.grading_status,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "items": items,
        },
    )
