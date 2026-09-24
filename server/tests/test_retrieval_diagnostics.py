from app.modules.knowledge.diagnostics import build_ranking_trace


def test_ranking_trace_keeps_candidates_removed_by_adaptive_cutoff() -> None:
    trace = build_ranking_trace(
        bm25_hits=[("bm-first", 1.0), ("target-page", 0.9)],
        vector_hits=[("vec-first", 0.8), ("target-page", 0.7)],
        pages={"bm-first": 10, "vec-first": 20, "target-page": 68},
        channel_priors={"sparse": 0.5, "dense": 0.5},
        top_k=1,
    )

    assert [item["physical_page"] for item in trace["fused"]] == [68, 10, 20]
    assert trace["cutoff"] == {
        "reason": "budget_exhausted",
        "chunk_ids": ["target-page"],
        "pages": [68],
    }
