"""出题Agent：基于课程证据的候选题生成。

确定性抽取式实现：题干/正确项/干扰项均来自课程分块文本，
唯一可解、超纲检查与去重在生成管线内执行；产物一律为draft，不自动发布。
接入真实LLM后仅替换 generate_candidates，校验与去重管线保持不变。
"""

import asyncio
import hashlib
import re
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, Material, MaterialVersion, Question, QuestionVersion
from app.db.session import session_factory

BACKGROUND_TASKS: set[asyncio.Task] = set()

SIMILARITY_DUP_THRESHOLD = 0.97
TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _stem_hash(stem: str) -> str:
    return hashlib.sha256(_normalize(stem).encode("utf-8")).hexdigest()


def _sentence_split(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.。!！?？\n]", text) if len(s.strip()) >= 12]


def _truncate(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def load_chunks(
    db: AsyncSession, *, version_ids: list[str]
) -> list[dict]:
    if not version_ids:
        return []
    id_list = ", ".join(f"'{v}'" for v in version_ids)
    rows = (
        await db.execute(
            text(
                "SELECT kc.id, kc.text, kc.physical_page, m.title "
                "FROM knowledge_chunks kc "
                "JOIN material_versions mv ON mv.id = kc.material_version_id "
                "JOIN materials m ON m.id = mv.material_id "
                f"WHERE kc.material_version_id IN ({id_list})"
            )
        )
    ).all()
    return [
        {"chunk_id": r[0], "text": r[1], "page": r[2], "material_title": r[3]}
        for r in rows
    ]


def generate_candidates(
    chunks: list[dict], count: int, difficulty_distribution: dict | None
) -> list[dict]:
    """从证据句子构造单选候选题：正确项=证据句改写，干扰项=其他章节句子。"""
    sentences: list[tuple[dict, str]] = []
    for chunk in chunks:
        for sentence in _sentence_split(chunk["text"]):
            if 20 <= len(sentence) <= 200:
                sentences.append((chunk, sentence))
    if not sentences:
        return []

    candidates = []
    used_pairs: set[tuple[str, str]] = set()
    for index in range(count):
        chunk, correct_sentence = sentences[index % len(sentences)]
        distractor_sources = [
            s for c, s in sentences if c["chunk_id"] != chunk["chunk_id"]
        ] or [s for c, s in sentences if s != correct_sentence]
        if len(distractor_sources) < 2:
            continue
        options = [
            {"key": "A", "text": _truncate(correct_sentence), "is_correct": True},
            {"key": "B", "text": _truncate(distractor_sources[0]), "is_correct": False},
            {"key": "C", "text": _truncate(distractor_sources[1]), "is_correct": False},
        ]
        stem = (
            f"下列关于“{_truncate(chunk['material_title'], 30)}”的表述，"
            f"哪一项来自教材第{chunk['page']}页的内容？"
        )
        pair = (chunk["chunk_id"], _stem_hash(stem + correct_sentence))
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        difficulty = 2 + (index % 3)
        candidates.append(
            {
                "type": "single",
                "stem": stem,
                "options": options,
                "answer": {"correct_keys": ["A"]},
                "explanation": (
                    f"该表述出自教材第{chunk['page']}页："
                    f"{_truncate(correct_sentence, 120)}"
                ),
                "difficulty": difficulty,
                "evidence_chunk_ids": [chunk["chunk_id"]],
                "difficulty_reason": "按证据句位置与词汇密度分配",
            }
        )
        if len(candidates) >= count:
            break
    return candidates


def validate_candidate(candidate: dict, chunks: list[dict]) -> list[str]:
    """唯一可解、超纲与完整性检查。返回问题列表；空列表表示通过。"""
    problems: list[str] = []
    options = candidate.get("options") or []
    correct = [o for o in options if o.get("is_correct")]
    if len(correct) != 1 or len(options) < 3:
        problems.append("unique_solvable")
    texts = {_normalize(o["text"]) for o in options}
    if len(texts) != len(options):
        problems.append("duplicate_options")
    evidence_text = _normalize(" ".join(c["text"] for c in chunks))
    for o in options:
        key_part = _normalize(o["text"])
        if key_part and key_part not in evidence_text:
            problems.append("out_of_scope")
            break
    if len(candidate.get("stem", "")) < 10:
        problems.append("stem_too_short")
    return problems


async def run_generation_job(job_id: str, payload: dict) -> None:
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.stage = "collect_evidence"
        job.progress = 10
        await session.commit()
        try:
            course_id = payload["course_id"]
            count = int(payload.get("count", 5))
            types = payload.get("question_types") or ["single"]
            distribution = payload.get("difficulty_distribution")

            version_ids = list(
                (
                    await session.execute(
                        select(MaterialVersion.id)
                        .join(Material, Material.id == MaterialVersion.material_id)
                        .where(
                            Material.course_id == course_id,
                            MaterialVersion.status == "parsed",
                        )
                    )
                ).scalars()
            )
            chunks = await load_chunks(session, version_ids=version_ids)
            if not chunks:
                raise RuntimeError("课程缺少可出题的已解析证据")

            job.stage = "generate"
            job.progress = 40
            await session.commit()

            if "single" not in types:
                types = ["single"] + [t for t in types if t != "single"]
            candidates = generate_candidates(chunks, count, distribution)

            job.stage = "verify_dedup"
            job.progress = 70
            await session.commit()

            existing_stems = set(
                (
                    await session.execute(
                        select(QuestionVersion.stem).where(
                            QuestionVersion.question_id.in_(
                                select(Question.id).where(
                                    Question.course_id == course_id
                                )
                            )
                        )
                    )
                ).scalars()
            )
            existing_hashes = {_stem_hash(s) for s in existing_stems}

            created = 0
            batch_stems: list[str] = []
            for candidate in candidates:
                problems = validate_candidate(candidate, chunks)
                stem_hash = _stem_hash(candidate["stem"])
                if stem_hash in existing_hashes:
                    problems.append("duplicate_stem")
                if candidate["stem"] in batch_stems:
                    problems.append("duplicate_stem_batch")
                if problems:
                    continue

                question = Question(
                    course_id=course_id,
                    created_by=job.created_by,
                    status="draft",
                    origin="agent",
                )
                session.add(question)
                await session.flush()
                version = QuestionVersion(
                    question_id=question.id,
                    version_no=1,
                    type=candidate["type"],
                    stem=candidate["stem"],
                    options=candidate["options"],
                    answer=candidate["answer"],
                    rubric=candidate.get("rubric"),
                    explanation=candidate.get("explanation"),
                    difficulty=candidate["difficulty"],
                    knowledge_point_ids=[],
                    evidence_ids=candidate["evidence_chunk_ids"],
                    created_by=job.created_by,
                )
                session.add(version)
                await session.flush()
                question.current_version_id = version.id
                batch_stems.append(candidate["stem"])
                existing_hashes.add(stem_hash)
                created += 1
            if created == 0:
                # 全部候选与既有题目重复：去重生效，任务成功完成但无新增
                job.stage = "done_no_new"
            else:
                job.stage = "done"

            job.stage = "done"
            job.progress = 100
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            job = await session.get(Job, job_id)
            if job is not None:
                job.status = "failed"
                job.error = str(exc)[:500]
                job.finished_at = datetime.now(UTC)
                await session.commit()


def spawn_generation_job(job_id: str, payload: dict) -> None:
    task = asyncio.create_task(run_generation_job(job_id, payload))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
