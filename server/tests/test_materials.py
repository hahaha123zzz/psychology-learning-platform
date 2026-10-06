import io

import pymupdf
from sqlalchemy import select

from app.modules.materials.parsers.stub_pdf import StubPdfParser
from tests.conftest import create_user_sync, make_pdf

MINIMAL_PDF = make_pdf([["Minimal test page for upload fixture text"]])
FAKE_DOCX = b"this is not a zip file at all" * 3


def test_pdf_parser_ignores_contents_chapters_and_detects_outline_boundary() -> None:
    source = make_pdf(
        [
            ["Contents", "Chapter 1: Introduction", "Chapter 2: Research"],
            [
                "Chapter 6",
                "INTRODUCTION",
                "CHAPTER OUTLINE",
                "6.1 What Is Learning?",
                "Body text",
            ],
        ]
    )

    result = StubPdfParser().parse(source, "application/pdf")
    chapters = [item for item in result.objects if item.type == "chapter"]

    assert [(item.title, item.physical_page, item.chapter_path) for item in chapters] == [
        ("Chapter 6", 2, "6")
    ]


def test_pdf_parser_emits_real_text_block_bbox() -> None:
    result = StubPdfParser().parse(MINIMAL_PDF, "application/pdf")
    paragraph = next(item for item in result.objects if item.type == "paragraph")

    assert paragraph.bbox is not None
    left, bottom, right, top = paragraph.bbox
    assert 0 <= left < right
    assert 0 <= bottom < top


def test_pdf_parser_emits_embedded_figure_with_real_bbox_and_asset() -> None:
    # 原生 PNG；PDF 中以真正的 image block 嵌入，避免以图注模拟图片对象。
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
    pixmap.clear_with(255)
    png = pixmap.tobytes("png")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Figure source page")
    page.insert_image(pymupdf.Rect(72, 120, 172, 220), stream=png)
    source = document.tobytes()
    document.close()

    result = StubPdfParser().parse(source, "application/pdf")

    figure = next(item for item in result.objects if item.type == "figure")
    assert figure.bbox is not None
    left, bottom, right, top = figure.bbox
    assert 0 <= left < right
    assert 0 <= bottom < top
    assert figure.asset_bytes
    assert figure.asset_mime_type == "image/png"


def test_pdf_parser_emits_only_native_grid_table_objects() -> None:
    document = pymupdf.open()
    page = document.new_page()
    for x in (72, 172, 272):
        page.draw_line((x, 100), (x, 200))
    for y in (100, 150, 200):
        page.draw_line((72, y), (272, y))
    cells = (
        ((82, 130), "变量"),
        ((182, 130), "定义"),
        ((82, 180), "自变量"),
        ((182, 180), "实验条件"),
    )
    for point, text in cells:
        page.insert_text(point, text)
    page.insert_text((72, 250), "The table discussion explains the results.")
    source = document.tobytes()
    document.close()

    result = StubPdfParser().parse(source, "application/pdf")

    table = next(item for item in result.objects if item.type == "table")
    assert table.bbox is not None
    assert table.confidence == 0.85
    assert "|" in table.raw_content
    assert not any(
        item.type == "paragraph" and "自变量" in item.raw_content
        for item in result.objects
    )
    assert any(
        item.type == "paragraph" and "table discussion" in item.raw_content
        for item in result.objects
    )


def test_pdf_parser_emits_conservative_standalone_formula_object() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((180, 180), "d' = Z(H) - Z(F)")
    page.insert_text((72, 260), "The result = 3 is explained in this complete sentence.")
    source = document.tobytes()
    document.close()

    result = StubPdfParser().parse(source, "application/pdf")

    formulas = [item for item in result.objects if item.type == "formula"]
    assert [item.raw_content for item in formulas] == ["d' = Z(H) - Z(F)"]
    assert formulas[0].bbox is not None


def _login(client, email: str, password: str = "correct-password"):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return response


def _setup_course(client):
    """创建教师与学生账号，教师建课，返回 (course_id, student_id)。"""
    create_user_sync(email="mt@uni.edu", is_teacher=True)
    create_user_sync(email="ms@uni.edu")
    _login(client, "mt@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "教材测试课", "term": "2026春"},
    ).json()["data"]
    _login(client, "ms@uni.edu")
    student_id = client.get("/api/v1/me").json()["data"]["id"]
    _login(client, "mt@uni.edu")
    client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    return course["id"], student_id


def _upload(client, course_id: str, *, content=MINIMAL_PDF, filename="a.pdf",
            title="第一章讲义", material_type="slides", visibility="draft",
            key=None):
    data = {
        "title": title,
        "material_type": material_type,
        "visibility": visibility,
    }
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/v1/courses/{course_id}/materials",
        data=data,
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        headers=headers,
    )


def test_student_cannot_upload_material(client) -> None:
    course_id, _ = _setup_course(client)
    _login(client, "ms@uni.edu")
    response = _upload(client, course_id)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_unauthenticated_upload_rejected(client) -> None:
    course_id, _ = _setup_course(client)
    client.cookies.clear()
    response = _upload(client, course_id)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_upload_pdf_material_success(client) -> None:
    course_id, _ = _setup_course(client)
    response = _upload(
        client, course_id, title="实验心理学教材", material_type="textbook"
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "uploaded"
    assert data["sha256"] and len(data["sha256"]) == 64
    assert data["size_bytes"] == len(MINIMAL_PDF)
    assert data["material_id"] and data["version_id"]


def test_upload_cannot_bypass_teacher_review_with_published_visibility(client) -> None:
    course_id, _ = _setup_course(client)
    response = _upload(client, course_id, visibility="published")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MATERIAL_REQUIRES_REVIEW"


def test_upload_unsupported_extension_rejected(client) -> None:
    course_id, _ = _setup_course(client)
    response = _upload(client, course_id, filename="virus.exe")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_signature_mismatch_rejected(client) -> None:
    course_id, _ = _setup_course(client)
    response = _upload(client, course_id, content=FAKE_DOCX, filename="fake.docx")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_SIGNATURE_MISMATCH"


def test_upload_empty_file_rejected(client) -> None:
    course_id, _ = _setup_course(client)
    response = _upload(client, course_id, content=b"")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_upload_duplicate_hash_rejected(client) -> None:
    course_id, _ = _setup_course(client)
    first = _upload(client, course_id, title="原始文件")
    assert first.status_code == 201
    duplicate = _upload(client, course_id, title="内容相同的新名字")
    assert duplicate.status_code == 409
    error = duplicate.json()["error"]
    assert error["code"] == "DUPLICATE_MATERIAL"
    assert error["details"]["material_id"] == first.json()["data"]["material_id"]


def test_upload_idempotent_replay_same_version(client) -> None:
    course_id, _ = _setup_course(client)
    first = _upload(client, course_id, key="upload-key-1")
    replay = _upload(client, course_id, key="upload-key-1")
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["data"]["version_id"] == first.json()["data"]["version_id"]


def test_upload_idempotency_key_conflict(client) -> None:
    course_id, _ = _setup_course(client)
    _upload(client, course_id, title="第一个文件", key="upload-key-2")
    conflict = _upload(
        client,
        course_id,
        title="换了标题",
        key="upload-key-2",
        content=b"%PDF-1.4 different content",
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_upload_file_too_large(client) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    original_limit = settings.upload_max_mb
    settings.upload_max_mb = 1
    try:
        course_id, _ = _setup_course(client)
        big = b"%PDF-1.4\n" + b"x" * (2 * 1024 * 1024)
        response = _upload(client, course_id, content=big)
    finally:
        settings.upload_max_mb = original_limit
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_nonexistent_course_404(client) -> None:
    create_user_sync(email="mt404@uni.edu", is_teacher=True)
    _login(client, "mt404@uni.edu")
    response = _upload(client, "01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_uploaded_draft_invisible_to_students_listing_placeholder(client) -> None:
    """D9 实现列表接口前的基线：草稿上传成功且状态为uploaded。"""
    course_id, _ = _setup_course(client)
    response = _upload(client, course_id)
    assert response.status_code == 201
    assert response.json()["data"]["status"] == "uploaded"


def _prepare_course_with_student_release_assignment(client):
    from app.db.base import new_ulid
    from tests.test_search import _create_student_search_release, _prepare

    course_id, student_id, version_id = _prepare(client, publish=True)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]
    _create_student_search_release(
        client,
        course_id=course_id,
        student_id=student_id,
        teacher_id=teacher_id,
        version_id=version_id,
        domain_release_id=new_ulid(),
    )
    return course_id, student_id, version_id, teacher_id


def test_student_material_list_uses_assigned_version_after_material_rotation(client) -> None:
    import asyncio

    from app.db.base import new_ulid
    from app.db.models import Material, MaterialVersion
    from app.db.session import session_factory

    course_id, student_id, pinned_version_id, teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )

    async def rotate_current_version() -> None:
        async with session_factory() as db:
            pinned_version = await db.get(MaterialVersion, pinned_version_id)
            assert pinned_version is not None
            material = await db.get(Material, pinned_version.material_id)
            assert material is not None
            replacement = MaterialVersion(
                id=new_ulid(),
                material_id=material.id,
                version_no=pinned_version.version_no + 1,
                status="parsed",
                object_key=f"synthetic/{new_ulid()}.pdf",
                sha256="f" * 64,
                size_bytes=1,
                content_type="application/pdf",
                original_filename="synthetic-rotated.pdf",
                created_by=teacher_id,
            )
            db.add(replacement)
            await db.flush()
            material.current_version_id = replacement.id
            await db.commit()

    asyncio.run(rotate_current_version())

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["current_version"]["id"] == pinned_version_id
    assert rows[0]["current_version"]["version_no"] == 1


def test_student_material_list_legacy_fallback_only_for_never_assigned_course(client) -> None:
    from tests.test_search import _prepare

    course_id, _student_id, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 200, response.text
    assert [item["current_version"]["id"] for item in response.json()["data"]] == [version_id]


def test_student_material_list_allows_assigned_release_with_no_materials(client) -> None:
    import asyncio

    from app.db.models import CourseRelease, CourseReleaseAssignment
    from app.db.session import session_factory

    course_id, _student_id, _version_id, _teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )

    async def empty_release_manifest() -> None:
        async with session_factory() as db:
            assignment = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            release.manifest = {
                **release.manifest,
                "materials": [],
                "material_version_ids": [],
                "publication_snapshots": [],
            }
            await db.commit()

    asyncio.run(empty_release_manifest())
    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


def test_student_material_list_keeps_staff_projection_unchanged(client) -> None:
    course_id, _student_id, version_id, _teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )
    _login(client, "mt@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["current_version"]["id"] == version_id
    assert rows[0]["visibility"] == "published"
    assert "quality_gate_status" in rows[0]["current_version"]
    assert "workflow_state" in rows[0]["current_version"]
    assert "published_snapshot_id" in rows[0]["current_version"]


def test_student_material_list_rejects_multiple_active_assignments(client) -> None:
    import asyncio

    from app.db.models import (
        ClassMember,
        CourseClass,
        CourseReleaseAssignment,
    )
    from app.db.session import session_factory

    course_id, student_id, _version_id, teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )

    async def add_second_active_assignment() -> None:
        async with session_factory() as db:
            first = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert first is not None
            second_class = CourseClass(
                course_id=course_id,
                code="MATERIAL-LIST-SECOND",
                name="合成第二班",
                created_by=teacher_id,
            )
            db.add(second_class)
            await db.flush()
            db.add_all(
                [
                    ClassMember(class_id=second_class.id, user_id=student_id),
                    CourseReleaseAssignment(
                        course_id=course_id,
                        class_id=second_class.id,
                        course_release_id=first.course_release_id,
                        status="active",
                        assigned_by=teacher_id,
                    ),
                ]
            )
            await db.commit()

    asyncio.run(add_second_active_assignment())

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS"


def test_student_material_list_denies_assignment_history_without_active_class_membership(
    client,
) -> None:
    import asyncio

    from app.db.models import ClassMember, CourseClass
    from app.db.session import session_factory

    course_id, student_id, _version_id, _teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )

    async def remove_active_class_membership() -> None:
        async with session_factory() as db:
            membership = await db.scalar(
                select(ClassMember)
                .join(CourseClass, CourseClass.id == ClassMember.class_id)
                .where(
                    CourseClass.course_id == course_id,
                    ClassMember.user_id == student_id,
                )
            )
            assert membership is not None
            membership.status = "removed"
            await db.commit()

    asyncio.run(remove_active_class_membership())

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_student_material_list_rejects_invalid_release_and_pins(client) -> None:
    import asyncio
    from copy import deepcopy

    from app.db.models import CourseRelease, CourseReleaseAssignment
    from app.db.session import session_factory

    course_id, _student_id, _version_id, _teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )

    async def corrupt_pin_then_release_status() -> None:
        async with session_factory() as db:
            assignment = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            original_manifest = deepcopy(release.manifest)
            invalid_manifest = deepcopy(original_manifest)
            invalid_manifest["publication_snapshots"][0]["publication_snapshot_id"] = "missing"
            release.manifest = invalid_manifest
            await db.commit()

    asyncio.run(corrupt_pin_then_release_status())
    _login(client, "ms@uni.edu")
    invalid_pin = client.get(f"/api/v1/courses/{course_id}/materials")
    assert invalid_pin.status_code == 409
    assert invalid_pin.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_INVALID"

    async def invalidate_release() -> None:
        async with session_factory() as db:
            assignment = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            release.status = "draft"
            await db.commit()

    asyncio.run(invalidate_release())
    invalid_release = client.get(f"/api/v1/courses/{course_id}/materials")
    assert invalid_release.status_code == 409
    assert invalid_release.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_INVALID"


def test_student_material_list_course_membership_revocation_precedes_release_lookup(client) -> None:
    course_id, student_id, _version_id, _teacher_id = (
        _prepare_course_with_student_release_assignment(client)
    )
    _login(client, "mt@uni.edu")
    members = client.get(f"/api/v1/courses/{course_id}/members")
    assert members.status_code == 200
    member = next(item for item in members.json()["data"] if item["user_id"] == student_id)
    removed = client.delete(f"/api/v1/courses/{course_id}/members/{member['id']}")
    assert removed.status_code == 200

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"
