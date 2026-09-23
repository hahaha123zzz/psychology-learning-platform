"""确定性 Query Analyzer：不调用模型，不把改写文本当作教材证据。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

PAGE_RE = re.compile(r"(?:第\s*)?(\d{1,4})\s*(?:页|page)(?![a-z0-9])", re.IGNORECASE)
CHAPTER_RE = re.compile(r"(?:第\s*)?(\d{1,2})\s*(?:章|chapter)(?![a-z0-9])", re.IGNORECASE)
FIGURE_RE = re.compile(r"(?:图|figure)\s*\d", re.IGNORECASE)
TABLE_RE = re.compile(r"(?:表|table)\s*\d", re.IGNORECASE)
FORMULA_RE = re.compile(r"(?:公式|equation|方程)(?![a-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class QueryPlan:
    question_type: str
    target_pages: tuple[int, ...]
    target_chapters: tuple[str, ...]
    modalities: tuple[str, ...]
    channel_priors: dict[str, float]
    retrieval_budget: int
    analyzer_version: str = "deterministic-v1"

    def as_dict(self) -> dict:
        return asdict(self)


def analyze_query(query: str) -> QueryPlan:
    normalized = query.lower()
    pages = tuple(dict.fromkeys(int(value) for value in PAGE_RE.findall(normalized)))
    chapters = tuple(dict.fromkeys(CHAPTER_RE.findall(normalized)))
    if FIGURE_RE.search(normalized):
        return QueryPlan(
            "visual", pages, chapters, ("visual", "text"),
            {"visual": 0.7, "dense": 0.2, "sparse": 0.1}, 12,
        )
    if TABLE_RE.search(normalized):
        return QueryPlan(
            "table", pages, chapters, ("table", "text"),
            {"dense": 0.45, "sparse": 0.35, "visual": 0.2}, 10,
        )
    if FORMULA_RE.search(normalized):
        return QueryPlan(
            "formula", pages, chapters, ("formula", "text"),
            {"dense": 0.5, "sparse": 0.4, "visual": 0.1}, 10,
        )
    comparison_words = ("区别", "比较", "对比", "不同", "difference", "compare")
    if any(word in normalized for word in comparison_words):
        return QueryPlan(
            "comparison", pages, chapters, ("text",),
            {"dense": 0.5, "sparse": 0.5, "visual": 0.0}, 12,
        )
    if any(word in normalized for word in ("什么是", "定义", "含义", "what is", "define")):
        return QueryPlan(
            "definition", pages, chapters, ("text",),
            {"dense": 0.45, "sparse": 0.55, "visual": 0.0}, 8,
        )
    return QueryPlan(
        "general", pages, chapters, ("text",),
        {"dense": 0.5, "sparse": 0.5, "visual": 0.0}, 8,
    )
