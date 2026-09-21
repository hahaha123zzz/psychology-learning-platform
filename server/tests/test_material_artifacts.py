import pytest

from app.modules.materials.artifacts import (
    PageTransform,
    canonical_pdf_object_key,
    object_crop_object_key,
    page_image_object_key,
    sha256_bytes,
    source_object_key,
)
from app.modules.materials.renderers.base import RenderedDocument, RenderedPage

ASSET_ARGS = {
    "course_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
    "material_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
    "version_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
}


def test_asset_keys_are_version_scoped_and_stable() -> None:
    assert source_object_key(**ASSET_ARGS, extension="DOCX").endswith("/source/source.docx")
    assert canonical_pdf_object_key(**ASSET_ARGS).endswith("/canonical/document.pdf")
    assert page_image_object_key(**ASSET_ARGS, physical_page=12).endswith("/pages/page-0012.png")
    assert object_crop_object_key(
        **ASSET_ARGS, knowledge_object_id="01ARZ3NDEKTSV4RRFFQ69G5FAY"
    ).endswith("/objects/01ARZ3NDEKTSV4RRFFQ69G5FAY/crop.png")
    assert sha256_bytes(b"textbook snapshot") == sha256_bytes(b"textbook snapshot")


@pytest.mark.parametrize("page, image_format", [(0, "png"), (1, "jpg")])
def test_page_asset_key_rejects_ambiguous_inputs(page: int, image_format: str) -> None:
    with pytest.raises(ValueError):
        page_image_object_key(**ASSET_ARGS, physical_page=page, image_format=image_format)


def test_pdf_bbox_maps_to_browser_pixel_coordinates() -> None:
    transform = PageTransform(pdf_width=100, pdf_height=200, pixel_width=200, pixel_height=400)
    assert transform.pdf_bbox_to_pixels([10, 20, 30, 40]) == [20.0, 320.0, 60.0, 360.0]
    assert transform.manifest()["dpi"] == 144


def test_rotation_is_recorded_and_applied() -> None:
    transform = PageTransform(
        pdf_width=100, pdf_height=200, pixel_width=400, pixel_height=200, rotation=90
    )
    assert transform.pdf_bbox_to_pixels([0, 0, 100, 200]) == [0.0, 0.0, 400.0, 200.0]


def test_render_manifest_retains_page_coordinate_contract() -> None:
    page = RenderedPage(
        physical_page=1,
        content=b"image",
        mime_type="image/png",
        transform=PageTransform(100, 200, 200, 400),
    )
    rendered = RenderedDocument(
        canonical_pdf=b"%PDF-", pages=[page], renderer_name="test", renderer_version="v1"
    )
    assert rendered.manifest() == {
        "renderer": "test",
        "renderer_version": "v1",
        "page_count": 1,
        "pages": [
            {
                "physical_page": 1,
                "pdf_width": 100,
                "pdf_height": 200,
                "pixel_width": 200,
                "pixel_height": 400,
                "rotation": 0,
                "dpi": 144,
            }
        ],
    }
