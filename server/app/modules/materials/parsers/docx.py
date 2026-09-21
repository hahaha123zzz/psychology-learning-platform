"""DOCX 结构解析器：提取标题、段落、表格、图片和公式对象。

DOCX 本身是流式排版格式，本解析器不伪造 bbox。真实页面坐标需由版面解析
供应商或 Office/PDF 渲染链产生，因此结果会附带 layout_bbox_unavailable 告警。
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from app.modules.materials.parsers.base import ParsedObject, ParserResult
from app.modules.materials.parsers.stub_pdf import CHAPTER_RE, MAX_PARAGRAPH_CHARS

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

HEADING_RE = re.compile(r"^(heading|标题)\s*([1-9])?$", re.IGNORECASE)


class DocxParser:
    name = "docx-xml"
    version = "1.0"

    def parse(self, data: bytes, content_type: str) -> ParserResult:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as package:
                document = package.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError("DOCX 文件结构无效或缺少 word/document.xml") from exc

        root = ElementTree.fromstring(document)
        body = root.find(f"{W}body")
        if body is None:
            return ParserResult(page_count=1, issues=["no_text_extracted"])

        objects: list[ParsedObject] = []
        order = 0
        page = 1
        chapter_counter = 0
        chapter_path = ""

        for element in body:
            if element.tag == f"{W}p":
                text = _paragraph_text(element)
                style = _paragraph_style(element)
                is_heading = bool(text and (HEADING_RE.match(style) or CHAPTER_RE.match(text)))
                if is_heading:
                    chapter_counter += 1
                    chapter_path = str(chapter_counter)
                    order += 1
                    objects.append(
                        ParsedObject(
                            type="chapter",
                            title=text[:200],
                            raw_content=text,
                            physical_page=page,
                            reading_order=order,
                            chapter_path=chapter_path,
                            confidence=0.9,
                        )
                    )
                elif text:
                    for start in range(0, len(text), MAX_PARAGRAPH_CHARS):
                        order += 1
                        objects.append(
                            ParsedObject(
                                type="paragraph",
                                raw_content=text[start : start + MAX_PARAGRAPH_CHARS],
                                physical_page=page,
                                reading_order=order,
                                chapter_path=chapter_path,
                                confidence=0.85,
                            )
                        )

                if element.find(f".//{M}oMath") is not None:
                    order += 1
                    objects.append(
                        ParsedObject(
                            type="formula",
                            raw_content=text or "[Word 公式]",
                            physical_page=page,
                            reading_order=order,
                            chapter_path=chapter_path,
                            confidence=0.65,
                        )
                    )
                for drawing in element.findall(f".//{W}drawing"):
                    order += 1
                    objects.append(
                        ParsedObject(
                            type="figure",
                            title=_drawing_title(drawing),
                            raw_content=_drawing_title(drawing),
                            physical_page=page,
                            reading_order=order,
                            chapter_path=chapter_path,
                            confidence=0.65,
                        )
                    )
                page += _page_break_count(element)
            elif element.tag == f"{W}tbl":
                table_text = _table_text(element)
                if table_text:
                    order += 1
                    objects.append(
                        ParsedObject(
                            type="table",
                            raw_content=table_text,
                            physical_page=page,
                            reading_order=order,
                            chapter_path=chapter_path,
                            confidence=0.8,
                        )
                    )
                page += _page_break_count(element)

        issues = ["layout_bbox_unavailable"]
        if not any(item.raw_content.strip() for item in objects):
            issues.append("no_text_extracted")
        return ParserResult(
            page_count=max(page, 1),
            objects=objects,
            issues=issues,
        )


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(f".//{W}t")).strip()


def _paragraph_style(paragraph: ElementTree.Element) -> str:
    node = paragraph.find(f"./{W}pPr/{W}pStyle")
    return node.get(f"{W}val", "") if node is not None else ""


def _table_text(table: ElementTree.Element) -> str:
    rows: list[str] = []
    for row in table.findall(f"./{W}tr"):
        cells = []
        for cell in row.findall(f"./{W}tc"):
            text = "".join(node.text or "" for node in cell.findall(f".//{W}t")).strip()
            cells.append(text)
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _drawing_title(drawing: ElementTree.Element) -> str:
    properties = drawing.find(f".//{WP}docPr")
    if properties is not None:
        return (
            properties.get("descr")
            or properties.get("title")
            or properties.get("name")
            or "Word 图片"
        )
    non_visual = drawing.find(f".//{A}cNvPr")
    if non_visual is not None:
        return non_visual.get("descr") or non_visual.get("name") or "Word 图片"
    return "Word 图片"


def _page_break_count(element: ElementTree.Element) -> int:
    explicit = sum(
        1
        for node in element.findall(f".//{W}br")
        if node.get(f"{W}type") == "page"
    )
    rendered = len(element.findall(f".//{W}lastRenderedPageBreak"))
    return explicit + rendered
