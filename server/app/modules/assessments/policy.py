from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import Assessment, Attempt


async def ensure_ai_support_available(db: AsyncSession, *, user_id: str) -> None:
    """拒绝通过普通学习入口访问进行中正式测评的内容性 AI 支持。

    当前没有独立且可验证的方向提示执行器，因此 direction_only 也必须
    fail-closed；测验提交后再按其策略展示结果解析。
    """
    policy = await db.scalar(
        select(Assessment.ai_policy)
        .join(Attempt, Attempt.assessment_id == Assessment.id)
        .where(
            Attempt.user_id == user_id,
            Attempt.status == "in_progress",
            # 兼容没有 purpose 的历史测评，继续按正式测评保守限制。
            or_(Assessment.purpose == "formal", Assessment.purpose.is_(None)),
        )
        .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        .limit(1)
    )
    if policy is None:
        return
    raise ApiError(
        status_code=403,
        code="EXAM_AI_SUPPORT_RESTRICTED",
        message="正式测验进行中，AI 学习支持和历史解析暂不可用；提交后按测验策略查看结果。",
        details={"ai_policy": policy},
    )


def result_is_visible(assessment: Assessment, attempt: Attempt, *, now: datetime) -> bool:
    """Evaluate the persisted result policy; missing legacy policy fails closed."""
    policy = assessment.result_visibility_policy
    if policy is None or attempt.status not in {"submitted", "graded"}:
        return False
    if policy == "immediate_after_submission":
        return assessment.purpose == "practice"
    if policy == "after_close":
        return assessment.status == "closed" or (
            assessment.closes_at is not None and now >= assessment.closes_at
        )
    if policy == "after_grading":
        return attempt.status == "graded"
    if policy == "manual_release":
        return assessment.results_released_at is not None
    return False


def require_result_visible(assessment: Assessment, attempt: Attempt, *, now: datetime) -> None:
    if not result_is_visible(assessment, attempt, now=now):
        raise ApiError(
            status_code=403,
            code="ASSESSMENT_RESULT_NOT_RELEASED",
            message="测评结果尚未按发布策略开放",
            details={"result_visibility_policy": assessment.result_visibility_policy},
        )
