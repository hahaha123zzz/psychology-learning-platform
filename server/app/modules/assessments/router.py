from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    Assessment,
    AssessmentItem,
    Attempt,
    AttemptAnswer,
    ClassMember,
    CourseClass,
    CourseRelease,
    CourseReleaseAssignment,
    Question,
    QuestionPurposeApproval,
    QuestionVersion,
    ReviewTask,
    RubricVersion,
    ScoreRecord,
    User,
    WrongAnswerTrace,
)
from app.db.session import get_db_session
from app.modules.assessments import policy as assessment_policy
from app.modules.assessments import service as assessment_service
from app.modules.assessments.schemas import (
    AnswerFlagUpdate,
    AnswerSave,
    AssessmentCreate,
    AssessmentPreview,
    AssessmentResultsRelease,
    QuestionCreate,
    QuestionPurposeDecision,
    QuestionReview,
    RubricApproval,
    RubricCreate,
    TeacherGradeSubmit,
)
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.learning_events import qualification as learning_qualification
from app.modules.learning_events import service as learning_event_service

router = APIRouter()

OBJECTIVE_TYPES = {"single", "multiple", "true_false"}


async def _attempt_release_binding(
    db: AsyncSession, assessment: Assessment, user: User
) -> tuple[str | None, str | None]:
    """Resolve one runnable release only inside the student's active class scopes."""
    base = (
        select(CourseReleaseAssignment, CourseRelease)
        .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
        .join(ClassMember, ClassMember.class_id == CourseClass.id)
        .join(CourseRelease, CourseRelease.id == CourseReleaseAssignment.course_release_id)
        .where(
            CourseReleaseAssignment.course_id == assessment.course_id,
            CourseReleaseAssignment.status == "active",
            CourseClass.course_id == assessment.course_id,
            CourseClass.status == "active",
            ClassMember.user_id == user.id,
            ClassMember.status == "active",
            CourseRelease.course_id == assessment.course_id,
        )
    )
    if assessment.course_release_assignment_id is not None:
        base = base.where(
            CourseReleaseAssignment.id == assessment.course_release_assignment_id
        )
    rows = (await db.execute(base)).all()
    if not rows:
        if assessment.course_release_assignment_id is not None:
            raise ApiError(
                status_code=409,
                code="ASSESSMENT_RELEASE_UNAVAILABLE",
                message="测评对应的课程版本当前不可用",
            )
        # Legacy assessments without a release assignment remain launchable only
        # when the student's active class scopes have no applicable assignment.
        scoped_assignments = await db.scalar(
            select(CourseReleaseAssignment.id)
            .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
            .join(ClassMember, ClassMember.class_id == CourseClass.id)
            .where(
                CourseReleaseAssignment.course_id == assessment.course_id,
                CourseReleaseAssignment.status == "active",
                CourseClass.course_id == assessment.course_id,
                CourseClass.status == "active",
                ClassMember.user_id == user.id,
                ClassMember.status == "active",
            )
            .limit(1)
        )
        if scoped_assignments is not None:
            raise ApiError(
                status_code=409,
                code="ASSESSMENT_RELEASE_UNAVAILABLE",
                message="班级当前没有可用于测评的已发布课程版本",
            )
        return None, None

    runnable = [
        (assignment, release)
        for assignment, release in rows
        if release.status == "published"
    ]
    if not runnable:
        raise ApiError(
            status_code=409,
            code="ASSESSMENT_RELEASE_UNAVAILABLE",
            message="班级当前没有可用于测评的已发布课程版本",
        )
    if len(runnable) > 1:
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_CONTEXT_AMBIGUOUS",
            message="该课程在多个班级有可用版本，请从明确的班级入口启动测评",
        )
    assignment, release = runnable[0]
    return assignment.id, release.id


async def _require_attempt_release_scope(
    db: AsyncSession, assessment: Assessment, attempt: Attempt, user: User
) -> None:
    """Keep historical bindings stable while requiring current class membership."""
    if attempt.course_release_assignment_id is None:
        return
    member_exists = await db.scalar(
        select(ClassMember.id)
        .join(CourseClass, CourseClass.id == ClassMember.class_id)
        .join(
            CourseReleaseAssignment,
            CourseReleaseAssignment.class_id == CourseClass.id,
        )
        .where(
            CourseReleaseAssignment.id == attempt.course_release_assignment_id,
            CourseReleaseAssignment.course_id == assessment.course_id,
            CourseReleaseAssignment.course_release_id == attempt.course_release_id,
            CourseClass.course_id == assessment.course_id,
            CourseClass.status == "active",
            ClassMember.user_id == user.id,
            ClassMember.status == "active",
        )
        .limit(1)
    )
    if member_exists is None:
        raise ApiError(
            status_code=404,
            code="ATTEMPT_NOT_FOUND",
            message="作答记录不存在或无权访问",
        )


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


@router.post(
    "/courses/{course_id}/question-versions/{question_version_id}/quality-feedback",
    response_model=None,
)
async def submit_question_quality_feedback(
    course_id: str,
    question_version_id: str,
    body: assessment_service.QualityFeedbackCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    feedback, replay = await assessment_service.create_quality_feedback(
        db,
        course_id=course_id,
        question_version_id=question_version_id,
        user=user,
        body=body,
    )
    return ok(
        request,
        {
            "id": feedback.id,
            "status": feedback.status,
            "category": feedback.category,
            "created_at": feedback.created_at.isoformat(),
        },
        status_code=200 if replay else 201,
        idempotent_replay=replay,
    )


@router.get("/courses/{course_id}/question-quality-feedback", response_model=None)
async def list_question_quality_feedback(
    course_id: str,
    request: Request,
    status: str | None = Query(
        default="pending", pattern="^(pending|accepted|rejected|invalidated)$"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    feedback = await assessment_service.list_quality_feedback(
        db, course_id=course_id, user=user, status=status, limit=limit
    )
    return ok(request, feedback, has_more=False)


@router.put(
    "/courses/{course_id}/question-quality-feedback/{feedback_id}/resolve",
    response_model=None,
)
async def resolve_question_quality_feedback(
    course_id: str,
    feedback_id: str,
    body: assessment_service.QualityFeedbackResolution,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    result, replay = await assessment_service.resolve_quality_feedback(
        db,
        course_id=course_id,
        feedback_id=feedback_id,
        user=user,
        body=body,
    )
    return ok(request, result, idempotent_replay=replay)


# ---- 测验 ----

@router.post("/courses/{course_id}/rubrics", response_model=None)
async def create_rubric_version(
    course_id: str,
    body: RubricCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    rubric = await assessment_service.create_rubric_version(
        db, course_id=course_id, user=user, body=body
    )
    return ok(request, {
        "id": rubric.id,
        "question_version_id": rubric.question_version_id,
        "version_no": rubric.version_no,
        "criteria": rubric.criteria,
        "max_score": rubric.max_score,
        "evidence_refs": rubric.evidence_refs,
        "status": rubric.status,
    }, status_code=201)


@router.post("/rubrics/{rubric_id}/approve", response_model=None)
async def approve_rubric_version(
    rubric_id: str,
    body: RubricApproval,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    rubric = await assessment_service.approve_rubric_version(
        db, rubric_id=rubric_id, user=user, reason=body.reason
    )
    return ok(
        request,
        {
            "id": rubric.id,
            "status": rubric.status,
            "approved_at": rubric.approved_at.isoformat(),
        },
    )


@router.get("/courses/{course_id}/rubrics", response_model=None)
async def list_rubric_versions(
    course_id: str,
    request: Request,
    question_version_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    await assessment_service._question_version_in_course(
        db, course_id=course_id, question_version_id=question_version_id
    )
    rows = await db.scalars(
        select(RubricVersion)
        .where(RubricVersion.question_version_id == question_version_id)
        .order_by(RubricVersion.version_no.desc())
    )
    return ok(request, [
        {
            "id": row.id,
            "version_no": row.version_no,
            "criteria": row.criteria,
            "max_score": row.max_score,
            "evidence_refs": row.evidence_refs,
            "status": row.status,
            "created_by": row.created_by,
            "approved_by": row.approved_by,
        }
        for row in rows
    ])


@router.post(
    "/courses/{course_id}/question-versions/{question_version_id}/purpose/{purpose}",
    response_model=None,
)
async def decide_question_purpose(
    course_id: str,
    question_version_id: str,
    purpose: str,
    body: QuestionPurposeDecision,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if purpose not in {"practice", "formal"}:
        raise ApiError(422, "QUESTION_PURPOSE_INVALID", "题目用途只能是 practice 或 formal")
    decision = await assessment_service.decide_question_purpose(
        db,
        course_id=course_id,
        question_version_id=question_version_id,
        purpose=purpose,
        decision=body.decision,
        reason=body.reason,
        user=user,
    )
    return ok(request, {
        "id": decision.id,
        "question_version_id": decision.question_version_id,
        "purpose": decision.purpose,
        "decision": decision.decision,
        "reason": decision.reason,
    }, status_code=201)


@router.post("/courses/{course_id}/assessments/preview", response_model=None)
async def preview_assessment(
    course_id: str,
    body: AssessmentPreview,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    if len(body.question_ids) != len(set(body.question_ids)):
        raise ApiError(422, "ASSESSMENT_QUESTIONS_DUPLICATED", "测评题目不能重复")
    _validate_assessment_schedule(body.opens_at, body.closes_at)
    versions = await _resolve_assessment_questions(db, course_id, body.question_ids)
    policy = body.result_visibility_policy or _default_result_policy(body.purpose, versions)
    issues = _assessment_config_issues(
        purpose=body.purpose,
        policy=policy,
        closes_at=body.closes_at,
        versions=versions,
    )
    total = 0.0
    preview_items = []
    for version in versions:
        rubric_id = body.rubric_version_ids.get(version.id)
        rubric = await db.get(RubricVersion, rubric_id) if rubric_id else None
        points = rubric.max_score if rubric else body.points_per_question
        total += points
        preview_items.append({
            "question_version_id": version.id,
            "type": version.type,
            "stem": version.stem,
            "points": points,
            "rubric_version_id": rubric.id if rubric else None,
            "rubric_status": rubric.status if rubric else None,
        })
        if body.purpose == "formal":
            approval = await db.scalar(
                select(QuestionPurposeApproval)
                .where(
                    QuestionPurposeApproval.question_version_id == version.id,
                    QuestionPurposeApproval.purpose == "formal",
                )
                .order_by(
                    QuestionPurposeApproval.created_at.desc(),
                    QuestionPurposeApproval.id.desc(),
                )
                .limit(1)
            )
            if approval is None or approval.decision != "approved":
                issues.append(
                    {
                        "code": "FORMAL_PURPOSE_NOT_APPROVED",
                        "question_version_id": version.id,
                        "message": "题目尚无正式测评用途批准",
                    }
                )
            if version.type not in OBJECTIVE_TYPES and (
                rubric is None
                or rubric.question_version_id != version.id
                or rubric.status != "approved"
            ):
                issues.append(
                    {
                        "code": "APPROVED_RUBRIC_REQUIRED",
                        "question_version_id": version.id,
                        "message": "主观题缺少已批准评分 Rubric",
                    }
                )
    return ok(
        request,
        {
            "title": body.title,
            "purpose": body.purpose,
            "result_visibility_policy": policy,
            "total_points": total,
            "items": preview_items,
            "blocking_issues": issues,
            "can_publish": not issues,
        },
    )


def _default_result_policy(purpose: str, versions: list[QuestionVersion]) -> str:
    if purpose == "practice":
        return "immediate_after_submission"
    if any(version.type not in OBJECTIVE_TYPES for version in versions):
        return "after_grading"
    return "after_close"


def _validate_assessment_schedule(opens_at: datetime | None, closes_at: datetime | None) -> None:
    for value in (opens_at, closes_at):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ApiError(
                422,
                "ASSESSMENT_SCHEDULE_TIMEZONE_REQUIRED",
                "开放和截止时间必须包含时区",
            )
    if opens_at and closes_at and closes_at <= opens_at:
        raise ApiError(422, "ASSESSMENT_SCHEDULE_INVALID", "截止时间必须晚于开放时间")


def _assessment_config_issues(
    *,
    purpose: str,
    policy: str,
    closes_at: datetime | None,
    versions: list[QuestionVersion],
) -> list[dict]:
    issues = []
    if purpose == "formal" and policy == "immediate_after_submission":
        issues.append(
            {
                "code": "FORMAL_RESULT_POLICY_INVALID",
                "message": "正式测评不能在提交后立即开放结果",
            }
        )
    if policy == "after_close" and closes_at is None:
        issues.append(
            {
                "code": "RESULT_CLOSE_REQUIRED",
                "message": "按截止时间开放结果需要设置截止时间",
            }
        )
    if purpose == "formal" and policy == "after_close" and any(
        version.type not in OBJECTIVE_TYPES for version in versions
    ):
        issues.append(
            {
                "code": "AFTER_CLOSE_REQUIRES_OBJECTIVE_GRADING",
                "message": "含主观题的正式测评应在评分完成后或教师手动发布结果",
            }
        )
    return issues


async def _resolve_assessment_questions(
    db: AsyncSession, course_id: str, question_ids: list[str]
) -> list[QuestionVersion]:
    versions: list[QuestionVersion] = []
    for question_id in question_ids:
        question = await db.scalar(
            select(Question).where(Question.id == question_id, Question.course_id == course_id)
        )
        if question is None or question.status != "published":
            raise ApiError(
                409,
                "QUESTION_NOT_PUBLISHED",
                "只能使用已发布题目组卷",
                details={"question_id": question_id},
            )
        version = await db.get(QuestionVersion, question.current_version_id)
        if version is None:
            raise ApiError(
                409,
                "QUESTION_NOT_PUBLISHED",
                "题目缺少可用版本",
                details={"question_id": question_id},
            )
        versions.append(version)
    return versions

@router.post("/courses/{course_id}/assessments", response_model=None)
async def create_assessment(
    course_id: str,
    body: AssessmentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    if len(body.question_ids) != len(set(body.question_ids)):
        raise ApiError(422, "ASSESSMENT_QUESTIONS_DUPLICATED", "测评题目不能重复")
    _validate_assessment_schedule(body.opens_at, body.closes_at)
    versions = await _resolve_assessment_questions(db, course_id, body.question_ids)
    policy = body.result_visibility_policy or _default_result_policy(body.purpose, versions)
    issues = _assessment_config_issues(
        purpose=body.purpose,
        policy=policy,
        closes_at=body.closes_at,
        versions=versions,
    )
    if issues:
        raise ApiError(
            422,
            issues[0]["code"],
            issues[0]["message"],
            details={"blocking_issues": issues},
        )
    for version in versions:
        rubric_id = body.rubric_version_ids.get(version.id)
        if rubric_id:
            rubric = await db.get(RubricVersion, rubric_id)
            if (
                rubric is None
                or rubric.question_version_id != version.id
                or rubric.status not in {"draft", "approved"}
            ):
                raise ApiError(422, "RUBRIC_VERSION_INVALID", "Rubric 必须属于所选题目版本")
        elif body.purpose == "formal" and version.type not in OBJECTIVE_TYPES:
            # Drafts remain editable, while publication stays blocked until a Rubric is attached.
            continue
    assessment = Assessment(
        course_id=course_id,
        title=body.title,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
        ai_policy=body.ai_policy,
        purpose=body.purpose,
        result_visibility_policy=policy,
        created_by=user.id,
    )
    db.add(assessment)
    await db.flush()
    for order_no, version in enumerate(versions, start=1):
        rubric_id = body.rubric_version_ids.get(version.id)
        rubric = await db.get(RubricVersion, rubric_id) if rubric_id else None
        db.add(
            AssessmentItem(
                assessment_id=assessment.id,
                question_version_id=version.id,
                points=rubric.max_score if rubric else body.points_per_question,
                order_no=order_no,
                rubric_version_id=rubric_id,
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
    issues = await assessment_service.assessment_publish_issues(db, assessment=assessment)
    if issues:
        raise ApiError(
            status_code=409,
            code="ASSESSMENT_PUBLISH_BLOCKED",
            message="测评未通过用途、Rubric 或结果可见策略门禁",
            details={"blocking_issues": issues},
        )
    assessment.status = "published"
    assessment.version += 1
    await db.commit()
    return ok(
        request,
        {"id": assessment.id, "status": assessment.status, "version": assessment.version},
    )


def _assessment_availability(assessment: Assessment, now: datetime) -> str:
    if assessment.status != "published":
        return assessment.status
    if assessment.opens_at and now < assessment.opens_at:
        return "scheduled"
    if assessment.closes_at and now > assessment.closes_at:
        return "closed"
    return "open"


@router.get("/courses/{course_id}/assessments", response_model=None)
async def list_assessments(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    role = await require_course_role(
        course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    staff = role in ("teacher", "assistant")
    query = select(Assessment).where(Assessment.course_id == course_id)
    if not staff:
        query = query.where(Assessment.status == "published")
    rows = (
        await db.execute(query.order_by(Assessment.created_at.desc(), Assessment.id.desc()))
    ).scalars()
    assessments = list(rows)
    current_attempt_ids: dict[str, str] = {}
    latest_completed_attempt_ids: dict[str, str] = {}
    if not staff and assessments:
        active_attempts = await db.execute(
            select(Attempt.assessment_id, Attempt.id)
            .where(
                Attempt.assessment_id.in_([assessment.id for assessment in assessments]),
                Attempt.user_id == user.id,
                Attempt.status == "in_progress",
            )
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        )
        for assessment_id, attempt_id in active_attempts.all():
            current_attempt_ids.setdefault(assessment_id, attempt_id)
        completed_attempts = await db.execute(
            select(Attempt.assessment_id, Attempt.id)
            .where(
                Attempt.assessment_id.in_([assessment.id for assessment in assessments]),
                Attempt.user_id == user.id,
                Attempt.status.in_(("submitted", "graded")),
            )
            .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        )
        for assessment_id, attempt_id in completed_attempts.all():
            latest_completed_attempt_ids.setdefault(assessment_id, attempt_id)
    now = datetime.now(UTC)
    return ok(
        request,
        [
            {
                "id": assessment.id,
                "title": assessment.title,
                "status": assessment.status,
                "availability": _assessment_availability(assessment, now),
                "ai_policy": assessment.ai_policy,
                "purpose": assessment.purpose,
                "result_visibility_policy": assessment.result_visibility_policy,
                "version": assessment.version,
                "results_released_at": (
                    assessment.results_released_at.isoformat()
                    if assessment.results_released_at
                    else None
                ),
                "opens_at": assessment.opens_at.isoformat()
                if assessment.opens_at
                else None,
                "closes_at": assessment.closes_at.isoformat()
                if assessment.closes_at
                else None,
                "current_attempt_id": current_attempt_ids.get(assessment.id),
                "latest_completed_attempt_id": latest_completed_attempt_ids.get(assessment.id),
            }
            for assessment in assessments
        ],
        has_more=False,
    )


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
    staff = role in ("teacher", "assistant")
    if not staff:
        if assessment.status != "published":
            raise ApiError(
                status_code=404,
                code="ASSESSMENT_NOT_FOUND",
                message="测验不存在或无权访问",
            )
        now = datetime.now(UTC)
        if assessment.opens_at and now < assessment.opens_at:
            raise ApiError(
                status_code=409,
                code="ASSESSMENT_NOT_OPEN",
                message="测验尚未开始",
                details={"opens_at": assessment.opens_at.isoformat()},
            )
        if assessment.closes_at and now > assessment.closes_at:
            raise ApiError(
                status_code=409,
                code="ASSESSMENT_CLOSED",
                message="测验已结束",
                details={"closes_at": assessment.closes_at.isoformat()},
            )
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
            entry["rubric_version_id"] = item.rubric_version_id
            entry["explanation"] = version.explanation
            entry["evidence_ids"] = version.evidence_ids
        items.append(entry)
    data = {
        "id": assessment.id,
        "title": assessment.title,
        "status": assessment.status,
        "ai_policy": assessment.ai_policy,
        "purpose": assessment.purpose,
        "result_visibility_policy": assessment.result_visibility_policy,
        "opens_at": assessment.opens_at.isoformat() if assessment.opens_at else None,
        "closes_at": assessment.closes_at.isoformat() if assessment.closes_at else None,
        "items": items,
    }
    return ok(request, data)


# ---- 作答 ----

async def _attempt_out(db: AsyncSession, attempt: Attempt, *, resumed: bool) -> dict:
    answers = (
        await db.execute(
            select(AttemptAnswer)
            .where(AttemptAnswer.attempt_id == attempt.id)
            .order_by(AttemptAnswer.question_version_id.asc())
        )
    ).scalars()
    return {
        "attempt_id": attempt.id,
        "resumed": resumed,
        "answers": [
            {
                "question_version_id": answer.question_version_id,
                "response": answer.response,
                "answer_version": answer.version,
                "flagged": answer.flagged,
            }
            for answer in answers
        ],
    }

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
        await _require_attempt_release_scope(db, assessment, existing, user)
        return ok(request, await _attempt_out(db, existing, resumed=True), status_code=200)
    invalidated_question = await db.scalar(
        select(QuestionVersion.id)
        .join(AssessmentItem, AssessmentItem.question_version_id == QuestionVersion.id)
        .join(Question, Question.id == QuestionVersion.question_id)
        .where(
            AssessmentItem.assessment_id == assessment_id,
            Question.status == "archived",
        )
        .limit(1)
    )
    if invalidated_question is not None:
        raise ApiError(
            status_code=409,
            code="ASSESSMENT_QUESTION_INVALIDATED",
            message="该测评包含已归档为无效的题目，不能开始新的作答",
        )
    assignment_id, release_id = await _attempt_release_binding(db, assessment, user)
    attempt = Attempt(
        assessment_id=assessment_id,
        user_id=user.id,
        course_release_assignment_id=assignment_id,
        course_release_id=release_id,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt, attribute_names=["id"])
    return ok(request, await _attempt_out(db, attempt, resumed=False), status_code=201)


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
    if attempt.course_release_assignment_id is not None:
        assessment = await db.get(Assessment, attempt.assessment_id)
        if assessment is None:
            raise ApiError(
                status_code=404,
                code="ATTEMPT_NOT_FOUND",
                message="作答记录不存在或无权访问",
            )
        await _require_attempt_release_scope(db, assessment, attempt, user)
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
    assessment = await db.get(Assessment, attempt.assessment_id)
    if assessment is None:
        raise ApiError(status_code=404, code="ASSESSMENT_NOT_FOUND", message="测验不存在")
    now = datetime.now(UTC)
    is_closed = assessment.status != "published" or (
        assessment.closes_at and now > assessment.closes_at
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
    if (
        answer is not None
        and answer.version == body.answer_version + 1
        and answer.response == body.response
        and answer.client_saved_at == body.client_saved_at
    ):
        return ok(
            request,
            {
                "answer_version": answer.version,
                "server_saved_at": datetime.now(UTC).isoformat(),
            },
            idempotent_replay=True,
        )
    if is_closed:
        raise ApiError(
            status_code=409,
            code="ASSESSMENT_CLOSED",
            message="测验已结束，不能继续保存答案",
            details={
                "closes_at": assessment.closes_at.isoformat()
                if assessment.closes_at
                else None
            },
        )
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
            # answer_version=1 是“尚无已保存答案”的初始版本；首次成功写入必须推进版本。
            version=body.answer_version + 1,
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


@router.put(
    "/attempts/{attempt_id}/answers/{question_version_id}/flag", response_model=None
)
async def update_answer_flag(
    attempt_id: str,
    question_version_id: str,
    body: AnswerFlagUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    attempt = await _get_owned_attempt(db, attempt_id, user)
    if attempt.status != "in_progress":
        raise ApiError(
            status_code=409, code="ATTEMPT_SUBMITTED", message="已提交，不能标记题目"
        )
    assessment = await db.get(Assessment, attempt.assessment_id)
    if assessment is None:
        raise ApiError(status_code=404, code="ASSESSMENT_NOT_FOUND", message="测验不存在")
    now = datetime.now(UTC)
    is_closed = assessment.status != "published" or (
        assessment.closes_at and now > assessment.closes_at
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
    if (
        answer is not None
        and answer.version == body.answer_version + 1
        and answer.flagged == body.flagged
    ):
        return ok(
            request,
            {"answer_version": answer.version, "flagged": answer.flagged},
            idempotent_replay=True,
        )
    if is_closed:
        raise ApiError(
            status_code=409,
            code="ASSESSMENT_CLOSED",
            message="测验已结束，不能标记题目",
            details={
                "closes_at": assessment.closes_at.isoformat()
                if assessment.closes_at
                else None
            },
        )
    if answer is None:
        raise ApiError(
            status_code=409,
            code="ANSWER_REQUIRED_TO_FLAG",
            message="先保存作答后才能标记题目",
        )
    if answer.version != body.answer_version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="答案已被更新，请刷新后重试",
            details={"expected_version": body.answer_version, "actual_version": answer.version},
        )
    answer.flagged = body.flagged
    answer.version += 1
    await db.commit()
    return ok(
        request,
        {"answer_version": answer.version, "flagged": answer.flagged},
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
    attempt = await db.scalar(
        select(Attempt)
        .where(Attempt.id == attempt_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None or attempt.user_id != user.id:
        raise ApiError(
            status_code=404, code="ATTEMPT_NOT_FOUND", message="作答记录不存在或无权访问"
        )
    assessment = await db.get(Assessment, attempt.assessment_id)
    if assessment is None:
        raise ApiError(404, "ASSESSMENT_NOT_FOUND", "测验不存在")
    if attempt.status in ("submitted", "graded"):
        return ok(
            request,
            {
                "attempt_id": attempt.id,
                "submitted_at": attempt.submitted_at.isoformat()
                if attempt.submitted_at
                else None,
                "score": (
                    attempt.score
                    if assessment_policy.result_is_visible(
                        assessment, attempt, now=datetime.now(UTC)
                    )
                    else None
                ),
                "grading_status": attempt.grading_status,
                "idempotent_replay": True,
            },
        )
    now = datetime.now(UTC)
    # closes_at freezes answer/flag writes; an active attempt may still be finalized
    # afterward so a client-side timeout can seal the server-persisted answer snapshot.

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
    question_version_ids = [version.id for _item, version, _answer in rows]
    invalidated_question_version_ids = set(
        (
            await db.execute(
                select(QuestionVersion.id)
                .join(Question, Question.id == QuestionVersion.question_id)
                .where(
                    QuestionVersion.id.in_(question_version_ids),
                    Question.status == "archived",
                )
            )
        ).scalars()
    ) if question_version_ids else set()

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
            db.add(
                WrongAnswerTrace(
                    attempt_id=attempt.id,
                    user_id=attempt.user_id,
                    course_id=assessment.course_id if assessment else "",
                    question_version_id=version.id,
                    answer_present=answer is not None,
                )
            )

    attempt.status = "graded" if not has_subjective else "submitted"
    attempt.score = total_score
    attempt.grading_status = "graded" if not has_subjective else "pending_teacher"
    attempt.submitted_at = now
    if assessment is not None:
        from app.modules.memory import service as memory_service

        for _item, version, answer in rows:
            if version.id in invalidated_question_version_ids:
                # 既有考试快照仍按原规则评分，但失效题不再产生掌握证据。
                continue
            correctness = None
            if answer is not None:
                correctness = answer.is_correct
            if correctness is None:
                continue
            event, _replay = await learning_event_service.append_event(
                db,
                user_id=attempt.user_id,
                course_id=assessment.course_id,
                event_key=f"assessment-answer:{attempt.id}:{version.id}",
                event_type="answer_submitted",
                source_type="assessment",
                source_ref=attempt.id,
                payload={"question_version_id": version.id},
                occurred_at=now,
            )
            await learning_qualification.qualify_event(db, event_id=event.id)
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
            if version_id in invalidated_question_version_ids:
                continue
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
            "score": (
                attempt.score
                if assessment_policy.result_is_visible(assessment, attempt, now=now)
                else None
            ),
            "grading_status": attempt.grading_status,
        },
    )


@router.get("/courses/{course_id}/grading-queue", response_model=None)
async def get_grading_queue(
    course_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    include_graded: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    queue = await assessment_service.list_grading_queue(
        db,
        course_id=course_id,
        user=user,
        limit=limit,
        include_graded=include_graded,
    )
    return ok(request, queue, has_more=False)


@router.get("/teacher/attempts/{attempt_id}/grading", response_model=None)
async def get_teacher_grading_detail(
    attempt_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    attempt, assessment = await assessment_service.get_teacher_attempt(
        db, attempt_id=attempt_id, user=user
    )
    detail = await assessment_service.get_grading_detail(
        db, attempt=attempt, assessment=assessment
    )
    return ok(request, detail)


@router.put("/teacher/attempts/{attempt_id}/grading", response_model=None)
async def submit_teacher_grading(
    attempt_id: str,
    body: TeacherGradeSubmit,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
        raise ApiError(
            status_code=422,
            code="IDEMPOTENCY_KEY_INVALID",
            message="幂等键不能为空且长度不能超过 128 个字符",
        )
    try:
        result, replay = await assessment_service.grade_attempt(
            db,
            attempt_id=attempt_id,
            user=user,
            body=body,
            idempotency_key=idempotency_key,
        )
    except IntegrityError:
        await db.rollback()
        if idempotency_key:
            endpoint, request_hash = assessment_service.grade_request_identity(
                attempt_id, body
            )
            replay_data = await assessment_service.find_idempotent_replay(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=endpoint,
                request_hash=request_hash,
            )
            if replay_data is not None:
                return ok(request, replay_data, idempotent_replay=True)
        raise ApiError(
            status_code=409,
            code="SCORE_VERSION_CONFLICT",
            message="成绩已由其他评分操作更新，请刷新后重试",
        ) from None
    return ok(request, result, idempotent_replay=replay)


@router.post("/assessments/{assessment_id}/release-results", response_model=None)
async def release_assessment_results(
    assessment_id: str,
    body: AssessmentResultsRelease,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    assessment = await _get_assessment_or_404(db, assessment_id, user)
    assessment = await db.scalar(
        select(Assessment)
        .where(Assessment.id == assessment.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if assessment is None:
        raise ApiError(404, "ASSESSMENT_NOT_FOUND", "测验不存在或无权访问")
    if assessment.result_visibility_policy != "manual_release":
        raise ApiError(409, "MANUAL_RELEASE_NOT_CONFIGURED", "此测评未配置人工发布结果策略")
    if assessment.results_released_at is not None:
        return ok(
            request,
            {
                "id": assessment.id,
                "results_released_at": assessment.results_released_at.isoformat(),
                "version": assessment.version,
            },
            idempotent_replay=True,
        )
    if assessment.version != body.expected_version:
        raise ApiError(
            409,
            "RESOURCE_VERSION_CONFLICT",
            "测评配置已更新，请刷新后重试",
            details={
                "expected_version": body.expected_version,
                "actual_version": assessment.version,
            },
        )
    pending = await db.scalar(
        select(Attempt.id)
        .where(
            Attempt.assessment_id == assessment.id,
            Attempt.status == "submitted",
            Attempt.grading_status == "pending_teacher",
        )
        .limit(1)
    )
    if pending is not None:
        raise ApiError(409, "GRADING_PENDING", "仍有作答等待人工评分，暂不能发布结果")
    assessment.results_released_at = datetime.now(UTC)
    assessment.version += 1
    await db.commit()
    return ok(request, {
        "id": assessment.id,
        "results_released_at": assessment.results_released_at.isoformat(),
        "version": assessment.version,
    })


@router.get("/attempts/{attempt_id}/result", response_model=None)
async def get_attempt_result(
    attempt_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    attempt = await _get_owned_attempt(db, attempt_id, user)
    assessment = await db.get(Assessment, attempt.assessment_id)
    if assessment is None:
        raise ApiError(404, "ASSESSMENT_NOT_FOUND", "测验不存在或无权访问")
    assessment_policy.require_result_visible(
        assessment, attempt, now=datetime.now(UTC)
    )
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
    after_submit = (
        assessment is not None
        and attempt.status in {"submitted", "graded"}
        and assessment.ai_policy == "full_after_submit"
    )
    latest_score = (
        await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.attempt_id == attempt.id)
            .order_by(ScoreRecord.score_version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    result_released = attempt.status == "graded"
    released_breakdown = {
        entry["question_version_id"]: entry
        for entry in (latest_score.breakdown if latest_score else [])
    }
    items = []
    for item, version, answer in rows:
        entry = {
            "question_version_id": version.id,
            "type": version.type,
            "stem": version.stem,
            "response": answer.response if answer else None,
            "points": item.points,
            "points_earned": (
                released_breakdown[version.id]["points_awarded"]
                if result_released and version.id in released_breakdown
                else answer.points_earned if answer and result_released else None
            ),
            "is_correct": answer.is_correct if answer and result_released else None,
        }
        if after_submit:
            entry["explanation"] = version.explanation
        items.append(entry)
    return ok(
        request,
        {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "score": (
                latest_score.score
                if latest_score
                else attempt.score if result_released else None
            ),
            "max_score": latest_score.max_score if latest_score else None,
            "score_version": latest_score.score_version if latest_score else None,
            "released_at": latest_score.released_at.isoformat() if latest_score else None,
            "grading_status": attempt.grading_status,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "items": items,
        },
    )
