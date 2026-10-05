"""原生数字 PDF 的本地布局解析器。

该解析器只使用 PDF 内的原生文字和图片对象，不调用外部服务，也不把猜测结果
伪装成表格、公式或视觉理解结果。类名因既有调用方兼容而保留。
"""

import io
import re

import pymupdf
import pypdf

from app.modules.materials.parsers.base import ParsedObject, ParserResult

CHAPTER_RE = re.compile(
    r"^(第\s*[一二三四五六七八九十百千0-9]+\s*[章节篇]"
    r"|附录\s*[A-Za-z0-9一二三四五六七八九十]?"
    r"|Chapter\s+[0-9]+|Appendix\s+[A-Z0-9])"
)
ENGLISH_CHAPTER_RE = re.compile(r"^Chapter\s+([0-9]+)\b", re.IGNORECASE)
CHAPTER_OUTLINE_RE = re.compile(r"^CHAPTER\s+OUTLINE$", re.IGNORECASE)
FIRST_SECTION_RE = re.compile(r"^([0-9]+)\.1\s+\S")
FORMULA_SIGNAL_RE = re.compile(r"[=≈≠≤≥±×÷∑∫√^_]")
FORMULA_FORBIDDEN_RE = re.compile(r"[。！？；，,:]")

MAX_PARAGRAPH_CHARS = 600


class StubPdfParser:
    name = "stub-pdf"
    version = "native-layout-v3.3"

    def parse(self, data: bytes, content_type: str) -> ParserResult:
        reader = pypdf.PdfReader(io.BytesIO(data))
        layout_document = pymupdf.open(stream=data, filetype="pdf")
        page_count = len(reader.pages)
        objects: list[ParsedObject] = []
        issues: list[str] = []
        order = 0
        chapter_no = 0
        current_path = ""
        total_text = 0

        for page_index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001  单页异常不中断整体解析
                text = ""
            total_text += len(text.strip())
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            page_paragraphs: list[str] = []
            chapter_lines: set[str] = set()
            english_chapter_lines = [line for line in lines if ENGLISH_CHAPTER_RE.match(line)]
            suppress_english_toc = len(english_chapter_lines) > 1

            # OpenStax 等原生数字教材的章首页常以 CHAPTER OUTLINE 加 N.1 开头，
            # 章名本身可能是图片文字。用首节编号恢复章边界，同时避免把前言中连续的
            # “Chapter 1…Chapter 16”目录条目当成真实章节。
            if any(CHAPTER_OUTLINE_RE.match(line) for line in lines):
                section_matches = (FIRST_SECTION_RE.match(line) for line in lines)
                first_section = next(
                    (match for match in section_matches if match is not None),
                    None,
                )
                if first_section is not None:
                    detected_chapter = int(first_section.group(1))
                    if current_path != str(detected_chapter):
                        chapter_no = detected_chapter
                        current_path = str(chapter_no)
                        order += 1
                        objects.append(
                            ParsedObject(
                                type="chapter",
                                title=f"Chapter {chapter_no}",
                                raw_content=f"Chapter {chapter_no}",
                                physical_page=page_index,
                                reading_order=order,
                                chapter_path=current_path,
                                confidence=0.8,
                            )
                        )
            for line in lines:
                english_chapter = ENGLISH_CHAPTER_RE.match(line)
                is_suppressed_toc_entry = suppress_english_toc and english_chapter
                if CHAPTER_RE.match(line) and not is_suppressed_toc_entry:
                    detected_chapter = (
                        int(english_chapter.group(1))
                        if english_chapter is not None
                        else chapter_no + 1
                    )
                    if current_path != str(detected_chapter):
                        chapter_no = detected_chapter
                        current_path = str(chapter_no)
                        order += 1
                        objects.append(
                            ParsedObject(
                                type="chapter",
                                title=line[:200],
                                raw_content=line,
                                physical_page=page_index,
                                reading_order=order,
                                chapter_path=current_path,
                                confidence=0.9,
                            )
                        )
                    chapter_lines.add(line)
                    continue
                else:
                    page_paragraphs.append(line)
            layout_entries = _page_layout_entries(layout_document[page_index - 1], chapter_lines)
            if layout_entries:
                for entry in layout_entries:
                    order += 1
                    entry.physical_page = page_index
                    entry.reading_order = order
                    entry.chapter_path = current_path
                    objects.append(entry)
            elif page_paragraphs:
                merged = " ".join(page_paragraphs)
                for block_start in range(0, len(merged), MAX_PARAGRAPH_CHARS):
                    block = merged[block_start : block_start + MAX_PARAGRAPH_CHARS]
                    order += 1
                    objects.append(
                        ParsedObject(
                            type="paragraph",
                            raw_content=block,
                            physical_page=page_index,
                            reading_order=order,
                            chapter_path=current_path,
                            confidence=0.8,
                        )
                    )

        if not objects:
            order += 1
            objects.append(
                ParsedObject(
                    type="chapter",
                    title="未识别内容",
                    raw_content="",
                    physical_page=1,
                    reading_order=order,
                    chapter_path="1",
                    confidence=0.1,
                )
            )

        if total_text < 20:
            issues.append("no_text_extracted")
        if any(object.confidence < 0.5 for object in objects):
            issues.append("low_confidence_objects")

        return ParserResult(
            page_count=page_count, objects=objects, issues=issues
        )


def _page_layout_entries(page: pymupdf.Page, chapter_lines: set[str]) -> list[ParsedObject]:
    """提取原生文本和嵌入图片，坐标统一为 [left, bottom, right, top]。"""
    # 文本与图像 block 的原始坐标在未旋转的 PDF 页面空间；page.rect 会随 /Rotate
    # 改变宽高，导致旋转页面的 bottom-left bbox 被错误平移。用 MediaBox 尺寸还原原空间。
    page_height = float(page.mediabox.height)
    table_entries = _page_table_entries(page, page_height)
    entries: list[ParsedObject] = []
    for block in page.get_text("dict").get("blocks", []):
        block_type = block.get("type")
        if block_type == 1:
            bbox = _to_pdf_bbox(block.get("bbox"), page_height)
            image = block.get("image")
            if bbox is None or not isinstance(image, bytes) or not image:
                continue
            entries.append(
                ParsedObject(
                    type="figure",
                    raw_content="",
                    physical_page=0,
                    bbox=bbox,
                    confidence=0.95,
                    asset_bytes=image,
                    asset_mime_type=_image_mime_type(block.get("ext")),
                    asset_width=_positive_int(block.get("width")),
                    asset_height=_positive_int(block.get("height")),
                )
            )
            continue
        if block_type != 0:
            continue
        kept_lines = []
        for line in block.get("lines", []):
            content = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if content and content not in chapter_lines:
                kept_lines.append((content, line["bbox"]))
        if not kept_lines:
            continue
        raw_bbox = [
            min(float(bbox[0]) for _, bbox in kept_lines),
            min(float(bbox[1]) for _, bbox in kept_lines),
            max(float(bbox[2]) for _, bbox in kept_lines),
            max(float(bbox[3]) for _, bbox in kept_lines),
        ]
        bbox = _to_pdf_bbox(raw_bbox, page_height)
        if bbox is None:
            continue
        if _text_block_is_covered_by_table(kept_lines, bbox, table_entries):
            continue
        entries.append(
            ParsedObject(
                type="paragraph",
                raw_content=" ".join(content for content, _ in kept_lines),
                physical_page=0,
                bbox=bbox,
                confidence=0.9,
            )
        )
        formula_text = " ".join(content for content, _ in kept_lines)
        if _looks_like_standalone_formula(formula_text, kept_lines):
            entries.append(
                ParsedObject(
                    type="formula",
                    raw_content=formula_text,
                    physical_page=0,
                    bbox=bbox,
                    confidence=0.8,
                )
            )
    entries.extend(table_entries)
    return sorted(entries, key=lambda item: (-item.bbox[3], item.bbox[0]))


def _text_block_is_covered_by_table(
    lines: list[tuple[str, object]], bbox: list[float], tables: list[ParsedObject]
) -> bool:
    """只去除完全落在已识别表格内、且内容可在表格单元格中核对的文本块。"""
    parts = [re.sub(r"\W+", "", text.casefold()) for text, _ in lines]
    if not parts or any(not part for part in parts):
        return False
    for table in tables:
        table_bbox = table.bbox
        if table_bbox is None or not (
            table_bbox[0] - 2 <= bbox[0]
            and table_bbox[1] - 2 <= bbox[1]
            and bbox[2] <= table_bbox[2] + 2
            and bbox[3] <= table_bbox[3] + 2
        ):
            continue
        table_text = re.sub(r"\W+", "", table.raw_content.casefold())
        if all(part in table_text for part in parts):
            return True
    return False


def _page_table_entries(page: pymupdf.Page, page_height: float) -> list[ParsedObject]:
    """仅接受 PyMuPDF 识别到的原生规则网格，不从普通段落猜测表格。"""
    if not _has_grid_like_drawings(page):
        return []
    try:
        tables = page.find_tables().tables
    except Exception:  # noqa: BLE001 - 单页版面异常不得中断整本教材
        return []
    entries: list[ParsedObject] = []
    for table in tables:
        rows = table.extract()
        if len(rows) < 2 or max((len(row) for row in rows), default=0) < 2:
            continue
        nonempty_rows = [
            [str(cell or "").strip() for cell in row]
            for row in rows
        ]
        if sum(bool(cell) for row in nonempty_rows for cell in row) < 2:
            continue
        bbox = _to_pdf_bbox(table.bbox, page_height)
        if bbox is None:
            continue
        entries.append(
            ParsedObject(
                type="table",
                raw_content="\n".join(" | ".join(row) for row in nonempty_rows),
                physical_page=0,
                bbox=bbox,
                confidence=0.85,
            )
        )
    return entries


def _has_grid_like_drawings(page: pymupdf.Page) -> bool:
    """先用廉价的绘制路径预筛，避免对每个纯文本页执行昂贵的 find_tables。"""
    horizontal = 0
    vertical = 0
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return False
    for drawing in drawings:
        for item in drawing.get("items", []):
            if not item or item[0] != "l":
                continue
            start, end = item[1], item[2]
            if abs(start.y - end.y) < 0.5 and abs(start.x - end.x) >= 12:
                horizontal += 1
            elif abs(start.x - end.x) < 0.5 and abs(start.y - end.y) >= 12:
                vertical += 1
            if horizontal >= 2 and vertical >= 2:
                return True
    return False


def _looks_like_standalone_formula(
    content: str, lines: list[tuple[str, object]]
) -> bool:
    """宁可漏检，也不把正文中的“x=…”描述伪装成公式对象。"""
    compact = content.strip()
    if len(lines) != 1 or not (3 <= len(compact) <= 160):
        return False
    if FORMULA_FORBIDDEN_RE.search(compact) or not FORMULA_SIGNAL_RE.search(compact):
        return False
    chinese_or_words = re.findall(r"[\u4e00-\u9fff]|[A-Za-z]{4,}", compact)
    return len(chinese_or_words) <= 1


def _to_pdf_bbox(raw_bbox, page_height: float) -> list[float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    left, top, right, bottom = (float(value) for value in raw_bbox)
    if left >= right or top >= bottom:
        return None
    return [left, page_height - bottom, right, page_height - top]


def _positive_int(value) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _image_mime_type(extension: object) -> str:
    normalized = str(extension or "png").lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "jpx": "image/jpx",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
    }.get(normalized, "application/octet-stream")


class UnsupportedTypeParser:
    name = "unsupported"
    version = "1.0"

    def parse(self, data: bytes, content_type: str) -> ParserResult:
        return ParserResult(
            page_count=0,
            objects=[
                ParsedObject(
                    type="chapter",
                    title="待接入解析器",
                    raw_content="",
                    physical_page=1,
                    reading_order=1,
                    chapter_path="1",
                    confidence=0.1,
                )
            ],
            issues=["parser_unavailable"],
        )
