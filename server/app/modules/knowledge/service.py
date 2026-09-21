import asyncio
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import get_embedding_client
from app.db.base import new_ulid
from app.db.models import (
    EvidenceTicket,
    Job,
    KnowledgeObject,
    Material,
    MaterialVersion,
)
from app.db.session import session_factory

BACKGROUND_TASKS: set[asyncio.Task] = set()

MAX_CHUNK_CHARS = 800
EMBED_BATCH = 32
RRF_K = 60
RETRIEVAL_VERSION = "hybrid-v1"
VECTOR_NONEXIST = "对象尚未完成嵌入或嵌入版本不匹配"

TSQ_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+")


def _or_tsquery(query: str) -> str:
    """把查询词转为 OR 连接的tsquery字面量，避免AND语义导致整句不匹配。"""
    tokens = [t for t in TSQ_TOKEN_RE.findall(query.lower()) if t]
    if not tokens:
        tokens = [query.strip().lower() or "x"]
    return " | ".join(t.replace("&", "").replace("|", "").replace("!", "") for t in tokens)


# ---- 分块构建 ----

def build_chunk_rows(objects: list[KnowledgeObject]) -> list[dict]:
    """章节感知分块：同章节内连续段落合并，超长截断为新块，保留父子关系。"""
    chapters = {o.chapter_path: o for o in objects if o.type == "chapter"}
    chunks: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and current["parts"]:
            chunks.append(current)
        current = None

    for object in sorted(objects, key=lambda o: o.reading_order):
        if object.type == "chapter":
            flush()
            continue
        content = (object.normalized_content or object.raw_content).strip()
        if object.type != "paragraph" or not content:
            continue
        if current is None or current["chapter_path"] != object.chapter_path:
            flush()
            chapter = chapters.get(object.chapter_path)
            current = {
                "chapter_object_id": chapter.id if chapter else None,
                "chapter_path": object.chapter_path,
                "chapter_title": (chapter.title if chapter else "") or "",
                "physical_page": object.physical_page,
                "reading_order": object.reading_order,
                "parts": [],
            }
        current["parts"].append(content)
        if sum(len(p) for p in current["parts"]) >= MAX_CHUNK_CHARS:
            flush()
    flush()
    rows = []
    for chunk in chunks:
        title = chunk["chapter_title"]
        body = "\n".join(chunk["parts"])
        rows.append(
            {
                "id": new_ulid(),
                "chapter_object_id": chunk["chapter_object_id"],
                "chapter_path": chunk["chapter_path"],
                "physical_page": chunk["physical_page"],
                "reading_order": chunk["reading_order"],
                "text": f"{title}\n{body}" if title else body,
            }
        )
    return rows


# ---- 嵌入任务 ----

async def run_embed_job(job_id: str, version_id: str) -> None:
    client = get_embedding_client()
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        version = await session.get(MaterialVersion, version_id)
        if job is None or version is None:
            return
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.stage = "chunk"
        job.progress = 5
        await session.commit()
        try:
            material = await session.get(Material, version.material_id)
            if material is None:
                raise RuntimeError("缺少所属资料")
            objects = list(
                (
                    await session.execute(
                        select(KnowledgeObject)
                        .where(KnowledgeObject.material_version_id == version_id)
                        .order_by(KnowledgeObject.reading_order.asc())
                    )
                ).scalars()
            )
            if not objects:
                raise RuntimeError("版本没有已解析的知识对象")
            rows = build_chunk_rows(objects)
            if not rows:
                raise RuntimeError("分块结果为空")

            job.stage = "embed"
            job.progress = 20
            await session.commit()

            total = len(rows)
            for start in range(0, total, EMBED_BATCH):
                batch = rows[start : start + EMBED_BATCH]
                vectors = await client.embed([r["text"] for r in batch])
                for row, vector in zip(batch, vectors, strict=True):
                    row["embedding"] = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
                progress = 20 + int(70 * (start + len(batch)) / total)
                job.progress = max(job.progress or 0, progress)
                await session.commit()

            # 先完整取得新向量，再在一个事务中替换旧索引；外部调用失败不会破坏旧索引。
            await session.execute(
                text("DELETE FROM knowledge_chunks WHERE material_version_id = :v"),
                {"v": version_id},
            )
            for row in rows:
                await session.execute(
                    text(
                        "INSERT INTO knowledge_chunks "
                        "(id, material_version_id, course_id, chapter_object_id, "
                        " chapter_path, physical_page, reading_order, text, "
                        " embedding, embedding_version) "
                        "VALUES (:id, :version, :course, :chapter, :path, "
                        " :page, :order, :text, CAST(:embedding AS vector), :ev)"
                    ),
                    {
                        "id": row["id"],
                        "version": version_id,
                        "course": material.course_id,
                        "chapter": row["chapter_object_id"],
                        "path": row["chapter_path"],
                        "page": row["physical_page"],
                        "order": row["reading_order"],
                        "text": row["text"],
                        "embedding": row["embedding"],
                        "ev": client.version,
                    },
                )
            await session.execute(text("ANALYZE knowledge_chunks"))
            version.status = "parsed"
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
                job.retryable = True
                job.finished_at = datetime.now(UTC)
                await session.commit()


def spawn_embed_job(job_id: str, version_id: str) -> None:
    task = asyncio.create_task(run_embed_job(job_id, version_id))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


async def find_active_embed_job(db: AsyncSession, version_id: str) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.kind == "material_embed",
            Job.status.in_(("queued", "running")),
            Job.payload["material_version_id"].as_string() == version_id,
        )
    )
    return result.scalar_one_or_none()


# ---- 混合检索 ----

async def resolve_searchable_versions(
    db: AsyncSession, *, course_id: str, requested_version_ids: list[str], staff: bool
) -> list[str]:
    query = (
        select(MaterialVersion.id)
        .join(Material, Material.id == MaterialVersion.material_id)
        .where(
            Material.course_id == course_id,
            MaterialVersion.status == "parsed",
        )
    )
    if not staff:
        query = query.where(
            Material.visibility == "published",
            Material.status == "active",
            Material.current_version_id == MaterialVersion.id,
        )
    if requested_version_ids:
        query = query.where(MaterialVersion.id.in_(requested_version_ids))
    result = await db.execute(query)
    return [row[0] for row in result.all()]


def _rrf_fuse(
    bm25_hits: list[tuple[str, float]], vector_hits: list[tuple[str, float]]
) -> list[tuple[str, float, list[str]]]:
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for rank, (chunk_id, _) in enumerate(bm25_hits, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        sources.setdefault(chunk_id, []).append("bm25")
    for rank, (chunk_id, _) in enumerate(vector_hits, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        sources.setdefault(chunk_id, []).append("vector")
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(cid, score, sources[cid]) for cid, score in ranked]


async def hybrid_search(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    version_ids: list[str],
    query: str,
    top_k: int,
    staff: bool,
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    if not version_ids:
        return [], ["当前课程没有可检索的已解析资料"]

    client = get_embedding_client()
    version_list = ", ".join(f"'{v}'" for v in version_ids)

    tsq = _or_tsquery(query)
    bm25_rows = (
        await db.execute(
            text(
                "SELECT id, ts_rank(text_tsv, to_tsquery('simple', :tsq)) AS rank "
                "FROM knowledge_chunks "
                f"WHERE material_version_id IN ({version_list}) "
                "AND text_tsv @@ to_tsquery('simple', :tsq) "
                "ORDER BY rank DESC LIMIT 50"
            ),
            {"tsq": tsq},
        )
    ).all()
    bm25_hits = [(row[0], float(row[1])) for row in bm25_rows]

    vector_hits: list[tuple[str, float]] = []
    try:
        query_vector = (await client.embed([query]))[0]
        vector_literal = "[" + ",".join(f"{v:.6f}" for v in query_vector) + "]"
        vector_rows = (
            await db.execute(
                text(
                    "SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS cosine "
                    "FROM knowledge_chunks "
                    f"WHERE material_version_id IN ({version_list}) "
                    "AND embedding_version = :ev AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 50"
                ),
                {"vec": vector_literal, "ev": client.version},
            )
        ).all()
        vector_hits = [(row[0], float(row[1])) for row in vector_rows]
    except Exception:  # noqa: BLE001 外部向量服务失败时保留 BM25 可用性
        warnings.append("语义检索暂时不可用，已降级为关键词检索")

    fused = _rrf_fuse(bm25_hits, vector_hits)[:top_k]

    items: list[dict] = []
    if not fused:
        return items, warnings

    id_list = ", ".join(f"'{cid}'" for cid, _, _ in fused)
    meta_rows = (
        await db.execute(
            text(
                "SELECT kc.id, kc.material_version_id, kc.chapter_path, "
                "kc.physical_page, kc.reading_order, kc.text, m.title, m.id "
                "FROM knowledge_chunks kc "
                "JOIN material_versions mv ON mv.id = kc.material_version_id "
                "JOIN materials m ON m.id = mv.material_id "
                f"WHERE kc.id IN ({id_list})"
            )
        )
    ).all()
    meta = {
        row[0]: {
            "material_version_id": row[1],
            "chapter_path": row[2],
            "physical_page": row[3],
            "reading_order": row[4],
            "text": row[5],
            "material_title": row[6],
            "material_id": row[7],
        }
        for row in meta_rows
    }

    now = datetime.now(UTC)
    expires = now + timedelta(seconds=600)
    for chunk_id, score, sources in fused:
        info = meta.get(chunk_id)
        if info is None:
            continue
        ticket = EvidenceTicket(
            id=new_ulid(),
            chunk_id=chunk_id,
            user_id=user_id,
            course_id=course_id,
            material_version_id=info["material_version_id"],
            expires_at=expires,
        )
        item = {
            "evidence_id": ticket.id,
            "material_id": info["material_id"],
            "material_version_id": info["material_version_id"],
            "title": info["material_title"],
            "chapter_path": info["chapter_path"],
            "physical_page": info["physical_page"],
            "printed_page": None,
            "anchor": f"p{info['physical_page']}#order{info['reading_order']}",
            "bbox": None,
            "object_type": "paragraph",
            "text": info["text"],
            "retrieval_sources": sources,
            "review_status": "pending",
        }
        if staff:
            item["score"] = round(score, 6)
        items.append(item)
        db.add(ticket)
    await db.flush()
    return items, warnings
