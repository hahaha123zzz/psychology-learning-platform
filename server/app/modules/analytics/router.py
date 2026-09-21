"""教师课程学情聚合接口；默认不返回学生私聊正文或个人画像。"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import ok
from app.db.models import (
    Assessment,
    Attempt,
    AttemptAnswer,
    CourseMember,
    KnowledgeObject,
    LearningSession,
    MasteryState,
    Material,
    QuestionVersion,
    ReviewTask,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role

router = APIRouter()


@router.get("/courses/{course_id}/analytics/overview", response_model=None)
async def course_analytics_overview(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """返回可核对的班级聚合；不下发问答正文、记忆条目或个人明细。"""
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})

    student_count = int(
        await db.scalar(
            select(func.count(CourseMember.id)).where(
                CourseMember.course_id == course_id,
                CourseMember.role == "student",
                CourseMember.status == "active",
            )
        )
        or 0
    )
    engaged_students = int(
        await db.scalar(
            select(func.count(func.distinct(LearningSession.user_id))).where(
                LearningSession.course_id == course_id
            )
        )
        or 0
    )
    completed_sessions = int(
        await db.scalar(
            select(func.count(LearningSession.id)).where(
                LearningSession.course_id == course_id,
                LearningSession.status == "closed",
            )
        )
        or 0
    )
    published_materials = int(
        await db.scalar(
            select(func.count(Material.id)).where(
                Material.course_id == course_id,
                Material.visibility == "published",
                Material.status == "active",
            )
        )
        or 0
    )

    assessment_row = (
        await db.execute(
            select(
                func.count(Attempt.id),
                func.count(func.distinct(Attempt.user_id)),
                func.avg(Attempt.score),
            )
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(
                Assessment.course_id == course_id,
                Attempt.status.in_(("submitted", "graded")),
            )
        )
    ).one()
    attempt_count = int(assessment_row[0] or 0)
    assessment_participants = int(assessment_row[1] or 0)
    average_score = (
        round(float(assessment_row[2]), 2) if assessment_row[2] is not None else None
    )

    mastery_rows = (
        await db.execute(
            select(MasteryState.state, func.count(MasteryState.id))
            .where(MasteryState.course_id == course_id)
            .group_by(MasteryState.state)
            .order_by(MasteryState.state.asc())
        )
    ).all()
    mastery_distribution = {state: int(count) for state, count in mastery_rows}

    difficulty_rows = (
        await db.execute(
            select(
                MasteryState.knowledge_point,
                func.count(MasteryState.id).label("student_count"),
                func.avg(MasteryState.correct_ratio).label("correct_ratio"),
            )
            .where(
                MasteryState.course_id == course_id,
                MasteryState.state.in_(("learning", "needs_consolidation")),
            )
            .group_by(MasteryState.knowledge_point)
            .order_by(func.count(MasteryState.id).desc())
            .limit(10)
        )
    ).all()
    difficulties = [
        {
            "knowledge_point": point,
            "student_count": int(count),
            "average_correct_ratio": round(float(ratio or 0), 3),
        }
        for point, count, ratio in difficulty_rows
    ]

    chapter_rows = (
        await db.execute(
            select(
                LearningSession.chapter_object_id,
                KnowledgeObject.title,
                func.count(func.distinct(LearningSession.user_id)),
                func.count(LearningSession.id).filter(LearningSession.status == "closed"),
            )
            .outerjoin(
                KnowledgeObject,
                KnowledgeObject.id == LearningSession.chapter_object_id,
            )
            .where(
                LearningSession.course_id == course_id,
                LearningSession.chapter_object_id.is_not(None),
            )
            .group_by(LearningSession.chapter_object_id, KnowledgeObject.title)
            .order_by(func.count(func.distinct(LearningSession.user_id)).desc())
        )
    ).all()
    chapter_participation = [
        {
            "chapter_object_id": chapter_id,
            "chapter_title": title or "未命名章节",
            "participant_count": int(participants),
            "completed_session_count": int(completed),
        }
        for chapter_id, title, participants, completed in chapter_rows
    ]

    wrong_rows = (
        await db.execute(
            select(
                AttemptAnswer.question_version_id,
                QuestionVersion.stem,
                func.count(AttemptAnswer.id),
            )
            .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .join(
                QuestionVersion,
                QuestionVersion.id == AttemptAnswer.question_version_id,
            )
            .where(
                Assessment.course_id == course_id,
                AttemptAnswer.is_correct.is_(False),
            )
            .group_by(AttemptAnswer.question_version_id, QuestionVersion.stem)
            .order_by(func.count(AttemptAnswer.id).desc())
            .limit(10)
        )
    ).all()
    common_wrong_questions = [
        {
            "question_version_id": question_version_id,
            "stem": stem,
            "wrong_count": int(count),
        }
        for question_version_id, stem, count in wrong_rows
    ]

    pending_reviews = int(
        await db.scalar(
            select(func.count(ReviewTask.id)).where(
                ReviewTask.course_id == course_id,
                ReviewTask.status == "pending",
            )
        )
        or 0
    )
    generated_at = datetime.now(UTC).isoformat()
    return ok(
        request,
        {
            "course_id": course_id,
            "scope": {
                "member_status": "active",
                "student_role": "student",
                "attempt_statuses": ["submitted", "graded"],
                "time_range": "all_time",
            },
            "generated_at": generated_at,
            "participation": {
                "student_count": student_count,
                "engaged_student_count": engaged_students,
                "completed_learning_session_count": completed_sessions,
                "published_material_count": published_materials,
            },
            "assessments": {
                "attempt_count": attempt_count,
                "participant_count": assessment_participants,
                "average_score": average_score,
            },
            "mastery_distribution": mastery_distribution,
            "chapter_participation": chapter_participation,
            "difficulties": difficulties,
            "common_wrong_questions": common_wrong_questions,
            "pending_review_task_count": pending_reviews,
            "privacy": {
                "aggregation_only": True,
                "chat_content_included": False,
                "memory_content_included": False,
            },
        },
    )
