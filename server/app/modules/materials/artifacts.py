"""教材版本不可变资产的命名、完整性与坐标合同。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def sha256_bytes(data: bytes) -> str:
    """返回二进制资产的稳定内容哈希。"""
    return hashlib.sha256(data).hexdigest()


def _asset_prefix(*, course_id: str, material_id: str, version_id: str) -> str:
    return f"courses/{course_id}/materials/{material_id}/versions/{version_id}"


def source_object_key(*, course_id: str, material_id: str, version_id: str, extension: str) -> str:
    """原始上传文件的不可变对象键。"""
    prefix = _asset_prefix(course_id=course_id, material_id=material_id, version_id=version_id)
    return f"{prefix}/source/source.{extension.lower()}"


def canonical_pdf_object_key(*, course_id: str, material_id: str, version_id: str) -> str:
    """同一资料版本唯一的标准 PDF 快照键。"""
    prefix = _asset_prefix(course_id=course_id, material_id=material_id, version_id=version_id)
    return f"{prefix}/canonical/document.pdf"


def page_image_object_key(
    *,
    course_id: str,
    material_id: str,
    version_id: str,
    physical_page: int,
    image_format: str = "png",
) -> str:
    """从 1 开始编号的标准页面图像键。"""
    if physical_page < 1:
        raise ValueError("physical_page 必须从 1 开始")
    normalized_format = image_format.lower()
    if normalized_format not in {"png", "webp"}:
        raise ValueError("页面图像只支持 png 或 webp")
    return (
        f"{_asset_prefix(course_id=course_id, material_id=material_id, version_id=version_id)}"
        f"/pages/page-{physical_page:04d}.{normalized_format}"
    )


def object_crop_object_key(
    *,
    course_id: str,
    material_id: str,
    version_id: str,
    knowledge_object_id: str,
    image_format: str = "png",
) -> str:
    """由教材对象 ID 定位的稳定裁剪图像键。"""
    normalized_format = image_format.lower()
    if normalized_format not in {"png", "webp"}:
        raise ValueError("对象裁剪只支持 png 或 webp")
    return (
        f"{_asset_prefix(course_id=course_id, material_id=material_id, version_id=version_id)}"
        f"/objects/{knowledge_object_id}/crop.{normalized_format}"
    )


@dataclass(frozen=True)
class PageTransform:
    """PDF 用户空间到渲染页面像素空间的可复现变换。

    bbox 使用 PDF 坐标 ``[left, bottom, right, top]``；输出使用页面像素
    坐标 ``[left, top, right, bottom]``，适于浏览器叠加高亮。
    """

    pdf_width: float
    pdf_height: float
    pixel_width: int
    pixel_height: int
    rotation: int = 0
    dpi: int = 144

    def __post_init__(self) -> None:
        if self.pdf_width <= 0 or self.pdf_height <= 0:
            raise ValueError("PDF 页面尺寸必须为正数")
        if self.pixel_width <= 0 or self.pixel_height <= 0:
            raise ValueError("渲染像素尺寸必须为正整数")
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("rotation 必须为 0、90、180 或 270")
        if self.dpi <= 0:
            raise ValueError("dpi 必须为正数")

    def pdf_bbox_to_pixels(self, bbox: list[float]) -> list[float]:
        if len(bbox) != 4:
            raise ValueError("bbox 必须包含 [left, bottom, right, top]")
        left, bottom, right, top = bbox
        if left > right or bottom > top:
            raise ValueError("bbox 边界顺序无效")
        points = ((left, bottom), (left, top), (right, bottom), (right, top))
        transformed = [self._point_to_pixels(x, y) for x, y in points]
        xs = [point[0] for point in transformed]
        ys = [point[1] for point in transformed]
        return [min(xs), min(ys), max(xs), max(ys)]

    def manifest(self) -> dict[str, int | float]:
        return {
            "pdf_width": self.pdf_width,
            "pdf_height": self.pdf_height,
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "rotation": self.rotation,
            "dpi": self.dpi,
        }

    def _point_to_pixels(self, x: float, y: float) -> tuple[float, float]:
        # 先换成未旋转页面的左上原点，再以 PDF 视图旋转规则变换。
        normalized_x = x / self.pdf_width
        normalized_y = 1 - (y / self.pdf_height)
        if self.rotation == 0:
            rotated_x, rotated_y = normalized_x, normalized_y
        elif self.rotation == 90:
            rotated_x, rotated_y = 1 - normalized_y, normalized_x
        elif self.rotation == 180:
            rotated_x, rotated_y = 1 - normalized_x, 1 - normalized_y
        else:
            rotated_x, rotated_y = normalized_y, 1 - normalized_x
        return rotated_x * self.pixel_width, rotated_y * self.pixel_height
