"""Stub 解析器：基于pypdf的文本抽取，演示解析器合同。

真实部署将替换为MinerU适配器（版面、表格、公式、OCR），业务模型不受影响。
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

MAX_PARAGRAPH_CHARS = 600


class StubPdfParser:
    name = "stub-pdf"
    version = "1.0"

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
            layout_blocks = _page_text_blocks(layout_document[page_index - 1], chapter_lines)
            if layout_blocks:
                for block, bbox in layout_blocks:
                    order += 1
                    objects.append(
                        ParsedObject(
                            type="paragraph",
                            raw_content=block,
                            physical_page=page_index,
                            reading_order=order,
                            chapter_path=current_path,
                            bbox=bbox,
                            confidence=0.9,
                        )
                    )
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


def _page_text_blocks(page: pymupdf.Page, chapter_lines: set[str]) -> list[tuple[str, list[float]]]:
    """提取原生 PDF 文本块并转换为项目统一的 [left, bottom, right, top] 坐标。"""
    page_height = float(page.rect.height)
    blocks: list[tuple[str, list[float]]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        kept_lines = []
        for line in block.get("lines", []):
            content = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if content and content not in chapter_lines:
                kept_lines.append((content, line["bbox"]))
        if not kept_lines:
            continue
        left = min(float(bbox[0]) for _, bbox in kept_lines)
        top = min(float(bbox[1]) for _, bbox in kept_lines)
        right = max(float(bbox[2]) for _, bbox in kept_lines)
        bottom = max(float(bbox[3]) for _, bbox in kept_lines)
        if left >= right or top >= bottom:
            continue
        blocks.append(
            (
                " ".join(content for content, _ in kept_lines),
                [left, page_height - bottom, right, page_height - top],
            )
        )
    return blocks


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
