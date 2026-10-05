"""PDF 标准化与页面渲染的供应商无关合同。"""

from __future__ import annotations

import hashlib
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
class RenderedArtifact:
    """渲染链产生的中间/最终文件；内容摘要可进入构建 manifest。"""

    name: str
    content: bytes
    mime_type: str

    def manifest(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "mime_type": self.mime_type,
            "byte_length": len(self.content),
            "sha256": hashlib.sha256(self.content).hexdigest(),
        }


@dataclass(frozen=True)
class RenderedDocument:
    canonical_pdf: bytes
    pages: list[RenderedPage] = field(default_factory=list)
    renderer_name: str = "unknown"
    renderer_version: str = "unknown"
    intermediate_artifacts: tuple[RenderedArtifact, ...] = ()
    renderer_metadata: dict[str, str | int | list[str]] = field(default_factory=dict)

    def manifest(self) -> dict:
        return {
            "renderer": self.renderer_name,
            "renderer_version": self.renderer_version,
            "canonical_pdf_sha256": hashlib.sha256(self.canonical_pdf).hexdigest(),
            "canonical_pdf_bytes": len(self.canonical_pdf),
            "intermediate_artifacts": [
                artifact.manifest() for artifact in self.intermediate_artifacts
            ],
            "renderer_metadata": self.renderer_metadata,
            "page_count": len(self.pages),
            "pages": [
                {
                    "physical_page": page.physical_page,
                    "image_sha256": hashlib.sha256(page.content).hexdigest(),
                    "image_bytes": len(page.content),
                    "mime_type": page.mime_type,
                    **page.transform.manifest(),
                }
                for page in self.pages
            ],
        }


class DocumentRenderer(Protocol):
    """将 PDF 或 DOCX 规范化为标准 PDF，并渲染稳定页面快照。"""

    name: str
    version: str

    def render(
        self,
        data: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> RenderedDocument: ...
