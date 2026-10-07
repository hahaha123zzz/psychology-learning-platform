from datetime import UTC, datetime

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Assessment,
    AssessmentItem,
    Attempt,
    AttemptAnswer,
    CaseSession,
    LearningEvent,
    LearningEvidence,
    LearningQualification,
    LearningSession,
    MiniLabSession,
    QuestionVersion,
    ReviewTask,
)
from app.modules.memory import service as memory_service

ALGORITHM_VERSION = "qualification-v1"


def tutor_response_can_recompute_mastery(
    *, correct: bool, current_independent: bool, distinct_attempt_count: int
) -> bool:
    """单次错误只保留证据；正确回合或跨回合聚合后才重算掌握状态。"""
    return correct or (current_independent and distinct_attempt_count >= 2)


def tutor_response_evidence_dimension(response_state: object) -> str | None:
    """只允许学生实际回答的 check/practice 回合生成证据。"""
    if not isinstance(response_state, str):
        return None
    return {"check": "understand", "practice": "apply"}.get(response_state)


def tutor_response_version_rejection_reason(
    *,
    session_id: str,
    current_session_version: object,
    event_key: object,
    event_payload: object,
) -> str | None:
    """校验服务端 Tutor 事件的版本链，允许资格化前会话继续前进。"""
    if not isinstance(event_payload, dict):
        return "tutor_session_version_mismatch"
    post_version = event_payload.get("state_version")
    if (
        not isinstance(post_version, int)
        or isinstance(post_version, bool)
        or post_version <= 0
        or not isinstance(current_session_version, int)
        or isinstance(current_session_version, bool)
        or current_session_version < post_version
        or event_key != f"learning-session-response:{session_id}:{post_version - 1}"
    ):
        return "tutor_session_version_mismatch"
    return None


async def qualify_event(
    db: AsyncSession,
    *,
    event_id: str,
) -> tuple[LearningQualification, bool]:
    """对原始事件做一次可重放的确定性资格化，不信任客户端成绩字段。"""

    event = await db.scalar(
        select(LearningEvent).where(LearningEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise ValueError("learning event not found")
    existing = await db.scalar(
        select(LearningQualification).where(LearningQualification.event_id == event.id)
    )
    if existing is not None:
        return existing, True

    status = "rejected"
    reason = "event_type_not_evidence_bearing"
    evidence_ids: list[str] = []
    if event.event_type == "answer_submitted" and event.source_type == "assessment":
        evidence_ids, reason = await _qualify_assessment_answer(db, event)
        status = "qualified" if evidence_ids else "rejected"
    elif event.event_type == "answer_submitted" and event.source_type == "review":
        evidence_ids, reason = await _qualify_review_task(db, event)
        status = "qualified" if evidence_ids else "rejected"
    elif event.event_type == "answer_submitted" and event.source_type == "practice":
        evidence_ids, reason = await _qualify_practice_case(db, event)
        status = "qualified" if evidence_ids else "rejected"
    elif event.event_type == "tutor_responded" and event.source_type == "tutor":
        evidence_ids, reason = await _qualify_tutor_response(db, event)
        status = "qualified" if evidence_ids else "rejected"
    elif event.event_type == "lab_trial_completed" and event.source_type == "lab":
        evidence_ids, reason = await _qualify_lab_result(db, event)
        status = "qualified" if evidence_ids else "rejected"

    event.qualification_status = status
    event.qualification_reason = reason
    event.qualified_at = datetime.now(UTC)
    if (
        getattr(event, "event_type", None) == "lab_trial_completed"
        and getattr(event, "source_type", None) == "lab"
        and getattr(event, "event_key", None) == f"lab:{event.source_ref}:completed"
    ):
        session = await db.scalar(
            select(MiniLabSession).where(MiniLabSession.id == event.source_ref)
        )
        if (
            session is not None
            and session.status == "completed"
            and session.user_id == event.user_id
            and session.course_id == event.course_id
            and isinstance(session.derived_measure, dict)
        ):
            session.derived_measure = {
                **session.derived_measure,
                "qualification_status": status,
                "qualification_reason": reason,
            }
    qualification = LearningQualification(
        event_id=event.id,
        user_id=event.user_id,
        course_id=event.course_id,
        status=status,
        reason=reason,
        algorithm_version=ALGORITHM_VERSION,
        evidence_ids=evidence_ids,
    )
    db.add(qualification)
    await db.flush()
    return qualification, False


async def _qualify_practice_case(
    db: AsyncSession, event: LearningEvent
) -> tuple[list[str], str]:
    """只从服务端 CaseSession 快照生成练习证据，不信任客户端分数。"""
    if not event.source_ref:
        return [], "missing_authoritative_case_reference"
    session = await db.scalar(
        select(CaseSession).where(
            CaseSession.id == event.source_ref,
            CaseSession.user_id == event.user_id,
            CaseSession.course_id == event.course_id,
        )
    )
    if session is None or session.status != "completed" or not isinstance(session.outcome, dict):
        return [], "case_session_not_completed"
    points = session.outcome.get("points")
    max_points = session.outcome.get("max_points")
    if not isinstance(points, int) or not isinstance(max_points, int) or max_points <= 0:
        return [], "case_outcome_not_authoritative"
    evidence_ids = await memory_service.record_evidence(
        db,
        user_id=event.user_id,
        course_id=event.course_id,
        knowledge_points=[f"case:{session.case_key}"],
        question_version_id=session.id,
        attempt_id=session.id,
        source_type="practice",
        hints_used=0,
        correct=points == max_points,
        dimension="apply",
        independence_status="independent",
        context_key=f"case:{session.case_key}",
    )
    await memory_service.recompute_mastery(
        db, user_id=event.user_id, course_id=event.course_id
    )
    session.outcome = {**session.outcome, "qualification_status": "qualified"}
    return evidence_ids, "authoritative_case_session"


async def _qualify_tutor_response(
    db: AsyncSession, event: LearningEvent
) -> tuple[list[str], str]:
    """只接受服务端学习状态机写入的检查/练习回合。"""
    if not event.source_ref or not isinstance(event.payload, dict):
        return [], "missing_authoritative_tutor_reference"
    session = await db.scalar(
        select(LearningSession).where(
            LearningSession.id == event.source_ref,
            LearningSession.user_id == event.user_id,
            LearningSession.course_id == event.course_id,
        )
    )
    version_rejection = tutor_response_version_rejection_reason(
        session_id=session.id if session is not None else event.source_ref,
        current_session_version=session.version if session is not None else None,
        event_key=event.event_key,
        event_payload=event.payload,
    )
    response_state = event.payload.get("response_state")
    correct = event.payload.get("correct")
    if session is None or version_rejection is not None:
        return [], version_rejection or "tutor_session_version_mismatch"
    dimension = tutor_response_evidence_dimension(response_state)
    if dimension is None or not isinstance(correct, bool):
        return [], "tutor_response_not_evidence_bearing"
    context = f"material:{session.material_version_id}"
    if session.chapter_object_id:
        context = f"{context}:chapter:{session.chapter_object_id}"
    hints_used = int(event.payload.get("hint_level") or 0)
    independence_status = "independent" if hints_used == 0 else "supported"
    evidence_ids = await memory_service.record_evidence(
        db,
        user_id=event.user_id,
        course_id=event.course_id,
        knowledge_points=[f"tutor:{session.chapter_object_id or session.material_version_id}"],
        question_version_id=session.id,
        attempt_id=session.id,
        source_type="practice",
        hints_used=hints_used,
        correct=correct,
        dimension=dimension,
        independence_status=independence_status,
        context_key=context,
    )
    attempt_ids = await db.scalars(
        select(distinct(LearningEvidence.attempt_id)).where(
            LearningEvidence.user_id == event.user_id,
            LearningEvidence.course_id == event.course_id,
            LearningEvidence.knowledge_point
            == f"tutor:{session.chapter_object_id or session.material_version_id}",
            LearningEvidence.source_type == "practice",
            LearningEvidence.quality_status == "valid",
            LearningEvidence.attempt_id.is_not(None),
        )
    )
    distinct_attempt_count = len(attempt_ids.all())
    if tutor_response_can_recompute_mastery(
        correct=correct,
        current_independent=independence_status == "independent",
        distinct_attempt_count=distinct_attempt_count,
    ):
        await memory_service.recompute_mastery(
            db, user_id=event.user_id, course_id=event.course_id
        )
    return evidence_ids, "authoritative_tutor_state_machine"


async def _qualify_lab_result(
    db: AsyncSession, event: LearningEvent
) -> tuple[list[str], str]:
    """拒绝尚无答案与评分合同的 MiniLab 结果；仅保留可审计参与事件。"""
    if not event.source_ref or not isinstance(event.payload, dict):
        return [], "missing_authoritative_lab_reference"
    session = await db.scalar(
        select(MiniLabSession).where(
            MiniLabSession.id == event.source_ref,
            MiniLabSession.user_id == event.user_id,
            MiniLabSession.course_id == event.course_id,
        ).with_for_update()
    )
    if (
        session is None
        or session.status != "completed"
        or not isinstance(session.derived_measure, dict)
    ):
        return [], "mini_lab_session_not_completed"
    measure = session.derived_measure
    if measure.get("qualification_status") != "pending":
        return [], "mini_lab_result_not_pending"
    trial_data = session.trial_data if isinstance(session.trial_data, list) else []
    responses_by_phase = {
        trial.get("phase"): trial.get("response")
        for trial in trial_data
        if isinstance(trial, dict)
    }
    if any(responses_by_phase.get(phase) is None for phase in ("predict", "run")):
        return [], "mini_lab_required_response_missing"
    if (
        event.payload.get("trial_count") != measure.get("trial_count")
        or event.payload.get("explanation_complete") != measure.get("explanation_complete")
        or event.payload.get("transfer_complete") != measure.get("transfer_complete")
    ):
        return [], "mini_lab_measure_mismatch"
    # Explain/Summary 仅有按钮回调，没有答案或评分结果；历史行中的 true
    # 标志也不构成验证。没有独立批准的版本化评分合同前，一律不投影证据。
    return [], "mini_lab_explanation_or_transfer_unverified"


async def qualify_pending_events(db: AsyncSession, *, limit: int = 100) -> dict[str, int]:
    """Worker 批量领取待资格化事件；行锁保证多 Worker 不重复投影。"""

    event_ids = list(
        (
            await db.execute(
                select(LearningEvent.id)
                .where(LearningEvent.qualification_status == "pending")
                .order_by(LearningEvent.occurred_at.asc(), LearningEvent.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    counts = {"claimed": len(event_ids), "qualified": 0, "rejected": 0}
    for event_id in event_ids:
        qualification, _replay = await qualify_event(db, event_id=event_id)
        counts[qualification.status] = counts.get(qualification.status, 0) + 1
    await db.commit()
    return counts


async def _qualify_assessment_answer(
    db: AsyncSession, event: LearningEvent
) -> tuple[list[str], str]:
    attempt_id = event.source_ref
    question_version_id = event.payload.get("question_version_id")
    if not isinstance(attempt_id, str) or not isinstance(question_version_id, str):
        return [], "missing_authoritative_assessment_reference"

    attempt_and_assessment = await db.execute(
        select(Attempt, Assessment)
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .where(
            Attempt.id == attempt_id,
            Attempt.user_id == event.user_id,
            Assessment.course_id == event.course_id,
        )
    )
    row = attempt_and_assessment.one_or_none()
    if row is None:
        return [], "assessment_scope_mismatch"
    attempt, assessment = row
    if attempt.status not in ("submitted", "graded"):
        return [], "assessment_attempt_not_submitted"

    answer = await db.scalar(
        select(AttemptAnswer).where(
            AttemptAnswer.attempt_id == attempt.id,
            AttemptAnswer.question_version_id == question_version_id,
        )
    )
    if answer is None or answer.is_correct is None:
        return [], "authoritative_answer_not_graded"

    version = await db.scalar(
        select(QuestionVersion)
        .join(AssessmentItem, AssessmentItem.question_version_id == QuestionVersion.id)
        .where(
            AssessmentItem.assessment_id == assessment.id,
            QuestionVersion.id == question_version_id,
        )
    )
    if version is None:
        return [], "question_not_in_assessment"
    knowledge_points = [
        kp for kp in (version.knowledge_point_ids or []) if isinstance(kp, str)
    ][:5] or [f"{version.stem[:30]}"]
    evidence_ids = await memory_service.record_evidence(
        db,
        user_id=event.user_id,
        course_id=event.course_id,
        knowledge_points=knowledge_points,
        question_version_id=version.id,
        attempt_id=attempt.id,
        source_type="formal_quiz",
        hints_used=0,
        correct=answer.is_correct,
        dimension="understand",
        independence_status="independent",
        context_key=f"assessment:{assessment.id}",
    )
    return evidence_ids, "authoritative_assessment_answer"


async def _qualify_review_task(
    db: AsyncSession, event: LearningEvent
) -> tuple[list[str], str]:
    """从到期复习题的服务端题目版本生成 retention 证据。"""
    if not event.source_ref or not isinstance(event.payload, dict):
        return [], "missing_authoritative_review_reference"
    task = await db.scalar(
        select(ReviewTask).where(
            ReviewTask.id == event.source_ref,
            ReviewTask.user_id == event.user_id,
            ReviewTask.course_id == event.course_id,
        )
    )
    question_id = event.payload.get("question_version_id")
    response = event.payload.get("response")
    if task is None or task.status != "done":
        return [], "review_task_not_completed"
    if not isinstance(question_id, str) or question_id != task.question_version_id:
        return [], "review_question_mismatch"
    if not isinstance(response, dict):
        return [], "review_response_invalid"
    question = await db.scalar(select(QuestionVersion).where(QuestionVersion.id == question_id))
    if question is None:
        return [], "review_question_not_found"
    if question.type not in {"single", "multiple", "true_false"}:
        return [], "review_question_not_objective"
    if not isinstance(question.answer, dict):
        return [], "review_answer_key_invalid"
    answer = question.answer
    if not isinstance(response, dict) or set(response) != {"selected_keys"}:
        return [], "review_response_shape_invalid"
    given = response.get("selected_keys")
    if question.type == "true_false":
        expected = answer.get("correct")
        if not isinstance(given, bool) or not isinstance(expected, bool):
            return [], "review_response_shape_invalid"
        correct = given is expected
    else:
        options = question.options
        option_keys = [
            option.get("key")
            for option in options
            if isinstance(option, dict) and isinstance(option.get("key"), str)
        ] if isinstance(options, list) else []
        raw_correct_keys = answer.get("correct_keys")
        if (
            not option_keys
            or len(set(option_keys)) != len(option_keys)
            or not isinstance(raw_correct_keys, list)
            or not raw_correct_keys
            or any(not isinstance(key, str) or not key for key in raw_correct_keys)
            or len(set(raw_correct_keys)) != len(raw_correct_keys)
            or not set(raw_correct_keys).issubset(option_keys)
            or (question.type == "single" and len(raw_correct_keys) != 1)
            or not isinstance(given, list)
            or not given
            or any(not isinstance(key, str) or not key for key in given)
            or len(set(given)) != len(given)
            or not set(given).issubset(option_keys)
            or (question.type == "single" and len(given) != 1)
        ):
            return [], "review_response_shape_invalid"
        correct = set(given) == set(raw_correct_keys)
    knowledge_points = [
        kp for kp in (question.knowledge_point_ids or []) if isinstance(kp, str)
    ][:5] or [question.stem[:30]]
    evidence_ids = await memory_service.record_evidence(
        db,
        user_id=event.user_id,
        course_id=event.course_id,
        knowledge_points=knowledge_points,
        question_version_id=question.id,
        attempt_id=task.id,
        source_type="review",
        hints_used=0,
        correct=correct,
        dimension="retention",
        independence_status="independent",
        context_key=f"review-question:{question.id}",
    )
    await memory_service.recompute_mastery(
        db, user_id=event.user_id, course_id=event.course_id
    )
    task.qualification_status = "qualified"
    task.qualification_reason = "authoritative_review_answer"
    return evidence_ids, "authoritative_review_answer"
