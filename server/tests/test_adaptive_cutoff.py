import pytest

from app.modules.knowledge.adaptive import adaptive_cutoff


def test_adaptive_cutoff_stops_after_meaningful_score_gap() -> None:
    decision = adaptive_cutoff(
        [("first", 0.040, ["bm25"]), ("second", 0.039, ["vector"]), ("weak", 0.030, ["bm25"])],
        max_items=8,
    )

    assert [item[0] for item in decision.items] == ["first", "second"]
    assert decision.reason == "score_gap"


def test_adaptive_cutoff_honors_hard_budget_without_score_gap() -> None:
    decision = adaptive_cutoff(
        [("first", 0.040, ["bm25"]), ("second", 0.039, ["vector"]), ("third", 0.038, ["bm25"])],
        max_items=2,
    )

    assert [item[0] for item in decision.items] == ["first", "second"]
    assert decision.reason == "budget_exhausted"


def test_adaptive_cutoff_requires_positive_budget() -> None:
    with pytest.raises(ValueError, match="max_items"):
        adaptive_cutoff([], max_items=0)
