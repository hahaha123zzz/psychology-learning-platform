import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta

import pymupdf
from sqlalchemy import select

from app.db.base import new_ulid
from app.db.models import (
    DomainRelease,
    EvidenceTicket,
    KnowledgeObject,
    Material,
    MaterialVersion,
    ObjectRelation,
    PublicationSnapshot,
    RetrievalUnit,
)
from app.db.session import session_factory
from app.modules.knowledge.service import _has_hash_keyword_anchor, _search_tokens
from app.modules.materials.service import _clear_parse_outputs
from tests.conftest import create_user_sync, make_pdf
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

ADJACENT_PARAGRAPHS_PDF = make_pdf(
    [
        [
            "Chapter 1 Foundations",
            "Independent variable control improves internal validity in experiments.",
        ],
        ["A control group gives researchers a comparison for the intervention."],
    ]
)


def _make_native_figure_table_pdf() -> tuple[bytes, str]:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 75), "Chapter 1 Experimental Results")
    page.insert_text((72, 385), "The surrounding paragraph explains the measured result.")
    for x in (72, 172, 272):
        page.draw_line((x, 250), (x, 350))
    for y in (250, 300, 350):
        page.draw_line((72, y), (272, y))
    rows = (
        ((82, 280), "Measure"),
        ((182, 280), "Score"),
        ((82, 330), "Recall"),
        ((182, 330), "42"),
    )
    table_text = "Measure | Score\nRecall | 42"
    for point, text in rows:
        page.insert_text(point, text)

    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pixmap.clear_with(255)
    page.insert_image(pymupdf.Rect(72, 135, 172, 235), stream=pixmap.tobytes("png"))
    content = document.tobytes()
    document.close()
    return content, table_text


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


def _prepare(client, *, publish: bool, content: bytes = TWO_CHAPTER_PDF):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=content)
    assert upload.status_code == 201
    version_id = upload.json()["data"]["version_id"]
    job = _parse_and_wait(client, version_id)
    assert job["status"] == "succeeded", job
    job = _parse_and_wait(client, version_id, kind="embed")
    assert job["status"] == "succeeded", job
    if publish:
        published = client.post(f"/api/v1/material-versions/{version_id}/publish")
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
    assert data["retrieval_budget"] == {
        "requested_top_k": 8,
        "plan_top_k": 8,
        "effective_top_k": 8,
    }
    assert len(data["items"]) >= 1
    first = data["items"][0]
    assert "score" in first
    assert first["retrieval_sources"]
    assert first["physical_page"] in (1, 2)
    assert first["text"]
    assert first["source_object_id"]
    assert first["retrieval_unit_id"]
    assert first["object_type"] == "paragraph"


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
    assert items[0]["retrieval_sources"] == ["bm25"]


def test_search_applies_chapter_and_object_type_before_ranking(client) -> None:
    course_id, _, version_id = _prepare(client, publish=False)

    async def load_chapter_id() -> str:
        async with session_factory() as db:
            result = await db.execute(
                select(KnowledgeObject.id).where(
                    KnowledgeObject.material_version_id == version_id,
                    KnowledgeObject.type == "chapter",
                    KnowledgeObject.chapter_path == "2",
                )
            )
            return result.scalar_one()

    chapter_id = asyncio.run(load_chapter_id())
    _login(client, "mt@uni.edu")
    scoped = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "participants conditions",
            "chapter_scope": [chapter_id],
            "object_types": ["paragraph"],
        },
    )
    assert scoped.status_code == 200
    assert scoped.json()["data"]["items"]
    assert all(item["chapter_path"] == "2" for item in scoped.json()["data"]["items"])

    unsupported_type = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "participants conditions",
            "object_types": ["figure"],
        },
    )
    assert unsupported_type.status_code == 200
    assert unsupported_type.json()["data"]["items"] == []


def test_visual_query_reports_text_only_weighted_fusion(client) -> None:
    course_id, _, _ = _prepare(client, publish=False)
    _login(client, "mt@uni.edu")

    response = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "图 1 independent variable validity",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["fusion"] == {
        "strategy": "bm25-keyword-anchor-v1",
        "text_channel_weights": {"sparse": 1.0},
    }
    assert any("visual" in warning and "文本检索" in warning for warning in data["warnings"])


def test_embed_persists_one_retrieval_unit_per_source_object(client) -> None:
    _, _, version_id = _prepare(client, publish=False)

    async def load_units() -> list[RetrievalUnit]:
        async with session_factory() as db:
            return list(
                (
                    await db.execute(
                        select(RetrievalUnit).where(RetrievalUnit.material_version_id == version_id)
                    )
                ).scalars()
            )

    units = asyncio.run(load_units())
    assert units
    assert all(unit.source_object_id for unit in units)
    assert all(unit.unit_type == "text_child" for unit in units)


def test_domain_release_search_uses_only_its_bound_index_job(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]
    release_a_id = new_ulid()
    release_b_id = new_ulid()

    async def create_domain_releases() -> None:
        async with session_factory() as db:
            db.add_all(
                [
                    DomainRelease(
                        id=release_a_id,
                        course_id=course_id,
                        version_no=1,
                        manifest={"domain_pack": {}},
                        pack_sha256="a" * 64,
                        status="published",
                        version=1,
                        created_by=teacher_id,
                        published_by=teacher_id,
                        published_at=datetime.now(UTC),
                    ),
                    DomainRelease(
                        id=release_b_id,
                        course_id=course_id,
                        version_no=2,
                        manifest={"domain_pack": {}},
                        pack_sha256="b" * 64,
                        status="published",
                        version=1,
                        created_by=teacher_id,
                        published_by=teacher_id,
                        published_at=datetime.now(UTC),
                    ),
                ]
            )
            await db.commit()

    asyncio.run(create_domain_releases())
    def build_domain_index(domain_release_id: str) -> str:
        embed = client.post(
            f"/api/v1/material-versions/{version_id}/embed?domain_release_id={domain_release_id}"
        )
        assert embed.status_code == 202, embed.text
        job_id = embed.json()["data"]["job_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            if job["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.3)
        assert job["status"] == "succeeded", job
        return job_id

    index_job_id = build_domain_index(release_a_id)
    unbound_index_job_id = build_domain_index(release_b_id)

    current_snapshot_id: str | None = None
    historical_snapshot_id = new_ulid()

    async def bind_publication_snapshot() -> None:
        nonlocal current_snapshot_id
        async with session_factory() as db:
            snapshot = await db.scalar(
                select(PublicationSnapshot)
                .where(PublicationSnapshot.material_version_id == version_id)
                .order_by(PublicationSnapshot.published_at.desc())
                .limit(1)
            )
            assert snapshot is not None
            snapshot.domain_release_id = release_a_id
            snapshot.index_job_id = index_job_id
            current_snapshot_id = snapshot.id
            historical_published_at = snapshot.published_at - timedelta(days=1)
            db.add(
                PublicationSnapshot(
                    id=historical_snapshot_id,
                    material_id=snapshot.material_id,
                    material_version_id=snapshot.material_version_id,
                    parse_job_id=snapshot.parse_job_id,
                    index_job_id=index_job_id,
                    domain_release_id=release_a_id,
                    embedding_version=snapshot.embedding_version,
                    published_by=snapshot.published_by,
                    published_at=historical_published_at,
                    superseded_at=snapshot.published_at,
                )
            )
            await db.commit()

    asyncio.run(bind_publication_snapshot())
    assert current_snapshot_id is not None

    async def load_bound_units() -> set[str]:
        async with session_factory() as db:
            rows = await db.execute(
                select(RetrievalUnit.id, RetrievalUnit.domain_release_id).where(
                    RetrievalUnit.material_version_id == version_id,
                    RetrievalUnit.domain_release_id.in_([release_a_id, release_b_id]),
                )
            )
            return {unit_id for unit_id, domain_id in rows if domain_id == release_a_id}

    release_a_unit_ids = asyncio.run(load_bound_units())
    assert release_a_unit_ids

    _login(client, "mt@uni.edu")
    search_a = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable validity",
            "domain_release_id": release_a_id,
        },
    )
    assert search_a.status_code == 200, search_a.text
    data_a = search_a.json()["data"]
    assert data_a["domain_release"]["index_job_ids"] == {version_id: index_job_id}
    assert data_a["items"]
    assert {item["retrieval_unit_id"] for item in data_a["items"]} <= release_a_unit_ids
    snapshots_a = data_a["domain_release"]["publication_snapshots"]
    assert len(snapshots_a) == 2
    assert {snapshot["publication_snapshot_id"] for snapshot in snapshots_a} == {
        current_snapshot_id,
        historical_snapshot_id,
    }
    assert all(
        set(snapshot)
        == {
            "material_id",
            "material_version_id",
            "publication_snapshot_id",
            "index_job_id",
            "embedding_version",
            "domain_release_id",
        }
        for snapshot in snapshots_a
    )

    search_b_staff = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable validity",
            "domain_release_id": release_b_id,
        },
    )
    assert search_b_staff.status_code == 200, search_b_staff.text
    data_b_staff = search_b_staff.json()["data"]
    assert data_b_staff["domain_release"]["index_job_ids"] == {
        version_id: unbound_index_job_id
    }
    assert data_b_staff["domain_release"]["publication_snapshots"] == []

    other_course = client.post(
        "/api/v1/courses", json={"title": "另一门课", "term": "2026秋"}
    ).json()["data"]
    other_release_id = new_ulid()

    async def create_other_course_release() -> None:
        async with session_factory() as db:
            db.add(
                DomainRelease(
                    id=other_release_id,
                    course_id=other_course["id"],
                    version_no=1,
                    manifest={"domain_pack": {}},
                    pack_sha256="c" * 64,
                    status="published",
                    version=1,
                    created_by=teacher_id,
                    published_by=teacher_id,
                    published_at=datetime.now(UTC),
                )
            )
            await db.commit()

    asyncio.run(create_other_course_release())
    cross_course_search = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable validity",
            "domain_release_id": other_release_id,
        },
    )
    assert cross_course_search.status_code == 404
    assert cross_course_search.json()["error"]["code"] == "DOMAIN_RELEASE_NOT_FOUND"

    _login(client, "ms@uni.edu")
    student_search_a = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable validity",
            "domain_release_id": release_a_id,
        },
    )
    assert student_search_a.status_code == 200, student_search_a.text
    student_data_a = student_search_a.json()["data"]
    assert student_data_a["domain_release"]["index_job_ids"] == {version_id: index_job_id}
    assert student_data_a["items"]
    assert "score" not in student_data_a["items"][0]
    student_snapshots_a = student_data_a["domain_release"]["publication_snapshots"]
    assert len(student_snapshots_a) == 1
    assert student_snapshots_a[0]["publication_snapshot_id"] == current_snapshot_id

    search_b = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable validity",
            "domain_release_id": release_b_id,
        },
    )
    assert search_b.status_code == 200, search_b.text
    assert search_b.json()["data"]["domain_release"]["index_job_ids"] == {}
    assert search_b.json()["data"]["domain_release"]["publication_snapshots"] == []
    assert search_b.json()["data"]["items"] == []


def test_hash_embedding_rejects_question_without_textbook_keyword_anchor(client) -> None:
    course_id, _, _ = _prepare(client, publish=False)
    _login(client, "mt@uni.edu")

    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "How do I make authentic mapo tofu?"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert "已拒绝" in response.json()["data"]["warnings"][0]


def test_hash_keyword_anchor_requires_two_meaningful_query_terms() -> None:
    tokens = _search_tokens("How do I make authentic mapo tofu?")

    assert tokens == ["authentic", "mapo", "tofu"]
    assert not _has_hash_keyword_anchor("An authentic assessment", tokens)
    assert _has_hash_keyword_anchor("A mapo tofu recipe", tokens)


def test_search_returns_only_approved_adjacent_evidence_closure(client) -> None:
    course_id, _, version_id = _prepare(client, publish=False, content=ADJACENT_PARAGRAPHS_PDF)
    _login(client, "mt@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "independent variable validity"},
    )
    assert response.status_code == 200
    closure = response.json()["data"]["items"][0]["closure"]
    assert closure
    assert closure[0]["object_id"]
    assert closure[0]["relation_type"] == "next"
    assert closure[0]["physical_page"] == 2

    without_neighbors = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "independent variable validity",
            "include_neighbors": False,
        },
    )
    assert without_neighbors.status_code == 200
    assert without_neighbors.json()["data"]["items"][0]["closure"] == []

    async def reject_relation() -> None:
        async with session_factory() as db:
            relation = (
                await db.execute(
                    select(ObjectRelation).where(
                        ObjectRelation.relation_type == "next",
                        ObjectRelation.source_object_id.in_(
                            select(RetrievalUnit.source_object_id).where(
                                RetrievalUnit.material_version_id == version_id
                            )
                        ),
                    )
                )
            ).scalar_one()
            relation.review_status = "rejected"
            await db.commit()

    asyncio.run(reject_relation())
    rejected = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "independent variable validity"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["items"][0]["closure"] == []


def test_native_pdf_table_search_pins_table_and_adjacent_figure(client, monkeypatch) -> None:
    from app.core.embedding import get_embedding_client as get_base_embedding_client
    from app.modules.knowledge import service as knowledge_service

    content, table_text = _make_native_figure_table_pdf()
    base_client = get_base_embedding_client()
    embedded_texts: list[str] = []

    class RecordingEmbeddingClient:
        version = base_client.version

        async def embed(self, texts: list[str]) -> list[list[float]]:
            embedded_texts.extend(texts)
            return await base_client.embed(texts)

    monkeypatch.setattr(
        knowledge_service, "get_embedding_client", lambda: RecordingEmbeddingClient()
    )
    course_id, _, version_id = _prepare(client, publish=True, content=content)

    async def load_table_and_chunks():
        async with session_factory() as db:
            table = await db.scalar(
                select(KnowledgeObject).where(
                    KnowledgeObject.material_version_id == version_id,
                    KnowledgeObject.type == "table",
                )
            )
            assert table is not None
            units = list(
                (
                    await db.execute(
                        select(RetrievalUnit).where(
                            RetrievalUnit.source_object_id == table.id,
                            RetrievalUnit.material_version_id == version_id,
                        )
                    )
                ).scalars()
            )
            return table, units

    table, units = asyncio.run(load_table_and_chunks())
    assert units
    assert all(unit.unit_type == "table_cells" and unit.channel_hint == "sparse" for unit in units)
    assert all(unit.bbox == table.bbox for unit in units)
    assert all(table_text not in embedded for embedded in embedded_texts)

    _login(client, "ms@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "measure score recall",
            "object_types": ["table"],
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()["data"]["items"][0]
    assert item["object_type"] == "table"
    assert item["source_object_id"] == table.id
    assert item["evidence_pointer_id"]
    assert item["physical_page"] == 1
    assert item["bbox"] == table.bbox
    assert item["text"]

    figure_closure = next(
        neighbor
        for neighbor in item["closure"]
        if neighbor["object_type"] == "figure"
    )
    assert figure_closure["relation_type"] in {"previous", "next"}
    assert figure_closure["physical_page"] == 1
    assert figure_closure["evidence_pointer_id"]
    table_pointer = client.get(
        f"/api/v1/evidence-pointers/{item['evidence_pointer_id']}"
    )
    figure_pointer = client.get(
        f"/api/v1/evidence-pointers/{figure_closure['evidence_pointer_id']}"
    )
    assert table_pointer.status_code == 200
    assert figure_pointer.status_code == 200
    assert figure_pointer.json()["data"]["excerpt"] == ""
    assert figure_pointer.json()["data"]["source_object_id"] == figure_closure["object_id"]
    assert figure_pointer.json()["data"]["physical_page"] == 1
    assert figure_pointer.json()["data"]["bbox"] == figure_closure["bbox"]

    figure_page = client.get(
        f"/api/v1/evidence-pointers/{figure_closure['evidence_pointer_id']}/page-image",
        params={"physical_page": 1},
    )
    assert figure_page.status_code == 200
    assert figure_page.headers["x-reader-physical-page"] == "1"
    assert figure_page.content.startswith(b"\x89PNG\r\n\x1a\n")

    _login(client, "mt@uni.edu")
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]
    cross_version_figure_id = new_ulid()
    cross_version_id = new_ulid()

    async def create_cross_version_relation() -> None:
        async with session_factory() as db:
            db.add(
                MaterialVersion(
                    id=cross_version_id,
                    material_id=item["material_id"],
                    version_no=2,
                    status="parsed",
                    object_key="test/other-version.pdf",
                    sha256="f" * 64,
                    size_bytes=100,
                    content_type="application/pdf",
                    original_filename="other-version.pdf",
                    created_by=teacher_id,
                    page_count=1,
                )
            )
            await db.flush()
            db.add(
                KnowledgeObject(
                    id=cross_version_figure_id,
                    material_version_id=cross_version_id,
                    type="figure",
                    chapter_path="1",
                    physical_page=1,
                    reading_order=5,
                    bbox=[72.0, 300.0, 172.0, 400.0],
                    raw_content="",
                    parser="stub-pdf",
                    parser_version="native-layout-v3.3",
                    confidence=0.95,
                    review_status="approved",
                )
            )
            db.add(
                ObjectRelation(
                    source_object_id=table.id,
                    target_object_id=cross_version_figure_id,
                    relation_type="next",
                    source="test:cross-version",
                    confidence=1.0,
                    review_status="approved",
                )
            )
            await db.commit()

    asyncio.run(create_cross_version_relation())
    from app.modules.knowledge.service import _load_evidence_closure

    async def load_cross_version_closure():
        async with session_factory() as db:
            return await _load_evidence_closure(
                db,
                source_object_ids=[table.id],
                version_ids=[version_id, cross_version_id],
            )

    cross_version_closure = asyncio.run(load_cross_version_closure())
    assert cross_version_figure_id not in {
        neighbor["object_id"] for neighbor in cross_version_closure.get(table.id, [])
    }

    cross_version_search = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course_id,
            "query": "measure score recall",
            "object_types": ["table"],
            "material_version_ids": [version_id, cross_version_id],
        },
    )
    assert cross_version_search.status_code == 200, cross_version_search.text
    cross_version_item = cross_version_search.json()["data"]["items"][0]
    assert cross_version_item["source_object_id"] == table.id
    assert cross_version_figure_id not in {
        neighbor["object_id"] for neighbor in cross_version_item["closure"]
    }


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
    assert body["evidence_pointer_id"]
    assert body["coordinate_space"] in {"pdf_user_bottom_left", "unavailable"}

    _login(client, "mt@uni.edu")
    forbidden = client.get(f"/api/v1/evidence/{evidence_id}")
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_evidence_pointer_restores_immutable_reference_after_ticket_expiry(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "participants"},
    )
    assert search.status_code == 200
    item = search.json()["data"]["items"][0]
    pointer_id = item["evidence_pointer_id"]

    async def expire_ticket() -> None:
        async with session_factory() as db:
            ticket = await db.get(EvidenceTicket, item["evidence_id"])
            assert ticket is not None
            ticket.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()

    asyncio.run(expire_ticket())
    expired = client.get(f"/api/v1/evidence/{item['evidence_id']}")
    assert expired.status_code == 404

    restored = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert restored.status_code == 200
    body = restored.json()["data"]
    assert body["evidence_pointer_id"] == pointer_id
    assert body["course_id"] == course_id
    assert body["material_version_id"] == version_id
    assert body["excerpt"] == item["text"]
    assert body["restored"] is True
    assert body["excerpt_sha256"] == hashlib.sha256(item["text"].encode("utf-8")).hexdigest()

    create_user_sync(email="evidence-outsider@uni.edu")
    _login(client, "evidence-outsider@uni.edu")
    forbidden = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert forbidden.status_code == 404


def test_evidence_pointer_keeps_published_historical_version_after_roll_forward(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "participants"},
    )
    pointer_id = search.json()["data"]["items"][0]["evidence_pointer_id"]

    async def publish_new_current_version() -> None:
        async with session_factory() as db:
            previous = await db.get(MaterialVersion, version_id)
            assert previous is not None
            material = await db.get(Material, previous.material_id)
            assert material is not None
            newer = MaterialVersion(
                id=new_ulid(),
                material_id=previous.material_id,
                version_no=previous.version_no + 1,
                status="parsed",
                created_by=previous.created_by,
            )
            db.add(newer)
            await db.flush()
            material.current_version_id = newer.id
            await db.commit()

    asyncio.run(publish_new_current_version())
    restored = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert restored.status_code == 200
    assert restored.json()["data"]["material_version_id"] == version_id


def test_evidence_pointer_survives_reparse_object_cleanup(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "participants"},
    )
    pointer = search.json()["data"]["items"][0]

    async def clear_old_parse() -> None:
        async with session_factory() as db:
            await _clear_parse_outputs(db, version_id)
            await db.commit()
            assert await db.get(KnowledgeObject, pointer["source_object_id"]) is None

    asyncio.run(clear_old_parse())
    restored = client.get(f"/api/v1/evidence-pointers/{pointer['evidence_pointer_id']}")
    assert restored.status_code == 200
    body = restored.json()["data"]
    assert body["source_object_id"] == pointer["source_object_id"]
    assert body["excerpt"] == pointer["text"]


def test_student_evidence_is_revoked_when_material_archived(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "participants"},
    )
    evidence_id = search.json()["data"]["items"][0]["evidence_id"]
    pointer_id = search.json()["data"]["items"][0]["evidence_pointer_id"]

    _login(client, "mt@uni.edu")

    async def archive_material() -> None:
        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None
            material = await db.get(Material, version.material_id)
            assert material is not None
            material.status = "archived"
            await db.commit()

    asyncio.run(archive_material())

    _login(client, "ms@uni.edu")
    revoked = client.get(f"/api/v1/evidence/{evidence_id}")
    assert revoked.status_code == 404
    assert revoked.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"
    revoked_pointer = client.get(f"/api/v1/evidence-pointers/{pointer_id}")
    assert revoked_pointer.status_code == 404
    assert revoked_pointer.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_search_unknown_course_404(client) -> None:
    from tests.conftest import create_user_sync

    create_user_sync(email="ks@uni.edu")
    _login(client, "ks@uni.edu")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "query": "anything"},
    )
    assert response.status_code == 404
