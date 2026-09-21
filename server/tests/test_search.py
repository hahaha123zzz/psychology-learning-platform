import asyncio
import time

from app.db.models import Material, MaterialVersion
from app.db.session import session_factory
from tests.conftest import make_pdf
from tests.test_materials import _login, _setup_course, _upload

TWO_CHAPTER_PDF = make_pdf(
    [
        [
            "Chapter 1 Foundations",
            "Independent variable control improves internal validity in experiments.",
        ],
        [
            "Chapter 2 Design",
            "Between subjects design assigns different participants to conditions.",
        ],
    ]
)


def _parse_and_wait(client, version_id: str, kind: str = "parse", timeout=20.0):
    if kind == "parse":
        response = client.post(f"/api/v1/material-versions/{version_id}/parse")
    else:
        response = client.post(f"/api/v1/material-versions/{version_id}/embed")
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.3)
    raise AssertionError("任务超时")


def _prepare(client, *, publish: bool):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    assert upload.status_code == 201
    version_id = upload.json()["data"]["version_id"]
    job = _parse_and_wait(client, version_id)
    assert job["status"] == "succeeded", job
    job = _parse_and_wait(client, version_id, kind="embed")
    assert job["status"] == "succeeded", job
    if publish:
        published = client.post(
            f"/api/v1/material-versions/{version_id}/publish"
        )
        assert published.status_code == 200
    return course_id, student_id, version_id


def test_embed_requires_parsed_and_is_idempotent(client) -> None:
    course_id, _, version_id = _prepare(client, publish=False)
    embed_again = client.post(
        f"/api/v1/material-versions/{version_id}/embed",
        headers={"Idempotency-Key": "embed-key-1"},
    )
    assert embed_again.status_code == 202
    first_job = embed_again.json()["data"]["job_id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{first_job}").json()["data"]
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.3)
    replay = client.post(
        f"/api/v1/material-versions/{version_id}/embed",
        headers={"Idempotency-Key": "embed-key-1"},
    )
    assert replay.status_code == 202
    assert replay.json()["data"]["job_id"] == first_job


def test_teacher_search_returns_evidence_with_scores(client) -> None:
    course_id, _, _ = _prepare(client, publish=False)
    _login(client, "mt@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "independent variable validity"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["retrieval_version"]
    assert len(data["items"]) >= 1
    first = data["items"][0]
    assert "score" in first
    assert first["retrieval_sources"]
    assert first["physical_page"] in (1, 2)
    assert first["text"]


def test_student_search_filtered_until_published(client) -> None:
    course_id, _, _ = _prepare(client, publish=False)
    _login(client, "ms@uni.edu")
    empty = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "variable"},
    )
    assert empty.status_code == 200
    assert empty.json()["data"]["items"] == []
    assert "score" not in (empty.json()["data"]["items"] or [{}])[0]


def test_student_search_after_publish_has_no_score(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "participants conditions"},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    assert "score" not in items[0]
    assert items[0]["evidence_id"]


def test_student_search_cannot_request_non_current_published_version(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)

    async def replace_current_version() -> None:
        async with session_factory() as db:
            old_version = await db.get(MaterialVersion, version_id)
            assert old_version is not None
            replacement = MaterialVersion(
                material_id=old_version.material_id,
                version_no=2,
                status="parsed",
                object_key="test/current.pdf",
                sha256="c" * 64,
                size_bytes=10,
                content_type="application/pdf",
                original_filename="current.pdf",
                created_by=old_version.created_by,
                page_count=1,
                quality_report={"issues": []},
            )
            db.add(replacement)
            await db.flush()
            material = await db.get(Material, old_version.material_id)
            assert material is not None
            material.current_version_id = replacement.id
            await db.commit()

    asyncio.run(replace_current_version())

    _login(client, "ms@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable",
            "material_version_ids": [version_id],
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_evidence_ticket_binds_to_owner(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "participants"},
    )
    evidence_id = search.json()["data"]["items"][0]["evidence_id"]

    detail = client.get(f"/api/v1/evidence/{evidence_id}")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["text"]
    assert body["material_title"]
    assert body["expires_at"]

    _login(client, "mt@uni.edu")
    forbidden = client.get(f"/api/v1/evidence/{evidence_id}")
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_search_unknown_course_404(client) -> None:
    from tests.conftest import create_user_sync

    create_user_sync(email="ks@uni.edu")
    _login(client, "ks@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "query": "anything"},
    )
    assert response.status_code == 404
