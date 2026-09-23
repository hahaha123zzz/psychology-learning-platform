"""可解释的检索结果截断；不依赖模型，也不改变候选排序。"""

from __future__ import annotations

from dataclasses import dataclass

RELATIVE_SCORE_GAP = 0.15
MIN_ITEMS_BEFORE_GAP_STOP = 2


@dataclass(frozen=True)
class CutoffDecision:
    items: tuple[tuple[str, float, list[str]], ...]
    reason: str


def adaptive_cutoff(
    candidates: list[tuple[str, float, list[str]]],
    *,
    max_items: int,
    relative_score_gap: float = RELATIVE_SCORE_GAP,
) -> CutoffDecision:
    """在明显 RRF 分数断层处停止，并始终遵守调用方给出的硬上限。

    RRF 分数只用于决定是否继续扩大候选集；它不被作为教材事实或生成依据。
    至少保留两个候选，避免单一首项偶然偏高造成过早截断。
    """
    if max_items < 1:
        raise ValueError("max_items 必须大于 0")
    if not candidates:
        return CutoffDecision(items=(), reason="candidate_exhausted")

    selected: list[tuple[str, float, list[str]]] = []
    for candidate in candidates:
        if len(selected) >= max_items:
            return CutoffDecision(items=tuple(selected), reason="budget_exhausted")
        if len(selected) >= MIN_ITEMS_BEFORE_GAP_STOP:
            previous_score = selected[-1][1]
            current_score = candidate[1]
            relative_drop = (
                (previous_score - current_score) / previous_score
                if previous_score > 0
                else 0.0
            )
            if relative_drop >= relative_score_gap:
                return CutoffDecision(items=tuple(selected), reason="score_gap")
        selected.append(candidate)

    return CutoffDecision(items=tuple(selected), reason="candidate_exhausted")
