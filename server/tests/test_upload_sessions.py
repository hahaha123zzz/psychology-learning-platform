"""可恢复分片上传会话：成功路径、边界校验、失败恢复与权限测试。"""

import httpx

from app.core.config import get_settings
from app.modules.materials.parsers.stub_pdf import StubPdfParser
from tests.conftest import create_user_sync, make_pdf

CONTENT = make_pdf([["Resumable upload session test page with enough text."]])


def _login(client, email: str, password: str = "correct-password"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response


def _setup_course(client):
    create_user_sync(email="ut@uni.edu", is_teacher=True)
    create_user_sync(email="us@uni.edu")
    _login(client, "ut@uni.edu")
    course = client.post(
        "/api/v1/courses", json={"title": "分片上传测试课", "term": "2026春"}
    ).json()["data"]
    _login(client, "us@uni.edu")
    student_id = client.get("/api/v1/me").json()["data"]["id"]
    _login(client, "ut@uni.edu")
    client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    return course["id"], student_id


def _create_session(client, course_id: str, *, size_bytes: int | None = None, title="分片教材"):
    return client.post(
        f"/api/v1/courses/{course_id}/upload-sessions",
        json={
            "title": title,
            "material_type": "textbook",
            "filename": "book.pdf",
            "size_bytes": size_bytes if size_bytes is not None else len(CONTENT),
        },
    )


def _upload_part_directly(client, session_id: str, part_number: int, content: bytes) -> str:
    url_data = client.post(f"/api/v1/upload-sessions/{session_id}/parts/{part_number}/url").json()[
        "data"
    ]
    assert url_data["size_bytes"] == len(content)
    response = httpx.put(url_data["upload_url"], content=content, timeout=30)
    assert response.status_code in (200, 201), response.text
    etag = response.headers["ETag"]
    assert etag
    return etag


def _record_part(client, session_id: str, part_number: int, etag: str, size_bytes: int):
    return client.put(
        f"/api/v1/upload-sessions/{session_id}/parts/{part_number}",
        json={"etag": etag, "size_bytes": size_bytes},
    )


def test_student_cannot_create_upload_session(client) -> None:
    course_id, _ = _setup_course(client)
    _login(client, "us@uni.edu")
    response = _create_session(client, course_id)
    # 课程成员但角色不符：按防资源枚举约定统一返回 404。
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_create_session_rejects_oversize_declaration(client) -> None:
    course_id, _ = _setup_course(client)
    response = _create_session(client, course_id, size_bytes=201 * 1024 * 1024)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_resumable_upload_completes_and_creates_material(client) -> None:
    course_id, _ = _setup_course(client)
    created = _create_session(client, course_id)
    assert created.status_code == 201
    session = created.json()["data"]
    session_id = session["upload_session_id"]
    assert session["status"] == "uploading"
    assert session["total_parts"] == 1
    assert session["completed_parts"] == []

    etag = _upload_part_directly(client, session_id, 1, CONTENT)
    recorded = _record_part(client, session_id, 1, etag, len(CONTENT))
    assert recorded.status_code == 200
    assert recorded.json()["data"]["status"] == "uploading"

    status = client.get(f"/api/v1/upload-sessions/{session_id}").json()["data"]
    assert status["completed_parts"] == [1]

    parsed = StubPdfParser().parse(CONTENT, "application/pdf")
    assert parsed.page_count >= 1

    completed = client.post(f"/api/v1/upload-sessions/{session_id}/complete")
    assert completed.status_code == 200
    data = completed.json()["data"]
    assert data["status"] == "uploaded"
    assert len(data["sha256"]) == 64
    assert data["size_bytes"] == len(CONTENT)

    materials = client.get(f"/api/v1/courses/{course_id}/materials").json()["data"]
    assert any(item["id"] == data["material_id"] for item in materials)

    final = client.get(f"/api/v1/upload-sessions/{session_id}").json()["data"]
    assert final["status"] == "completed"
    assert final["material_id"] == data["material_id"]
    assert final["material_version_id"] == data["version_id"]
    assert final["sha256"] == data["sha256"]


def test_complete_without_all_parts_is_rejected(client) -> None:
    course_id, _ = _setup_course(client)
    session_id = _create_session(client, course_id, size_bytes=9 * 1024 * 1024).json()["data"][
        "upload_session_id"
    ]
    response = client.post(f"/api/v1/upload-sessions/{session_id}/complete")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "UPLOAD_PARTS_INCOMPLETE"


def test_record_part_rejects_size_mismatch_and_bad_etag(client) -> None:
    course_id, _ = _setup_course(client)
    session_id = _create_session(client, course_id).json()["data"]["upload_session_id"]
    etag = _upload_part_directly(client, session_id, 1, CONTENT)

    mismatch = _record_part(client, session_id, 1, etag, len(CONTENT) + 1)
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "UPLOAD_PART_SIZE_MISMATCH"

    missing_etag = _record_part(client, session_id, 1, "   ", len(CONTENT))
    assert missing_etag.status_code == 422
    assert missing_etag.json()["error"]["code"] == "UPLOAD_PART_ETAG_REQUIRED"

    out_of_range = _record_part(client, session_id, 2, etag, 1)
    assert out_of_range.status_code == 422
    assert out_of_range.json()["error"]["code"] == "UPLOAD_PART_OUT_OF_RANGE"


def test_complete_detects_size_mismatch_after_merge(client) -> None:
    course_id, _ = _setup_course(client)
    declared = len(CONTENT) + 10
    session_id = _create_session(client, course_id, size_bytes=declared).json()["data"][
        "upload_session_id"
    ]
    url_data = client.post(f"/api/v1/upload-sessions/{session_id}/parts/1/url").json()["data"]
    assert url_data["size_bytes"] == declared
    response = httpx.put(url_data["upload_url"], content=CONTENT, timeout=30)
    etag = response.headers["ETag"]
    recorded = _record_part(client, session_id, 1, etag, declared)
    assert recorded.status_code == 200

    completed = client.post(f"/api/v1/upload-sessions/{session_id}/complete")
    assert completed.status_code == 422
    assert completed.json()["error"]["code"] == "UPLOAD_SIZE_MISMATCH"
    final = client.get(f"/api/v1/upload-sessions/{session_id}").json()["data"]
    assert final["status"] == "failed"


def test_duplicate_content_is_rejected_on_complete(client) -> None:
    course_id, _ = _setup_course(client)
    first_id = _create_session(client, course_id, title="第一本").json()["data"][
        "upload_session_id"
    ]
    etag = _upload_part_directly(client, first_id, 1, CONTENT)
    assert _record_part(client, first_id, 1, etag, len(CONTENT)).status_code == 200
    assert client.post(f"/api/v1/upload-sessions/{first_id}/complete").status_code == 200

    second_id = _create_session(client, course_id, title="重复本").json()["data"][
        "upload_session_id"
    ]
    etag = _upload_part_directly(client, second_id, 1, CONTENT)
    assert _record_part(client, second_id, 1, etag, len(CONTENT)).status_code == 200
    duplicate = client.post(f"/api/v1/upload-sessions/{second_id}/complete")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_MATERIAL"


def test_cancel_session_and_double_cancel(client) -> None:
    course_id, _ = _setup_course(client)
    session_id = _create_session(client, course_id).json()["data"]["upload_session_id"]
    cancelled = client.delete(f"/api/v1/upload-sessions/{session_id}")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"

    again = client.delete(f"/api/v1/upload-sessions/{session_id}")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "UPLOAD_SESSION_NOT_CANCELLABLE"


def test_expired_session_blocks_part_operations(client, monkeypatch) -> None:
    course_id, _ = _setup_course(client)
    monkeypatch.setattr(get_settings(), "upload_session_ttl_hours", 0)
    session_id = _create_session(client, course_id).json()["data"]["upload_session_id"]
    monkeypatch.undo()

    status = client.get(f"/api/v1/upload-sessions/{session_id}").json()["data"]
    assert status["status"] == "expired"

    url_response = client.post(f"/api/v1/upload-sessions/{session_id}/parts/1/url")
    assert url_response.status_code == 409
    assert url_response.json()["error"]["code"] == "UPLOAD_SESSION_EXPIRED"
