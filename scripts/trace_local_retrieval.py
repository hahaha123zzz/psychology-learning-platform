"""导出本地 hash-v1 教材检索的逐阶段排序追踪，不调用外部服务。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

from app.core.config import get_settings
from app.core.embedding import get_embedding_client
from app.db.session import session_factory
from app.modules.knowledge.diagnostics import build_ranking_trace
from app.modules.knowledge.query import analyze_query
from app.modules.knowledge.service import (
    _has_hash_keyword_anchor,
    _or_tsquery,
    _search_tokens,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def _trace_case(*, version_id: str, case: dict, top_k: int) -> dict:
    client = get_embedding_client()
    if client.version != "hash-v1":
        raise RuntimeError("本地开放教材追踪只允许 hash-v1")
    query = case["query"]
    tokens = _search_tokens(query)
    plan = analyze_query(query)
    async with session_factory() as db:
        bm25_rows = (
            await db.execute(
                text(
                    "SELECT kc.id, kc.physical_page, "
                    "ts_rank(kc.text_tsv, to_tsquery('simple', :tsq)) AS rank, kc.text "
                    "FROM knowledge_chunks kc "
                    "WHERE kc.material_version_id = :version_id "
                    "AND kc.text_tsv @@ to_tsquery('simple', :tsq) "
                    "ORDER BY rank DESC LIMIT 50"
                ),
                {"version_id": version_id, "tsq": _or_tsquery(query)},
            )
        ).all()
        bm25_hits = [
            (row[0], float(row[2]))
            for row in bm25_rows
            if _has_hash_keyword_anchor(row[3], tokens)
        ]

        vector = (await client.embed([query]))[0]
        literal = "[" + ",".join(f"{value:.6f}" for value in vector) + "]"
        vector_rows = (
            await db.execute(
                text(
                    "SELECT kc.id, kc.physical_page, "
                    "1 - (kc.embedding <=> CAST(:vector AS vector)) AS cosine "
                    "FROM knowledge_chunks kc "
                    "WHERE kc.material_version_id = :version_id "
                    "AND kc.embedding_version = :embedding_version "
                    "AND kc.embedding IS NOT NULL "
                    "AND 1 - (kc.embedding <=> CAST(:vector AS vector)) >= :minimum "
                    "ORDER BY kc.embedding <=> CAST(:vector AS vector) LIMIT 50"
                ),
                {
                    "version_id": version_id,
                    "embedding_version": client.version,
                    "vector": literal,
                    "minimum": get_settings().retrieval_min_vector_similarity,
                },
            )
        ).all()
        pages = {row[0]: row[1] for row in bm25_rows}
        pages.update({row[0]: row[1] for row in vector_rows})
        trace = build_ranking_trace(
            bm25_hits=bm25_hits,
            vector_hits=[(row[0], float(row[2])) for row in vector_rows],
            pages=pages,
            channel_priors=plan.channel_priors,
            top_k=min(top_k, plan.retrieval_budget),
        )
        await db.rollback()
    return {
        "case_id": case["id"],
        "query": query,
        "query_plan": plan.as_dict(),
        "trace": trace,
    }


async def _run(*, dataset: dict, version_id: str, top_k: int) -> dict:
    traces = []
    for case in dataset["cases"]:
        if not case["expected_refusal"]:
            traces.append(
                await _trace_case(version_id=version_id, case=case, top_k=top_k)
            )
    return {
        "dataset_id": dataset["dataset_id"],
        "material_version_id": version_id,
        "embedding_version": "hash-v1",
        "traces": traces,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="导出本地教材检索排序追踪")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--material-version-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    if args.top_k < 1:
        raise SystemExit("--top-k 必须大于 0")
    try:
        trace = asyncio.run(
            _run(
                dataset=_read_json(args.dataset),
                version_id=args.material_version_id,
                top_k=args.top_k,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"本地排序追踪失败: {exc}") from exc
    args.output.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
