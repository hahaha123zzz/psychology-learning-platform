import asyncio
import time

from app.db.models import DomainRelease, Job, Material, ParsedPage, PublicationSnapshot
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


def _embed_and_wait(client, version_id: str, *, domain_release_id: str | None = None) -> dict:
    params = {"domain_release_id": domain_release_id} if domain_release_id else None
    response = client.post(f"/api/v1/material-versions/{version_id}/embed", params=params)
    assert response.status_code == 202
    return _wait_job(client, response.json()["data"]["job_id"])


def test_domain_release_is_fixed_across_index_publication_and_course_release(client) -> None:
    course_id, _ = _setup_course(client)
    data = _upload_one(
        client,
        course_id,
        title="领域快照教材",
        content=make_pdf([["Domain release indexing snapshot evidence for testing"]]),
    )
    parse_job_id = _parse(client, data["version_id"]).json()["data"]["job_id"]
    assert _wait_job(client, parse_job_id)["status"] == "succeeded"
    creator_id = client.get("/api/v1/me").json()["data"]["id"]
    domain_pack = {"knowledge_points": [{"key": "kp-a", "title": "注意"}]}

    async def create_published_domain_release() -> str:
        async with session_factory() as db:
            release = DomainRelease(
                course_id=course_id,
                version_no=1,
                manifest={"domain_pack": domain_pack},
                pack_sha256="a" * 64,
                status="published",
                created_by=creator_id,
                published_by=creator_id,
            )
            db.add(release)
            await db.commit()
            return release.id

    domain_release_id = asyncio.run(create_published_domain_release())
    index_job = _embed_and_wait(
        client,
        data["version_id"],
        domain_release_id=domain_release_id,
    )
    assert index_job["status"] == "succeeded", index_job

    published = client.post(
        f"/api/v1/material-versions/{data['version_id']}/publish",
        params={"domain_release_id": domain_release_id},
    )
    assert published.status_code == 200, published.text
    snapshot_id = published.json()["data"]["publication_snapshot_id"]
    assert published.json()["data"]["domain_release_id"] == domain_release_id

    async def assert_snapshot_and_units() -> None:
        from sqlalchemy import select

        from app.db.models import RetrievalUnit

        async with session_factory() as db:
            snapshot = await db.get(PublicationSnapshot, snapshot_id)
            assert snapshot is not None
            assert snapshot.domain_release_id == domain_release_id
            assert snapshot.index_job_id == index_job["job_id"]
            saved_job = await db.get(Job, snapshot.index_job_id)
            assert saved_job is not None
            assert saved_job.payload["material_version_id"] == data["version_id"]
            assert saved_job.payload["domain_release_id"] == domain_release_id
            rows = await db.execute(
                select(RetrievalUnit).where(
                    RetrievalUnit.material_version_id == data["version_id"],
                    RetrievalUnit.domain_release_id == domain_release_id,
                    RetrievalUnit.build_version == f"v1-{index_job['job_id']}",
                    RetrievalUnit.status == "ready",
                )
            )
            assert len(list(rows.scalars())) > 0

    asyncio.run(assert_snapshot_and_units())

    course_release = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "固定领域与教材索引快照",
            "material_ids": [data["material_id"]],
            "domain_release_id": domain_release_id,
        },
    )
    assert course_release.status_code == 201, course_release.text
    release_data = course_release.json()["data"]
    assert release_data["domain_release_id"] == domain_release_id
    assert release_data["manifest"]["domain_pack"] == domain_pack
    gate = client.get(
        f"/api/v1/courses/{course_id}/releases/{release_data['id']}/gate"
    )
    assert gate.status_code == 200, gate.text
    gate_codes = {item["code"] for item in gate.json()["data"]["errors"]}
    assert not gate_codes.intersection(
        {
            "RELEASE_DOMAIN_SNAPSHOT_REQUIRED",
            "RELEASE_DOMAIN_SNAPSHOT_INVALID",
            "RELEASE_DOMAIN_SNAPSHOT_MISMATCH",
            "RELEASE_PUBLICATION_DOMAIN_SNAPSHOT_MISMATCH",
            "RELEASE_DOMAIN_INDEX_JOB_MISMATCH",
            "RELEASE_DOMAIN_RETRIEVAL_SNAPSHOT_MISSING",
        }
    )

    async def corrupt_snapshot_domain_binding() -> None:
        async with session_factory() as db:
            snapshot = await db.get(PublicationSnapshot, snapshot_id)
            assert snapshot is not None
            snapshot.domain_release_id = None
            await db.commit()

    asyncio.run(corrupt_snapshot_domain_binding())
    blocked_gate = client.get(
        f"/api/v1/courses/{course_id}/releases/{release_data['id']}/gate"
    )
    assert blocked_gate.status_code == 200, blocked_gate.text
    blocked_codes = {item["code"] for item in blocked_gate.json()["data"]["errors"]}
    assert "RELEASE_PUBLICATION_DOMAIN_SNAPSHOT_MISMATCH" in blocked_codes


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
    assert job["checkpoint"]["completed_pages"] == 1
    assert job["checkpoint"]["total_pages"] == 1
    assert job["checkpoint"]["object_count"] >= 1

    async def load_page_checkpoint() -> list[ParsedPage]:
        async with session_factory() as db:
            from sqlalchemy import select

            return list(
                (
                    await db.execute(
                        select(ParsedPage).where(
                            ParsedPage.material_version_id == data["version_id"]
                        )
                    )
                ).scalars()
            )

    pages = asyncio.run(load_page_checkpoint())
    assert [(page.physical_page, page.status) for page in pages] == [(1, "completed")]

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
