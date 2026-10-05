"""OOXML Canonical Object 到固定 PDF 的保守文本定位合同。"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import pymupdf


@dataclass(frozen=True)
class PageAnchor:
    physical_page: int
    bbox: tuple[float, float, float, float]
    coordinate_space: Literal["pdf_user_bottom_left"] = "pdf_user_bottom_left"
    precision: str = "pdf_text_span_union"

    def manifest(self) -> dict[str, int | list[float] | str]:
        return {
            "physical_page": self.physical_page,
            "bbox": list(self.bbox),
            "coordinate_space": self.coordinate_space,
            "precision": self.precision,
        }


@dataclass(frozen=True)
class ObjectMapping:
    object_index: int
    object_fingerprint: str
    object_type: str
    reading_order: int
    status: Literal["anchored", "unsupported"]
    anchors: tuple[PageAnchor, ...] = ()
    reason: str | None = None

    def manifest(self) -> dict[str, int | str | list[dict] | None]:
        return {
            "object_index": self.object_index,
            "object_fingerprint": self.object_fingerprint,
            "object_type": self.object_type,
            "reading_order": self.reading_order,
            "status": self.status,
            "anchors": [anchor.manifest() for anchor in self.anchors],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CitationAnchorGate:
    enabled: bool
    allowed: bool
    missing_object_fingerprints: tuple[str, ...] = ()

    def manifest(self) -> dict[str, bool | list[str]]:
        return {
            "enabled": self.enabled,
            "allowed": self.allowed,
            "missing_object_fingerprints": list(self.missing_object_fingerprints),
        }


@dataclass(frozen=True)
class _PageText:
    page_number: int
    width: float
    height: float
    normalized_text: str
    character_rects: tuple[tuple[float, float, float, float], ...]
    transformation_matrix: pymupdf.Matrix
    mediabox: pymupdf.Rect


def _normalized_characters(value: str) -> str:
    characters: list[str] = []
    for char in unicodedata.normalize("NFKC", value):
        for folded in char.casefold():
            if unicodedata.category(folded)[0] in {"L", "N"}:
                characters.append(folded)
    return "".join(characters)


def _object_fingerprint(index: int, item) -> str:
    payload = "\0".join(
        (
            str(index),
            item.type,
            str(item.reading_order),
            item.raw_content,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_page_text(page: pymupdf.Page, physical_page: int) -> _PageText:
    extracted = page.get_text("dict", sort=True)
    characters: list[str] = []
    rectangles: list[tuple[float, float, float, float]] = []
    for block in extracted.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                rect = tuple(float(value) for value in span.get("bbox", ()))
                if len(rect) != 4:
                    continue
                for char in unicodedata.normalize("NFKC", text):
                    for folded in char.casefold():
                        if unicodedata.category(folded)[0] in {"L", "N"}:
                            characters.append(folded)
                            rectangles.append(rect)
    return _PageText(
        page_number=physical_page,
        width=float(page.mediabox.width),
        height=float(page.mediabox.height),
        normalized_text="".join(characters),
        character_rects=tuple(rectangles),
        transformation_matrix=page.transformation_matrix,
        mediabox=page.mediabox,
    )


def _all_occurrences(haystack: str, needle: str) -> list[int]:
    starts: list[int] = []
    cursor = 0
    while True:
        found = haystack.find(needle, cursor)
        if found < 0:
            return starts
        starts.append(found)
        cursor = found + 1


def _unsupported(
    index: int,
    item,
    reason: str,
) -> ObjectMapping:
    return ObjectMapping(
        object_index=index,
        object_fingerprint=_object_fingerprint(index, item),
        object_type=item.type,
        reading_order=item.reading_order,
        status="unsupported",
        reason=reason,
    )


def _pdf_bbox(page_text: _PageText, rects: Sequence[tuple[float, float, float, float]]):
    mupdf_rect = pymupdf.Rect(rects[0])
    for rect in rects[1:]:
        mupdf_rect |= pymupdf.Rect(rect)
    pdf_rect = mupdf_rect * ~page_text.transformation_matrix
    pdf_rect.normalize()
    if pdf_rect.is_empty or not all(
        math.isfinite(value)
        for value in (pdf_rect.x0, pdf_rect.y0, pdf_rect.x1, pdf_rect.y1)
    ):
        return None
    media = page_text.mediabox
    if (
        pdf_rect.x0 < media.x0 - 1
        or pdf_rect.y0 < media.y0 - 1
        or pdf_rect.x1 > media.x1 + 1
        or pdf_rect.y1 > media.y1 + 1
    ):
        return None
    return tuple(round(value, 4) for value in pdf_rect)


def map_ooxml_objects_to_pdf(
    objects: Sequence,
    canonical_pdf: bytes,
) -> list[ObjectMapping]:
    """忽略解析器推测的页码，只接受 PDF 文本中的唯一、完整字符序列。

    返回的 bbox 来自固定 PDF 中实际提取文本 span 的并集，不由 DOCX
    阅读顺序或渲染页数推算。图片等非文本对象和重复文本明确返回 unsupported。
    """
    try:
        document = pymupdf.open(stream=canonical_pdf, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("固定 PDF 无法读取") from exc
    try:
        if document.is_encrypted or document.page_count < 1:
            raise ValueError("固定 PDF 不可定位")
        pages = [
            _extract_page_text(document.load_page(page_index), page_index + 1)
            for page_index in range(document.page_count)
        ]
        document_text_parts: list[str] = []
        character_locations: list[tuple[_PageText, tuple[float, float, float, float]]] = []
        for page in pages:
            document_text_parts.append(page.normalized_text)
            character_locations.extend((page, rect) for rect in page.character_rects)
        document_text = "".join(document_text_parts)

        mappings: list[ObjectMapping] = []
        for index, item in enumerate(objects):
            object_type = item.type
            if object_type == "figure":
                mappings.append(
                    _unsupported(index, item, "non_text_figure_requires_verified_layout")
                )
                continue
            if object_type == "formula" and not _normalized_characters(item.raw_content):
                mappings.append(_unsupported(index, item, "formula_text_unavailable"))
                continue
            needle = _normalized_characters(item.raw_content)
            if len(needle) < 2:
                mappings.append(_unsupported(index, item, "text_anchor_too_short"))
                continue

            starts = _all_occurrences(document_text, needle)
            if not starts:
                mappings.append(_unsupported(index, item, "text_not_found_in_fixed_pdf"))
                continue
            if len(starts) != 1:
                mappings.append(_unsupported(index, item, "ambiguous_text_match"))
                continue

            start = starts[0]
            end = start + len(needle)
            selected_locations = character_locations[start:end]
            grouped: dict[int, tuple[_PageText, list[tuple[float, float, float, float]]]] = {}
            for page_text, rect in selected_locations:
                grouped.setdefault(page_text.page_number, (page_text, []))[1].append(rect)
            if any(len(rectangles) < 2 for _, rectangles in grouped.values()):
                mappings.append(_unsupported(index, item, "cross_page_fragment_too_short"))
                continue

            anchors: list[PageAnchor] = []
            invalid_bbox = False
            for page_number in sorted(grouped):
                page_text, rectangles = grouped[page_number]
                bbox = _pdf_bbox(page_text, rectangles)
                if bbox is None:
                    invalid_bbox = True
                    break
                anchors.append(PageAnchor(physical_page=page_number, bbox=bbox))
            if invalid_bbox or not anchors:
                mappings.append(_unsupported(index, item, "pdf_text_coordinates_unverifiable"))
                continue
            mappings.append(
                ObjectMapping(
                    object_index=index,
                    object_fingerprint=_object_fingerprint(index, item),
                    object_type=object_type,
                    reading_order=item.reading_order,
                    status="anchored",
                    anchors=tuple(anchors),
                )
            )
        return mappings
    finally:
        document.close()


def verify_precise_reference_anchors(
    mappings: Sequence[ObjectMapping],
    required_object_fingerprints: Sequence[str],
    *,
    enabled: bool,
) -> CitationAnchorGate:
    """精确引用能力开启时，要求每个目标对象都有可验证页锚点。"""
    if not enabled:
        return CitationAnchorGate(enabled=False, allowed=True)
    verified = {
        mapping.object_fingerprint
        for mapping in mappings
        if mapping.status == "anchored" and mapping.anchors
    }
    missing = tuple(sorted(set(required_object_fingerprints) - verified))
    return CitationAnchorGate(
        enabled=True,
        allowed=not missing,
        missing_object_fingerprints=missing,
    )
