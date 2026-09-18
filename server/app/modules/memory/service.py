import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_ulid
from app.db.models import (
    LearningEvidence,
    MasteryState,
    MemoryItem,
)

CRISIS_RE = re.compile(
    r"(不想活|自杀|自残|伤害自己|轻生|结束生命|kill myself|suicide|self.?harm)",
    re.IGNORECASE,
)

# 可解释权重：正式测验高于练习；使用提示越多权重越低；复习证据更可信。
SOURCE_WEIGHTS = {"formal_quiz": 1.0, "practice": 0.5, "review": 1.5}

MASTERY_ORDER = [
    "not_started",
    "learning",
    "needs_consolidation",
    "proficient",
    "mastered",
]

# 升级门槛：正确率、加权分与最少证据数同时满足才升级（可解释、可审计）。
PROMOTION_RULES = [
    ("mastered", 0.85, 3.0, 4),
    ("proficient", 0.7, 1.5, 3),
    ("needs_consolidation", 0.4, 0.0, 2),
    ("learning", 0.0, -99.0, 1),
]


def is_crisis_content(content: str) -> bool:
    return bool(CRISIS_RE.search(content or ""))


def safety_response() -> str:
    return (
        "你刚才提到的事情很重要，但这不是学习问题，我无法提供帮助。"
        "如果你现在感到痛苦或有伤害自己的想法，请立即联系学校心理咨询中心、"
        "辅导员，或拨打全国24小时心理援助热线。你并不孤单，专业帮助是可及的。"
    )


def evidence_weight(*, source_type: str, hints_used: int) -> float:
    base = SOURCE_WEIGHTS.get(source_type, 0.5)
    return base / (1.0 + max(hints_used, 0))


async def record_evidence(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    knowledge_points: list[str],
    question_version_id: str,
    attempt_id: str | None,
    source_type: str,
    hints_used: int,
    correct: bool,
) -> list[str]:
    evidence_ids: list[str] = []
    weight = evidence_weight(source_type=source_type, hints_used=hints_used)
    for knowledge_point in knowledge_points:
        evidence = LearningEvidence(
            id=new_ulid(),
            user_id=user_id,
            course_id=course_id,
            knowledge_point=knowledge_point[:200],
            question_version_id=question_version_id,
            attempt_id=attempt_id,
            source_type=source_type,
            hints_used=hints_used,
            correct=correct,
            weight=weight,
        )
        db.add(evidence)
        evidence_ids.append(evidence.id)
    await db.flush()
    return evidence_ids


async def recompute_mastery(
    db: AsyncSession, *, user_id: str, course_id: str
) -> None:
    evidence_rows = (
        await db.execute(
            select(LearningEvidence).where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
            )
        )
    ).scalars()
    groups: dict[str, list[LearningEvidence]] = {}
    for evidence in evidence_rows:
        groups.setdefault(evidence.knowledge_point, []).append(evidence)

    existing = {
        state.knowledge_point: state
        for state in (
            await db.execute(
                select(MasteryState).where(
                    MasteryState.user_id == user_id,
                    MasteryState.course_id == course_id,
                )
            )
        ).scalars()
    }

    for knowledge_point, evidences in groups.items():
        evidences.sort(key=lambda e: e.created_at)
        total_weight = sum(e.weight for e in evidences)
        correct_weight = sum(e.weight for e in evidences if e.correct)
        ratio = correct_weight / total_weight if total_weight else 0.0
        count = len(evidences)
        last = evidences[-1]

        # 最近一次答错且加权分不足时，直接进入需巩固，避免“刷通过率”。
        new_state = "learning"
        for state_name, min_ratio, min_score, min_count in PROMOTION_RULES:
            if count >= min_count and ratio >= min_ratio and total_weight >= min_score:
                new_state = state_name
                break
        if not last.correct and new_state in ("proficient", "mastered"):
            new_state = "needs_consolidation"

        state_row = existing.get(knowledge_point)
        if state_row is None:
            state_row = MasteryState(
                user_id=user_id,
                course_id=course_id,
                knowledge_point=knowledge_point,
                version=1,
            )
            db.add(state_row)
        state_row.state = new_state
        state_row.evidence_count = count
        state_row.correct_ratio = round(ratio, 4)
        state_row.weight_score = round(total_weight, 4)
        state_row.last_evidence_id = last.id
        state_row.version = (state_row.version or 1) + 1


def _weakness_from_recent(recent: list[LearningEvidence]) -> float | None:
    """同一知识点最近两条证据均错误时返回置信度，否则None（单次错误仅待确认）。"""
    if len(recent) == 2 and all(not e.correct for e in recent):
        return min(0.4 + 0.1 * sum(e.hints_used for e in recent), 0.9)
    return None


async def update_memory_after_submit(
    db: AsyncSession, *, user_id: str, course_id: str, attempt_id: str
) -> None:
    evidences = list(
        (
            await db.execute(
                select(LearningEvidence).where(
                    LearningEvidence.user_id == user_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.attempt_id == attempt_id,
                )
            )
        ).scalars()
    )
    if not evidences:
        return
    knowledge_points = sorted({e.knowledge_point for e in evidences})
    for knowledge_point in knowledge_points:
        recent_rows = await db.execute(
            select(LearningEvidence)
            .where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.knowledge_point == knowledge_point,
            )
            .order_by(
                LearningEvidence.created_at.desc(),
                LearningEvidence.id.desc(),
            )
            .limit(2)
        )
        recent = list(recent_rows.scalars())
        confidence = _weakness_from_recent(recent)
        if confidence is None:
            continue
        content = f"对“{knowledge_point}”的掌握仍不稳定，测验中多次出错。"
        existing = (
            await db.execute(
                select(MemoryItem).where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.course_id == course_id,
                    MemoryItem.layer == "L1",
                    MemoryItem.kind == "weakness",
                    MemoryItem.content == content,
                    MemoryItem.stale.is_(False),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.confidence = min(existing.confidence + 0.1, 0.95)
            continue
        db.add(
            MemoryItem(
                user_id=user_id,
                course_id=course_id,
                layer="L1",
                kind="weakness",
                content=content,
                source_type="quiz",
                source_ref=attempt_id[:64],
                confidence=confidence,
            )
        )


async def promote_weakness_if_mastered(
    db: AsyncSession, *, user_id: str, course_id: str
) -> None:
    """L2升级：连续复习证据正确时，旧L1记忆标记为被新事实替代（不删除）。"""
    states = list(
        (
            await db.execute(
                select(MasteryState).where(
                    MasteryState.user_id == user_id,
                    MasteryState.course_id == course_id,
                    MasteryState.state.in_(("mastered", "proficient")),
                )
            )
        ).scalars()
    )
    for state_row in states:
        stale_candidates = list(
            (
                await db.execute(
                    select(MemoryItem).where(
                        MemoryItem.user_id == user_id,
                        MemoryItem.course_id == course_id,
                        MemoryItem.layer == "L1",
                        MemoryItem.kind == "weakness",
                        MemoryItem.stale.is_(False),
                        MemoryItem.content.contains(state_row.knowledge_point),
                    )
                )
            ).scalars()
        )
        for item in stale_candidates:
            fact = MemoryItem(
                user_id=user_id,
                course_id=course_id,
                layer="L2",
                kind="strength",
                content=f"“{state_row.knowledge_point}”已通过复习确认为掌握项。",
                source_type="review",
                source_ref=state_row.id,
                confidence=0.85,
            )
            db.add(fact)
            await db.flush()
            item.stale = True
            item.superseded_by_id = fact.id


async def memory_summary(db: AsyncSession, *, user_id: str) -> dict:
    """渐进加载：目录与摘要优先，明细按需再取。"""
    rows = (
        await db.execute(
            select(
                MemoryItem.layer,
                MemoryItem.kind,
                func.count(MemoryItem.id),
            )
            .where(
                MemoryItem.user_id == user_id,
                MemoryItem.stale.is_(False),
            )
            .group_by(MemoryItem.layer, MemoryItem.kind)
        )
    ).all()
    summary = {
        f"{layer}:{kind}": count for layer, kind, count in rows
    }
    stale_count = (
        await db.execute(
            select(func.count(MemoryItem.id)).where(
                MemoryItem.user_id == user_id,
                MemoryItem.stale.is_(True),
            )
        )
    ).scalar_one()
    return {"summary": summary, "stale_hidden": stale_count}


async def memory_items_detail(
    db: AsyncSession, *, user_id: str, layer: str | None, limit: int
) -> list[dict]:
    query = select(MemoryItem).where(
        MemoryItem.user_id == user_id,
        MemoryItem.stale.is_(False),
    )
    if layer:
        query = query.where(MemoryItem.layer == layer)
    rows = (
        await db.execute(query.order_by(MemoryItem.confidence.desc()).limit(limit))
    ).scalars()
    return [
        {
            "id": item.id,
            "layer": item.layer,
            "kind": item.kind,
            "content": item.content,
            "confidence": item.confidence,
            "course_id": item.course_id,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in rows
    ]


def next_review_due(last_completed: datetime | None) -> datetime:
    """简易间隔：完成1天后到期；接入FSRS时替换此处。"""
    base = last_completed or datetime.now(UTC)
    return base + timedelta(days=1)
