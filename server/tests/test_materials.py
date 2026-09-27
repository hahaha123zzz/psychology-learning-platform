import io

import pymupdf

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
