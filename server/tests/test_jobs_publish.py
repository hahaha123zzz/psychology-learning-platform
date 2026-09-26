import asyncio
import time

from app.db.models import Material
from app.db.session import session_factory
from tests.conftest import create_user_sync, make_pdf
from tests.test_materials import _login, _setup_course, _upload


def _parse(client, version_id: str, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"/api/v1/material-versions/{version_id}/parse", headers=headers)


def _wait_job(client, job_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        last = response.json()["data"]
        if last["status"] in ("succeeded", "failed"):
            return last
        time.sleep(0.3)
    raise AssertionError(f"任务未在{timeout}s内完成: {last}")


def _embed_and_wait(client, version_id: str) -> dict:
    response = client.post(f"/api/v1/material-versions/{version_id}/embed")
    assert response.status_code == 202
    return _wait_job(client, response.json()["data"]["job_id"])


def _upload_one(client, course_id: str, **kwargs):
    response = _upload(client, course_id, **kwargs)
    assert response.status_code == 201
    return response.json()["data"]


def test_parse_job_lifecycle_and_version_status(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    response = _parse(client, data["version_id"])
    assert response.status_code == 202
    body = response.json()["data"]
    assert body["status"] == "queued"

    job = _wait_job(client, body["job_id"])
    assert job["status"] == "succeeded"
    assert job["progress"] == 100
    assert job["kind"] == "material_parse"

    listing = client.get(f"/api/v1/courses/{course_id}/materials")
    version = listing.json()["data"][0]["current_version"]
    assert version["status"] == "parsed"


def test_parse_progress_never_regresses_and_stages_ordered(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    job_id = _parse(client, data["version_id"]).json()["data"]["job_id"]
    stages_seen = []
    deadline = time.time() + 20
    previous_progress = -1
    while time.time() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        data = response.json()["data"]
        assert data["progress"] >= previous_progress
        previous_progress = data["progress"]
        if data["stage"] and (not stages_seen or stages_seen[-1] != data["stage"]):
            stages_seen.append(data["stage"])
        if data["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.15)
    assert stages_seen[-1] in ("done", "persist")
    assert "queued" in stages_seen or "download" in stages_seen


def test_parse_idempotent_key_returns_same_job(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    first = _parse(client, data["version_id"], key="parse-key-1")
    replay = _parse(client, data["version_id"], key="parse-key-1")
    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json()["data"]["job_id"] == first.json()["data"]["job_id"]
    _wait_job(client, first.json()["data"]["job_id"])


def test_parse_concurrent_active_job_conflict(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    first = _parse(client, data["version_id"])
    assert first.status_code == 202
    conflict = _parse(client, data["version_id"])
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PARSE_JOB_ALREADY_ACTIVE"
    _wait_job(client, first.json()["data"]["job_id"])


def test_parsed_draft_can_be_reparsed_and_old_index_is_invalidated(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    job_id = _parse(client, data["version_id"]).json()["data"]["job_id"]
    _wait_job(client, job_id)
    assert _embed_and_wait(client, data["version_id"])["status"] == "succeeded"

    again = _parse(client, data["version_id"])
    assert again.status_code == 202
    assert _wait_job(client, again.json()["data"]["job_id"])["status"] == "succeeded"

    publish = client.post(f"/api/v1/material-versions/{data['version_id']}/publish")
    assert publish.status_code == 409
    assert publish.json()["error"]["code"] == "MATERIAL_INDEX_NOT_READY"


def test_student_cannot_trigger_parse_or_view_job(client) -> None:
    course_id, student_id = _setup_course(client)
    data = _upload_one(client, course_id)
    _login(client, "ms@uni.edu")
    response = _parse(client, data["version_id"])
    assert response.status_code == 404
    teacher_client_job = None
    _login(client, "mt@uni.edu")
    teacher_client_job = _parse(client, data["version_id"]).json()["data"]["job_id"]
    _login(client, "ms@uni.edu")
    job_view = client.get(f"/api/v1/jobs/{teacher_client_job}")
    assert job_view.status_code == 404
    _login(client, "mt@uni.edu")
    _wait_job(client, teacher_client_job)


def test_unknown_job_404(client) -> None:
    create_user_sync(email="mj@uni.edu", is_teacher=True)
    _login(client, "mj@uni.edu")
    response = client.get("/api/v1/jobs/01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_publish_requires_parsed_status(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    early = client.post(f"/api/v1/material-versions/{data['version_id']}/publish")
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "MATERIAL_NOT_PARSED"


def test_publish_requires_current_embedding_index(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    parse_job = _parse(client, data["version_id"]).json()["data"]["job_id"]
    assert _wait_job(client, parse_job)["status"] == "succeeded"

    response = client.post(f"/api/v1/material-versions/{data['version_id']}/publish")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MATERIAL_INDEX_NOT_READY"


def test_publish_makes_material_visible_to_students(client) -> None:
    course_id, _ = _setup_course(client)
    _upload_one(
        client,
        course_id,
        title="草稿章节",
        content=make_pdf([["Draft chapter body text for visibility test"]]),
    )
    published = _upload_one(
        client,
        course_id,
        title="已发布章节",
        content=make_pdf([["Published chapter body text for test"]]),
    )

    _login(client, "ms@uni.edu")
    empty = client.get(f"/api/v1/courses/{course_id}/materials")
    assert empty.status_code == 200
    assert empty.json()["data"] == []

    _login(client, "mt@uni.edu")
    job_id = _parse(client, published["version_id"]).json()["data"]["job_id"]
    _wait_job(client, job_id)
    embed_job = _embed_and_wait(client, published["version_id"])
    assert embed_job["status"] == "succeeded", embed_job
    publish = client.post(f"/api/v1/material-versions/{published['version_id']}/publish")
    assert publish.status_code == 200
    body = publish.json()["data"]
    assert body["material_id"] == published["material_id"]
    assert body["published_at"]
    assert body["index_job_id"]
    assert body["publication_snapshot_id"]

    reparse = _parse(client, published["version_id"])
    assert reparse.status_code == 409
    assert reparse.json()["error"]["code"] == "PUBLISHED_VERSION_IMMUTABLE"

    _login(client, "ms@uni.edu")
    student_view = client.get(f"/api/v1/courses/{course_id}/materials")
    items = student_view.json()["data"]
    assert [i["title"] for i in items] == ["已发布章节"]
    assert "visibility" not in items[0]

    _login(client, "mt@uni.edu")
    teacher_view = client.get(f"/api/v1/courses/{course_id}/materials")
    teacher_items = teacher_view.json()["data"]
    assert len(teacher_items) == 2
    assert all("visibility" in item for item in teacher_items)
    published_item = next(i for i in teacher_items if i["id"] == published["material_id"])
    assert published_item["current_version"]["quality_gate_status"] == "approved"
    assert published_item["current_version"]["workflow_state"] == "published"
    assert published_item["current_version"]["published_snapshot_id"]


def test_material_workflow_reaches_ready_then_published(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id, title="工作流教材")

    uploaded = client.get(f"/api/v1/material-versions/{data['version_id']}/workflow")
    assert uploaded.status_code == 200
    assert uploaded.json()["data"]["state"] == "uploaded"
    assert uploaded.json()["data"]["allowed_actions"] == ["start_parse"]

    parse_job = _parse(client, data["version_id"]).json()["data"]["job_id"]
    assert _wait_job(client, parse_job)["status"] == "succeeded"
    parsed = client.get(f"/api/v1/material-versions/{data['version_id']}/workflow").json()["data"]
    assert parsed["state"] == "index_required"
    assert "build_index" in parsed["allowed_actions"]

    assert _embed_and_wait(client, data["version_id"])["status"] == "succeeded"
    ready = client.get(f"/api/v1/material-versions/{data['version_id']}/workflow").json()["data"]
    assert ready["state"] == "ready_to_publish"
    assert ready["allowed_actions"] == ["publish"]

    published = client.post(f"/api/v1/material-versions/{data['version_id']}/publish")
    assert published.status_code == 200
    first_snapshot = published.json()["data"]["publication_snapshot_id"]

    replay = client.post(f"/api/v1/material-versions/{data['version_id']}/publish")
    assert replay.status_code == 200
    assert replay.json()["data"]["publication_snapshot_id"] == first_snapshot

    workflow = client.get(f"/api/v1/material-versions/{data['version_id']}/workflow").json()["data"]
    assert workflow["state"] == "published"
    assert workflow["publication"]["id"] == first_snapshot


def test_material_jobs_are_course_scoped_and_hidden_from_students(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id, title="任务中心教材")
    job_id = _parse(client, data["version_id"]).json()["data"]["job_id"]
    _wait_job(client, job_id)

    jobs = client.get(f"/api/v1/courses/{course_id}/material-jobs")
    assert jobs.status_code == 200
    item = next(job for job in jobs.json()["data"] if job["job_id"] == job_id)
    assert item["material_title"] == "任务中心教材"
    assert item["material_version_id"] == data["version_id"]

    _login(client, "ms@uni.edu")
    denied = client.get(f"/api/v1/courses/{course_id}/material-jobs")
    assert denied.status_code == 404


def test_student_listing_requires_current_version_to_be_parsed(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id, title="未解析但错误标记可见")

    async def mark_published() -> None:
        async with session_factory() as db:
            material = await db.get(Material, data["material_id"])
            assert material is not None
            material.visibility = "published"
            await db.commit()

    asyncio.run(mark_published())

    _login(client, "ms@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}/materials")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_archive_hides_material_from_students(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id, title="将被归档")
    _login(client, "mt@uni.edu")
    job_id = _parse(client, data["version_id"]).json()["data"]["job_id"]
    _wait_job(client, job_id)
    _embed_and_wait(client, data["version_id"])
    client.post(f"/api/v1/material-versions/{data['version_id']}/publish")

    archived = client.delete(f"/api/v1/materials/{data['material_id']}")
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"

    duplicate_archive = client.delete(f"/api/v1/materials/{data['material_id']}")
    assert duplicate_archive.status_code == 409
    assert duplicate_archive.json()["error"]["code"] == "MATERIAL_ALREADY_ARCHIVED"

    _login(client, "ms@uni.edu")
    student_view = client.get(f"/api/v1/courses/{course_id}/materials")
    assert student_view.json()["data"] == []

    _login(client, "mt@uni.edu")
    republish = client.post(f"/api/v1/material-versions/{data['version_id']}/publish")
    assert republish.status_code == 409
    assert republish.json()["error"]["code"] == "MATERIAL_ARCHIVED"


def test_student_cannot_archive_material(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(client, course_id)
    _login(client, "ms@uni.edu")
    response = client.delete(f"/api/v1/materials/{data['material_id']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"
