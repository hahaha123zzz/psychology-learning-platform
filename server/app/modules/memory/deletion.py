"""隐私删除工作单的本地执行逻辑。

请求受理与账号停用在 API 事务内立即完成；本模块仅处理可清除的个人学习数据。
正式作答/成绩、审计及课程归属历史按当前明确的保留边界保留。
"""

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CaseSession,
    ChatSession,
    ChatTurn,
    ClassMember,
    CourseMember,
    CurrentLearningTask,
    EvidenceTicket,
    IdempotencyRecord,
    InterventionRun,
    LearningEpisode,
    LearningEvent,
    LearningEvidence,
    LearningQualification,
    LearningSession,
    MasteryState,
    MemoryItem,
    MiniLabSession,
    ModelCallLog,
    Notification,
    QuestionQualityFeedback,
    ReviewTask,
    RoleAssignment,
    TeacherObservation,
    TeachingSession,
    UserPreference,
    WrongAnswerTrace,
)

RETAINED_CATEGORIES = [
    "正式测评作答与成绩：保留内容但关联已去标识化账号编号，需按机构/法律规则处理",
    "审计记录：仅保留履责所需的最小审计信息",
    "课程创建与任课历史：保留在去标识账号编号下以维持资源归属和审计",
]


async def delete_personal_learning_data(db: AsyncSession, *, user_id: str) -> dict[str, int]:
    """幂等清除属于用户的个人上下文并解除模型用量记录的用户关联。"""
    counts: dict[str, int] = {}

    async def delete_rows(model: type, criterion: object, key: str) -> None:
        result = await db.execute(delete(model).where(criterion))
        counts[key] = max(result.rowcount or 0, 0)

    turns = await db.execute(
        delete(ChatTurn).where(
            ChatTurn.session_id.in_(select(ChatSession.id).where(ChatSession.user_id == user_id))
        )
    )
    counts["chat_turns"] = max(turns.rowcount or 0, 0)
    await delete_rows(ChatSession, ChatSession.user_id == user_id, "chat_sessions")

    user_tasks = select(CurrentLearningTask.id).where(CurrentLearningTask.user_id == user_id)
    await delete_rows(
        LearningEpisode, LearningEpisode.task_id.in_(user_tasks), "learning_episodes"
    )
    await delete_rows(
        TeachingSession, TeachingSession.task_id.in_(user_tasks), "teaching_sessions"
    )
    await delete_rows(CurrentLearningTask, CurrentLearningTask.user_id == user_id, "learning_tasks")
    await delete_rows(LearningSession, LearningSession.user_id == user_id, "learning_sessions")
    await delete_rows(CaseSession, CaseSession.user_id == user_id, "case_sessions")
    await delete_rows(MiniLabSession, MiniLabSession.user_id == user_id, "mini_lab_sessions")
    await delete_rows(InterventionRun, InterventionRun.user_id == user_id, "intervention_runs")
    await delete_rows(
        TeacherObservation,
        TeacherObservation.student_id == user_id,
        "teacher_observations",
    )
    await delete_rows(ReviewTask, ReviewTask.user_id == user_id, "review_tasks")
    await delete_rows(WrongAnswerTrace, WrongAnswerTrace.user_id == user_id, "wrong_answer_traces")
    await delete_rows(
        QuestionQualityFeedback,
        QuestionQualityFeedback.user_id == user_id,
        "question_quality_feedback",
    )
    await delete_rows(
        LearningQualification,
        LearningQualification.user_id == user_id,
        "learning_qualifications",
    )
    await delete_rows(LearningEvent, LearningEvent.user_id == user_id, "learning_events")
    await delete_rows(LearningEvidence, LearningEvidence.user_id == user_id, "learning_evidences")
    await delete_rows(MasteryState, MasteryState.user_id == user_id, "mastery_states")
    await delete_rows(EvidenceTicket, EvidenceTicket.user_id == user_id, "evidence_tickets")
    await delete_rows(MemoryItem, MemoryItem.user_id == user_id, "memory_items")
    await delete_rows(UserPreference, UserPreference.user_id == user_id, "user_preferences")
    await delete_rows(Notification, Notification.user_id == user_id, "notifications")
    await delete_rows(CourseMember, CourseMember.user_id == user_id, "course_memberships")
    await delete_rows(ClassMember, ClassMember.user_id == user_id, "class_memberships")
    await delete_rows(RoleAssignment, RoleAssignment.user_id == user_id, "role_assignments")
    await delete_rows(
        IdempotencyRecord,
        IdempotencyRecord.user_id == user_id,
        "idempotency_records",
    )

    detached = await db.execute(
        update(ModelCallLog).where(ModelCallLog.user_id == user_id).values(user_id=None)
    )
    counts["detached_model_usage_records"] = max(detached.rowcount or 0, 0)
    return counts
