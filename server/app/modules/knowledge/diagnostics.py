"""检索排序诊断的数据整形；只供本地评测脚本使用。"""

from __future__ import annotations

from app.modules.knowledge.adaptive import adaptive_cutoff
from app.modules.knowledge.service import _rrf_fuse


def build_ranking_trace(
    *,
    bm25_hits: list[tuple[str, float]],
    vector_hits: list[tuple[str, float]],
    pages: dict[str, int],
    channel_priors: dict[str, float],
    top_k: int,
) -> dict:
    """保留候选的真实排名，包含被截断结果之前的完整融合序列。"""
    fused = _rrf_fuse(bm25_hits, vector_hits, channel_priors=channel_priors)
    cutoff = adaptive_cutoff(fused, max_items=top_k)

    def ranked(items: list[tuple[str, float]]) -> list[dict]:
        return [
            {"rank": rank, "chunk_id": chunk_id, "physical_page": pages[chunk_id], "score": score}
            for rank, (chunk_id, score) in enumerate(items, start=1)
        ]

    return {
        "bm25": ranked(bm25_hits),
        "vector": ranked(vector_hits),
        "fused": [
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "physical_page": pages[chunk_id],
                "score": score,
                "sources": sources,
            }
            for rank, (chunk_id, score, sources) in enumerate(fused, start=1)
        ],
        "cutoff": {
            "reason": cutoff.reason,
            "chunk_ids": [chunk_id for chunk_id, _, _ in cutoff.items],
            "pages": [pages[chunk_id] for chunk_id, _, _ in cutoff.items],
        },
    }
