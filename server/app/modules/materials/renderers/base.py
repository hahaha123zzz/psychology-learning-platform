"""PDF 标准化与页面渲染的供应商无关合同。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.materials.artifacts import PageTransform


class RendererUnavailableError(RuntimeError):
    """当前部署缺少渲染器运行依赖时抛出，调用方应创建 blocking Issue。"""


@dataclass(frozen=True)
class RenderedPage:
    physical_page: int
    content: bytes
    mime_type: str
    transform: PageTransform


@dataclass(frozen=True)
class RenderedDocument:
    canonical_pdf: bytes
    pages: list[RenderedPage] = field(default_factory=list)
    renderer_name: str = "unknown"
    renderer_version: str = "unknown"

    def manifest(self) -> dict:
        return {
            "renderer": self.renderer_name,
            "renderer_version": self.renderer_version,
            "page_count": len(self.pages),
            "pages": [
                {"physical_page": page.physical_page, **page.transform.manifest()}
                for page in self.pages
            ],
        }


class DocumentRenderer(Protocol):
    """将 PDF 或 DOCX 规范化为标准 PDF，并渲染稳定页面快照。"""

    name: str
    version: str

    def render(self, data: bytes, content_type: str) -> RenderedDocument: ...
