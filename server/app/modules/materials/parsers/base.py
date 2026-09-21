"""解析器适配层：业务层只依赖本模块的数据合同，不依赖任何具体解析器。"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ParsedObject:
    type: str  # chapter | paragraph | figure | table | formula
    raw_content: str
    physical_page: int
    printed_page: int | None = None
    reading_order: int = 0
    title: str | None = None
    chapter_path: str = ""
    bbox: list[float] | None = None
    confidence: float = 0.9


@dataclass
class ParserResult:
    page_count: int
    objects: list[ParsedObject] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


class DocumentParser(Protocol):
    name: str
    version: str

    def parse(self, data: bytes, content_type: str) -> ParserResult: ...


def get_parser(content_type: str | None) -> DocumentParser:
    from app.modules.materials.parsers.stub_pdf import StubPdfParser

    if content_type == "application/pdf":
        return StubPdfParser()
    if content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        from app.modules.materials.parsers.docx import DocxParser

        return DocxParser()
    from app.modules.materials.parsers.stub_pdf import UnsupportedTypeParser

    return UnsupportedTypeParser()
