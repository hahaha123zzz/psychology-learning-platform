"""可解释的 V1 学习进度决策。

这是一个纯函数适配器：只使用服务端已经确认的状态和复习窗口，不把一次作答
直接转换为掌握度，也不在证据不足时判定失败。
"""

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Assessment,
    Attempt,
    CourseRelease,
    LearningEvidence,
    ReviewTask,
)

ProgressDecision = Literal["continue", "review", "remediate", "complete"]


def decide_progress(
    *,
    task_status: str | None,
    task_state: str | None,
    due_review_count: int,
) -> dict[str, str | int | list]:
    if task_status in ("closed", "completed") or task_state == "completed":
        decision: ProgressDecision = "complete"
        reason = "当前学习任务已完成，可查看总结或开始下一项。"
    elif due_review_count > 0:
        decision = "review"
        reason = "存在到期复习任务，应先完成一次独立提取。"
    elif task_state in ("diagnose", "needs_consolidation"):
        decision = "remediate"
        reason = "当前证据仍不足以稳定迁移，先完成一次有依据的补强活动。"
    else:
        decision = "continue"
        reason = "继续当前学习任务，等待新的可验证学习证据。"
    return {
        "decision": decision,
        "reason": reason,
        "due_review_count": due_review_count,
        "fallback": "continue",
        "candidate_budget": 5,
        "candidates": [],
        "source_refs": [],
    }


async def plan_next_step(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    task_status: str | None,
    task_state: str | None,
    timeout_seconds: float = 0.25,
) -> dict[str, Any]:
    """Build a read-only, bounded plan from current published and authorized records."""
    import asyncio

    async def collect() -> dict[str, Any]:
        now = datetime.now(UTC)
        active_attempt_id = await db.scalar(
            select(Attempt.id)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(
                Attempt.user_id == user_id,
                Attempt.status == "in_progress",
                Assessment.course_id == course_id,
            )
            .limit(1)
        )
        if active_attempt_id:
            return {
                "decision": "continue",
                "reason": "正式测评进行中；Planner 不安排内容型教学或额外复习入口。",
                "budget": 0,
                "candidates": [],
                "candidate_budget": 5,
                "source_refs": [],
                "fallback": "continue",
                "fallback_reason": "正式测评的授权安排优先。",
                "policy_version": "planner.v1",
            }
        release = (
            await db.execute(
                select(CourseRelease.id, CourseRelease.version_no)
                .where(
                    CourseRelease.course_id == course_id,
                    CourseRelease.status == "published",
                )
                .order_by(CourseRelease.version_no.desc(), CourseRelease.id.desc())
                .limit(1)
            )
        ).one_or_none()
        release_id = release[0] if release is not None else None
        due_reviews = list(
            (
                await db.execute(
                    select(ReviewTask)
                    .where(
                        ReviewTask.user_id == user_id,
                        ReviewTask.course_id == course_id,
                        ReviewTask.status == "pending",
                        ReviewTask.due_at <= now,
                    )
                    .order_by(ReviewTask.due_at.asc(), ReviewTask.id.asc())
                    .limit(5)
                )
            ).scalars()
        )
        evidence_count = await db.scalar(
            select(LearningEvidence.id)
            .where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.quality_status == "valid",
            )
            .limit(1)
        )
        candidates: list[dict[str, Any]] = []
        for review in due_reviews:
            candidates.append(
                {
                    "choice": "review",
                    "reason": review.reason or "复习任务已到期。",
                    "budget": 1,
                    "source_ref": review.id,
                    "due_at": review.due_at.isoformat(),
                }
            )
        if task_status == "active" and task_state != "completed":
            candidates.append(
                {"choice": "continue", "reason": "当前任务仍处于活动状态。", "budget": 1}
            )
        if release is not None and evidence_count is not None and task_state in (
            "needs_consolidation",
            "diagnose",
        ):
            candidates.append(
                {
                    "choice": "practice",
                    "reason": "当前有效证据提示仍需巩固；课程版本已发布。",
                    "budget": 1,
                    "source_ref": release_id,
                }
            )
        candidates = candidates[:5]
        if candidates:
            selected = candidates[0]
        elif (
            task_state in ("diagnose", "needs_consolidation")
            and release_id is not None
            and evidence_count is not None
        ):
            selected = {
                "choice": "practice",
                "reason": "当前状态需要一次补强练习。",
                "budget": 1,
                "source_ref": release_id,
            }
        else:
            selected = {
                "choice": "continue",
                "reason": "当前证据不足以证明需要切换任务；继续当前学习。",
                "budget": 1,
                "source_ref": release_id,
            }
        return {
            "decision": selected["choice"],
            "reason": selected["reason"],
            "budget": selected["budget"],
            "candidates": candidates,
            "candidate_budget": 5,
            "source_refs": [c["source_ref"] for c in candidates if c.get("source_ref")],
            "fallback": "continue",
            "fallback_reason": "缺少可验证的下一步来源时继续当前任务，不改变学习状态。",
            "policy_version": "planner.v1",
        }

    try:
        return await asyncio.wait_for(collect(), timeout=timeout_seconds)
    except Exception:  # noqa: BLE001 数据陈旧、未知或上游失败时不阻断当前任务
        return {
            "decision": "continue",
            "reason": "暂时无法验证候选来源，继续当前任务。",
            "budget": 1,
            "candidates": [],
            "candidate_budget": 5,
            "source_refs": [],
            "fallback": "continue",
            "fallback_reason": "Planner 查询失败或超时；未写入任务、复习或掌握状态。",
            "policy_version": "planner.v1",
        }
