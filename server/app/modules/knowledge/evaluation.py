"""RAG V3 离线评测指标。

本模块只处理结构化输入，不访问数据库、对象存储或外部模型，确保同一实验输入
可以稳定复现。检索列表中的重复 ID 只按首次出现计入排名，避免重复候选放大指标。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

SUPPORTED_LEVELS = {"supported"}


def _unique_top_k(items: Sequence[str], k: int) -> list[str]:
    if k < 0:
        raise ValueError("k 不能为负数")
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= k:
            break
    return result


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """返回前 K 个唯一结果覆盖的相关对象比例。

    无相关对象的问题属于拒答评测范围，因此 Recall 定义为 1.0，避免把“教材确实
    没有答案”误记为检索失败。
    """

    relevant_set = set(relevant)
    if not relevant_set:
        return 1.0
    hits = relevant_set.intersection(_unique_top_k(retrieved, k))
    return len(hits) / len(relevant_set)


def reciprocal_rank(
    retrieved: Sequence[str], relevant: Iterable[str], k: int | None = None
) -> float:
    """返回首个相关唯一结果的倒数排名。"""

    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    limit = len(retrieved) if k is None else k
    for rank, item in enumerate(_unique_top_k(retrieved, limit), start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """使用二元相关性计算 nDCG@K。"""

    relevant_set = set(relevant)
    if not relevant_set:
        return 1.0
    ranked = _unique_top_k(retrieved, k)
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, item in enumerate(ranked, start=1)
        if item in relevant_set
    )
    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def page_accuracy(predicted_page: int | None, expected_pages: Iterable[int]) -> float:
    """预测页命中任一允许页面时返回 1，否则返回 0。"""

    expected = set(expected_pages)
    if not expected:
        return 1.0 if predicted_page is None else 0.0
    return 1.0 if predicted_page in expected else 0.0


def bbox_iou(predicted: Sequence[float] | None, expected: Sequence[float] | None) -> float:
    """计算两个 ``[x1, y1, x2, y2]`` 框的 IoU；非法或缺失坐标返回 0。"""

    if not _valid_bbox(predicted) or not _valid_bbox(expected):
        return 0.0
    assert predicted is not None and expected is not None
    left = max(predicted[0], expected[0])
    top = max(predicted[1], expected[1])
    right = min(predicted[2], expected[2])
    bottom = min(predicted[3], expected[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    predicted_area = (predicted[2] - predicted[0]) * (predicted[3] - predicted[1])
    expected_area = (expected[2] - expected[0]) * (expected[3] - expected[1])
    union = predicted_area + expected_area - intersection
    return intersection / union if union > 0 else 0.0


def citation_precision_recall(
    cited: Iterable[str], allowed: Iterable[str]
) -> tuple[float, float]:
    """返回引用的 precision 和 recall；重复引用只计算一次。"""

    cited_set = set(cited)
    allowed_set = set(allowed)
    hits = cited_set.intersection(allowed_set)
    precision = len(hits) / len(cited_set) if cited_set else (1.0 if not allowed_set else 0.0)
    recall = len(hits) / len(allowed_set) if allowed_set else (1.0 if not cited_set else 0.0)
    return precision, recall


def claim_support_rate(support_levels: Iterable[str]) -> float:
    """返回被完整教材证据支持的 Claim 比例。"""

    levels = list(support_levels)
    if not levels:
        return 1.0
    return sum(level in SUPPORTED_LEVELS for level in levels) / len(levels)


def refusal_accuracy(
    predicted_refusals: Iterable[bool], expected_refusals: Iterable[bool]
) -> float:
    """计算拒答决策准确率；输入长度不一致时拒绝产生误导指标。"""

    predicted = list(predicted_refusals)
    expected = list(expected_refusals)
    if len(predicted) != len(expected):
        raise ValueError("预测与标注数量必须一致")
    if not expected:
        return 1.0
    return sum(left == right for left, right in zip(predicted, expected, strict=True)) / len(
        expected
    )


def _valid_bbox(value: Sequence[float] | None) -> bool:
    if value is None or len(value) != 4:
        return False
    x1, y1, x2, y2 = value
    return all(math.isfinite(point) for point in value) and x1 < x2 and y1 < y2
