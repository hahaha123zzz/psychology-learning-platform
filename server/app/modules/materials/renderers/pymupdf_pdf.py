"""本地 PyMuPDF 单页渲染器；输出固定 DPI 的 PNG 与坐标变换。"""

from __future__ import annotations

import pymupdf

from app.modules.materials.artifacts import PageTransform
from app.modules.materials.renderers.base import RenderedPage, RendererUnavailableError

READER_DPI = 144
RENDERER_VERSION = f"pymupdf-{pymupdf.VersionBind}-dpi{READER_DPI}-v1"


def render_pdf_page(data: bytes, physical_page: int) -> RenderedPage:
    """仅在本机渲染指定 PDF 页；物理页从 1 开始，坐标保留原 PDF 用户空间。"""
    if physical_page < 1:
        raise ValueError("physical_page 必须从 1 开始")

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - 底层解析错误不应泄漏给 Reader API
        raise RendererUnavailableError("PDF 页面无法由本地渲染器读取") from exc

    try:
        if document.is_encrypted or physical_page > document.page_count:
            raise RendererUnavailableError("PDF 页面不可用")
        page = document.load_page(physical_page - 1)
        pixmap = page.get_pixmap(dpi=READER_DPI, alpha=False)
        content = pixmap.tobytes("png")
        transform = PageTransform(
            pdf_width=float(page.mediabox.width),
            pdf_height=float(page.mediabox.height),
            pixel_width=pixmap.width,
            pixel_height=pixmap.height,
            rotation=page.rotation,
            dpi=READER_DPI,
        )
        return RenderedPage(
            physical_page=physical_page,
            content=content,
            mime_type="image/png",
            transform=transform,
        )
    except RendererUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - 坏页/资源限制按不可用降级，不伪造定位
        raise RendererUnavailableError("PDF 页面无法由本地渲染器读取") from exc
    finally:
        document.close()
