import io
import zipfile
from xml.etree import ElementTree

import pytest

from app.modules.materials.parsers.base import get_parser
from app.modules.materials.parsers.docx import DocxParser

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes(document_xml: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("word/document.xml", document_xml)
    return output.getvalue()


def test_get_parser_routes_docx_to_structural_parser() -> None:
    assert isinstance(get_parser(CONTENT_TYPE), DocxParser)


def test_docx_parser_extracts_structures_without_guessing_physical_pages() -> None:
    data = _docx_bytes(
        """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <w:body>
            <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章 绪论</w:t></w:r></w:p>
            <w:p><w:r><w:t>实验心理学研究行为与心理过程。</w:t></w:r>
              <w:r><w:br w:type="page"/><w:lastRenderedPageBreak/></w:r></w:p>
            <w:p><m:oMath><m:r><m:t>F = m a</m:t></m:r></m:oMath></w:p>
            <w:tbl><w:tr>
              <w:tc><w:p><w:r><w:t>变量</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:t>定义</w:t></w:r></w:p></w:tc>
            </w:tr></w:tbl>
          </w:body>
        </w:document>"""
    )

    result = DocxParser().parse(data, CONTENT_TYPE)

    assert result.page_count is None
    assert [item.type for item in result.objects] == [
        "chapter",
        "paragraph",
        "formula",
        "table",
    ]
    assert all(item.physical_page is None for item in result.objects)
    assert result.objects[0].title == "第一章 绪论"
    assert result.objects[1].chapter_path == "1"
    assert result.objects[2].raw_content == "F = m a"
    assert result.objects[3].raw_content == "变量 | 定义"
    assert "layout_bbox_unavailable" in result.issues
    assert "physical_page_unavailable" in result.issues


def test_docx_parser_rejects_zip_without_document_xml() -> None:
    data = _docx_bytes("<invalid")
    broken = io.BytesIO()
    with zipfile.ZipFile(broken, "w") as package:
        package.writestr("not-word.txt", "x")

    with pytest.raises(ValueError, match="DOCX 文件结构无效"):
        DocxParser().parse(broken.getvalue(), CONTENT_TYPE)

    with pytest.raises(ElementTree.ParseError):
        DocxParser().parse(data, CONTENT_TYPE)
