"""版本范围的固定 PDF 页图缓存；所有内容访问由调用方先完成鉴权。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import re

from minio.error import S3Error

from app.core.storage import get_object_bytes, put_object
from app.modules.materials.artifacts import (
    PageTransform,
    page_image_metadata_object_key,
    page_image_object_key,
)
from app.modules.materials.renderers.base import RenderedPage
from app.modules.materials.renderers.pymupdf_pdf import RENDERER_VERSION, render_pdf_page

_MISSING_OBJECT_CODES = {"NoSuchKey", "NoSuchObject"}


class MaterialVersionIntegrityError(RuntimeError):
    """存储中的 PDF 与不可变版本摘要不一致。"""


async def get_or_create_pdf_page(
    *,
    course_id: str,
    material_id: str,
    version_id: str,
    source_object_key: str,
    expected_source_sha256: str | None,
    physical_page: int,
) -> RenderedPage:
    """从该版本的 PDF 创建或读取固定 PNG；不会调用外部模型或外部解析服务。"""
    if not expected_source_sha256 or not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256):
        raise MaterialVersionIntegrityError("教材版本缺少可验证的 SHA-256")

    image_key = page_image_object_key(
        course_id=course_id,
        material_id=material_id,
        version_id=version_id,
        physical_page=physical_page,
        render_version=RENDERER_VERSION,
    )
    metadata_key = page_image_metadata_object_key(
        course_id=course_id,
        material_id=material_id,
        version_id=version_id,
        physical_page=physical_page,
        render_version=RENDERER_VERSION,
    )

    cached_image = await _read_optional_object(image_key)
    cached_metadata = await _read_optional_object(metadata_key)
    if cached_image is not None and cached_metadata is not None:
        cached = _decode_cached_asset(
            image=cached_image,
            metadata=cached_metadata,
            expected_source_sha256=expected_source_sha256,
            physical_page=physical_page,
        )
        if cached is not None:
            return cached

    source = await get_object_bytes(source_object_key)
    source_sha256 = hashlib.sha256(source).hexdigest()
    if source_sha256 != expected_source_sha256:
        raise MaterialVersionIntegrityError("教材源文件摘要与不可变版本记录不一致")

    rendered = await asyncio.to_thread(render_pdf_page, source, physical_page)
    image_sha256 = hashlib.sha256(rendered.content).hexdigest()
    metadata = {
        "renderer_version": RENDERER_VERSION,
        "physical_page": physical_page,
        "source_sha256": source_sha256,
        "image_sha256": image_sha256,
        "transform": rendered.transform.manifest(),
    }
    await put_object(
        key=image_key,
        data=io.BytesIO(rendered.content),
        length=len(rendered.content),
        content_type="image/png",
    )
    serialized_metadata = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    await put_object(
        key=metadata_key,
        data=io.BytesIO(serialized_metadata),
        length=len(serialized_metadata),
        content_type="application/json",
    )
    return rendered


async def _read_optional_object(key: str) -> bytes | None:
    try:
        return await get_object_bytes(key)
    except S3Error as exc:
        if exc.code in _MISSING_OBJECT_CODES:
            return None
        raise


def _decode_cached_asset(
    *,
    image: bytes,
    metadata: bytes,
    expected_source_sha256: str | None,
    physical_page: int,
) -> RenderedPage | None:
    try:
        decoded = json.loads(metadata)
        if not isinstance(decoded, dict):
            return None
        if (
            decoded.get("renderer_version") != RENDERER_VERSION
            or decoded.get("physical_page") != physical_page
            or decoded.get("source_sha256") != expected_source_sha256
            or decoded.get("image_sha256") != hashlib.sha256(image).hexdigest()
            or not image.startswith(b"\x89PNG\r\n\x1a\n")
            or len(image) < 24
        ):
            return None
        transform = PageTransform(**decoded["transform"])
        if (
            not math.isfinite(transform.pdf_width)
            or not math.isfinite(transform.pdf_height)
            or type(transform.pixel_width) is not int
            or type(transform.pixel_height) is not int
            or transform.pixel_width != int.from_bytes(image[16:20], "big")
            or transform.pixel_height != int.from_bytes(image[20:24], "big")
        ):
            return None
        return RenderedPage(
            physical_page=physical_page,
            content=image,
            mime_type="image/png",
            transform=transform,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
