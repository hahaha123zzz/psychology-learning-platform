import math
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import (
    Assessment,
    AssessmentItem,
    Attempt,
    AttemptAnswer,
    LearningEvent,
    LearningEvidence,
    MemoryItem,
    Question,
    QuestionPurposeApproval,
    QuestionQualityFeedback,
    QuestionVersion,
    ReviewTask,
    RubricVersion,
    ScoreRecord,
    TeacherGradingDecision,
    User,
)
from app.modules.assessments.schemas import TeacherGradeSubmit
from app.modules.auth.dependencies import require_course_role
from app.modules.courses import service as course_service


async def _question_version_in_course(
    db: AsyncSession, *, course_id: str, question_version_id: str
) -> tuple[QuestionVersion, Question]:
    row = await db.execute(
        select(QuestionVersion, Question)
        .join(Question, Question.id == QuestionVersion.question_id)
        .where(
            QuestionVersion.id == question_version_id,
            Question.course_id == course_id,
        )
    )
    result = row.one_or_none()
    if result is None:
        raise ApiError(
            status_code=404,
            code="QUESTION_VERSION_NOT_FOUND",
            message="题目版本不存在或无权访问",
        )
    return result


def _validate_rubric_content(
    *, criteria: list[dict[str, Any]], max_score: float,
    evidence_refs: list[str], question_evidence_ids: list[str],
    status_code: int = 422,
) -> None:
    def invalid(code: str, message: str) -> None:
        raise ApiError(status_code, code, message)

    keys = [str(criterion.get("key", "")).strip() for criterion in criteria]
    points = [float(criterion.get("points", 0)) for criterion in criteria]
    if (
        any(not key for key in keys)
        or len(keys) != len(set(keys))
        or any(not math.isfinite(value) or value <= 0 for value in points)
        or not math.isfinite(max_score)
        or max_score <= 0
        or abs(sum(points) - max_score) > 1e-6
    ):
        invalid(
            "RUBRIC_CRITERIA_INVALID",
            "Rubric 标准项 key 必须唯一，且分值总和必须等于满分",
        )

    question_evidence = set(question_evidence_ids)
    if (
        not question_evidence
        or not evidence_refs
        or len(set(evidence_refs)) != len(evidence_refs)
        or not set(evidence_refs).issubset(question_evidence)
    ):
        invalid(
            "RUBRIC_EVIDENCE_INVALID",
            "Rubric 依据必须来自当前题目版本的教材证据，且不能重复",
        )

    for criterion in criteria:
        anchors = criterion.get("anchors")
        criterion_points = float(criterion.get("points", 0))
        if not isinstance(anchors, dict) or len(anchors) < 2:
            invalid("RUBRIC_ANCHORS_INVALID", "每个标准项至少需要两个分值锚点")
        try:
            scores = [float(score) for score in anchors]
        except (TypeError, ValueError):
            invalid("RUBRIC_ANCHORS_INVALID", "评分锚点必须使用数值分值")
        if (
            any(not math.isfinite(score) for score in scores)
            or len(scores) != len(set(scores))
            or min(scores) < 0
            or abs(min(scores)) > 1e-6
            or abs(max(scores) - criterion_points) > 1e-6
        ):
            invalid(
                "RUBRIC_ANCHORS_INVALID",
                "评分锚点须唯一、位于 0 至标准项满分范围，并覆盖两端",
            )


async def create_rubric_version(
    db: AsyncSession, *, course_id: str, user: User, body
) -> RubricVersion:
    version, _question = await _question_version_in_course(
        db, course_id=course_id, question_version_id=body.question_version_id
    )
    if version.type in OBJECTIVE_TYPES:
        raise ApiError(422, "RUBRIC_NOT_REQUIRED", "客观题不能绑定主观题 Rubric")
    _validate_rubric_content(
        criteria=[item.model_dump(mode="json") for item in body.criteria],
        max_score=body.max_score,
        evidence_refs=body.evidence_refs,
        question_evidence_ids=version.evidence_ids or [],
    )
    current = await db.scalar(
        select(RubricVersion.version_no)
        .where(RubricVersion.question_version_id == version.id)
        .order_by(RubricVersion.version_no.desc())
        .limit(1)
    )
    rubric = RubricVersion(
        question_version_id=version.id,
        version_no=(current or 0) + 1,
        criteria=[item.model_dump(mode="json") for item in body.criteria],
        max_score=body.max_score,
        evidence_refs=body.evidence_refs,
        status="draft",
        created_by=user.id,
    )
    db.add(rubric)
    await db.commit()
    await db.refresh(rubric)
    return rubric


async def approve_rubric_version(
    db: AsyncSession, *, rubric_id: str, user: User, reason: str
) -> RubricVersion:
    rubric = await db.scalar(
        select(RubricVersion).where(RubricVersion.id == rubric_id).with_for_update()
    )
    if rubric is None:
        raise ApiError(404, "RUBRIC_NOT_FOUND", "Rubric 版本不存在或无权访问")
    row = await db.execute(
        select(QuestionVersion, Question)
        .join(Question, Question.id == QuestionVersion.question_id)
        .where(QuestionVersion.id == rubric.question_version_id)
    )
    found = row.one_or_none()
    if found is None:
        raise ApiError(404, "RUBRIC_NOT_FOUND", "Rubric 版本不存在或无权访问")
    version, question = found
    await require_course_role(question.course_id, user, db, roles={"teacher"})
    if rubric.status != "draft":
        raise ApiError(409, "RUBRIC_NOT_DRAFT", "只有草稿 Rubric 可以审核")
    if rubric.created_by == user.id:
        raise ApiError(403, "RUBRIC_SELF_REVIEW", "Rubric 作者不能审核自己的评分依据")
    _validate_rubric_content(
        criteria=rubric.criteria,
        max_score=rubric.max_score,
        evidence_refs=rubric.evidence_refs,
        question_evidence_ids=version.evidence_ids or [],
        status_code=409,
    )
    rubric.status = "approved"
    rubric.approved_by = user.id
    rubric.approved_at = datetime.now(UTC)
    rubric.approval_reason = reason.strip()
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="assessment.rubric_approved",
        resource_type="rubric_version",
        resource_id=rubric.id,
        course_id=question.course_id,
        detail={
            "question_version_id": rubric.question_version_id,
            "reason": rubric.approval_reason,
        },
    )
    await db.commit()
    await db.refresh(rubric)
    return rubric


async def decide_question_purpose(
    db: AsyncSession,
    *,
    course_id: str,
    question_version_id: str,
    purpose: str,
    decision: str,
    reason: str,
    user: User,
) -> QuestionPurposeApproval:
    _version, question = await _question_version_in_course(
        db, course_id=course_id, question_version_id=question_version_id
    )
    await require_course_role(course_id, user, db, roles={"teacher"})
    if question.status not in {"approved", "published"}:
        raise ApiError(409, "QUESTION_NOT_APPROVED", "只能为已审核题目版本确认用途")
    if question.created_by == user.id:
        raise ApiError(403, "QUESTION_SELF_REVIEW", "题目作者不能审批自己的正式用途")
    row = QuestionPurposeApproval(
        question_version_id=question_version_id,
        purpose=purpose,
        decision=decision,
        reviewer_id=user.id,
        reason=reason.strip(),
    )
    db.add(row)
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="assessment.question_purpose_decided",
        resource_type="question_version",
        resource_id=question_version_id,
        course_id=course_id,
        detail={"purpose": purpose, "decision": decision, "reason": row.reason},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def assessment_publish_issues(
    db: AsyncSession, *, assessment: Assessment
) -> list[dict[str, str]]:
    if assessment.purpose not in {"practice", "formal"}:
        return [{"code": "ASSESSMENT_PURPOSE_REQUIRED", "message": "测评用途缺失"}]
    policy = assessment.result_visibility_policy
    allowed = {"immediate_after_submission", "after_close", "after_grading", "manual_release"}
    if policy not in allowed:
        return [{"code": "RESULT_POLICY_REQUIRED", "message": "结果可见策略缺失或未知"}]
    if policy == "immediate_after_submission" and assessment.purpose != "practice":
        return [{"code": "FORMAL_RESULT_POLICY_INVALID", "message": "正式测评不能即时开放结果"}]
    if policy == "after_close" and assessment.closes_at is None:
        return [{"code": "RESULT_CLOSE_REQUIRED", "message": "按截止时间开放结果需要设置截止时间"}]
    rows = (
        await db.execute(
            select(AssessmentItem, QuestionVersion, Question)
            .join(QuestionVersion, QuestionVersion.id == AssessmentItem.question_version_id)
            .join(Question, Question.id == QuestionVersion.question_id)
            .where(AssessmentItem.assessment_id == assessment.id)
            .order_by(AssessmentItem.order_no)
        )
    ).all()
    issues: list[dict[str, str]] = []
    if policy == "after_close" and any(
        version.type not in OBJECTIVE_TYPES for _item, version, _question in rows
    ):
        issues.append(
            {
                "code": "AFTER_CLOSE_REQUIRES_OBJECTIVE_GRADING",
                "message": "含主观题的正式测评应在评分完成后或教师手动发布结果",
            }
        )
    for item, version, question in rows:
        if question.status == "archived":
            issues.append({"code": "QUESTION_ARCHIVED", "message": f"题目版本 {version.id} 已归档"})
            continue
        if assessment.purpose == "formal":
            latest = await db.scalar(
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
            if latest is None or latest.decision != "approved":
                issues.append(
                    {
                        "code": "FORMAL_PURPOSE_NOT_APPROVED",
                        "message": f"题目版本 {version.id} 尚无有效 formal 批准",
                    }
                )
            if version.type not in OBJECTIVE_TYPES:
                rubric = (
                    await db.get(RubricVersion, item.rubric_version_id)
                    if item.rubric_version_id
                    else None
                )
                if (
                    rubric is None
                    or rubric.question_version_id != version.id
                    or rubric.status != "approved"
                ):
                    issues.append(
                        {
                            "code": "APPROVED_RUBRIC_REQUIRED",
                            "message": f"主观题版本 {version.id} 缺少已批准 Rubric",
                        }
                    )
                elif abs(rubric.max_score - item.points) > 1e-6:
                    issues.append(
                        {
                            "code": "RUBRIC_SCORE_MISMATCH",
                            "message": f"Rubric 满分与题目分值不一致：{version.id}",
                        }
                    )
                elif not rubric.evidence_refs or not version.evidence_ids:
                    issues.append(
                        {
                            "code": "RUBRIC_EVIDENCE_REQUIRED",
                            "message": f"题目版本 {version.id} 缺少 Rubric 或题目依据",
                        }
                    )
    return issues


OBJECTIVE_TYPES = {"single", "multiple", "true_false"}


class QualityFeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(min_length=26, max_length=26)
    category: str = Field(pattern="^(answer_key|ambiguous|outdated|other)$")
    detail: str = Field(min_length=8, max_length=1500)


class QualityFeedbackResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_question_version: int = Field(ge=1)
    action: str = Field(pattern="^(accept|reject|invalidate)$")
    rationale: str = Field(min_length=8, max_length=1000)


async def create_quality_feedback(
    db: AsyncSession,
    *,
    course_id: str,
    question_version_id: str,
    user: User,
    body: QualityFeedbackCreate,
) -> tuple[QuestionQualityFeedback, bool]:
    await require_course_role(course_id, user, db, roles={"student"})
    question_row = await db.execute(
        select(QuestionVersion, Question)
        .join(Question, Question.id == QuestionVersion.question_id)
        .where(
            QuestionVersion.id == question_version_id,
            Question.course_id == course_id,
        )
    )
    if question_row.one_or_none() is None:
        raise ApiError(
            status_code=404,
            code="QUESTION_NOT_FOUND",
            message="题目版本不存在或无权访问",
        )

    attempt = await db.scalar(
        select(Attempt)
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .join(AssessmentItem, AssessmentItem.assessment_id == Assessment.id)
        .where(
            Attempt.id == body.attempt_id,
            Attempt.user_id == user.id,
            Attempt.status.in_(("submitted", "graded")),
            Assessment.course_id == course_id,
            AssessmentItem.question_version_id == question_version_id,
        )
    )
    if attempt is None:
        raise ApiError(
            status_code=404,
            code="ASSESSMENT_ATTEMPT_NOT_FOUND",
            message="已完成的课程测评作答不存在或无权访问",
        )
    answer = await db.scalar(
        select(AttemptAnswer).where(
            AttemptAnswer.attempt_id == attempt.id,
            AttemptAnswer.question_version_id == question_version_id,
        )
    )
    if answer is None:
        raise ApiError(
            status_code=409,
            code="QUESTION_NOT_ANSWERED",
            message="只能反馈本人已作答的题目",
        )
    normalized_detail = body.detail.strip()
    if len(normalized_detail) < 8:
        raise ApiError(
            status_code=422,
            code="QUALITY_FEEDBACK_DETAIL_REQUIRED",
            message="请提供至少 8 个非空字符说明题目质量问题",
        )

    existing = await db.scalar(
        select(QuestionQualityFeedback).where(
            QuestionQualityFeedback.user_id == user.id,
            QuestionQualityFeedback.attempt_id == attempt.id,
            QuestionQualityFeedback.question_version_id == question_version_id,
        )
    )
    if existing is not None:
        if existing.category == body.category and existing.detail == normalized_detail:
            return existing, True
        raise ApiError(
            status_code=409,
            code="QUALITY_FEEDBACK_EXISTS",
            message="本次作答已经提交过该题反馈；原记录不会被覆盖",
        )

    feedback = QuestionQualityFeedback(
        course_id=course_id,
        user_id=user.id,
        attempt_id=attempt.id,
        question_version_id=question_version_id,
        category=body.category,
        detail=normalized_detail,
    )
    db.add(feedback)
    try:
        await db.flush()
        await course_service.write_audit(
            db,
            actor_id=user.id,
            action="question.quality_feedback_submitted",
            resource_type="question_quality_feedback",
            resource_id=feedback.id,
            course_id=course_id,
            detail={"question_version_id": question_version_id, "category": body.category},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(QuestionQualityFeedback).where(
                QuestionQualityFeedback.user_id == user.id,
                QuestionQualityFeedback.attempt_id == attempt.id,
                QuestionQualityFeedback.question_version_id == question_version_id,
            )
        )
        if (
            existing is not None
            and existing.category == body.category
            and existing.detail == normalized_detail
        ):
            return existing, True
        if existing is not None:
            raise ApiError(
                status_code=409,
                code="QUALITY_FEEDBACK_EXISTS",
                message="本次作答已经提交过该题反馈；原记录不会被覆盖",
            ) from None
        raise
    return feedback, False


async def list_quality_feedback(
    db: AsyncSession,
    *,
    course_id: str,
    user: User,
    status: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    await require_course_role(course_id, user, db, roles={"teacher"})
    query = (
        select(QuestionQualityFeedback, User.display_name, QuestionVersion)
        .join(User, User.id == QuestionQualityFeedback.user_id)
        .join(QuestionVersion, QuestionVersion.id == QuestionQualityFeedback.question_version_id)
        .where(QuestionQualityFeedback.course_id == course_id)
        .order_by(
            QuestionQualityFeedback.created_at.asc(),
            QuestionQualityFeedback.id.asc(),
        )
    )
    if status is not None:
        query = query.where(QuestionQualityFeedback.status == status)
    rows = (await db.execute(query.limit(limit))).all()
    return [
        {
            "id": feedback.id,
            "attempt_id": feedback.attempt_id,
            "question_version_id": feedback.question_version_id,
            "question_stem": version.stem,
            "student_display_name": student_name,
            "category": feedback.category,
            "detail": feedback.detail,
            "status": feedback.status,
            "resolution_action": feedback.resolution_action,
            "resolution_rationale": feedback.resolution_rationale,
            "created_at": feedback.created_at.isoformat(),
            "resolved_at": feedback.resolved_at.isoformat() if feedback.resolved_at else None,
        }
        for feedback, student_name, version in rows
    ]


async def _invalidate_question_learning_state(
    db: AsyncSession,
    *,
    question_id: str,
    feedback_id: str,
) -> int:
    version_ids = list(
        (
            await db.execute(
                select(QuestionVersion.id).where(QuestionVersion.question_id == question_id)
            )
        ).scalars()
    )
    if not version_ids:
        return 0

    all_evidence = list(
        (
            await db.execute(
                select(LearningEvidence).where(
                    LearningEvidence.question_version_id.in_(version_ids)
                )
            )
        ).scalars()
    )
    affected_groups = {(row.user_id, row.course_id) for row in all_evidence}
    affected_attempt_ids = {row.attempt_id for row in all_evidence if row.attempt_id}
    invalidated_count = 0
    for evidence in all_evidence:
        if evidence.quality_status == "valid":
            evidence.quality_status = "invalidated"
            evidence.invalidated_reason = f"题目质量复核确认失效；反馈编号 {feedback_id}"
            invalidated_count += 1

    review_tasks = list(
        (
            await db.execute(
                select(ReviewTask).where(ReviewTask.question_version_id.in_(version_ids))
            )
        ).scalars()
    )
    review_task_ids = {task.id for task in review_tasks}
    affected_attempt_ids.update(
        task.source_attempt_id for task in review_tasks if task.source_attempt_id
    )
    for task in review_tasks:
        if task.status == "pending":
            task.status = "dismissed"
            task.version += 1
        if task.qualification_status == "pending":
            task.qualification_status = "rejected"
            task.qualification_reason = "question_invalidated"

    event_refs = affected_attempt_ids | review_task_ids
    if event_refs:
        pending_events = list(
            (
                await db.execute(
                    select(LearningEvent).where(
                        LearningEvent.source_type.in_(("assessment", "review")),
                        LearningEvent.source_ref.in_(event_refs),
                        LearningEvent.qualification_status == "pending",
                    )
                )
            ).scalars()
        )
        version_id_set = set(version_ids)
        for event in pending_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if payload.get("question_version_id") in version_id_set:
                event.qualification_status = "invalidated"
                event.qualification_reason = "question_invalidated"
                event.qualified_at = datetime.now(UTC)

    # 已由这些作答产生的候选薄弱记忆不再进入 Planner；正文不删除，只标为过时。
    if affected_attempt_ids:
        stale_memories = (
            await db.execute(
                select(MemoryItem).where(
                    MemoryItem.source_type == "quiz",
                    MemoryItem.source_ref.in_(affected_attempt_ids),
                    MemoryItem.stale.is_(False),
                )
            )
        ).scalars()
        for memory in stale_memories:
            memory.stale = True

    from app.modules.memory import service as memory_service

    for user_id, course_id in affected_groups:
        await memory_service.recompute_mastery(db, user_id=user_id, course_id=course_id)
    return invalidated_count


async def resolve_quality_feedback(
    db: AsyncSession,
    *,
    course_id: str,
    feedback_id: str,
    user: User,
    body: QualityFeedbackResolution,
) -> tuple[dict[str, Any], bool]:
    await require_course_role(course_id, user, db, roles={"teacher"})
    feedback = await db.scalar(
        select(QuestionQualityFeedback)
        .where(
            QuestionQualityFeedback.id == feedback_id,
            QuestionQualityFeedback.course_id == course_id,
        )
        .with_for_update()
    )
    if feedback is None:
        raise ApiError(
            status_code=404,
            code="QUALITY_FEEDBACK_NOT_FOUND",
            message="题目反馈不存在或无权访问",
        )
    version = await db.get(QuestionVersion, feedback.question_version_id)
    if version is None:
        raise ApiError(status_code=404, code="QUESTION_NOT_FOUND", message="题目版本不存在")
    question = await db.scalar(
        select(Question)
        .where(Question.id == version.question_id, Question.course_id == course_id)
        .with_for_update()
    )
    if question is None:
        raise ApiError(status_code=404, code="QUESTION_NOT_FOUND", message="题目不存在")

    normalized_rationale = body.rationale.strip()
    if len(normalized_rationale) < 8:
        raise ApiError(
            status_code=422,
            code="QUALITY_RESOLUTION_RATIONALE_REQUIRED",
            message="处置理由至少需要 8 个非空字符",
        )
    if feedback.status != "pending":
        if (
            feedback.resolved_by == user.id
            and feedback.resolution_action == body.action
            and feedback.resolution_rationale == normalized_rationale
        ):
            return _quality_resolution_out(feedback, question), True
        raise ApiError(
            status_code=409,
            code="QUALITY_FEEDBACK_RESOLVED",
            message="该反馈已经处置，不能覆盖历史决定",
        )
    if question.version != body.expected_question_version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="题目已被其他处置更新，请刷新后重试",
            details={
                "expected_version": body.expected_question_version,
                "actual_version": question.version,
            },
        )

    status_by_action = {"accept": "accepted", "reject": "rejected", "invalidate": "invalidated"}
    if body.action == "invalidate":
        question.status = "archived"
    question.version += 1
    feedback.status = status_by_action[body.action]
    feedback.resolution_action = body.action
    feedback.resolution_rationale = normalized_rationale
    feedback.resolved_by = user.id
    feedback.resolved_at = datetime.now(UTC)
    invalidated_evidence_count = 0
    if body.action == "invalidate":
        invalidated_evidence_count = await _invalidate_question_learning_state(
            db, question_id=question.id, feedback_id=feedback.id
        )
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action=f"question.quality_feedback_{body.action}",
        resource_type="question_quality_feedback",
        resource_id=feedback.id,
        course_id=course_id,
        detail={
            "question_id": question.id,
            "question_version": question.version,
            "invalidated_evidence_count": invalidated_evidence_count,
        },
    )
    await db.commit()
    return {
        **_quality_resolution_out(feedback, question),
        "invalidated_evidence_count": invalidated_evidence_count,
    }, False


def _quality_resolution_out(
    feedback: QuestionQualityFeedback, question: Question
) -> dict[str, Any]:
    return {
        "feedback_id": feedback.id,
        "feedback_status": feedback.status,
        "resolution_action": feedback.resolution_action,
        "question_id": question.id,
        "question_status": question.status,
        "question_version": question.version,
        "invalidated_evidence_count": 0,
    }

OBJECTIVE_TYPES = {"single", "multiple", "true_false"}


async def get_teacher_attempt(
    db: AsyncSession, *, attempt_id: str, user: User
) -> tuple[Attempt, Assessment]:
    attempt = await db.get(Attempt, attempt_id)
    if attempt is None:
        raise ApiError(
            status_code=404, code="ATTEMPT_NOT_FOUND", message="作答记录不存在或无权访问"
        )
    assessment = await db.get(Assessment, attempt.assessment_id)
    if assessment is None:
        raise ApiError(
            status_code=404, code="ASSESSMENT_NOT_FOUND", message="测验不存在或无权访问"
        )
    await require_course_role(assessment.course_id, user, db, roles={"teacher"})
    return attempt, assessment


async def list_grading_queue(
    db: AsyncSession,
    *,
    course_id: str,
    user: User,
    limit: int,
    include_graded: bool = False,
) -> list[dict[str, Any]]:
    await require_course_role(course_id, user, db, roles={"teacher"})
    rows = (
        await db.execute(
            select(Attempt, Assessment, User)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .join(User, User.id == Attempt.user_id)
            .join(AssessmentItem, AssessmentItem.assessment_id == Assessment.id)
            .join(QuestionVersion, QuestionVersion.id == AssessmentItem.question_version_id)
            .where(
                Assessment.course_id == course_id,
                QuestionVersion.type.notin_(OBJECTIVE_TYPES),
                or_(
                    and_(
                        Attempt.status == "submitted",
                        Attempt.grading_status == "pending_teacher",
                    ),
                    and_(include_graded, Attempt.status == "graded"),
                ),
            )
            .distinct()
            .order_by(Attempt.submitted_at.asc(), Attempt.id.asc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "attempt_id": attempt.id,
            "assessment_id": assessment.id,
            "assessment_title": assessment.title,
            "student_display_name": student.display_name,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "grading_status": attempt.grading_status,
        }
        for attempt, assessment, student in rows
    ]


async def get_grading_detail(
    db: AsyncSession, *, attempt: Attempt, assessment: Assessment
) -> dict[str, Any]:
    if attempt.status not in {"submitted", "graded"}:
        raise ApiError(
            status_code=409,
            code="ATTEMPT_NOT_SUBMITTED",
            message="只能查看已提交测验的评分材料",
        )
    rows = (
        await db.execute(
            select(AssessmentItem, QuestionVersion, AttemptAnswer)
            .join(QuestionVersion, QuestionVersion.id == AssessmentItem.question_version_id)
            .outerjoin(
                AttemptAnswer,
                (AttemptAnswer.attempt_id == attempt.id)
                & (AttemptAnswer.question_version_id == AssessmentItem.question_version_id),
            )
            .where(AssessmentItem.assessment_id == assessment.id)
            .order_by(AssessmentItem.order_no.asc())
        )
    ).all()
    manual_ids = [
        version.id for _item, version, _answer in rows if version.type not in OBJECTIVE_TYPES
    ]
    decisions_by_question: dict[str, list[TeacherGradingDecision]] = {
        question_id: [] for question_id in manual_ids
    }
    if manual_ids:
        decisions = (
            await db.execute(
                select(TeacherGradingDecision)
                .where(
                    TeacherGradingDecision.attempt_id == attempt.id,
                    TeacherGradingDecision.question_version_id.in_(manual_ids),
                )
                .order_by(
                    TeacherGradingDecision.question_version_id.asc(),
                    TeacherGradingDecision.decision_version.asc(),
                )
            )
        ).scalars()
        for decision in decisions:
            decisions_by_question[decision.question_version_id].append(decision)
    latest_score = await db.scalar(
        select(ScoreRecord)
        .where(ScoreRecord.attempt_id == attempt.id)
        .order_by(ScoreRecord.score_version.desc())
        .limit(1)
    )
    return {
        "attempt_id": attempt.id,
        "assessment_id": assessment.id,
        "assessment_title": assessment.title,
        "student_display_name": await db.scalar(
            select(User.display_name).where(User.id == attempt.user_id)
        ),
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "grading_status": attempt.grading_status,
        "score_version": latest_score.score_version if latest_score else 0,
        "score_record": (
            {
                "score": latest_score.score,
                "max_score": latest_score.max_score,
                "released_at": latest_score.released_at.isoformat(),
                "override_reason": latest_score.override_reason,
            }
            if latest_score
            else None
        ),
        "items": [
            {
                "question_version_id": version.id,
                "order_no": item.order_no,
                "type": version.type,
                "stem": version.stem,
                "response": answer.response if answer else None,
                "rubric": version.rubric if version.type not in OBJECTIVE_TYPES else None,
                "max_points": item.points,
                "gradable": version.type not in OBJECTIVE_TYPES,
                "objective_points_earned": (
                    answer.points_earned
                    if answer and version.type in OBJECTIVE_TYPES
                    else None
                ),
                "decisions": [
                    {
                        "decision_id": decision.id,
                        "decision_version": decision.decision_version,
                        "grader_id": decision.grader_id,
                        "points_awarded": decision.points_awarded,
                        "rationale": decision.rationale,
                        "override_reason": decision.override_reason,
                        "created_at": decision.created_at.isoformat(),
                    }
                    for decision in decisions_by_question.get(version.id, [])
                ],
            }
            for item, version, answer in rows
        ],
    }


async def grade_attempt(
    db: AsyncSession,
    *,
    attempt_id: str,
    user: User,
    body: TeacherGradeSubmit,
    idempotency_key: str | None,
) -> tuple[dict[str, Any], bool]:
    attempt, assessment = await get_teacher_attempt(db, attempt_id=attempt_id, user=user)
    endpoint, request_hash = grade_request_identity(attempt.id, body)
    if idempotency_key:
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
        )
        if previous is not None:
            return previous["body"]["data"], True

    attempt = (
        await db.execute(
            select(Attempt).where(Attempt.id == attempt.id).with_for_update()
        )
    ).scalar_one()
    if attempt.status not in {"submitted", "graded"}:
        raise ApiError(
            status_code=409,
            code="ATTEMPT_NOT_SUBMITTED",
            message="只能为已提交的测验评分",
        )

    rows = (
        await db.execute(
            select(AssessmentItem, QuestionVersion, AttemptAnswer)
            .join(QuestionVersion, QuestionVersion.id == AssessmentItem.question_version_id)
            .outerjoin(
                AttemptAnswer,
                (AttemptAnswer.attempt_id == attempt.id)
                & (AttemptAnswer.question_version_id == AssessmentItem.question_version_id),
            )
            .where(AssessmentItem.assessment_id == assessment.id)
            .order_by(AssessmentItem.order_no.asc())
        )
    ).all()
    manual_rows = [row for row in rows if row[1].type not in OBJECTIVE_TYPES]
    expected_question_ids = {version.id for _item, version, _answer in manual_rows}
    submitted_ids = [item.question_version_id for item in body.items]
    if len(submitted_ids) != len(set(submitted_ids)) or set(submitted_ids) != expected_question_ids:
        raise ApiError(
            status_code=422,
            code="GRADING_ITEMS_MISMATCH",
            message="评分请求必须且只能包含本次测验的全部主观题",
            details={"expected_question_version_ids": sorted(expected_question_ids)},
        )
    if not expected_question_ids:
        raise ApiError(
            status_code=409,
            code="NO_MANUAL_GRADING_REQUIRED",
            message="本次测验没有待人工评分的主观题",
        )
    by_id = {item.question_version_id: item for item in body.items}
    items_by_id = {version.id: item for item, version, _answer in manual_rows}
    for question_id, grade in by_id.items():
        if grade.points_awarded > items_by_id[question_id].points:
            raise ApiError(
                status_code=422,
                code="GRADE_EXCEEDS_MAX_POINTS",
                message="评分不得超过该题分值",
                details={"question_version_id": question_id},
            )
        if not grade.rationale.strip():
            raise ApiError(
                status_code=422,
                code="GRADING_RATIONALE_REQUIRED",
                message="教师评分必须记录理由",
                details={"question_version_id": question_id},
            )

    latest_score = (
        await db.execute(
            select(ScoreRecord)
            .where(ScoreRecord.attempt_id == attempt.id)
            .order_by(ScoreRecord.score_version.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    current_score_version = latest_score.score_version if latest_score else 0
    if body.expected_score_version != current_score_version:
        raise ApiError(
            status_code=409,
            code="SCORE_VERSION_CONFLICT",
            message="成绩已被其他教师更新，请刷新评分记录后重试",
            details={
                "expected_version": body.expected_score_version,
                "actual_version": current_score_version,
            },
        )
    override_reason = body.override_reason.strip() if body.override_reason else None
    if latest_score and not override_reason:
        raise ApiError(
            status_code=422,
            code="OVERRIDE_REASON_REQUIRED",
            message="修改已发布成绩必须填写复核/覆盖理由",
        )

    old_decisions = (
        await db.execute(
            select(TeacherGradingDecision)
            .where(TeacherGradingDecision.attempt_id == attempt.id)
            .order_by(
                TeacherGradingDecision.question_version_id.asc(),
                TeacherGradingDecision.decision_version.desc(),
            )
        )
    ).scalars()
    previous_by_question: dict[str, TeacherGradingDecision] = {}
    for previous in old_decisions:
        previous_by_question.setdefault(previous.question_version_id, previous)

    now = datetime.now(UTC)
    decisions: dict[str, TeacherGradingDecision] = {}
    for _item, version, _answer in manual_rows:
        previous = previous_by_question.get(version.id)
        decision = TeacherGradingDecision(
            attempt_id=attempt.id,
            question_version_id=version.id,
            grader_id=user.id,
            decision_version=(previous.decision_version + 1) if previous else 1,
            points_awarded=by_id[version.id].points_awarded,
            max_points=items_by_id[version.id].points,
            rationale=by_id[version.id].rationale.strip(),
            override_reason=override_reason,
            supersedes_id=previous.id if previous else None,
        )
        db.add(decision)
        decisions[version.id] = decision
    await db.flush()

    objective_score = sum(
        (answer.points_earned or 0.0)
        for _item, version, answer in rows
        if answer is not None and version.type in OBJECTIVE_TYPES
    )
    manual_score = sum(grade.points_awarded for grade in body.items)
    max_score = sum(item.points for item, _version, _answer in rows)
    score_version = current_score_version + 1
    score = ScoreRecord(
        attempt_id=attempt.id,
        score_version=score_version,
        score=objective_score + manual_score,
        max_score=max_score,
        breakdown=[
            {
                "question_version_id": version.id,
                "points_awarded": (
                    decisions[version.id].points_awarded
                    if version.id in decisions
                    else (answer.points_earned or 0.0 if answer else 0.0)
                ),
                "max_points": item.points,
                "source": "teacher" if version.id in decisions else "objective",
                "decision_id": decisions[version.id].id if version.id in decisions else None,
            }
            for item, version, answer in rows
        ],
        override_reason=override_reason,
        created_by=user.id,
        released_at=now,
        supersedes_id=latest_score.id if latest_score else None,
    )
    db.add(score)
    attempt.status = "graded"
    attempt.grading_status = "graded"
    attempt.score = score.score
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="assessment.manual_grade" if not latest_score else "assessment.score_override",
        resource_type="attempt",
        resource_id=attempt.id,
        course_id=assessment.course_id,
        detail={"score_version": score_version, "item_count": len(decisions)},
    )
    result = {
        "attempt_id": attempt.id,
        "score_version": score_version,
        "score": score.score,
        "max_score": max_score,
        "grading_status": attempt.grading_status,
        "released_at": now.isoformat(),
        "override_reason": override_reason,
    }
    if idempotency_key:
        await course_service.save_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
            status=200,
            body={"data": result},
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if idempotency_key:
            replay = await find_idempotent_replay(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=endpoint,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay, True
        raise ApiError(
            status_code=409,
            code="SCORE_VERSION_CONFLICT",
            message="成绩已由其他评分操作更新，请重新读取后再提交",
        ) from None
    return result, False


def grade_request_identity(attempt_id: str, body: TeacherGradeSubmit) -> tuple[str, str]:
    endpoint = f"teacher-attempt-grading:{attempt_id}"
    payload = {"attempt_id": attempt_id, **body.model_dump(mode="json")}
    return endpoint, course_service.canonical_request_hash(payload)


async def find_idempotent_replay(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
) -> dict[str, Any] | None:
    previous = await course_service.find_idempotent_response(
        db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=request_hash,
    )
    return previous["body"]["data"] if previous else None
