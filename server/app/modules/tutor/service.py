"""教学运行时：证据包构建、主张—证据校验、SSE教学回合与学习状态机。

当前答案生成采用"教材证据抽取式"实现（确定性、可校验、无外部模型依赖）；
接入真实LLM时仅替换 generate_answer，检索、校验、引用与状态机合同不变。
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.model_gateway import call_model
from app.core.providers.llm import OpenAICompatibleLLM
from app.db.base import new_ulid
from app.db.models import ChatTurn, LearningSession
from app.modules.knowledge import service as knowledge_service
from app.modules.knowledge.context import GenerationUnit, assemble_generation_units
from app.modules.knowledge.query import analyze_query

SENTENCE_RE = re.compile(r"[^。！？.!?]+[。！？]?")
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")

MAX_HINT_LEVEL = 3
TOP_EVIDENCE = 3

BACKGROUND_TASKS: set[asyncio.Task] = set()


# ---- 数据结构 ----

@dataclass
class EvidencePackage:
    package_id: str
    course_id: str
    query: str
    retrieval_version: str
    items: list[dict] = field(default_factory=list)
    generation_units: list[GenerationUnit] = field(default_factory=list)
    context_budget_chars: int = 12000
    created_at: str = ""

    def evidence_text(self) -> str:
        return "\n".join(unit.text for unit in self.generation_units)


# ---- 证据包 ----

def build_evidence_package(
    *, user_id: str, course_id: str, query: str, items: list[dict]
) -> EvidencePackage:
    package = EvidencePackage(
        package_id=new_ulid(),
        course_id=course_id,
        query=query,
        retrieval_version=knowledge_service.RETRIEVAL_VERSION,
        created_at=datetime.now(UTC).isoformat(),
    )
    package.generation_units = assemble_generation_units(
        items, context_budget_chars=package.context_budget_chars, max_units=TOP_EVIDENCE
    )
    selected_evidence_ids = {unit.evidence_id for unit in package.generation_units}
    package.items = [item for item in items if item["evidence_id"] in selected_evidence_ids]
    return package


# ---- 抽取式回答生成（可替换为LLM） ----

def generate_answer(query: str, package: EvidencePackage) -> str:
    """从证据中抽取与问题最相关的句子。无可用证据时返回拒答话术。"""
    if not package.items:
        return "当前教材中未找到足够依据回答这个问题，建议补充资料或向教师求助。"
    query_tokens = set(TOKEN_RE.findall(query.lower()))
    best_sentences: list[tuple[float, str]] = []
    for item in package.items:
        for sentence in SENTENCE_RE.findall(item["text"]):
            sentence = sentence.strip()
            if len(sentence) < 8:
                continue
            tokens = set(TOKEN_RE.findall(sentence.lower()))
            overlap = len(tokens & query_tokens) / max(len(tokens), 1)
            best_sentences.append((overlap, sentence))
    best_sentences.sort(key=lambda pair: pair[0], reverse=True)
    picked = [s for score, s in best_sentences if score > 0][:3]
    if not picked:
        picked = [best_sentences[0][1]] if best_sentences else []
    return "根据教材：" + " ".join(picked)


async def generate_grounded_answer(
    db: AsyncSession,
    *,
    query: str,
    package: EvidencePackage,
    user_id: str,
    purpose: str,
) -> tuple[str, str]:
    """按部署配置调用单一供应商；失败时退回教材抽取式答案。"""
    settings = get_settings()
    if settings.llm_provider == "internal" or not package.items:
        return generate_answer(query, package), "internal"
    try:
        provider = OpenAICompatibleLLM(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    except ValueError:
        return generate_answer(query, package), "internal_configuration_fallback"

    async def invoke():
        generated = await provider.generate_grounded_answer(
            query=query, evidence=package.items
        )
        return generated, generated.prompt_tokens, generated.completion_tokens

    try:
        result = await call_model(
            db,
            purpose=purpose,
            provider=settings.llm_provider,
            model=settings.llm_model,
            invoke=invoke,
            user_id=user_id,
        )
    except Exception:  # noqa: BLE001 外部失败不得破坏教材约束回答
        return generate_answer(query, package), "internal_fallback"
    if result.status != "ok" or result.output is None:
        return generate_answer(query, package), "internal_fallback"
    return result.output.answer, settings.llm_provider


# ---- 主张—证据校验 ----

def verify_claims(answer: str, package: EvidencePackage) -> dict:
    """逐句核对是否被证据支持。无支持内容标记为not_found（应删除或标注）。"""
    evidence_text = package.evidence_text().lower()
    evidence_tokens = set(TOKEN_RE.findall(evidence_text))
    claims = []
    for sentence in SENTENCE_RE.findall(answer):
        sentence = sentence.strip()
        if len(sentence) < 4:
            continue
        normalized = sentence.lower().removeprefix("根据教材：")
        tokens = set(TOKEN_RE.findall(normalized))
        if not tokens:
            continue
        overlap = len(tokens & evidence_tokens) / len(tokens)
        level = "supported" if overlap >= 0.9 else "partial" if overlap >= 0.6 else "not_found"
        claims.append({"claim": sentence, "support": level, "overlap": round(overlap, 3)})
    unsupported = sum(1 for c in claims if c["support"] == "not_found")
    return {"claims": claims, "unsupported_count": unsupported}


# ---- SSE 回合 ----

def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": data}


async def run_turn_stream(
    db: AsyncSession,
    *,
    session_row,  # ChatSession
    student_turn_id: str,
    client_turn_id: str,
    content: str,
    purpose: str,
):
    """生成SSE事件流。仅当全部成功时才提交（半截结论不落库）。"""
    yield _sse("state", {"stage": "retrieving"})

    from app.modules.memory.service import is_crisis_content, safety_response

    if is_crisis_content(content):
        answer = safety_response()
        yield _sse("state", {"stage": "safety"})
        for chunk_start in range(0, len(answer), 24):
            yield _sse(
                "delta",
                {"sequence": chunk_start // 24, "text": answer[chunk_start : chunk_start + 24]},
            )
        db.add(
            ChatTurn(
                session_id=session_row.id,
                client_turn_id=client_turn_id,
                role="student",
                content=content,
            )
        )
        tutor_turn = ChatTurn(
            session_id=session_row.id,
            client_turn_id=f"{client_turn_id}:tutor",
            role="tutor",
            content=answer,
            citations=[],
            refusal=True,
            finish_reason="safety",
        )
        db.add(tutor_turn)
        await db.flush()
        await db.refresh(tutor_turn, attribute_names=["id"])
        await db.commit()
        yield _sse(
            "done",
            {
                "turn_id": tutor_turn.id,
                "finish_reason": "safety",
                "saved": True,
                "refusal": True,
            },
        )
        return

    try:
        plan = analyze_query(content)
        items, warnings = await knowledge_service.hybrid_search(
            db,
            user_id=session_row.user_id,
            course_id=session_row.course_id,
            version_ids=await knowledge_service.resolve_searchable_versions(
                db,
                course_id=session_row.course_id,
                requested_version_ids=[],
                staff=False,
            ),
            query=content,
            top_k=min(8, plan.retrieval_budget),
            staff=False,
            channel_priors=plan.channel_priors,
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        yield _sse(
            "error",
            {"code": "RETRIEVAL_FAILED", "retryable": True, "message": str(exc)[:200]},
        )
        return

    package = build_evidence_package(
        user_id=session_row.user_id,
        course_id=session_row.course_id,
        query=content,
        items=items,
    )
    yield _sse(
        "state",
        {"stage": "generating", "evidence_count": len(package.items), "warnings": warnings},
    )

    refusal = not package.items
    answer, generation_provider = await generate_grounded_answer(
        db,
        query=content,
        package=package,
        user_id=session_row.user_id,
        purpose=purpose,
    )
    verification = verify_claims(answer, package)
    if verification["unsupported_count"]:
        answer = generate_answer(content, package)
        generation_provider = "internal_verification_fallback"
        verification = verify_claims(answer, package)
    verification["generation_provider"] = generation_provider
    answer = answer.removeprefix("根据教材：")
    answer = "根据教材：" + answer if not refusal else answer

    for index, item in enumerate(package.items, start=1):
        yield _sse(
            "citation",
            {
                "evidence_id": item["evidence_id"],
                "label": f"[{index}] {item['title']} 第{item['physical_page']}页",
            },
        )

    yield _sse("state", {"stage": "verifying"})
    for chunk_start in range(0, len(answer), 24):
        yield _sse(
            "delta",
            {"sequence": chunk_start // 24, "text": answer[chunk_start : chunk_start + 24]},
        )
        await asyncio.sleep(0.02)

    db.add(
        ChatTurn(
            session_id=session_row.id,
            client_turn_id=client_turn_id,
            role="student",
            content=content,
        )
    )
    tutor_turn = ChatTurn(
        session_id=session_row.id,
        client_turn_id=f"{client_turn_id}:tutor",
        role="tutor",
        content=answer,
        citations=[
            {
                "evidence_id": item["evidence_id"],
                "material_id": item["material_id"],
                "material_version_id": item["material_version_id"],
                "physical_page": item["physical_page"],
                "label": f"[{index}] {item['title']} 第{item['physical_page']}页",
            }
            for index, item in enumerate(package.items, start=1)
        ],
        verification=verification,
        refusal=refusal,
        finish_reason="stop",
    )
    db.add(tutor_turn)
    await db.flush()
    await db.refresh(tutor_turn, attribute_names=["id"])
    await db.commit()
    yield _sse(
        "done",
        {
            "turn_id": tutor_turn.id,
            "finish_reason": "stop",
            "saved": True,
            "refusal": refusal,
            "unsupported_count": verification["unsupported_count"],
        },
    )


# ---- 学习状态机 ----

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "对", "被", "把",
    "个", "这", "那", "the", "a", "an", "of", "to", "is", "are",
}
CORRECT_THRESHOLD = 0.2


def _texts_from_objects(objects: list) -> list[str]:
    return [
        (o.normalized_content or o.raw_content)
        for o in objects
        if o.type in ("paragraph",) and (o.normalized_content or o.raw_content).strip()
    ]


def top_keywords(texts: list[str], n: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        for token in TOKEN_RE.findall(text.lower()):
            if token in STOPWORDS or len(token) == 1:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [token for token, _ in ranked[:n]]


def _evaluate(content: str, keywords: list[str]) -> tuple[bool, float]:
    tokens = set(TOKEN_RE.findall(content.lower()))
    if not tokens or not keywords:
        return False, 0.0
    hits = sum(1 for k in keywords if any(k in t or t in k for t in tokens))
    ratio = hits / len(keywords)
    return ratio >= CORRECT_THRESHOLD, ratio


async def load_chapter_texts(
    db: AsyncSession, *, material_version_id: str, chapter_object_id: str | None
) -> list[str]:
    from app.db.models import KnowledgeObject

    query = select(KnowledgeObject).where(
        KnowledgeObject.material_version_id == material_version_id
    )
    if chapter_object_id:
        chapter = await db.get(KnowledgeObject, chapter_object_id)
        if chapter is not None:
            query = query.where(
                (KnowledgeObject.id == chapter_object_id)
                | (KnowledgeObject.chapter_path == chapter.chapter_path)
            )
    result = await db.execute(query.order_by(KnowledgeObject.reading_order.asc()))
    return _texts_from_objects(list(result.scalars()))


def opening_message(texts: list[str]) -> str:
    summary = texts[0][:120] if texts else "本章暂无可用教材内容。"
    return (
        "在开始讲解之前，想先了解你目前的理解："
        "请用自己的话说说你对这部分内容的认识，或者直接选择“从零开始”。\n"
        f"教材要点提示：{summary}"
    )


def teach_message(texts: list[str]) -> str:
    body = " ".join(texts)[:600] if texts else "教材中暂无本节内容。"
    return (
        f"{body}\n\n"
        "请确认理解情况：回复“继续”进入检查，或回复“没懂”换个方式再讲。"
    )


def check_question(keywords: list[str]) -> str:
    focus = "、".join(keywords[:3]) if keywords else "核心概念"
    return f"检查一下理解：请用自己的话解释“{focus}”之间的关系或区别。"


HINT_LADDER = [
    "先想想这一节主要讨论的是哪两个概念的对比。",
    "提示：关注“控制”与“有效性”之间的因果关系。",
    "示例：研究者控制参与者的分组方式，观察结果差异，由此推断因果。",
]


def hint_message(level: int) -> str:
    if level <= len(HINT_LADDER):
        return f"提示{level}：{HINT_LADDER[level - 1]}"
    return "提示已用完，下面给出完整讲解，请认真学习后进入练习。"


def full_explanation(texts: list[str]) -> str:
    return "完整讲解：" + (" ".join(texts)[:500] if texts else "教材中暂无本节内容。")


def practice_question(keywords: list[str]) -> str:
    focus = keywords[0] if keywords else "本章概念"
    return f"迁移练习：请举一个体现“{focus}”的新例子，并说明理由。"


def summary_message(texts: list[str], keywords: list[str]) -> str:
    focus = "、".join(keywords[:3]) if keywords else "本章内容"
    return f"小结：本节围绕{focus}展开。已完成学习，稍后会安排间隔复习。"


async def start_learning_session(
    db: AsyncSession, *, material_version_id: str, chapter_object_id: str | None
) -> str:
    texts = await load_chapter_texts(
        db, material_version_id=material_version_id, chapter_object_id=chapter_object_id
    )
    return opening_message(texts)


async def respond_learning_session(
    db: AsyncSession,
    session_row: LearningSession,
    content: str,
) -> dict:
    """推进状态机。调用方需先校验state_version。"""
    texts = await load_chapter_texts(
        db,
        material_version_id=session_row.material_version_id,
        chapter_object_id=session_row.chapter_object_id,
    )
    keywords = top_keywords(texts)
    correct, _ = _evaluate(content, keywords)
    state = session_row.state
    action = "wait_for_student"

    if content.strip() in ("从零开始", "没懂", "不会"):
        state, session_row.hint_level = "teach", 0
        session_row.tutor_message = teach_message(texts)
        return {"state": state, "message": session_row.tutor_message, "action": action}

    if state == "diagnose":
        state = "teach"
        session_row.tutor_message = teach_message(texts)
    elif state == "teach":
        if correct:
            state = "check"
            session_row.tutor_message = check_question(keywords)
        else:
            state = "teach"
            session_row.hint_level = min(session_row.hint_level + 1, MAX_HINT_LEVEL)
            session_row.tutor_message = (
                hint_message(session_row.hint_level) + "\n" + teach_message(texts)
            )
    elif state == "check":
        if correct:
            state = "practice"
            session_row.tutor_message = practice_question(keywords)
        else:
            session_row.hint_level += 1
            if session_row.hint_level >= MAX_HINT_LEVEL:
                state = "practice"
                action = "show_example"
                full_note = full_explanation(texts)
                session_row.tutor_message = full_note + "\n" + practice_question(keywords)
                session_row.hint_level = MAX_HINT_LEVEL
            else:
                state = "hint"
                session_row.tutor_message = hint_message(
                    session_row.hint_level
                ) + "\n" + check_question(keywords)
    elif state == "hint":
        if correct:
            state = "practice"
            session_row.tutor_message = practice_question(keywords)
        else:
            session_row.hint_level += 1
            if session_row.hint_level >= MAX_HINT_LEVEL:
                state = "practice"
                action = "show_example"
                session_row.tutor_message = full_explanation(texts) + "\n" + practice_question(
                    keywords
                )
            else:
                session_row.tutor_message = hint_message(
                    session_row.hint_level
                ) + "\n" + check_question(keywords)
    elif state == "practice":
        state = "summary"
        verdict = "回答正确" if correct else "回答有偏差，已记录为待巩固"
        session_row.tutor_message = f"{verdict}。\n" + summary_message(texts, keywords)
    elif state == "summary":
        state = "completed"
        action = "complete"
        session_row.tutor_message = "本节学习已完成，可随时回来复习。"
        session_row.status = "closed"
    else:  # completed
        session_row.tutor_message = "学习已结束。"

    session_row.state = state
    session_row.version += 1
    return {
        "state": session_row.state,
        "message": session_row.tutor_message,
        "action": action,
        "hint_level": session_row.hint_level,
        "correct": correct,
    }
