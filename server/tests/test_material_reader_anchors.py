import asyncio

from app.db.models import EvidencePointer
from app.db.session import session_factory
from tests.test_material_reader import _search_pointer
from tests.test_search import _prepare


def test_reader_selects_only_persisted_anchor_pages(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    search_item = _search_pointer(client, course_id)
    pointer_id = search_item["evidence_pointer_id"]
    first_page = search_item["physical_page"]
    bbox = search_item["bbox"]
    second_page = 2 if first_page != 2 else 1

    async def add_second_page_anchor() -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            pointer.anchors = [
                {
                    "physical_page": first_page,
                    "bbox": bbox,
                    "coordinate_space": "pdf_user_bottom_left",
                    "precision": "test_verified_bbox",
                },
                {
                    "physical_page": second_page,
                    "bbox": bbox,
                    "coordinate_space": "pdf_user_bottom_left",
                    "precision": "test_verified_bbox",
                },
            ]
            await db.commit()

    asyncio.run(add_second_page_anchor())

    selected = client.get(
        f"/api/v1/evidence-pointers/{pointer_id}/page-image",
        params={"physical_page": second_page},
    )
    assert selected.status_code == 200
    assert selected.headers["x-reader-physical-page"] == str(second_page)
    assert selected.content.startswith(b"\x89PNG\r\n\x1a\n")

    outside = client.get(
        f"/api/v1/evidence-pointers/{pointer_id}/page-image",
        params={"physical_page": 3},
    )
    assert outside.status_code == 404
    assert outside.json()["error"]["code"] == "EVIDENCE_ANCHOR_NOT_FOUND"
