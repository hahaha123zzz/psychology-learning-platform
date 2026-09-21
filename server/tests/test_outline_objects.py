import asyncio
import time

from app.db.models import Material, MaterialVersion
from app.db.session import session_factory
from tests.conftest import make_pdf
from tests.test_materials import _login, _setup_course, _upload


def _parse_and_wait(client, version_id: str, timeout: float = 20.0) -> dict:
    response = client.post(f"/api/v1/material-versions/{version_id}/parse")
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.3)
    raise AssertionError("任务超时")


def _embed_and_wait(client, version_id: str, timeout: float = 20.0) -> dict:
    response = client.post(f"/api/v1/material-versions/{version_id}/embed")
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.3)
    raise AssertionError("索引任务超时")


TWO_CHAPTER_PDF = make_pdf(
    [
        [
            "Chapter 1 Foundations of Experimental Psychology",
            "This chapter introduces variables, control techniques and validity.",
        ],
        [
            "Chapter 2 Research Design Details",
            "Between-subjects and within-subjects designs are compared here.",
        ],
    ]
)


def test_outline_returns_stable_chapter_tree(client) -> None:
    course_id, _ = _setup_course(client)
    upload = _upload(
        client, course_id, title="实验心理学教材", content=TWO_CHAPTER_PDF
    )
    assert upload.status_code == 201
    version_id = upload.json()["data"]["version_id"]

    job = _parse_and_wait(client, version_id)
    assert job["status"] == "succeeded", job

    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    assert outline.status_code == 200
    chapters = outline.json()["data"]
    assert len(chapters) == 2
    assert chapters[0]["title"] == "Chapter 1 Foundations of Experimental Psychology"
    assert chapters[0]["start_page"] == 1
    assert chapters[0]["end_page"] == 1
    assert chapters[1]["start_page"] == 2
    assert chapters[1]["level"] == 1
    assert chapters[1]["object_count"] >= 1
    assert chapters[0]["id"] != chapters[1]["id"]
    assert len(chapters[0]["id"]) == 26


def test_draft_outline_hidden_from_students(client) -> None:
    course_id, _ = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    _parse_and_wait(client, version_id)
    _embed_and_wait(client, version_id)

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/material-versions/{version_id}/outline")
    assert response.status_code == 404


def test_student_cannot_read_non_current_version_outline(client) -> None:
    course_id, _ = _setup_course(client)
    first = _upload(client, course_id, title="已发布教材", content=TWO_CHAPTER_PDF)
    first_version_id = first.json()["data"]["version_id"]
    material_id = first.json()["data"]["material_id"]
    _parse_and_wait(client, first_version_id)
    _embed_and_wait(client, first_version_id)
    client.post(f"/api/v1/material-versions/{first_version_id}/publish")

    async def replace_current_version() -> None:
        async with session_factory() as db:
            old_version = await db.get(MaterialVersion, first_version_id)
            assert old_version is not None
            replacement = MaterialVersion(
                material_id=material_id,
                version_no=2,
                status="parsed",
                object_key="test/replacement.pdf",
                sha256="b" * 64,
                size_bytes=10,
                content_type="application/pdf",
                original_filename="replacement.pdf",
                created_by=old_version.created_by,
                page_count=1,
                quality_report={"issues": []},
            )
            db.add(replacement)
            await db.flush()
            material = await db.get(Material, material_id)
            assert material is not None
            material.current_version_id = replacement.id
            await db.commit()

    asyncio.run(replace_current_version())

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/material-versions/{first_version_id}/outline")
    assert response.status_code == 404


def test_teacher_correction_creates_override_and_new_version(client) -> None:
    course_id, _ = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    _parse_and_wait(client, version_id)

    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    chapter_id = outline.json()["data"][0]["id"]

    wrong_version = client.patch(
        f"/api/v1/knowledge-objects/{chapter_id}",
        json={"version": 99, "reason": "修正标题"},
    )
    assert wrong_version.status_code == 409
    assert wrong_version.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    no_changes = client.patch(
        f"/api/v1/knowledge-objects/{chapter_id}",
        json={"version": 1, "reason": "无字段"},
    )
    assert no_changes.status_code == 422

    corrected = client.patch(
        f"/api/v1/knowledge-objects/{chapter_id}",
        json={
            "version": 1,
            "reason": "解析标题包含英文编号，教师修正为中文",
            "title": "第一章 实验心理学基础",
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["data"]["version"] == 2

    outline_after = client.get(f"/api/v1/material-versions/{version_id}/outline")
    assert outline_after.json()["data"][0]["title"] == "第一章 实验心理学基础"

    stale_publish = client.post(f"/api/v1/material-versions/{version_id}/publish")
    assert stale_publish.status_code == 409
    assert stale_publish.json()["error"]["code"] == "MATERIAL_INDEX_NOT_READY"


def test_quality_gate_blocks_scanned_pdf_publish(client) -> None:
    scanned = make_pdf([[], []])
    course_id, _ = _setup_course(client)
    upload = _upload(
        client, course_id, title="扫描版讲义", content=scanned
    )
    version_id = upload.json()["data"]["version_id"]
    job = _parse_and_wait(client, version_id)
    assert job["status"] == "succeeded"

    publish = client.post(f"/api/v1/material-versions/{version_id}/publish")
    assert publish.status_code == 409
    error = publish.json()["error"]
    assert error["code"] == "QUALITY_GATE_FAILED"
    assert "no_text_extracted" in error["details"]["issues"]

    issues = client.get(f"/api/v1/material-versions/{version_id}/review-issues")
    assert issues.status_code == 200
    blocking = next(
        issue
        for issue in issues.json()["data"]
        if issue["code"] == "no_text_extracted"
    )
    assert blocking["severity"] == "blocking"
    assert blocking["status"] == "open"

    cannot_close = client.patch(
        f"/api/v1/parse-review-issues/{blocking['id']}",
        json={"status": "ignored", "resolution": "直接忽略"},
    )
    assert cannot_close.status_code == 409
    assert (
        cannot_close.json()["error"]["code"]
        == "BLOCKING_ISSUE_REQUIRES_REPARSE"
    )

    _login(client, "ms@uni.edu")
    hidden = client.get(f"/api/v1/material-versions/{version_id}/review-issues")
    assert hidden.status_code == 404


def test_published_outline_visible_to_students(client) -> None:
    course_id, _ = _setup_course(client)
    upload = _upload(
        client, course_id, title="已发布教材", content=TWO_CHAPTER_PDF,
        visibility="draft",
    )
    version_id = upload.json()["data"]["version_id"]
    _parse_and_wait(client, version_id)
    _embed_and_wait(client, version_id)
    publish = client.post(f"/api/v1/material-versions/{version_id}/publish")
    assert publish.status_code == 200

    _login(client, "ms@uni.edu")
    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    assert outline.status_code == 200
    assert len(outline.json()["data"]) == 2
