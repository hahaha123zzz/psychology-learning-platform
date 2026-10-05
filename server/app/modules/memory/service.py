import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_ulid
from app.db.models import (
    AuditLog,
    CourseMember,
    LearningEvidence,
    LearningSession,
    MasteryState,
    MemoryItem,
)

CRISIS_RE = re.compile(
    r"(不想活|自杀|自残|伤害自己|轻生|结束生命|kill myself|suicide|self.?harm)",
    re.IGNORECASE,
)
ACADEMIC_CONTEXT_RE = re.compile(
    r"(教材|课程|课堂|实验心理学|心理学研究|研究中|论文|学术|量表|定义|概念|操作化|"
    r"理论|被试|变量|作业|案例分析|文献|历史上|科普|什么是|请解释|解释一下|如何定义|"
    r"\b(?:define|what is|explain)\b)",
    re.IGNORECASE,
)
PERSONAL_RISK_RE = re.compile(
    r"(?:我|本人|自己)(?!的(?:朋友|同学|家人|室友|同事)).{0,12}(?:不想活|不愿活|想死|"
    r"想(?:自杀|自残|轻生|伤害自己)|(?:有|出现|控制不住).{0,4}(?:自杀|自残).{0,5}"
    r"(?:念头|想法|冲动)|准备.{0,6}(?:自杀|自残|结束生命))|"
    r"(?:我的)(?:自杀|轻生|自残|伤害自己)(?:念头|想法|冲动)|"
    r"(?:准备|计划)(?:今晚|现在|今天)?.{0,5}(?:自杀|轻生|结束生命|自残)",
    re.IGNORECASE,
)
OTHER_PERSON_RISK_RE = re.compile(
    r"(?:朋友|同学|家人|室友|同事).{0,10}(?:说|表示|提到|计划|准备|有).{0,8}"
    r"(?:不想活|自杀|自残|轻生|结束生命)",
    re.IGNORECASE,
)

# 可解释权重：正式测验高于练习；使用提示越多权重越低；复习证据更可信。
SOURCE_WEIGHTS = {"formal_quiz": 1.0, "practice": 0.5, "review": 1.5}
MASTERY_ALGORITHM_VERSION = "mastery-v2-independent-context"

MASTERY_ORDER = [
    "not_started",
    "learning",
    "needs_consolidation",
    "proficient",
    "mastered",
]

def mastery_decision(
    *,
    evidence_count: int,
    correct_ratio: float,
    weight_score: float,
    context_count: int,
    independent_evidence_count: int,
    last_correct: bool,
) -> tuple[str, str]:
    """返回符合独立性与跨情境门槛的掌握状态及可读理由。"""
    if evidence_count <= 0:
        return "not_started", "尚无有效学习证据。"

    mastered_base = evidence_count >= 4 and correct_ratio >= 0.85 and weight_score >= 3.0
    proficient_base = evidence_count >= 3 and correct_ratio >= 0.7 and weight_score >= 1.5
    if mastered_base:
        if independent_evidence_count < 3 or context_count < 2:
            return "learning", "总体表现达到掌握区间，但仍需至少3条独立证据并覆盖2种情境。"
        if not last_correct:
            return "needs_consolidation", "最近一次验证未通过，需要巩固后再次检查。"
        return "mastered", "达到正确率与证据量门槛，且有3条独立证据覆盖至少2种情境。"
    if proficient_base:
        if independent_evidence_count < 2 or context_count < 2:
            return "learning", "总体表现达到熟练区间，但仍需至少2条独立证据并覆盖2种情境。"
        if not last_correct:
            return "needs_consolidation", "最近一次验证未通过，需要巩固后再次检查。"
        return "proficient", "达到熟练门槛，且有2条独立证据覆盖至少2种情境。"
    if evidence_count >= 2 and correct_ratio >= 0.4:
        return "needs_consolidation", "已有多条证据，但当前表现仍需要巩固。"
    return "learning", "证据尚不足以稳定判断掌握情况。"


def is_crisis_content(content: str) -> bool:
    text = content or ""
    if not CRISIS_RE.search(text):
        return False
    # 明确个人意图及身边人的现实风险优先于课程语境，不允许以学术措辞压过求助信号。
    if PERSONAL_RISK_RE.search(text) or OTHER_PERSON_RISK_RE.search(text):
        return True
    # 教材/研究中的术语讨论不应退出教学流程；没有明确教育语境时仍保守转入支持回复。
    return not ACADEMIC_CONTEXT_RE.search(text)


def safety_response() -> str:
    return (
        "谢谢你告诉我，这听起来很难受。你不必独自处理。如果你或你关心的人现在可能马上伤害自己，"
        "请先到有他人在场的安全地点，联系可信任的人陪伴，并联系当地急救服务或前往最近的医院急诊。"
        "也可以尝试拨打全国统一心理援助热线12356；各地接听安排和服务时段可能不同。"
    )


def evidence_weight(
    *, source_type: str, hints_used: int, independence_status: str = "unknown"
) -> float:
    base = SOURCE_WEIGHTS.get(source_type, 0.5)
    support_factor = 0.5 if independence_status == "supported" else 1.0
    return base * support_factor / (1.0 + max(hints_used, 0))


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
    dimension: str = "understand",
    independence_status: str = "unknown",
    context_key: str | None = None,
    course_release_assignment_id: str | None = None,
    course_release_id: str | None = None,
) -> list[str]:
    if (course_release_assignment_id is None) != (course_release_id is None):
        raise ValueError("课程版本 assignment 与 release 必须同时提供")
    if attempt_id is not None:
        source_session = await db.get(LearningSession, attempt_id)
        if source_session is not None:
            if source_session.user_id != user_id or source_session.course_id != course_id:
                raise ValueError("学习证据来源会话不属于当前用户或课程")
            source_assignment_id = source_session.course_release_assignment_id
            source_release_id = source_session.course_release_id
            if (source_assignment_id is None) != (source_release_id is None):
                raise ValueError("学习会话的课程版本绑定不完整")
            if course_release_assignment_id is None:
                course_release_assignment_id = source_assignment_id
                course_release_id = source_release_id
            elif (
                course_release_assignment_id != source_assignment_id
                or course_release_id != source_release_id
            ):
                raise ValueError("学习证据课程版本必须与来源会话绑定一致")
    evidence_ids: list[str] = []
    weight = evidence_weight(
        source_type=source_type,
        hints_used=hints_used,
        independence_status=independence_status,
    )
    for knowledge_point in knowledge_points:
        evidence = LearningEvidence(
            id=new_ulid(),
            user_id=user_id,
            course_id=course_id,
            course_release_assignment_id=course_release_assignment_id,
            course_release_id=course_release_id,
            knowledge_point=knowledge_point[:200],
            question_version_id=question_version_id,
            attempt_id=attempt_id,
            source_type=source_type,
            dimension=dimension,
            independence_status=independence_status,
            context_key=context_key,
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
                LearningEvidence.quality_status == "valid",
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
        context_count = len({e.context_key for e in evidences if e.context_key})
        independent_count = sum(1 for e in evidences if e.independence_status == "independent")
        last = evidences[-1]

        new_state, state_reason = mastery_decision(
            evidence_count=count,
            correct_ratio=ratio,
            weight_score=total_weight,
            context_count=context_count,
            independent_evidence_count=independent_count,
            last_correct=last.correct,
        )

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
        state_row.context_count = context_count
        state_row.independent_evidence_count = independent_count
        state_row.last_evidence_id = last.id
        state_row.algorithm_version = MASTERY_ALGORITHM_VERSION
        state_row.state_reason = state_reason
        state_row.version = (state_row.version or 1) + 1

    for knowledge_point, state_row in existing.items():
        if knowledge_point in groups:
            continue
        state_row.state = "not_started"
        state_row.evidence_count = 0
        state_row.correct_ratio = 0.0
        state_row.weight_score = 0.0
        state_row.context_count = 0
        state_row.independent_evidence_count = 0
        state_row.last_evidence_id = None
        state_row.algorithm_version = MASTERY_ALGORITHM_VERSION
        state_row.state_reason = "当前没有有效证据；状态在证据失效后重新计算。"
        state_row.version = (state_row.version or 1) + 1


def _weakness_from_recent(recent: list[LearningEvidence]) -> float | None:
    """仅两次独立作答的重复错误可形成待复核候选，不确认技能/误区。"""
    attempts = {item.attempt_id for item in recent if item.attempt_id}
    if (
        len(recent) == 2
        and all(not item.correct for item in recent)
        and all(item.independence_status == "independent" for item in recent)
        and len(attempts) >= 2
    ):
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
                    LearningEvidence.quality_status == "valid",
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
                LearningEvidence.quality_status == "valid",
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
        content = f"对“{knowledge_point}”的掌握仍不稳定，多个独立作答中出现错误，待复核。"
        now = datetime.now(UTC)
        evidence_refs = sorted({e.id for e in recent})
        existing = (
            await db.execute(
                select(MemoryItem).where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.course_id == course_id,
                    MemoryItem.layer == "L1",
                    MemoryItem.kind == "weakness",
                    MemoryItem.content == content,
                    MemoryItem.stale.is_(False),
                    MemoryItem.conflict_status == "none",
                    or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.confidence = min(existing.confidence + 0.1, 0.95)
            existing.evidence_refs = sorted(set(existing.evidence_refs or []) | set(evidence_refs))
            existing.review_after = now + timedelta(days=14)
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
                provenance_level="inferred",
                evidence_refs=evidence_refs,
                valid_from=now,
                review_after=now + timedelta(days=14),
                confidence=confidence,
            )
        )


async def promote_weakness_if_mastered(
    db: AsyncSession, *, user_id: str, course_id: str
) -> None:
    """Legacy hook retained as a no-op; mastery never auto-promotes/demotes Memory."""
    del db, user_id, course_id


def effective_memory_conditions(*, user_id: str, course_id: str | None, now: datetime):
    """Return only this learner's current-scope, currently valid, non-conflicted memories."""
    return (
        MemoryItem.user_id == user_id,
        MemoryItem.course_id.is_(None) if course_id is None else MemoryItem.course_id == course_id,
        MemoryItem.stale.is_(False),
        or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
        or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
        MemoryItem.conflict_status.in_(("none", "resolved")),
    )


async def memory_summary(
    db: AsyncSession, *, user_id: str, course_id: str | None = None
) -> dict:
    """渐进加载：目录与摘要优先，明细按需再取。"""
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(
                MemoryItem.layer,
                MemoryItem.kind,
                func.count(MemoryItem.id),
            )
            .where(
                *effective_memory_conditions(
                    user_id=user_id, course_id=course_id, now=now
                )
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
                (
                    MemoryItem.course_id.is_(None)
                    if course_id is None
                    else MemoryItem.course_id == course_id
                ),
                MemoryItem.stale.is_(True),
            )
        )
    ).scalar_one()
    return {"summary": summary, "stale_hidden": stale_count}


async def memory_items_detail(
    db: AsyncSession, *, user_id: str, layer: str | None, limit: int, course_id: str | None = None
) -> list[dict]:
    now = datetime.now(UTC)
    query = select(MemoryItem).where(
        *effective_memory_conditions(user_id=user_id, course_id=course_id, now=now)
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
            "provenance_level": item.provenance_level,
            "evidence_refs": item.evidence_refs or [],
            "valid_from": item.valid_from.isoformat() if item.valid_from else None,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "review_after": item.review_after.isoformat() if item.review_after else None,
            "needs_review": item.review_after is not None and item.review_after <= now,
            "conflict_status": item.conflict_status,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in rows
    ]


async def record_memory_candidate(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str | None,
    layer: str,
    kind: str,
    content: str,
    source_type: str,
    source_ref: str | None,
    provenance_level: str,
    evidence_refs: list[str],
    confidence: float,
    source_completed: bool,
    valid_from: datetime | None = None,
    expires_at: datetime | None = None,
    review_after: datetime | None = None,
) -> MemoryItem:
    """Persist a completed-source candidate; streaming/partial sources are rejected."""
    if not source_completed:
        raise ValueError("未完成的回合或作答不能写入长期记忆")
    if layer not in {"L1", "L2", "L3"}:
        raise ValueError("不支持的记忆层级")
    if provenance_level not in {"observed", "inferred", "explicit", "teacher_confirmed"}:
        raise ValueError("不支持的来源等级")
    if source_type not in {"quiz", "tutor", "practice", "user", "review"}:
        raise ValueError("不支持的记忆来源")
    if provenance_level in {"observed", "inferred", "teacher_confirmed"} and not evidence_refs:
        raise ValueError("该来源等级必须保留至少一个证据引用")
    if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
        raise ValueError("证据引用必须为非空字符串")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence 必须在 0 到 1 之间")
    item = MemoryItem(
        id=new_ulid(),
        user_id=user_id,
        course_id=course_id,
        layer=layer,
        kind=kind,
        content=content,
        source_type=source_type,
        source_ref=source_ref,
        provenance_level=provenance_level,
        evidence_refs=sorted(set(evidence_refs)),
        valid_from=valid_from or datetime.now(UTC),
        expires_at=expires_at,
        review_after=review_after,
        confidence=confidence,
    )
    db.add(item)
    await db.flush()
    return item


async def open_memory_conflict(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str | None,
    first_memory_id: str,
    second_memory_id: str,
    reason: str,
) -> str:
    """Keep both alternatives and mark them unresolved; never pick one automatically."""
    if first_memory_id == second_memory_id or not reason.strip():
        raise ValueError("冲突需要两个不同的记忆条目和理由")
    rows = list(
        (
            await db.execute(
                select(MemoryItem)
                .where(
                    MemoryItem.id.in_((first_memory_id, second_memory_id)),
                    MemoryItem.user_id == user_id,
                    MemoryItem.course_id.is_(None)
                    if course_id is None
                    else MemoryItem.course_id == course_id,
                    MemoryItem.stale.is_(False),
                )
                .order_by(MemoryItem.id.asc())
                .with_for_update()
            )
        ).scalars()
    )
    if {item.id for item in rows} != {first_memory_id, second_memory_id}:
        raise ValueError("冲突条目不属于同一用户与课程 Scope")
    if any(item.conflict_status == "open" for item in rows):
        raise ValueError("记忆条目已属于待处理冲突")
    group_id = new_ulid()
    for item in rows:
        item.conflict_group_id = group_id
        item.conflict_status = "open"
        item.conflict_resolution_reason = reason.strip()
        item.conflict_resolved_by_id = None
        item.conflict_resolved_at = None
    await db.flush()
    return group_id


async def resolve_memory_conflict(
    db: AsyncSession,
    *,
    owner_user_id: str,
    course_id: str | None,
    conflict_group_id: str,
    keep_memory_id: str,
    actor_user_id: str,
    reason: str,
) -> dict[str, str | int]:
    """Resolve a conflict without deleting sides; only the owner or scoped staff may decide."""
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 1000:
        raise ValueError("冲突处理必须提供不超过1000字的理由")
    rows = list(
        (
            await db.execute(
                select(MemoryItem)
                .where(
                    MemoryItem.user_id == owner_user_id,
                    MemoryItem.course_id.is_(None)
                    if course_id is None
                    else MemoryItem.course_id == course_id,
                    MemoryItem.conflict_group_id == conflict_group_id,
                    MemoryItem.conflict_status == "open",
                )
                .order_by(MemoryItem.id.asc())
                .with_for_update()
            )
        ).scalars()
    )
    chosen = next((item for item in rows if item.id == keep_memory_id), None)
    if chosen is None or len(rows) < 2:
        raise ValueError("冲突组不存在或不完整")
    teacher_authorized = False
    if actor_user_id != owner_user_id and course_id is not None:
        teacher_authorized = (
            await db.scalar(
                select(CourseMember.id).where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id == actor_user_id,
                    CourseMember.status == "active",
                    CourseMember.role.in_(("teacher", "assistant")),
                ).limit(1)
            )
        ) is not None
    if actor_user_id != owner_user_id and not teacher_authorized:
        raise PermissionError("只有记忆所有者或当前课程教师/助教可处理该冲突")

    now = datetime.now(UTC)
    for item in rows:
        item.conflict_status = "resolved"
        item.conflict_resolution_reason = normalized_reason
        item.conflict_resolved_by_id = actor_user_id
        item.conflict_resolved_at = now
        if item.id != chosen.id:
            item.stale = True
            item.superseded_by_id = chosen.id
    if teacher_authorized:
        chosen.provenance_level = "teacher_confirmed"
    db.add(
        AuditLog(
            actor_id=actor_user_id,
            action="memory.conflict.resolved",
            resource_type="memory_conflict",
            resource_id=conflict_group_id,
            course_id=course_id,
            detail={
                "owner_user_id": owner_user_id,
                "kept_memory_id": chosen.id,
                "reason": normalized_reason,
            },
        )
    )
    await db.flush()
    return {
        "conflict_group_id": conflict_group_id,
        "kept_memory_id": chosen.id,
        "resolved_count": len(rows),
    }


def next_review_due(last_completed: datetime | None) -> datetime:
    """简易间隔：完成1天后到期；接入FSRS时替换此处。"""
    base = last_completed or datetime.now(UTC)
    return base + timedelta(days=1)
