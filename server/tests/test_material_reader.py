import asyncio
import hashlib
import io
import json
import zipfile

import pymupdf
from sqlalchemy import select

from app.core.storage import get_object_bytes, put_object
from app.db.base import new_ulid
from app.db.models import (
    CourseMember,
    EvidencePointer,
    Material,
    MaterialVersion,
    PublicationSnapshot,
)
from app.db.session import session_factory
from app.modules.materials.artifacts import page_image_object_key
from app.modules.materials.parsers.stub_pdf import StubPdfParser
from app.modules.materials.renderers.pymupdf_pdf import RENDERER_VERSION, render_pdf_page
from tests.conftest import create_user_sync
from tests.test_materials import _login, _setup_course, _upload
from tests.test_search import _prepare


def _search_pointer(client, course_id: str) -> dict:
    _login(client, "ms@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "independent variable validity"},
    )
    assert response.status_code == 200
    item = next(
        item
        for item in response.json()["data"]["items"]
        if item.get("evidence_pointer_id") and item.get("bbox")
    )
    return item


def _valid_docx() -> bytes:
    document_xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>Synthetic DOCX reader fixture</w:t></w:r></w:p></w:body>
    </w:document>"""
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", document_xml)
    return result.getvalue()


def test_rotated_pdf_parser_bbox_and_render_transform_share_pdf_coordinates() -> None:
    document = pymupdf.open()
    page = document.new_page(width=400, height=600)
    page.insert_text((50, 80), "Synthetic rotated reader fixture")
    page.draw_rect(pymupdf.Rect(50, 60, 90, 100), color=(0, 0, 0), fill=(0, 0, 0))
    page.set_rotation(90)
    source = document.tobytes()
    document.close()

    parsed = StubPdfParser().parse(source, "application/pdf")
    paragraph = next(item for item in parsed.objects if item.type == "paragraph")
    assert paragraph.bbox is not None
    left, bottom, right, top = paragraph.bbox
    assert 0 <= left < right <= 400
    assert 500 < bottom < top < 600

    rendered = render_pdf_page(source, 1)
    assert rendered.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert rendered.transform.rotation == 90
    assert rendered.transform.pixel_width == 1200
    assert rendered.transform.pixel_height == 800
    pixel_box = rendered.transform.pdf_bbox_to_pixels(paragraph.bbox)
    assert 0 <= pixel_box[0] < pixel_box[2] <= 1200
    assert 0 <= pixel_box[1] < pixel_box[3] <= 800
    rect_pixels = rendered.transform.pdf_bbox_to_pixels([50, 500, 90, 540])
    pixmap = pymupdf.Pixmap(rendered.content)
    center_x = round((rect_pixels[0] + rect_pixels[2]) / 2)
    center_y = round((rect_pixels[1] + rect_pixels[3]) / 2)
    assert pixmap.pixel(center_x, center_y) == (0, 0, 0)


def test_reader_page_image_is_versioned_cached_and_keeps_historical_pointer(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    pointer = _search_pointer(client, course_id)
    pointer_id = pointer["evidence_pointer_id"]

    pointer_view = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert pointer_view.status_code == 200
    assert pointer_view.json()["data"]["course_id"] == course_id
    assert pointer_view.json()["data"]["material_version_id"] == version_id
    assert pointer_view.json()["data"]["physical_page"] == pointer["physical_page"]
    assert any(
        anchor["physical_page"] == pointer["physical_page"]
        and anchor["bbox"] == pointer["bbox"]
        and anchor["coordinate_space"] == "pdf_user_bottom_left"
        for anchor in pointer_view.json()["data"]["anchors"]
    )

    page_image = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert page_image.status_code == 200
    assert page_image.headers["content-type"].startswith("image/png")
    assert page_image.headers["cache-control"] == "private, no-store"
    assert page_image.headers["x-content-type-options"] == "nosniff"
    assert page_image.content.startswith(b"\x89PNG\r\n\x1a\n")
    transform = json.loads(page_image.headers["x-reader-transform"])
    bbox_pixels = json.loads(page_image.headers["x-reader-bbox-pixels"])
    assert transform["dpi"] == 144
    assert 0 <= bbox_pixels[0] < bbox_pixels[2] <= transform["pixel_width"]
    assert 0 <= bbox_pixels[1] < bbox_pixels[3] <= transform["pixel_height"]

    image_key = page_image_object_key(
        course_id=course_id,
        material_id=pointer["material_id"],
        version_id=version_id,
        physical_page=pointer["physical_page"],
        render_version=RENDERER_VERSION,
    )
    stored_image = asyncio.run(get_object_bytes(image_key))
    assert stored_image == page_image.content

    async def corrupt_cached_image() -> None:
        damaged = b"not a PNG"
        await put_object(
            key=image_key,
            data=io.BytesIO(damaged),
            length=len(damaged),
            content_type="image/png",
        )

    asyncio.run(corrupt_cached_image())
    repaired_page = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert repaired_page.status_code == 200
    assert repaired_page.content == stored_image
    assert asyncio.run(get_object_bytes(image_key)) == stored_image

    metadata_key = f"{image_key.rsplit('.', 1)[0]}.json"

    async def corrupt_cached_metadata() -> None:
        damaged = b"[]"
        await put_object(
            key=metadata_key,
            data=io.BytesIO(damaged),
            length=len(damaged),
            content_type="application/json",
        )

    asyncio.run(corrupt_cached_metadata())
    repaired_metadata = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert repaired_metadata.status_code == 200
    assert repaired_metadata.content == stored_image

    async def remove_version_hash() -> str:
        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None and version.sha256 is not None
            expected_hash = version.sha256
            version.sha256 = None
            await db.commit()
            return expected_hash

    expected_hash = asyncio.run(remove_version_hash())
    missing_hash = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert missing_hash.status_code == 409
    assert missing_hash.json()["error"]["code"] == "MATERIAL_VERSION_INTEGRITY_FAILED"

    async def restore_version_hash() -> None:
        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None
            version.sha256 = expected_hash
            await db.commit()

    asyncio.run(restore_version_hash())

    async def advance_current_version() -> None:
        async with session_factory() as db:
            previous = await db.get(MaterialVersion, version_id)
            assert previous is not None
            material = await db.get(Material, previous.material_id)
            assert material is not None
            replacement = MaterialVersion(
                id=new_ulid(),
                material_id=previous.material_id,
                version_no=previous.version_no + 1,
                status="uploaded",
                object_key="synthetic/unread-current-version.pdf",
                sha256="f" * 64,
                size_bytes=1,
                content_type="application/pdf",
                original_filename="current.pdf",
                created_by=previous.created_by,
            )
            db.add(replacement)
            await db.flush()
            material.current_version_id = replacement.id
            await db.commit()

    asyncio.run(advance_current_version())
    historical_page = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert historical_page.status_code == 200
    assert historical_page.content == stored_image
    historical_pointer = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert historical_pointer.status_code == 200
    assert historical_pointer.json()["data"]["material_version_id"] == version_id


def test_reader_page_image_rechecks_membership_and_archive_state(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    pointer = _search_pointer(client, course_id)
    pointer_id = pointer["evidence_pointer_id"]

    create_user_sync(email="reader-outsider@uni.edu")
    _login(client, "reader-outsider@uni.edu")
    outside = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert outside.status_code == 404

    _login(client, "mt@uni.edu")

    async def archive_material() -> None:
        async with session_factory() as db:
            material = await db.get(Material, pointer["material_id"])
            assert material is not None
            material.status = "archived"
            await db.commit()

    asyncio.run(archive_material())
    _login(client, "ms@uni.edu")
    archived = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert archived.status_code == 404
    assert archived.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_reader_page_image_rechecks_removed_membership_after_image_is_cached(client) -> None:
    course_id, student_id, _ = _prepare(client, publish=True)
    pointer = _search_pointer(client, course_id)
    pointer_id = pointer["evidence_pointer_id"]

    cached = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert cached.status_code == 200

    async def remove_student() -> None:
        async with session_factory() as db:
            member = await db.scalar(
                select(CourseMember).where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            await db.commit()

    asyncio.run(remove_student())
    _login(client, "ms@uni.edu")
    revoked = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert revoked.status_code == 404
    assert revoked.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_reader_pointer_metadata_rechecks_removed_membership(client) -> None:
    course_id, student_id, _ = _prepare(client, publish=True)
    pointer = _search_pointer(client, course_id)
    pointer_id = pointer["evidence_pointer_id"]

    before_revocation = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert before_revocation.status_code == 200

    async def remove_student() -> None:
        async with session_factory() as db:
            member = await db.scalar(
                select(CourseMember).where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            await db.commit()

    asyncio.run(remove_student())
    _login(client, "ms@uni.edu")
    revoked = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert revoked.status_code == 404
    assert revoked.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_reader_page_image_requires_auth_and_exact_published_snapshot(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    pointer = _search_pointer(client, course_id)
    pointer_id = pointer["evidence_pointer_id"]
    endpoint = f"/api/v1/evidence-pointers/{pointer_id}/page-image"

    client.cookies.clear()
    unauthenticated = client.get(endpoint)
    assert unauthenticated.status_code == 401

    _login(client, "ms@uni.edu")

    async def unpublish_material() -> None:
        async with session_factory() as db:
            material = await db.get(Material, pointer["material_id"])
            assert material is not None
            material.visibility = "draft"
            await db.commit()

    asyncio.run(unpublish_material())
    unpublished = client.get(endpoint)
    assert unpublished.status_code == 404
    assert unpublished.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"

    async def remove_exact_publication_snapshot() -> None:
        async with session_factory() as db:
            material = await db.get(Material, pointer["material_id"])
            assert material is not None
            material.visibility = "published"
            snapshot = await db.scalar(
                select(PublicationSnapshot).where(
                    PublicationSnapshot.material_id == pointer["material_id"],
                    PublicationSnapshot.material_version_id == version_id,
                )
            )
            assert snapshot is not None
            await db.delete(snapshot)
            await db.commit()

    asyncio.run(remove_exact_publication_snapshot())
    unrecorded_version = client.get(endpoint)
    assert unrecorded_version.status_code == 404
    assert unrecorded_version.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_reader_malformed_bbox_degrades_to_text_snapshot(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    pointer = _search_pointer(client, course_id)
    pointer_id = pointer["evidence_pointer_id"]

    async def corrupt_pointer_bbox() -> None:
        async with session_factory() as db:
            stored_pointer = await db.get(EvidencePointer, pointer_id)
            assert stored_pointer is not None
            stored_pointer.bbox = [None, 0, 100, 100]
            await db.commit()

    asyncio.run(corrupt_pointer_bbox())
    response = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "READER_LAYOUT_UNAVAILABLE"

    async def move_pointer_bbox_outside_page() -> None:
        async with session_factory() as db:
            stored_pointer = await db.get(EvidencePointer, pointer_id)
            assert stored_pointer is not None
            stored_pointer.bbox = [0, 0, 10000, 10000]
            await db.commit()

    asyncio.run(move_pointer_bbox_outside_page())
    out_of_bounds = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert out_of_bounds.status_code == 409
    assert out_of_bounds.json()["error"]["code"] == "READER_LAYOUT_UNAVAILABLE"


def test_docx_pointer_without_layout_returns_text_fallback_status(client) -> None:
    course_id, _ = _setup_course(client)
    upload = _upload(client, course_id, content=_valid_docx(), filename="synthetic.docx")
    assert upload.status_code == 201
    data = upload.json()["data"]
    excerpt = "Synthetic DOCX reader fixture"
    pointer_id = new_ulid()

    async def seed_pointer() -> None:
        async with session_factory() as db:
            db.add(
                EvidencePointer(
                    id=pointer_id,
                    course_id=course_id,
                    material_id=data["material_id"],
                    material_version_id=data["version_id"],
                    source_object_id=None,
                    retrieval_unit_id=None,
                    material_title="Synthetic DOCX",
                    excerpt=excerpt,
                    excerpt_sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                    chapter_path=None,
                    physical_page=1,
                    reading_order=1,
                    object_type="paragraph",
                    coordinate_space="unavailable",
                    bbox=None,
                )
            )
            await db.commit()

    asyncio.run(seed_pointer())
    response = client.get(f"/api/v1/evidence-pointers/{pointer_id}/page-image")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "READER_LAYOUT_UNAVAILABLE"
    assert "文字来源快照" in response.json()["error"]["message"]
