import pytest

from app.modules.knowledge.evaluation import (
    bbox_iou,
    citation_precision_recall,
    claim_support_rate,
    ndcg_at_k,
    page_accuracy,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
)


def test_rank_metrics_deduplicate_results_and_respect_k() -> None:
    retrieved = ["noise", "target-a", "target-a", "target-b"]
    relevant = {"target-a", "target-b"}

    assert recall_at_k(retrieved, relevant, 2) == 0.5
    assert reciprocal_rank(retrieved, relevant) == 0.5
    assert ndcg_at_k(retrieved, relevant, 3) == pytest.approx(
        (1 / 1.584962500721156 + 1 / 2) / (1 + 1 / 1.584962500721156)
    )


def test_rank_metrics_handle_unanswerable_case_without_fake_relevance() -> None:
    assert recall_at_k(["noise"], set(), 5) == 1.0
    assert ndcg_at_k(["noise"], set(), 5) == 1.0
    assert reciprocal_rank(["noise"], set()) == 0.0


def test_negative_k_is_rejected() -> None:
    with pytest.raises(ValueError, match="k 不能为负数"):
        recall_at_k(["a"], {"a"}, -1)


def test_page_accuracy_supports_multiple_allowed_pages_and_no_answer() -> None:
    assert page_accuracy(8, {8, 9}) == 1.0
    assert page_accuracy(7, {8, 9}) == 0.0
    assert page_accuracy(None, set()) == 1.0
    assert page_accuracy(1, set()) == 0.0


def test_bbox_iou_handles_overlap_and_invalid_boxes() -> None:
    assert bbox_iou([0.0, 0.0, 0.5, 0.5], [0.25, 0.25, 0.75, 0.75]) == pytest.approx(
        1 / 7
    )
    assert bbox_iou([0.0, 0.0, 1.0, 1.0], [0.0, 0.0, 1.0, 1.0]) == 1.0
    assert bbox_iou([0.5, 0.0, 0.5, 1.0], [0.0, 0.0, 1.0, 1.0]) == 0.0
    assert bbox_iou(None, [0.0, 0.0, 1.0, 1.0]) == 0.0


def test_citation_metrics_cover_empty_and_partial_sets() -> None:
    assert citation_precision_recall(["a", "wrong"], ["a", "b"]) == (0.5, 0.5)
    assert citation_precision_recall([], []) == (1.0, 1.0)
    assert citation_precision_recall(["wrong"], []) == (0.0, 0.0)


def test_claim_support_and_refusal_accuracy() -> None:
    assert claim_support_rate(["supported", "partial", "conflict", "not_found"]) == 0.25
    assert claim_support_rate([]) == 1.0
    assert refusal_accuracy([True, False, True], [True, True, True]) == pytest.approx(2 / 3)


def test_refusal_accuracy_rejects_mismatched_inputs() -> None:
    with pytest.raises(ValueError, match="数量必须一致"):
        refusal_accuracy([True], [True, False])
