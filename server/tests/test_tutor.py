import json

from tests.test_materials import _login, _setup_course, _upload
from tests.test_search import TWO_CHAPTER_PDF


def _prepare(client, *, publish=True, content=TWO_CHAPTER_PDF):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=content)
    version_id = upload.json()["data"]["version_id"]
    for kind in ("parse", "embed"):
        response = client.post(f"/api/v1/material-versions/{version_id}/{kind}")
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        import time

        deadline = time.time() + 20
        while time.time() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            if job["status"] in ("succeeded", "failed"):
                assert job["status"] == "succeeded", job
                break
            time.sleep(0.3)
    if publish:
        assert (
            client.post(f"/api/v1/material-versions/{version_id}/publish").status_code
            == 200
        )
    return course_id, student_id, version_id


def _seed_pinned_table_chat(client, *, course_id: str, student_id: str, version_id: str):
    import asyncio
    import hashlib
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.base import new_ulid
    from app.db.models import (
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
        EvidencePointer,
        KnowledgeObject,
        MaterialVersion,
        PublicationSnapshot,
        RetrievalUnit,
    )
    from app.db.session import session_factory
    from app.modules.knowledge import service as knowledge_service

    teacher = client.get("/api/v1/me").json()["data"]
    teacher_id = teacher["id"]

    async def seed() -> tuple[str, str, str, str]:
        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None
            snapshot = await db.scalar(
                select(PublicationSnapshot).where(
                    PublicationSnapshot.material_version_id == version_id
                )
            )
            assert snapshot is not None
            pin = {
                "material_id": version.material_id,
                "material_version_id": version_id,
                "publication_snapshot_id": snapshot.id,
                "index_job_id": snapshot.index_job_id,
                "embedding_version": snapshot.embedding_version,
                "domain_release_id": snapshot.domain_release_id,
            }
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="合成 Table Tutor Release",
                status="published",
                manifest={
                    "materials": [version.material_id],
                    "material_version_ids": [version_id],
                    "publication_snapshots": [pin],
                },
                domain_release_id=snapshot.domain_release_id,
                created_by=teacher_id,
                published_by=teacher_id,
                published_at=datetime.now(UTC),
            )
            course_class = CourseClass(
                course_id=course_id,
                code=f"TBL-{new_ulid()[:10]}",
                name="合成 Table Tutor 班级",
                created_by=teacher_id,
            )
            db.add_all([release, course_class])
            await db.flush()
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=course_class.id,
                course_release_id=release.id,
                status="active",
                assigned_by=teacher_id,
            )
            db.add_all([assignment, ClassMember(class_id=course_class.id, user_id=student_id)])
            pointers = []
            objects = []
            retrieval_units = []
            for index in (1, 2):
                excerpt = f"合成组别{index} | 均值\n实验组 | {index + 3}"
                object_id = new_ulid()
                unit = RetrievalUnit(
                    id=new_ulid(),
                    material_version_id=version_id,
                    domain_release_id=snapshot.domain_release_id,
                    source_object_id=object_id,
                    parent_object_id=None,
                    unit_type="table_cells",
                    channel_hint="sparse",
                    char_start=0,
                    char_end=len(excerpt),
                    bbox=[10, 10, 100, 100],
                    text_content=excerpt,
                    content_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
                    build_strategy=knowledge_service.TABLE_RETRIEVAL_UNIT_BUILD_STRATEGY,
                    build_version=(
                        f"{knowledge_service.RETRIEVAL_UNIT_BUILD_VERSION}-{snapshot.index_job_id}"
                    ),
                    status="ready",
                )
                objects.append(
                    KnowledgeObject(
                        id=object_id,
                        material_version_id=version_id,
                        type="table",
                        title=f"合成表格 {index}",
                        chapter_path="合成章节",
                        reading_order=index,
                        physical_page=1,
                        bbox=[10, 10, 100, 100],
                        raw_content=excerpt,
                        normalized_content=excerpt,
                        parser="stub-pdf",
                        parser_version="test",
                    )
                )
                retrieval_units.append(unit)
                pointers.append(EvidencePointer(
                    course_id=course_id,
                    material_id=version.material_id,
                    material_version_id=version_id,
                    source_object_id=object_id,
                    retrieval_unit_id=unit.id,
                    material_title="合成心理学教材",
                    excerpt=excerpt,
                    excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
                    chapter_path="合成章节",
                    physical_page=1,
                    reading_order=index,
                    object_type="table",
                    coordinate_space="pdf_user_bottom_left",
                    bbox=[10, 10, 100, 100],
                    anchors=[
                        {
                            "physical_page": 1,
                            "bbox": [10, 10, 100, 100],
                            "coordinate_space": "pdf_user_bottom_left",
                        }
                    ],
                ))
            figure_object_id = new_ulid()
            objects.append(
                KnowledgeObject(
                    id=figure_object_id,
                    material_version_id=version_id,
                    type="figure",
                    title="合成图像",
                    chapter_path="合成章节",
                    reading_order=3,
                    physical_page=1,
                    bbox=[110, 10, 200, 100],
                    raw_content="",
                    parser="stub-pdf",
                    parser_version="test",
                )
            )
            figure = EvidencePointer(
                course_id=course_id,
                material_id=version.material_id,
                material_version_id=version_id,
                source_object_id=figure_object_id,
                retrieval_unit_id=None,
                material_title="合成心理学教材",
                excerpt="",
                excerpt_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                chapter_path="合成章节",
                physical_page=1,
                reading_order=3,
                object_type="figure",
                coordinate_space="pdf_user_bottom_left",
                bbox=[110, 10, 200, 100],
                anchors=[
                    {
                        "physical_page": 1,
                        "bbox": [110, 10, 200, 100],
                        "coordinate_space": "pdf_user_bottom_left",
                    }
                ],
            )
            db.add_all([*objects, *retrieval_units, *pointers, figure])
            await db.commit()
            return assignment.id, pointers[0].id, pointers[1].id, figure.id

    return asyncio.run(seed())


def _seed_pinned_paragraph_chat(client, *, course_id: str, student_id: str, version_id: str):
    """从合成发布快照构造一个带完整版本 pin 的段落选择指针。"""
    import asyncio
    import hashlib

    from sqlalchemy import func, select

    from app.db.models import (
        CourseRelease,
        CourseReleaseAssignment,
        DomainRelease,
        EvidencePointer,
        Job,
        KnowledgeObject,
        MaterialVersion,
        PublicationSnapshot,
        RetrievalUnit,
    )
    from app.db.session import session_factory
    from app.modules.knowledge import service as knowledge_service

    assignment_id, pointer_id, other_pointer_id, figure_pointer_id = _seed_pinned_table_chat(
        client, course_id=course_id, student_id=student_id, version_id=version_id
    )
    excerpt = (
        "操作性定义是把抽象概念转化为可观察、可测量的操作步骤。"
        "例如，研究记忆保持时可以规定材料呈现、延迟时间和测量方式。"
    )
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def pin_paragraph() -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            source = await db.get(KnowledgeObject, pointer.source_object_id)
            unit = await db.get(RetrievalUnit, pointer.retrieval_unit_id)
            version = await db.get(MaterialVersion, version_id)
            assert source is not None and unit is not None and version is not None
            snapshot = await db.scalar(
                select(PublicationSnapshot).where(
                    PublicationSnapshot.material_version_id == version_id
                )
            )
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert snapshot is not None and assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            job = await db.get(Job, snapshot.index_job_id)
            assert job is not None
            version_no = await db.scalar(
                select(func.coalesce(func.max(DomainRelease.version_no), 0) + 1).where(
                    DomainRelease.course_id == course_id
                )
            )
            domain_release = DomainRelease(
                course_id=course_id,
                version_no=version_no,
                manifest={
                    "knowledge_points": [],
                    "misconceptions": [],
                    "evidence_bindings": [],
                },
                pack_sha256="b" * 64,
                status="published",
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(domain_release)
            await db.flush()
            snapshot.domain_release_id = domain_release.id
            unit.domain_release_id = domain_release.id
            job.payload = {
                **(job.payload if isinstance(job.payload, dict) else {}),
                "domain_release_id": domain_release.id,
            }
            release.domain_release_id = domain_release.id
            manifest = dict(release.manifest)
            pins = [dict(item) for item in manifest["publication_snapshots"]]
            pins[0]["domain_release_id"] = domain_release.id
            manifest["publication_snapshots"] = pins
            release.manifest = manifest

            source.type = "paragraph"
            source.raw_content = excerpt
            source.normalized_content = excerpt
            unit.unit_type = "text_child"
            unit.build_strategy = knowledge_service.RETRIEVAL_UNIT_BUILD_STRATEGY
            unit.text_content = excerpt
            unit.content_hash = hashlib.sha256(excerpt.encode()).hexdigest()
            pointer.object_type = "paragraph"
            pointer.excerpt = excerpt
            pointer.excerpt_sha256 = hashlib.sha256(excerpt.encode()).hexdigest()
            pointer.publication_snapshot_id = snapshot.id
            pointer.index_job_id = snapshot.index_job_id
            pointer.domain_release_id = domain_release.id
            await db.commit()

    asyncio.run(pin_paragraph())
    return assignment_id, pointer_id, other_pointer_id, figure_pointer_id, excerpt


def test_paragraph_pointer_pin_requires_three_exact_values() -> None:
    from app.modules.tutor.service import _paragraph_pointer_pin_matches_exact_release

    expected = ("snapshot-id", "index-job-id", "domain-release-id")
    assert _paragraph_pointer_pin_matches_exact_release(expected, expected)
    assert not _paragraph_pointer_pin_matches_exact_release((None, None, None), expected)
    assert not _paragraph_pointer_pin_matches_exact_release(
        ("snapshot-id", "index-job-id", None), expected
    )
    assert not _paragraph_pointer_pin_matches_exact_release(
        ("other-snapshot", "index-job-id", "domain-release-id"), expected
    )


def _parse_sse_events(line_bytes: bytes) -> list[tuple[str, dict]]:
    events = []
    for block in line_bytes.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_name and data is not None:
            events.append((event_name, data))
    return events


def test_tutor_citation_labels_omit_unavailable_physical_page() -> None:
    from app.modules.materials.parsers.stub_pdf import StubPdfParser
    from app.modules.tutor.service import _citation_label

    assert _citation_label(1, "DOCX 段落", None) == "[1] DOCX 段落"
    parsed_pdf = StubPdfParser().parse(TWO_CHAPTER_PDF, "application/pdf")
    pdf_paragraph = next(item for item in parsed_pdf.objects if item.type == "paragraph")
    assert pdf_paragraph.physical_page == 1
    assert _citation_label(2, "PDF 段落", pdf_paragraph.physical_page) == "[2] PDF 段落 第1页"


def test_saved_citation_material_type_values_and_legacy_fallback_without_database() -> None:
    from app.modules.tutor.router import ChatTurnRead, _serialize_citation

    allowed = ("textbook", "slides", "handout", "exercise", "reference", "other")
    for material_type in allowed:
        citation = _serialize_citation(
            {"evidence_pointer_id": "synthetic", "material_type": material_type}
        )
        assert citation["material_type"] == material_type
    assert _serialize_citation({"evidence_pointer_id": "legacy"})["material_type"] is None
    assert _serialize_citation({"material_type": "untrusted-category"})["material_type"] is None
    assert _serialize_citation({"material_type": ["slides"]})["material_type"] is None
    assert _serialize_citation("legacy-scalar") == "legacy-scalar"
    safe = _serialize_citation(
        {
            "evidence_pointer_id": "synthetic-pointer",
            "provenance": {"review_note": "must not leak"},
            "provenance_reviewed_by": "reviewer-id",
            "provenance_submitted_by": "submitter-id",
            "review_note": "must not leak",
        },
        {
            "source_title": "Synthetic source",
            "publisher": None,
            "content_author": None,
            "edition": None,
            "source_url": None,
            "license": None,
            "course_resource_role": None,
            "status": "rejected",
            "version": 2,
        },
    )
    assert safe["provenance"]["source_title"] == "Synthetic source"
    assert safe["provenance"]["status"] == "rejected"
    assert safe["provenance"]["version"] == 2
    assert not {"review_note", "provenance_reviewed_by", "provenance_submitted_by"} & safe.keys()
    assert _serialize_citation(
        {"evidence_pointer_id": "legacy-pointer", "provenance": {"source_title": "stale"}}
    )["provenance"] is None
    legacy_turn = ChatTurnRead(
        id="legacy-turn",
        role="tutor",
        content="legacy response",
        citations=None,
        verification=None,
        refusal=False,
        created_at="2026-10-06T00:00:00+00:00",
    )
    assert legacy_turn.citations is None


def test_tutor_sse_replay_keeps_material_type_and_uses_neutral_legacy_fallback() -> None:
    import asyncio
    import json
    from types import SimpleNamespace

    from app.modules.tutor.router import _replay_saved_turn

    async def citation_events(turn) -> list[dict]:
        result = []
        async for frame in _replay_saved_turn(turn):
            for block in frame.split("\n\n"):
                if not block.startswith("event: citation\n"):
                    continue
                data_line = next(line for line in block.splitlines() if line.startswith("data: "))
                result.append(json.loads(data_line.removeprefix("data: ")))
        return result

    base_turn = {
        "id": "synthetic-turn",
        "finish_reason": "stop",
        "content": "Synthetic saved answer",
        "verification": {},
        "refusal": False,
    }
    supplemental = SimpleNamespace(
        **base_turn,
        citations=[
            {
                "evidence_pointer_id": "synthetic-pointer",
                "material_type": "slides",
                "label": "[1] Synthetic title",
            }
        ],
    )
    legacy = SimpleNamespace(
        **base_turn,
        citations=[
            {
                "evidence_pointer_id": "legacy-pointer",
            }
        ],
    )
    assert asyncio.run(citation_events(supplemental)) == [
        {
            "evidence_id": None,
            "evidence_pointer_id": "synthetic-pointer",
            "material_type": "slides",
            "provenance": None,
            "label": "[1] Synthetic title",
        }
    ]
    assert asyncio.run(citation_events(legacy)) == [
        {
            "evidence_id": None,
            "evidence_pointer_id": "legacy-pointer",
            "material_type": None,
            "provenance": None,
            "label": "引用",
        }
    ]


def test_citation_provenance_requires_exact_pointer_scope_and_version_without_database(
    monkeypatch,
) -> None:
    import asyncio
    from types import SimpleNamespace

    from app.core.errors import ApiError
    from app.modules.knowledge import service as knowledge_service
    from app.modules.tutor import service as tutor_service
    from app.modules.tutor.router import _citation_provenance

    pointer = SimpleNamespace(
        id="p" * 26,
        course_id="c" * 26,
        material_id="m" * 26,
        material_version_id="v" * 26,
        publication_snapshot_id=None,
        index_job_id=None,
        domain_release_id=None,
    )
    session_row = SimpleNamespace(
        course_id=pointer.course_id,
        course_release_assignment_id=None,
        course_release_id=None,
    )

    class FakeDB:
        scalar_calls = 0

        async def get(self, model, requested_id):
            from app.db.models import EvidencePointer, PublicationSnapshot

            if model is EvidencePointer:
                assert requested_id == pointer.id
                return pointer
            if model is PublicationSnapshot:
                assert requested_id == "s" * 26
                return SimpleNamespace(
                    material_id=pointer.material_id,
                    material_version_id=pointer.material_version_id,
                    index_job_id="i" * 26,
                    embedding_version="synthetic-embedding",
                    domain_release_id=None,
                )
            raise AssertionError(f"unexpected model: {model}")

        async def scalar(self, statement):
            self.scalar_calls += 1
            return SimpleNamespace(
                source_title="Exact synthetic version",
                publisher=None,
                content_author=None,
                edition=None,
                source_url=None,
                license=None,
                course_resource_role=None,
                provenance_status="verified",
                provenance_version=2,
            )

    read_count = 0
    project_count = 0

    async def readable_pointer(db, candidate):
        nonlocal read_count
        assert candidate is pointer
        read_count += 1

    async def projected_provenance(db, **kwargs):
        nonlocal project_count
        project_count += 1
        assert kwargs == {
            "material_id": pointer.material_id,
            "material_version_id": pointer.material_version_id,
            "course_id": pointer.course_id,
        }
        return {"source_title": "Exact synthetic version", "status": "verified", "version": 2}

    monkeypatch.setattr(knowledge_service, "require_student_pointer_read_access", readable_pointer)
    monkeypatch.setattr(knowledge_service, "project_pointer_provenance", projected_provenance)

    async def verify():
        db = FakeDB()
        mismatched_version = await _citation_provenance(
            db,
            pointer_id=pointer.id,
            session_row=session_row,
            user_id="u" * 26,
            material_id=pointer.material_id,
            material_version_id="x" * 26,
        )
        assert mismatched_version is None
        assert db.scalar_calls == 0
        wrong_course = await _citation_provenance(
            db,
            pointer_id=pointer.id,
            session_row=SimpleNamespace(
                course_id="z" * 26,
                course_release_assignment_id=None,
                course_release_id=None,
            ),
            user_id="u" * 26,
        )
        assert wrong_course is None
        assert db.scalar_calls == 0
        exact = await _citation_provenance(
            db,
            pointer_id=pointer.id,
            session_row=session_row,
            user_id="u" * 26,
            material_id=pointer.material_id,
            material_version_id=pointer.material_version_id,
        )
        assert exact["source_title"] == "Exact synthetic version"
        assert exact["status"] == "verified"
        assert exact["version"] == 2
        assert read_count == 1
        assert project_count == 1

        release_pin = {
            "material_id": pointer.material_id,
            "material_version_id": pointer.material_version_id,
            "publication_snapshot_id": "s" * 26,
            "index_job_id": "i" * 26,
            "embedding_version": "synthetic-embedding",
            "domain_release_id": None,
        }
        binding = SimpleNamespace(
            domain_release_id=None,
            manifest={
                "materials": [pointer.material_id],
                "material_version_ids": [pointer.material_version_id],
                "publication_snapshots": [release_pin],
            },
        )
        bound_session = SimpleNamespace(
            course_id=pointer.course_id,
            course_release_assignment_id="a" * 26,
            course_release_id="r" * 26,
        )

        async def current_release_binding(db, *, session_row, user_id):
            if session_row is not bound_session:
                return None
            assert session_row is bound_session
            assert user_id == "u" * 26
            return binding

        monkeypatch.setattr(
            tutor_service, "authorize_chat_session_release_scope", current_release_binding
        )
        null_domain_exact_pin = await _citation_provenance(
            db,
            pointer_id=pointer.id,
            session_row=bound_session,
            user_id="u" * 26,
            material_id=pointer.material_id,
            material_version_id=pointer.material_version_id,
        )
        assert null_domain_exact_pin["source_title"] == "Exact synthetic version"

        binding.domain_release_id = "d" * 26
        assert await _citation_provenance(
            db,
            pointer_id=pointer.id,
            session_row=bound_session,
            user_id="u" * 26,
            material_id=pointer.material_id,
            material_version_id=pointer.material_version_id,
        ) is None

        async def unreadable_pointer(db, candidate):
            raise ApiError(404, "EVIDENCE_NOT_FOUND", "synthetic revocation")

        monkeypatch.setattr(
            knowledge_service, "require_student_pointer_read_access", unreadable_pointer
        )
        revoked = await _citation_provenance(
            db,
            pointer_id=pointer.id,
            session_row=session_row,
            user_id="u" * 26,
            material_id=pointer.material_id,
            material_version_id=pointer.material_version_id,
        )
        assert revoked is None
        assert project_count == 2
        legacy = await _citation_provenance(
            db, pointer_id=None, session_row=session_row, user_id="u" * 26
        )
        assert legacy is None

    asyncio.run(verify())


def test_material_type_is_in_search_reader_and_saved_chat_openapi_without_database() -> None:
    from app.main import app

    schema = app.openapi()
    values = ["textbook", "slides", "handout", "exercise", "reference", "other"]
    search_item = schema["components"]["schemas"]["SearchResultRead"]
    pointer = schema["components"]["schemas"]["EvidencePointerRead"]
    citation = schema["components"]["schemas"]["ChatCitationRead"]
    assert search_item["properties"]["material_type"]["enum"] == values
    assert pointer["properties"]["material_type"]["enum"] == values
    assert citation["properties"]["material_type"]["anyOf"][0]["enum"] == values
    provenance = schema["components"]["schemas"]["MaterialProvenancePointerRead"]
    expected = {
        "source_title",
        "publisher",
        "content_author",
        "edition",
        "source_url",
        "license",
        "course_resource_role",
        "status",
        "version",
    }
    assert set(provenance["properties"]) == expected
    assert "provenance" in pointer["properties"]
    assert "provenance" in citation["properties"]
    assert not {"submitted_by", "reviewed_by", "reviewed_at", "review_note"} & set(
        provenance["properties"]
    )


def test_chat_session_creation_validates_mode_context(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    tutor_without_chapter = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "tutor"},
    )
    assert tutor_without_chapter.status_code == 422
    qa = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa", "title": "答疑"},
    )
    assert qa.status_code == 201
    assert qa.json()["data"]["mode"] == "course_qa"


def test_student_chat_session_pins_release_and_refuses_missing_snapshot_after_rotation(
    client,
) -> None:
    import asyncio
    from datetime import UTC, datetime

    from app.db.models import (
        ChatSession,
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
        DomainRelease,
        MaterialVersion,
    )
    from app.db.session import session_factory

    course_id, student_id, version_id = _prepare(client, publish=True)
    teacher = client.get("/api/v1/me").json()["data"]
    teacher_id = teacher["id"]

    async def seed_release() -> tuple[str, str, str, str]:
        async with session_factory() as db:
            material_version = await db.get(MaterialVersion, version_id)
            assert material_version is not None
            course_class = CourseClass(
                course_id=course_id,
                code="R3B-CHAT",
                name="Tutor 固定版本班",
                created_by=teacher_id,
            )
            db.add(course_class)
            await db.flush()
            db.add(ClassMember(class_id=course_class.id, user_id=student_id))
            domain_release = DomainRelease(
                course_id=course_id,
                version_no=1,
                manifest={"knowledge_points": [], "misconceptions": [], "evidence_bindings": []},
                pack_sha256="a" * 64,
                status="published",
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(domain_release)
            await db.flush()
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="Tutor bound release",
                status="published",
                manifest={
                    "materials": [material_version.material_id],
                    "material_version_ids": [version_id],
                    "publication_snapshots": [
                        {
                            "material_id": material_version.material_id,
                            "material_version_id": version_id,
                            "publication_snapshot_id": "01ARZ3NDEKTSV4RRFFQ69G5FAZ",
                            "index_job_id": "01ARZ3NDEKTSV4RRFFQ69G5FAY",
                            "embedding_version": "hash-v1",
                            "domain_release_id": domain_release.id,
                        }
                    ],
                },
                domain_release_id=domain_release.id,
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(release)
            await db.flush()
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=course_class.id,
                course_release_id=release.id,
                status="active",
                assigned_by=teacher_id,
            )
            db.add(assignment)
            await db.commit()
            return course_class.id, assignment.id, release.id, domain_release.id

    class_id, assignment_id, release_id, domain_release_id = asyncio.run(seed_release())
    _login(client, "ms@uni.edu")
    created = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert created.status_code == 201
    session_id = created.json()["data"]["id"]

    async def rotate_assignment() -> None:
        async with session_factory() as db:
            previous = await db.get(CourseReleaseAssignment, assignment_id)
            old_release = await db.get(CourseRelease, release_id)
            assert previous is not None and old_release is not None
            previous.status = "closed"
            previous.closed_at = datetime.now(UTC)
            previous.close_reason = "R3-B ChatSession pin test"
            old_release.status = "deprecated"
            replacement = CourseRelease(
                course_id=course_id,
                version_no=2,
                name="Replacement chat release",
                status="published",
                manifest={
                    "materials": old_release.manifest["materials"],
                    "material_version_ids": [version_id],
                },
                domain_release_id=domain_release_id,
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(replacement)
            await db.flush()
            db.add(
                CourseReleaseAssignment(
                    course_id=course_id,
                    class_id=class_id,
                    course_release_id=replacement.id,
                    status="active",
                    assigned_by=teacher_id,
                    supersedes_id=assignment_id,
                )
            )
            await db.commit()

    asyncio.run(rotate_assignment())
    turn = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json={"content": "请解释课程内容", "client_turn_id": "r3b-chat-pin-0001"},
    )
    assert turn.status_code == 200
    events = _parse_sse_events(turn.content)
    done = next(data for name, data in events if name == "done")
    assert done["saved"] is True

    saved = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert saved.status_code == 200
    tutor_turn = saved.json()["data"]["turns"][-1]
    claim = tutor_turn["verification"]["domain_claim"]
    assert claim["status"] == "unknown"
    assert claim["refusal_reason"] == "publication_snapshot_unavailable"
    assert claim["scope"]["class_id"] == class_id
    assert claim["scope"]["course_release_assignment_id"] == assignment_id
    assert claim["scope"]["course_release_id"] == release_id
    assert claim["scope"]["domain_release_id"] == domain_release_id
    assert claim["scope"]["publication_snapshots"] == []
    assert claim["supplemental_retrieval_attempts"] == 0
    assert tutor_turn["refusal"] is True

    async def assert_session_binding() -> tuple[str | None, str | None]:
        async with session_factory() as db:
            session_row = await db.get(ChatSession, session_id)
            return (
                session_row.course_release_assignment_id,
                session_row.course_release_id,
            )

    assert asyncio.run(assert_session_binding()) == (assignment_id, release_id)
    replay = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json={"content": "请解释课程内容", "client_turn_id": "r3b-chat-pin-0001"},
    )
    assert replay.status_code == 200
    assert any(data.get("replayed") is True for _name, data in _parse_sse_events(replay.content))


def test_bound_chat_claim_reads_superseded_snapshot_and_rejects_withdrawal(client) -> None:
    import asyncio
    import time
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.models import (
        ChatSession,
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
        DomainRelease,
        EvidencePointer,
        EvidenceTicket,
        Material,
        MaterialVersion,
        PublicationSnapshot,
        RetrievalUnit,
    )
    from app.db.session import session_factory
    from tests.conftest import publish_course_release_for_test

    course_id, student_id, version_id = _prepare(client, publish=False)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def material_id_for_version() -> str:
        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None
            return version.material_id

    material_id = asyncio.run(material_id_for_version())

    async def seed_domain_release(version_no: int, previous_id: str | None = None) -> str:
        async with session_factory() as db:
            if previous_id:
                previous = await db.get(DomainRelease, previous_id)
                assert previous is not None
                previous.status = "deprecated"
            release = DomainRelease(
                course_id=course_id,
                version_no=version_no,
                manifest={
                    "domain_pack": {
                        "knowledge_points": [],
                        "misconceptions": [],
                        "evidence_bindings": [],
                    }
                },
                pack_sha256=f"{version_no:064x}",
                status="published",
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(release)
            await db.commit()
            return release.id

    def wait_for_job(job_id: str) -> dict:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/jobs/{job_id}")
            assert response.status_code == 200, response.text
            job = response.json()["data"]
            if job["status"] in {"succeeded", "failed"}:
                assert job["status"] == "succeeded", job
                return job
            time.sleep(0.2)
        raise AssertionError(f"索引任务超时：{job_id}")

    def build_domain_index(domain_release_id: str) -> str:
        response = client.post(
            f"/api/v1/material-versions/{version_id}/embed?domain_release_id={domain_release_id}"
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["data"]["job_id"]
        wait_for_job(job_id)
        return job_id

    def publish_material(domain_release_id: str) -> dict:
        response = client.post(
            f"/api/v1/material-versions/{version_id}/publish?domain_release_id={domain_release_id}"
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    old_domain_id = asyncio.run(seed_domain_release(1))
    old_job_id = build_domain_index(old_domain_id)
    old_snapshot = publish_material(old_domain_id)
    old_snapshot_id = old_snapshot["publication_snapshot_id"]

    created_release = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "Tutor 固定快照版本一",
            "material_ids": [material_id],
            "domain_release_id": old_domain_id,
        },
    )
    assert created_release.status_code == 201, created_release.text
    release1 = created_release.json()["data"]
    pinned = release1["manifest"]["publication_snapshots"][0]
    assert pinned["publication_snapshot_id"] == old_snapshot_id
    assert pinned["index_job_id"] == old_job_id

    async def seed_assignment() -> tuple[str, str]:
        async with session_factory() as db:
            course_class = CourseClass(
                course_id=course_id,
                code="TUTOR-HISTORY",
                name="Tutor 历史快照班",
                created_by=teacher_id,
            )
            db.add(course_class)
            await db.flush()
            db.add(ClassMember(class_id=course_class.id, user_id=student_id))
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=course_class.id,
                course_release_id=release1["id"],
                status="active",
                assigned_by=teacher_id,
            )
            db.add(assignment)
            await db.commit()
            return course_class.id, assignment.id

    class_id, old_assignment_id = asyncio.run(seed_assignment())
    published_release1 = publish_course_release_for_test(client, course_id, release1["id"])
    assert published_release1["manifest"]["publication_snapshots"][0][
        "publication_snapshot_id"
    ] == old_snapshot_id

    _login(client, "ms@uni.edu")
    created_session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert created_session.status_code == 201, created_session.text
    session_id = created_session.json()["data"]["id"]

    original_turn_body = {
        "content": "Explain internal validity in experiments.",
        "client_turn_id": "old-release-claim-001",
    }
    original_turn_response = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json=original_turn_body,
    )
    assert original_turn_response.status_code == 200, original_turn_response.text
    original_events = _parse_sse_events(original_turn_response.content)
    original_done = next(data for name, data in original_events if name == "done")
    assert original_done["saved"] is True
    original_answer = "".join(
        data["text"] for name, data in original_events if name == "delta"
    )

    _login(client, "mt@uni.edu")
    new_domain_id = asyncio.run(seed_domain_release(2, old_domain_id))
    new_job_id = build_domain_index(new_domain_id)
    new_snapshot = publish_material(new_domain_id)
    assert new_snapshot["publication_snapshot_id"] != old_snapshot_id
    assert new_snapshot["index_job_id"] == new_job_id

    created_release2 = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "Tutor 固定快照版本二",
            "material_ids": [material_id],
            "domain_release_id": new_domain_id,
        },
    )
    assert created_release2.status_code == 201, created_release2.text
    release2 = created_release2.json()["data"]
    publish_course_release_for_test(client, course_id, release2["id"])

    async def rotate_assignment() -> str:
        async with session_factory() as db:
            old_assignment = await db.get(CourseReleaseAssignment, old_assignment_id)
            assert old_assignment is not None
            old_assignment.status = "closed"
            old_assignment.closed_at = datetime.now(UTC)
            old_assignment.close_reason = "Tutor historical PublicationSnapshot test"
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=class_id,
                course_release_id=release2["id"],
                status="active",
                assigned_by=teacher_id,
                supersedes_id=old_assignment_id,
            )
            db.add(assignment)
            await db.commit()
            return assignment.id

    new_assignment_id = asyncio.run(rotate_assignment())
    _login(client, "ms@uni.edu")
    turn_response = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json=original_turn_body,
    )
    assert turn_response.status_code == 200, turn_response.text
    replay_events = _parse_sse_events(turn_response.content)
    replay_done = next(data for name, data in replay_events if name == "done")
    assert replay_done["saved"] is True
    assert replay_done["replayed"] is True
    assert replay_done["turn_id"] == original_done["turn_id"]
    replay_answer = "".join(data["text"] for name, data in replay_events if name == "delta")
    assert replay_answer == original_answer
    original_citations = [
        data["evidence_id"] for name, data in original_events if name == "citation"
    ]
    replay_citations = [
        data["evidence_id"] for name, data in replay_events if name == "citation"
    ]
    assert replay_citations == original_citations
    session_detail = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert session_detail.status_code == 200
    assert [turn["role"] for turn in session_detail.json()["data"]["turns"]] == [
        "student",
        "tutor",
    ]
    tutor_turn = session_detail.json()["data"]["turns"][-1]
    claim = tutor_turn["verification"]["domain_claim"]
    assert claim["status"] == "supported"
    assert claim["scope"]["course_release_assignment_id"] == old_assignment_id
    assert claim["scope"]["course_release_id"] == release1["id"]
    assert claim["scope"]["domain_release_id"] == old_domain_id
    assert claim["scope"]["publication_snapshots"] == [pinned]
    assert claim["initial_evidence_refs"]

    async def assert_evidence_uses_old_index() -> None:
        async with session_factory() as db:
            tickets = (
                await db.execute(
                    select(EvidenceTicket).where(
                        EvidenceTicket.id.in_(claim["initial_evidence_refs"])
                    )
                )
            ).scalars().all()
            assert tickets
            pointer_ids = {ticket.pointer_id for ticket in tickets if ticket.pointer_id}
            pointers = (
                await db.execute(
                    select(EvidencePointer).where(EvidencePointer.id.in_(pointer_ids))
                )
            ).scalars().all()
            assert pointers
            units = [await db.get(RetrievalUnit, pointer.retrieval_unit_id) for pointer in pointers]
            assert units and all(unit is not None for unit in units)
            assert all(
                unit.material_version_id == version_id
                and unit.domain_release_id == old_domain_id
                and unit.build_version == f"v1-{old_job_id}"
                for unit in units
            )
            old_domain = await db.get(DomainRelease, old_domain_id)
            old_publication = await db.get(PublicationSnapshot, old_snapshot_id)
            session_row = await db.get(ChatSession, session_id)
            assert old_domain is not None and old_domain.status == "deprecated"
            assert old_publication is not None and old_publication.superseded_at is not None
            assert session_row is not None
            assert (
                session_row.course_release_assignment_id,
                session_row.course_release_id,
            ) == (old_assignment_id, release1["id"])
            assert new_assignment_id != old_assignment_id

    asyncio.run(assert_evidence_uses_old_index())

    async def corrupt_release_pin(*, index_job_id: str, domain_release_id: str) -> None:
        async with session_factory() as db:
            old_release = await db.get(CourseRelease, release1["id"])
            assert old_release is not None
            manifest = dict(old_release.manifest)
            pins = [dict(pin) for pin in manifest["publication_snapshots"]]
            pins[0]["index_job_id"] = index_job_id
            pins[0]["domain_release_id"] = domain_release_id
            manifest["publication_snapshots"] = pins
            old_release.manifest = manifest
            await db.commit()

    async def restore_release_pin() -> None:
        async with session_factory() as db:
            old_release = await db.get(CourseRelease, release1["id"])
            assert old_release is not None
            manifest = dict(old_release.manifest)
            manifest["publication_snapshots"] = [dict(pinned)]
            old_release.manifest = manifest
            await db.commit()

    def assert_corrupt_pin_is_rejected(
        *, client_turn_id: str, expected_refusal: str
    ) -> None:
        response = client.post(
            f"/api/v1/chat/sessions/{session_id}/turns",
            json={
                "content": "请基于课程材料再解释一次",
                "client_turn_id": client_turn_id,
            },
        )
        assert response.status_code == 200, response.text
        detail = client.get(f"/api/v1/chat/sessions/{session_id}")
        assert detail.status_code == 200
        claim_record = detail.json()["data"]["turns"][-1]["verification"]["domain_claim"]
        assert claim_record["status"] == "unknown"
        assert claim_record["refusal_reason"] == expected_refusal
        assert claim_record["initial_evidence_refs"] == []
        assert claim_record["supplemental_retrieval_attempts"] == 0

    asyncio.run(
        corrupt_release_pin(
            index_job_id=new_job_id,
            domain_release_id=old_domain_id,
        )
    )
    assert_corrupt_pin_is_rejected(
        client_turn_id="old-release-wrong-index-job-001",
        expected_refusal="publication_snapshot_unavailable",
    )
    asyncio.run(
        corrupt_release_pin(
            index_job_id=old_job_id,
            domain_release_id=new_domain_id,
        )
    )
    assert_corrupt_pin_is_rejected(
        client_turn_id="old-release-wrong-domain-001",
        expected_refusal="release_material_snapshots_mismatch",
    )
    asyncio.run(restore_release_pin())

    async def withdraw_material() -> None:
        async with session_factory() as db:
            material = await db.get(Material, material_id)
            assert material is not None
            material.status = "archived"
            await db.commit()

    asyncio.run(withdraw_material())
    withdrawn_turn = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json={
            "content": "再解释一次 internal validity",
            "client_turn_id": "old-release-withdrawn-001",
        },
    )
    assert withdrawn_turn.status_code == 200
    withdrawn_detail = client.get(f"/api/v1/chat/sessions/{session_id}")
    withdrawn_claim = withdrawn_detail.json()["data"]["turns"][-1]["verification"]["domain_claim"]
    assert withdrawn_claim["status"] == "unknown"
    assert withdrawn_claim["refusal_reason"] == "publication_snapshot_unavailable"

    async def revoke_class_membership() -> None:
        async with session_factory() as db:
            member = await db.scalar(
                select(ClassMember).where(
                    ClassMember.class_id == class_id,
                    ClassMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            member.removed_at = datetime.now(UTC)
            await db.commit()

    asyncio.run(revoke_class_membership())
    assert client.get(f"/api/v1/chat/sessions/{session_id}").status_code == 404
    revoked_replay = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json=original_turn_body,
    )
    assert revoked_replay.status_code == 404
    assert revoked_replay.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


def test_bound_chat_session_is_hidden_after_class_membership_revocation(client) -> None:
    import asyncio

    from sqlalchemy import select

    from app.db.models import ClassMember, CourseClass, CourseRelease, CourseReleaseAssignment
    from app.db.session import session_factory

    course_id, student_id, _version_id = _prepare(client, publish=True)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def seed_assignment() -> str:
        async with session_factory() as db:
            course_class = CourseClass(
                course_id=course_id,
                code="R3B-REVOKE",
                name="Tutor 权限撤回班",
                created_by=teacher_id,
            )
            db.add(course_class)
            await db.flush()
            db.add(ClassMember(class_id=course_class.id, user_id=student_id))
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="Tutor revoke release",
                status="published",
                manifest={"materials": []},
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(release)
            await db.flush()
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=course_class.id,
                course_release_id=release.id,
                status="active",
                assigned_by=teacher_id,
            )
            db.add(assignment)
            await db.commit()
            return course_class.id

    class_id = asyncio.run(seed_assignment())
    _login(client, "ms@uni.edu")
    session = client.post(
        "/api/v1/chat/sessions", json={"course_id": course_id, "mode": "course_qa"}
    ).json()["data"]

    async def revoke_member() -> None:
        async with session_factory() as db:
            member = await db.scalar(
                select(ClassMember).where(
                    ClassMember.class_id == class_id,
                    ClassMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            await db.commit()

    asyncio.run(revoke_member())
    recovered = client.get(f"/api/v1/chat/sessions/{session['id']}")
    assert recovered.status_code == 404


def test_student_chat_session_rejects_multiple_active_class_assignments(client) -> None:
    import asyncio

    from app.db.models import ClassMember, CourseClass, CourseRelease, CourseReleaseAssignment
    from app.db.session import session_factory

    course_id, student_id = _setup_course(client)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def seed_assignments() -> None:
        async with session_factory() as db:
            for index in range(2):
                course_class = CourseClass(
                    course_id=course_id,
                    code=f"R3B-CHAT-{index}",
                    name=f"Tutor 多班 {index}",
                    created_by=teacher_id,
                )
                db.add(course_class)
                await db.flush()
                db.add(ClassMember(class_id=course_class.id, user_id=student_id))
                release = CourseRelease(
                    course_id=course_id,
                    version_no=index + 1,
                    name=f"Tutor multi-class release {index}",
                    status="published",
                    manifest={"materials": []},
                    created_by=teacher_id,
                    published_by=teacher_id,
                )
                db.add(release)
                await db.flush()
                db.add(
                    CourseReleaseAssignment(
                        course_id=course_id,
                        class_id=course_class.id,
                        course_release_id=release.id,
                        status="active",
                        assigned_by=teacher_id,
                    )
                )
            await db.commit()

    asyncio.run(seed_assignments())
    _login(client, "ms@uni.edu")
    response = client.post(
        "/api/v1/chat/sessions", json={"course_id": course_id, "mode": "course_qa"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS"


def test_saved_presentation_preferences_shape_tutor_answer_only(client, monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    from sqlalchemy import func, select

    from app.db.models import LearningEvidence, MasteryState
    from app.db.session import session_factory
    from app.modules.tutor import service as tutor_service
    from tests.conftest import make_pdf

    synthetic_pdf = make_pdf(
        [
            [
                "Chapter Attention",
                "Attention control selects relevant signals.",
                "For example, attention control selects a target voice.",
                "Attention control reduces distraction from irrelevant signals.",
            ]
        ]
    )
    course_id, student_id, _ = _prepare(
        client, publish=True, content=synthetic_pdf
    )
    _login(client, "ms@uni.edu")
    monkeypatch.setattr(
        tutor_service,
        "get_settings",
        lambda: SimpleNamespace(llm_provider="internal"),
    )
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    endpoint = f"/api/v1/chat/sessions/{session['id']}/turns"

    async def learning_state_counts() -> tuple[int, int]:
        async with session_factory() as db:
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return evidence_count or 0, mastery_count or 0

    state_before = asyncio.run(learning_state_counts())
    preferences = client.get("/api/v1/me/preferences").json()["data"]
    concise_preferences = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": preferences["version"],
            "response_length": "CONCISE",
            "example_order": "EXAMPLE_FIRST",
        },
    )
    assert concise_preferences.status_code == 200, concise_preferences.text
    assert concise_preferences.json()["data"]["preferences"]["response_length"] == "CONCISE"
    concise_turn = client.post(
        endpoint,
        json={"content": "attention control", "client_turn_id": "prefs-concise-0001"},
    )
    assert concise_turn.status_code == 200, concise_turn.text
    concise_events = _parse_sse_events(concise_turn.content)
    concise_answer = "".join(
        data["text"] for name, data in concise_events if name == "delta"
    )
    assert concise_answer.startswith("根据教材：For example,")
    assert "selects relevant signals" not in concise_answer
    assert "reduces distraction" not in concise_answer
    assert next(data for name, data in concise_events if name == "done")["saved"] is True

    current_preferences = concise_preferences.json()["data"]
    detailed_preferences = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": current_preferences["version"],
            "response_length": "DETAILED",
            "example_order": "CONCEPT_FIRST",
        },
    )
    assert detailed_preferences.status_code == 200, detailed_preferences.text
    detailed_turn = client.post(
        endpoint,
        json={"content": "attention control", "client_turn_id": "prefs-detailed-0001"},
    )
    assert detailed_turn.status_code == 200, detailed_turn.text
    detailed_events = _parse_sse_events(detailed_turn.content)
    detailed_answer = "".join(
        data["text"] for name, data in detailed_events if name == "delta"
    )
    concept_position = detailed_answer.index("Attention control selects relevant signals")
    example_position = detailed_answer.index("For example, attention control")
    assert concept_position < example_position
    assert "reduces distraction" in detailed_answer
    assert len(detailed_answer) > len(concise_answer)
    assert next(data for name, data in detailed_events if name == "done")["saved"] is True
    assert asyncio.run(learning_state_counts()) == state_before


def test_guided_learning_preferences_only_change_display_not_learning_state(client) -> None:
    import asyncio

    from sqlalchemy import func, select

    from app.db.models import LearningEvidence, LearningSession, MasteryState
    from app.db.session import session_factory
    from tests.conftest import make_pdf

    synthetic_pdf = make_pdf(
        [
            [
                "Chapter Attention",
                "Attention control selects relevant signals.",
                "For example, attention control selects a target voice.",
                "Attention control reduces distraction from irrelevant signals.",
            ]
        ]
    )
    course_id, student_id, version_id = _prepare(
        client, publish=True, content=synthetic_pdf
    )
    _login(client, "ms@uni.edu")

    concise_task = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    detailed_task = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    assert concise_task.status_code == detailed_task.status_code == 201
    concise_task = concise_task.json()["data"]
    detailed_task = detailed_task.json()["data"]

    async def learning_state_counts() -> tuple[int, int]:
        async with session_factory() as db:
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return evidence_count or 0, mastery_count or 0

    state_before = asyncio.run(learning_state_counts())
    preferences = client.get("/api/v1/me/preferences").json()["data"]
    concise_preferences = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": preferences["version"],
            "response_length": "CONCISE",
            "example_order": "EXAMPLE_FIRST",
        },
    )
    assert concise_preferences.status_code == 200, concise_preferences.text
    concise_response = client.post(
        f"/api/v1/student/learning/tasks/{concise_task['id']}/respond",
        json={"state_version": concise_task["state_version"], "content": "从零开始"},
    )
    assert concise_response.status_code == 200, concise_response.text
    concise_data = concise_response.json()["data"]

    current_preferences = concise_preferences.json()["data"]
    detailed_preferences = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": current_preferences["version"],
            "response_length": "DETAILED",
            "example_order": "CONCEPT_FIRST",
        },
    )
    assert detailed_preferences.status_code == 200, detailed_preferences.text
    detailed_response = client.post(
        f"/api/v1/student/learning/tasks/{detailed_task['id']}/respond",
        json={"state_version": detailed_task["state_version"], "content": "从零开始"},
    )
    assert detailed_response.status_code == 200, detailed_response.text
    detailed_data = detailed_response.json()["data"]

    assert concise_data["tutor_message"].startswith(
        "For example, attention control selects a target voice"
    )
    assert "Attention control selects relevant signals" not in concise_data["tutor_message"]
    assert detailed_data["tutor_message"].index("Attention control selects relevant") < (
        detailed_data["tutor_message"].index("For example, attention control")
    )
    assert len(detailed_data["tutor_message"]) > len(concise_data["tutor_message"])
    assert "根据教材：" not in concise_data["tutor_message"]
    assert "根据教材：" not in detailed_data["tutor_message"]
    assert concise_data["blocks"][0]["text"] == concise_data["tutor_message"]
    assert detailed_data["blocks"][0]["text"] == detailed_data["tutor_message"]
    assert concise_data["blocks"][0]["evidence_refs"] == []
    assert detailed_data["blocks"][0]["evidence_refs"] == []

    unchanged_fields = (
        "state",
        "status",
        "state_version",
        "task_version",
        "hint_level",
        "action",
        "correct",
        "teaching_action",
        "support_gradient",
    )
    assert {key: concise_data[key] for key in unchanged_fields} == {
        key: detailed_data[key] for key in unchanged_fields
    }

    async def stored_messages() -> list[str]:
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(LearningSession.tutor_message)
                    .where(LearningSession.id.in_([concise_task["id"], detailed_task["id"]]))
                    .order_by(LearningSession.id)
                )
            ).scalars().all()
            return list(rows)

    raw_messages = asyncio.run(stored_messages())
    assert len(raw_messages) == 2
    assert raw_messages[0] == raw_messages[1]
    assert asyncio.run(learning_state_counts()) == state_before


def test_turn_stream_answers_with_citations_and_persists(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]

    turn = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={
            "content": "between subjects design 是什么？",
            "client_turn_id": "turn-abc-0001",
        },
    )
    assert turn.status_code == 200
    assert turn.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(turn.content)
    names = [name for name, _ in events]
    assert "state" in names
    assert "citation" in names
    assert "delta" in names
    done = [data for name, data in events if name == "done"][0]
    assert done["saved"] is True
    assert done["refusal"] is False

    detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    turns = detail.json()["data"]["turns"]
    assert [t["role"] for t in turns] == ["student", "tutor"]
    assert turns[1]["citations"]
    assert turns[1]["citations"][0]["material_type"] == "slides"
    citation_event = next(data for name, data in events if name == "citation")
    assert citation_event["material_type"] == "slides"
    assert turns[1]["verification"]["claims"]


def test_turn_same_client_turn_id_replays_saved_answer_and_rejects_content_change(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    body = {"content": "你好", "client_turn_id": "turn-abc-0002"}
    first = client.post(f"/api/v1/chat/sessions/{session['id']}/turns", json=body)
    assert first.status_code == 200
    duplicate = client.post(f"/api/v1/chat/sessions/{session['id']}/turns", json=body)
    assert duplicate.status_code == 200
    first_events = _parse_sse_events(first.content)
    replay_events = _parse_sse_events(duplicate.content)
    first_answer = "".join(
        data["text"] for name, data in first_events if name == "delta"
    )
    replay_answer = "".join(
        data["text"] for name, data in replay_events if name == "delta"
    )
    assert replay_answer == first_answer
    first_done = next(data for name, data in first_events if name == "done")
    replay_done = next(data for name, data in replay_events if name == "done")
    assert first_done["saved"] is True
    assert replay_done["saved"] is True
    assert replay_done["turn_id"] == first_done["turn_id"]

    changed_content = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={**body, "content": "这不是原来的问题"},
    )
    assert changed_content.status_code == 409
    assert changed_content.json()["error"]["code"] == "TURN_IDEMPOTENCY_CONFLICT"

    turns = client.get(f"/api/v1/chat/sessions/{session['id']}").json()["data"]["turns"]
    assert [turn["role"] for turn in turns] == ["student", "tutor"]


def test_selected_table_turn_uses_pinned_local_context_and_binds_idempotency(
    client, monkeypatch
) -> None:
    import asyncio

    from app.db.models import CourseRelease, CourseReleaseAssignment
    from app.db.session import session_factory
    from app.modules.tutor import service as tutor_service

    course_id, student_id, version_id = _prepare(client, publish=True)
    assignment_id, pointer_id, other_pointer_id, _ = _seed_pinned_table_chat(
        client, course_id=course_id, student_id=student_id, version_id=version_id
    )
    _login(client, "ms@uni.edu")
    session_response = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert session_response.status_code == 201, session_response.text
    session = session_response.json()["data"]

    async def set_pointer_version_provenance() -> None:
        from app.db.models import MaterialVersion

        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None
            version.source_title = "Synthetic Table source"
            version.publisher = "Synthetic Table publisher"
            version.course_resource_role = "supplementary_resource"
            version.provenance_status = "unreviewed"
            version.provenance_version = 2
            version.provenance_submitted_by = version.created_by
            version.provenance_review_note = "synthetic private review note"
            await db.commit()

    asyncio.run(set_pointer_version_provenance())

    def forbidden_provider(*args, **kwargs):
        raise AssertionError("selected Table turn must stay on local extractive path")

    monkeypatch.setattr(tutor_service.knowledge_service, "hybrid_search", forbidden_provider)
    monkeypatch.setattr(tutor_service, "generate_grounded_answer", forbidden_provider)
    monkeypatch.setattr(tutor_service, "call_model", forbidden_provider)

    endpoint = f"/api/v1/chat/sessions/{session['id']}/turns"
    body = {
        "content": "请说明这张表怎么读",
        "client_turn_id": "table-context-0001",
        "selected_evidence_pointer_ids": [pointer_id],
    }
    first = client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    first_events = _parse_sse_events(first.content)
    event_names = [name for name, _ in first_events]
    object_state = next(
        data
        for name, data in first_events
        if name == "state" and data.get("stage") == "explaining_object"
    )
    assert object_state == {
        "stage": "explaining_object",
        "object_type": "table",
        "evidence_pointer_id": pointer_id,
    }
    assert event_names.index("state") < event_names.index("citation") < event_names.index("delta")
    first_citation = next(data for name, data in first_events if name == "citation")
    assert first_citation["evidence_pointer_id"] == pointer_id
    assert first_citation["provenance"]["source_title"] == "Synthetic Table source"
    assert first_citation["provenance"]["status"] == "unreviewed"
    assert "submitted_by" not in first_citation["provenance"]
    assert "review_note" not in first_citation["provenance"]
    first_done = next(data for name, data in first_events if name == "done")
    assert first_done["saved"] is True
    saved_turns = client.get(f"/api/v1/chat/sessions/{session['id']}").json()["data"]["turns"]
    saved_student_turn, saved_tutor_turn = saved_turns[-2:]
    object_context = saved_tutor_turn["verification"]["object_context"]
    saved_citation = saved_tutor_turn["citations"][0]
    assert saved_citation["provenance"]["publisher"] == "Synthetic Table publisher"
    assert saved_citation["provenance"]["course_resource_role"] == "supplementary_resource"
    assert "provenance_submitted_by" not in saved_citation
    assert "provenance_review_note" not in saved_citation
    assert saved_student_turn["citations"] == [{"evidence_pointer_id": pointer_id}]
    assert object_context["evidence_pointer_id"] == pointer_id
    assert object_context["material_version_id"] == version_id
    assert object_context["publication_snapshot_id"] == saved_citation["publication_snapshot_id"]
    assert object_context["index_job_id"] == saved_citation["index_job_id"]

    replay = client.post(endpoint, json=body)
    assert replay.status_code == 200, replay.text
    replay_events = _parse_sse_events(replay.content)
    replay_done = next(data for name, data in replay_events if name == "done")
    assert replay_done["saved"] is True
    assert replay_done["replayed"] is True
    replay_state = next(
        data
        for name, data in replay_events
        if name == "state" and data.get("stage") == "explaining_object"
    )
    assert replay_state["evidence_pointer_id"] == pointer_id
    assert next(data for name, data in replay_events if name == "citation")[
        "evidence_pointer_id"
    ] == pointer_id
    replay_citation = next(data for name, data in replay_events if name == "citation")
    assert replay_citation["provenance"]["source_title"] == "Synthetic Table source"

    async def change_release_pointer_pin() -> dict:
        from copy import deepcopy

        async with session_factory() as db:
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            original = deepcopy(release.manifest)
            pins = list(release.manifest["publication_snapshots"])
            pins[0] = {**pins[0], "publication_snapshot_id": "x" * 26}
            release.manifest = {**release.manifest, "publication_snapshots": pins}
            await db.commit()
            return original

    original_manifest = asyncio.run(change_release_pointer_pin())
    stale_release_detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    assert stale_release_detail.status_code == 200, stale_release_detail.text
    stale_saved_citation = stale_release_detail.json()["data"]["turns"][-1]["citations"][0]
    assert stale_saved_citation["provenance"] is None
    assert stale_release_detail.json()["data"]["turns"][-1]["content"]

    new_turn_with_stale_pointer = client.post(
        endpoint,
        json={**body, "client_turn_id": "table-context-new-stale-pin"},
    )
    assert new_turn_with_stale_pointer.status_code == 404
    assert new_turn_with_stale_pointer.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"

    stale_release_replay = client.post(endpoint, json=body)
    assert stale_release_replay.status_code == 200, stale_release_replay.text
    stale_replay_events = _parse_sse_events(stale_release_replay.content)
    stale_replay_done = next(data for name, data in stale_replay_events if name == "done")
    assert stale_replay_done["saved"] is True
    assert any(data.get("text") for name, data in stale_replay_events if name == "delta")
    stale_replay_citation = next(
        data for name, data in stale_replay_events if name == "citation"
    )
    assert stale_replay_citation["provenance"] is None

    async def restore_release_manifest() -> None:
        async with session_factory() as db:
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            release.manifest = original_manifest
            await db.commit()

    asyncio.run(restore_release_manifest())

    conflict = client.post(
        endpoint,
        json={**body, "selected_evidence_pointer_ids": [other_pointer_id]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "TURN_IDEMPOTENCY_CONFLICT"

    async def revoke_assignment() -> None:
        async with session_factory() as db:
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert assignment is not None
            assignment.status = "revoked"
            await db.commit()

    asyncio.run(revoke_assignment())
    revoked_replay = client.post(endpoint, json=body)
    assert revoked_replay.status_code == 404


def test_selected_table_turn_replays_after_commit_before_done_reaches_client(
    client, monkeypatch
) -> None:
    import asyncio
    from copy import deepcopy

    from fastapi import Request
    from sqlalchemy import func, select

    from app.db.models import (
        ChatSession,
        ChatTurn,
        CourseRelease,
        CourseReleaseAssignment,
        User,
    )
    from app.db.session import session_factory
    from app.modules.tutor import service as tutor_service
    from app.modules.tutor.router import TurnCreate, create_turn

    course_id, student_id, version_id = _prepare(client, publish=True)
    assignment_id, pointer_id, _, _ = _seed_pinned_table_chat(
        client, course_id=course_id, student_id=student_id, version_id=version_id
    )
    _login(client, "ms@uni.edu")
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    endpoint = f"/api/v1/chat/sessions/{session['id']}/turns"
    body = {
        "content": "请说明这张表怎么读",
        "client_turn_id": "table-reconnect-commit-0001",
        "selected_evidence_pointer_ids": [pointer_id],
    }

    def forbidden_provider(*args, **kwargs):
        raise AssertionError("selected Table turn must stay on local extractive path")

    monkeypatch.setattr(tutor_service.knowledge_service, "hybrid_search", forbidden_provider)
    monkeypatch.setattr(tutor_service, "generate_grounded_answer", forbidden_provider)
    monkeypatch.setattr(tutor_service, "call_model", forbidden_provider)

    async def commit_then_drop_done() -> tuple[bytes, int]:
        async with session_factory() as db:
            user = await db.scalar(select(User).where(User.id == student_id))
            session_row = await db.scalar(
                select(ChatSession).where(ChatSession.id == session["id"])
            )
            assert user is not None
            assert session_row is not None
            request = Request(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": f"/api/v1/chat/sessions/{session_row.id}/turns",
                    "raw_path": f"/api/v1/chat/sessions/{session_row.id}/turns".encode(),
                    "query_string": b"",
                    "root_path": "",
                    "headers": [],
                    "server": ("testserver", 80),
                    "client": ("testclient", 123),
                }
            )
            response = await create_turn(
                session_row.id,
                TurnCreate(**body),
                request,
                user,
                db,
            )
            iterator = response.body_iterator.__aiter__()
            frames = []
            while True:
                frame = await anext(iterator)
                if "event: done" in frame:
                    # run_turn_stream 在发送 done 前已提交；丢弃该帧模拟确认消息丢失。
                    break
                frames.append(frame)
            await iterator.aclose()
            persisted_count = await db.scalar(
                select(func.count()).select_from(ChatTurn).where(
                    ChatTurn.session_id == session_row.id
                )
            )
            return "".join(frames).encode("utf-8"), persisted_count or 0

    pre_done_stream, count_after_lost_ack = asyncio.run(commit_then_drop_done())
    first_events = _parse_sse_events(pre_done_stream)
    assert count_after_lost_ack == 2
    first_citation = next(data for name, data in first_events if name == "citation")
    assert any(
        name == "state"
        and data.get("stage") == "explaining_object"
        and data.get("evidence_pointer_id") == pointer_id
        for name, data in first_events
    )

    retry = client.post(endpoint, json=body)
    assert retry.status_code == 200, retry.text
    replay_events = _parse_sse_events(retry.content)
    replay_done = next(data for name, data in replay_events if name == "done")
    assert replay_done["saved"] is True
    assert replay_done["replayed"] is True
    assert any(
        name == "state"
        and data.get("stage") == "explaining_object"
        and data.get("evidence_pointer_id") == pointer_id
        for name, data in replay_events
    )
    first_answer = "".join(
        data["text"] for name, data in first_events if name == "delta"
    )
    replay_answer = "".join(
        data["text"] for name, data in replay_events if name == "delta"
    )
    assert replay_answer == first_answer
    replay_citation = next(data for name, data in replay_events if name == "citation")
    assert replay_citation["evidence_pointer_id"] == pointer_id
    assert replay_citation["label"] == first_citation["label"]

    saved_turns = client.get(
        f"/api/v1/chat/sessions/{session['id']}"
    ).json()["data"]["turns"]
    assert len(saved_turns) == 2
    assert [turn["role"] for turn in saved_turns] == ["student", "tutor"]
    assert replay_done["turn_id"] == saved_turns[1]["id"]
    assert saved_turns[0]["citations"] == [{"evidence_pointer_id": pointer_id}]
    assert saved_turns[1]["citations"][0]["evidence_pointer_id"] == pointer_id

    changed_content_replay = client.post(
        endpoint,
        json={**body, "content": "请改为说明另一张表"},
    )
    assert changed_content_replay.status_code == 409
    assert changed_content_replay.json()["error"]["code"] == "TURN_IDEMPOTENCY_CONFLICT"

    async def invalidate_pinned_snapshot() -> None:
        async with session_factory() as db:
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert assignment is not None
            release = await db.get(CourseRelease, assignment.course_release_id)
            assert release is not None
            manifest = deepcopy(release.manifest)
            pins = manifest["publication_snapshots"]
            pin = next(item for item in pins if item["material_version_id"] == version_id)
            # 合成一个失效的快照引用，验证重放仍须先通过当前 pin 授权。
            pin["publication_snapshot_id"] = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
            release.manifest = manifest
            await db.commit()

    asyncio.run(invalidate_pinned_snapshot())
    invalid_snapshot_replay = client.post(endpoint, json=body)
    assert invalid_snapshot_replay.status_code == 404, invalid_snapshot_replay.text
    assert invalid_snapshot_replay.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_turn_disconnect_after_delta_closes_generation_and_retry_saves_once(
    client, monkeypatch
) -> None:
    import asyncio

    from fastapi import Request
    from sqlalchemy import func, select

    from app.db.models import ChatSession, ChatTurn, User
    from app.db.session import session_factory
    from app.modules.tutor import service as tutor_service
    from app.modules.tutor.router import TurnCreate, create_turn

    course_id, student_id, _ = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    session_data = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    closed = False

    async def interrupted_stream(*args, **kwargs):
        nonlocal closed
        try:
            yield {"event": "state", "data": {"stage": "generating"}}
            yield {"event": "delta", "data": {"sequence": 0, "text": "半截回答"}}
            await asyncio.Event().wait()
        finally:
            closed = True

    async def close_after_first_delta() -> tuple[str, str, int]:
        async with session_factory() as db:
            user = await db.scalar(select(User).where(User.id == student_id))
            session_row = await db.scalar(
                select(ChatSession).where(ChatSession.id == session_data["id"])
            )
            assert user is not None
            assert session_row is not None
            request = Request(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/chat/sessions/turns",
                    "raw_path": b"/api/v1/chat/sessions/turns",
                    "query_string": b"",
                    "root_path": "",
                    "headers": [],
                    "server": ("testserver", 80),
                    "client": ("testclient", 123),
                }
            )
            response = await create_turn(
                session_row.id,
                TurnCreate(content="你好", client_turn_id="turn-disconnect-01"),
                request,
                user,
                db,
            )
            iterator = response.body_iterator.__aiter__()
            first = await anext(iterator)
            second = await anext(iterator)
            await iterator.aclose()
            count = await db.scalar(
                select(func.count()).select_from(ChatTurn).where(
                    ChatTurn.session_id == session_row.id
                )
            )
            return first, second, count or 0

    with monkeypatch.context() as patcher:
        patcher.setattr(tutor_service, "run_turn_stream", interrupted_stream)
        state_frame, delta_frame, saved_turn_count = asyncio.run(close_after_first_delta())

    assert "event: state" in state_frame
    assert "event: delta" in delta_frame
    assert "半截回答" in delta_frame
    assert closed is True
    assert saved_turn_count == 0

    retry = client.post(
        f"/api/v1/chat/sessions/{session_data['id']}/turns",
        json={"content": "你好", "client_turn_id": "turn-disconnect-01"},
    )
    assert retry.status_code == 200
    retry_events = _parse_sse_events(retry.content)
    assert next(data for name, data in retry_events if name == "done")["saved"] is True
    turns = client.get(
        f"/api/v1/chat/sessions/{session_data['id']}"
    ).json()["data"]["turns"]
    assert [turn["role"] for turn in turns] == ["student", "tutor"]


def test_turn_without_evidence_refuses(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    turn = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={
            "content": "量子纠缠在超导实验中的应用 zzqq",
            "client_turn_id": "turn-abc-0003",
        },
    )
    events = _parse_sse_events(turn.content)
    done = [data for name, data in events if name == "done"][0]
    assert done["refusal"] is True
    detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    tutor_turn = detail.json()["data"]["turns"][1]
    assert tutor_turn["refusal"] is True
    assert "未找到足够依据" in tutor_turn["content"]


def test_turn_safety_gate_distinguishes_academic_topic_from_personal_risk(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]

    academic = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={
            "content": "在实验心理学教材中，什么是自杀意念的操作化定义？",
            "client_turn_id": "turn-safety-academic-01",
        },
    )
    academic_events = _parse_sse_events(academic.content)
    assert "safety" not in [data.get("stage") for name, data in academic_events if name == "state"]

    personal = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={
            "content": "我最近不想活了，担心自己会伤害自己。",
            "client_turn_id": "turn-safety-personal-01",
        },
    )
    personal_events = _parse_sse_events(personal.content)
    assert "safety" in [data.get("stage") for name, data in personal_events if name == "state"]
    saved = client.get(f"/api/v1/chat/sessions/{session['id']}").json()["data"]["turns"]
    safety_reply = saved[-1]
    assert safety_reply["refusal"] is True
    assert "12356" in safety_reply["content"]


def test_learning_session_state_machine_flow(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    chapter_id = outline.json()["data"][0]["id"]
    created_by_student = client.post(
        "/api/v1/learning-sessions",
        json={
            "course_id": course_id,
            "material_version_id": version_id,
            "chapter_object_id": chapter_id,
        },
    )
    assert created_by_student.status_code == 201
    learning = created_by_student.json()["data"]
    assert learning["runtime"]["current_task_id"] == learning["id"]
    assert learning["runtime"]["episode_id"]
    assert learning["state"] == "diagnose"
    assert learning["action"] == "wait_for_student"
    assert learning["task_id"] == learning["id"]
    assert learning["task_version"] == learning["state_version"]
    assert learning["allowed_actions"] == ["RESPOND_TASK"]
    assert learning["context_refs"]["course_id"] == course_id
    assert learning["completion"]["activity_completed"] is False

    recovered = client.get(f"/api/v1/student/learning/tasks/{learning['id']}")
    assert recovered.status_code == 200
    recovered_data = recovered.json()["data"]
    assert recovered_data["state_version"] == learning["state_version"]
    assert recovered_data["blocks"] == learning["blocks"]

    home = client.get("/api/v1/student/home")
    assert home.status_code == 200
    assert home.json()["data"]["current_task"]["task_id"] == learning["id"]
    assert home.json()["data"]["next_actions"] == ["RESPOND_TASK"]
    assert home.json()["data"]["task_queue"][0]["task_id"] == learning["id"]

    _login(client, "ms@uni.edu")
    stale = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": 99, "content": "完全不懂"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    response = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": learning["state_version"], "content": "继续"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] in ("teach", "check")
    assert data["message"]
    events = client.get(f"/api/v1/me/learning-events?course_id={course_id}")
    assert events.status_code == 200
    tutor_events = [
        item for item in events.json()["data"] if item["event_type"] == "tutor_responded"
    ]
    assert tutor_events[-1]["payload"]["state_version"] == data["state_version"]

    current = client.get(f"/api/v1/learning-sessions/{learning['id']}")
    assert current.json()["data"]["state_version"] == learning["state_version"] + 1


def test_learning_microcycle_repairs_misconceptions_and_uses_grounded_example_fallback(
    client,
) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    chapter_id = outline.json()["data"][0]["id"]
    learning = client.post(
        "/api/v1/learning-sessions",
        json={
            "course_id": course_id,
            "material_version_id": version_id,
            "chapter_object_id": chapter_id,
        },
    ).json()["data"]

    def respond(content: str) -> dict:
        nonlocal learning
        response = client.post(
            f"/api/v1/learning-sessions/{learning['id']}/responses",
            json={"state_version": learning["state_version"], "content": content},
        )
        assert response.status_code == 200, response.text
        learning = response.json()["data"]
        return learning

    assert respond("继续")["state"] == "teach"
    repair = respond("我不知道")
    assert repair["hint_level"] == 1
    assert repair["teaching_action"] == "hint"
    assert "回到教材" in repair["message"]
    corrected = respond("Independent variable control improves internal validity in experiments.")
    assert corrected["state"] == "check"
    assert corrected["teaching_action"] == "check"
    assert corrected["hint_level"] == 1
    assert corrected["blocks"][0]["type"] == "Question"
    assert corrected["blocks"][0]["prompt"] == corrected["message"]
    repair = respond("我不知道")
    assert repair["state"] == "hint"
    assert repair["teaching_action"] == "hint"
    assert "不急着判断对错" in repair["message"]
    example = respond("我不知道")
    assert example["state"] == "practice"
    assert example["action"] == "show_example"
    assert example["teaching_action"] == "hint"
    assert example["blocks"][0]["type"] == "TutorExplanation"
    assert "当前教材段落没有明确标记的例子" in example["message"]
    assert "研究者控制参与者" not in example["message"]

    standalone_session = client.post(
        "/api/v1/learning-sessions",
        json={
            "course_id": course_id,
            "material_version_id": version_id,
            "chapter_object_id": chapter_id,
        },
    ).json()["data"]

    def respond_standalone(content: str) -> dict:
        nonlocal standalone_session
        response = client.post(
            f"/api/v1/learning-sessions/{standalone_session['id']}/responses",
            json={"state_version": standalone_session["state_version"], "content": content},
        )
        assert response.status_code == 200, response.text
        standalone_session = response.json()["data"]
        return standalone_session

    assert respond_standalone("继续")["state"] == "teach"
    assert respond_standalone(
        "Independent variable control improves internal validity in experiments."
    )["state"] == "check"
    practice = respond_standalone(
        "Independent variable control improves internal validity in experiments."
    )
    assert practice["state"] == "practice"
    assert practice["action"] == "wait_for_student"
    assert practice["blocks"][0]["type"] == "Question"
    assert practice["blocks"][0]["prompt"] == practice["message"]


def test_terminal_hint_requires_practice_policy_before_emitting_example(client) -> None:
    import asyncio

    from sqlalchemy import func, select

    from app.db.models import (
        LearningEvent,
        LearningEvidence,
        LearningSession,
        MasteryState,
        UserPreference,
    )
    from app.db.session import session_factory

    course_id, student_id, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    preference = client.get("/api/v1/me/preferences").json()["data"]
    presentation = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": preference["version"],
            "response_length": "DETAILED",
            "example_order": "EXAMPLE_FIRST",
        },
    )
    assert presentation.status_code == 200, presentation.text

    async def set_policy(*, allow_practice: bool = False) -> None:
        async with session_factory() as db:
            row = await db.scalar(
                select(UserPreference).where(UserPreference.user_id == student_id)
            )
            assert row is not None
            row.preferences = {
                **row.preferences,
                "teaching_policy": {
                    "allowed_actions": [
                        "diagnose", "teach", "check", "hint",
                        *( ["practice"] if allow_practice else [] ),
                    ],
                    "max_hints": 3,
                },
            }
            await db.commit()

    async def state_and_side_effect_counts(learning_id: str) -> tuple:
        async with session_factory() as db:
            learning_row = await db.get(LearningSession, learning_id)
            assert learning_row is not None
            event_count = await db.scalar(
                select(func.count()).select_from(LearningEvent).where(
                    LearningEvent.event_key.like(
                        f"learning-session-response:{learning_id}:%"
                    )
                )
            )
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return (
                learning_row.state,
                learning_row.version,
                learning_row.hint_level,
                event_count or 0,
                evidence_count or 0,
                mastery_count or 0,
            )

    asyncio.run(set_policy())
    started = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    assert started.status_code == 201, started.text
    learning = started.json()["data"]

    def respond(content: str):
        response = client.post(
            f"/api/v1/learning-sessions/{learning['id']}/responses",
            json={"state_version": learning["state_version"], "content": content},
        )
        assert response.status_code == 200, response.text
        learning.update(response.json()["data"])

    respond("继续")
    assert learning["state"] == "teach"
    respond("我不知道")
    assert learning["hint_level"] == 1
    respond("Independent variable control improves internal validity in experiments.")
    assert learning["state"] == "check"
    respond("我不知道")
    assert learning["state"] == "hint"
    assert learning["hint_level"] == 2

    before = asyncio.run(state_and_side_effect_counts(learning["id"]))
    assert before[0] == "hint"
    assert before[2] == 2
    blocked = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": learning["state_version"], "content": "我不知道"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "TEACHING_ACTION_NOT_ALLOWED"
    assert blocked.json()["error"]["details"]["action"] == "practice"
    assert asyncio.run(state_and_side_effect_counts(learning["id"])) == before

    asyncio.run(set_policy(allow_practice=True))
    allowed = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": learning["state_version"], "content": "我不知道"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["state"] == "practice"
    assert allowed.json()["data"]["action"] == "show_example"
    assert allowed.json()["data"]["hint_level"] == 3


def test_guided_hint_policy_rejections_preserve_version_state_and_evidence(client) -> None:
    import asyncio

    from sqlalchemy import func, select

    from app.db.models import (
        LearningEvent,
        LearningEvidence,
        LearningQualification,
        LearningSession,
        MasteryState,
        UserPreference,
    )
    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_pending_events

    course_id, student_id, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")

    async def set_teaching_policy(policy: dict) -> None:
        async with session_factory() as db:
            preference = await db.scalar(
                select(UserPreference).where(UserPreference.user_id == student_id)
            )
            if preference is None:
                db.add(
                    UserPreference(
                        user_id=student_id,
                        preferences={"teaching_policy": policy},
                    )
                )
            else:
                preference.preferences = {
                    **preference.preferences,
                    "teaching_policy": policy,
                }
            await db.commit()

    async def learning_state_counts(learning_id: str) -> tuple[int, int, int, int]:
        async with session_factory() as db:
            learning = await db.get(LearningSession, learning_id)
            assert learning is not None
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return (
                learning.version,
                learning.hint_level,
                evidence_count or 0,
                mastery_count or 0,
            )

    def create_learning() -> dict:
        response = client.post(
            "/api/v1/learning-sessions",
            json={"course_id": course_id, "material_version_id": version_id},
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    def post_response(learning_id: str, version: int, content: str):
        return client.post(
            f"/api/v1/learning-sessions/{learning_id}/responses",
            json={"state_version": version, "content": content},
        )

    async def set_budget_policy() -> None:
        await set_teaching_policy(
            {
                "allowed_actions": ["diagnose", "teach", "check", "hint"],
                "max_hints": 1,
            }
        )

    async def set_restricted_policy() -> None:
        await set_teaching_policy({"allowed_actions": ["pause", "handoff"]})

    preferences = client.get("/api/v1/me/preferences").json()["data"]
    presentation_preferences = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": preferences["version"],
            "response_length": "DETAILED",
            "example_order": "EXAMPLE_FIRST",
        },
    )
    assert presentation_preferences.status_code == 200, presentation_preferences.text

    asyncio.run(set_restricted_policy())
    blocked_start = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    assert blocked_start.status_code == 403
    assert blocked_start.json()["error"]["code"] == "TEACHING_ACTION_NOT_ALLOWED"

    asyncio.run(set_budget_policy())
    budget_learning = create_learning()
    first = post_response(budget_learning["id"], budget_learning["state_version"], "继续")
    assert first.status_code == 200, first.text
    taught = first.json()["data"]
    repair_response = post_response(
        budget_learning["id"], taught["state_version"], "我不知道"
    )
    assert repair_response.status_code == 200, repair_response.text
    repaired = repair_response.json()["data"]
    assert repaired["teaching_action"] == "hint"
    assert repaired["hint_level"] == 1
    assert "不急着判断对错" in repaired["message"]

    corrected_response = post_response(
        budget_learning["id"],
        repaired["state_version"],
        "Independent variable control improves internal validity in experiments.",
    )
    assert corrected_response.status_code == 200, corrected_response.text
    corrected = corrected_response.json()["data"]
    assert corrected["state"] == "check"
    assert corrected["teaching_action"] == "check"
    assert corrected["hint_level"] == 1

    stale = post_response(budget_learning["id"], repaired["state_version"], "我不知道")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    over_budget = post_response(
        budget_learning["id"], corrected["state_version"], "我不知道"
    )
    assert over_budget.status_code == 403
    assert over_budget.json()["error"]["code"] == "TEACHING_HINT_BUDGET_EXHAUSTED"

    async def qualify_budgeted_turns() -> list[tuple[str, str]]:
        async with session_factory() as db:
            await qualify_pending_events(db, limit=100)
            events = list(
                (
                    await db.scalars(
                        select(LearningEvent).where(
                            LearningEvent.source_ref == budget_learning["id"],
                            LearningEvent.event_type == "tutor_responded",
                        )
                    )
                ).all()
            )
            results: list[tuple[str, str]] = []
            for event in events:
                qualification = await db.scalar(
                    select(LearningQualification).where(
                        LearningQualification.event_id == event.id
                    )
                )
                assert qualification is not None
                results.append((qualification.status, qualification.reason))
            await db.commit()
            return results

    qualifications = asyncio.run(qualify_budgeted_turns())
    assert len(qualifications) == 3
    assert all(status == "rejected" for status, _reason in qualifications)
    assert all(
        reason in {
            "tutor_response_not_evidence_bearing",
            "tutor_session_version_mismatch",
        }
        for _status, reason in qualifications
    )
    assert asyncio.run(learning_state_counts(budget_learning["id"])) == (
        corrected["state_version"],
        1,
        0,
        0,
    )

    asyncio.run(
        set_teaching_policy(
            {"allowed_actions": ["diagnose", "teach", "check"], "max_hints": 3}
        )
    )
    restricted_learning = create_learning()
    restricted_first = post_response(
        restricted_learning["id"], restricted_learning["state_version"], "继续"
    )
    assert restricted_first.status_code == 200, restricted_first.text
    restricted_taught = restricted_first.json()["data"]
    denied_hint = post_response(
        restricted_learning["id"], restricted_taught["state_version"], "我不知道"
    )
    assert denied_hint.status_code == 403
    assert denied_hint.json()["error"]["code"] == "TEACHING_ACTION_NOT_ALLOWED"
    assert asyncio.run(learning_state_counts(restricted_learning["id"])) == (
        restricted_taught["state_version"],
        0,
        0,
        0,
    )


def test_single_incorrect_guided_answer_is_evidence_without_mastery_or_profile_change(
    client,
) -> None:
    import asyncio

    from sqlalchemy import select

    from app.db.models import (
        LearningEvent,
        LearningEvidence,
        LearningQualification,
        MasteryState,
        MemoryItem,
    )
    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_pending_events

    course_id, student_id, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    learning = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    ).json()["data"]

    def read_qualification(event_key: str) -> tuple[dict, list]:
        async def _read() -> tuple[dict, list]:
            async with session_factory() as db:
                event = await db.scalar(
                    select(LearningEvent).where(LearningEvent.event_key == event_key)
                )
                assert event is not None
                qualification = await db.scalar(
                    select(LearningQualification).where(
                        LearningQualification.event_id == event.id
                    )
                )
                assert qualification is not None
                evidences = list(
                    (
                        await db.scalars(
                            select(LearningEvidence).where(
                                LearningEvidence.id.in_(qualification.evidence_ids)
                            )
                        )
                    ).all()
                )
                return (
                    {"event": event, "qualification": qualification},
                    evidences,
                )

        return asyncio.run(_read())

    def respond(
        content: str, *, qualify: bool = True
    ) -> tuple[dict, dict | None, list]:
        nonlocal learning
        response_version = learning["state_version"]
        response = client.post(
            f"/api/v1/student/learning/tasks/{learning['id']}/respond",
            json={"state_version": learning["state_version"], "content": content},
        )
        assert response.status_code == 200, response.text
        learning = response.json()["data"]
        event_key = f"learning-session-response:{learning['id']}:{response_version}"
        if not qualify:
            return learning, None, []

        async def qualify_and_read() -> tuple[dict, list]:
            async with session_factory() as db:
                counts = await qualify_pending_events(db, limit=100)
                event = await db.scalar(
                    select(LearningEvent).where(LearningEvent.event_key == event_key)
                )
                assert event is not None
                qualification = await db.scalar(
                    select(LearningQualification).where(
                        LearningQualification.event_id == event.id
                    )
                )
                assert qualification is not None
                evidences = list(
                    (
                        await db.scalars(
                            select(LearningEvidence).where(
                                LearningEvidence.id.in_(qualification.evidence_ids)
                            )
                        )
                    ).all()
                )
                await db.commit()
                return (
                    {
                        "event": event,
                        "qualification": qualification,
                        "counts": counts,
                    },
                    evidences,
                )

        record, evidences = asyncio.run(qualify_and_read())
        return learning, record, evidences

    assert respond("继续")[0]["state"] == "teach"
    assert respond("我不知道")[0]["state"] == "teach"
    assert respond(
        "Independent variable control improves internal validity in experiments."
    )[0]["state"] == "check"
    check_answer, _, _ = respond("我不知道", qualify=False)
    assert check_answer["state"] == "hint"
    # 先推进到下一状态再做资格化，旧 check 事件仍可按自身签名被验证。
    hint_answer, hint_record, hint_evidences = respond("我不知道")
    check_record, check_evidences = read_qualification(
        f"learning-session-response:{learning['id']}:{check_answer['state_version'] - 1}"
    )
    assert check_record["qualification"].status == "qualified"
    assert len(check_evidences) == 1
    assert check_evidences[0].dimension == "understand"
    assert check_evidences[0].correct is False
    assert hint_answer["state"] == "practice"
    assert hint_answer["action"] == "show_example"
    assert hint_record["qualification"].status == "rejected"
    assert hint_record["qualification"].reason == "tutor_response_not_evidence_bearing"
    assert hint_evidences == []

    wrong_answer, practice_record, practice_evidences = respond("我不知道")
    assert wrong_answer["state"] == "summary"
    assert wrong_answer["correct"] is False
    assert practice_record["qualification"].status == "qualified"
    assert len(practice_evidences) == 1
    assert practice_evidences[0].dimension == "apply"
    assert practice_evidences[0].correct is False

    async def read_learning_state() -> tuple[list, list]:
        async with session_factory() as db:
            mastery = list(
                (
                    await db.scalars(
                        select(MasteryState).where(
                            MasteryState.user_id == student_id,
                            MasteryState.course_id == course_id,
                        )
                    )
                ).all()
            )
            memory = list(
                (
                    await db.scalars(
                        select(MemoryItem).where(
                            MemoryItem.user_id == student_id,
                            MemoryItem.course_id == course_id,
                            MemoryItem.kind == "weakness",
                        )
                    )
                ).all()
            )
            return mastery, memory

    mastery, memory = asyncio.run(read_learning_state())
    assert check_evidences[0].attempt_id == learning["id"]
    assert practice_evidences[0].attempt_id == learning["id"]
    assert check_evidences[0].independence_status == "supported"
    assert practice_evidences[0].independence_status == "supported"
    assert check_evidences[0].correct is False
    assert practice_evidences[0].correct is False
    assert mastery == []
    assert memory == []


def test_active_formal_assessment_fails_closed_for_learning_response(client) -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.db.models import Assessment, LearningEvent, LearningEvidence, MasteryState
    from app.db.session import session_factory
    from tests.test_assessment_reliability import (
        OBJECTIVE_QUESTION,
        _create_assessment,
        _create_published_question,
    )

    course_id, student_id, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    learning = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    ).json()["data"]

    for answer, expected_state in (
        ("继续", "teach"),
        (
            "Independent variable control improves internal validity in experiments.",
            "check",
        ),
    ):
        response = client.post(
            f"/api/v1/learning-sessions/{learning['id']}/responses",
            json={"state_version": learning["state_version"], "content": answer},
        )
        assert response.status_code == 200, response.text
        learning = response.json()["data"]
        assert learning["state"] == expected_state

    _login(client, "mt@uni.edu")
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])
    async def mark_as_formal() -> None:
        async with session_factory() as db:
            assessment = await db.get(Assessment, assessment_id)
            assert assessment is not None
            assessment.purpose = "formal"
            assessment.result_visibility_policy = "after_close"
            assessment.closes_at = datetime.now(UTC) + timedelta(hours=1)
            await db.commit()

    asyncio.run(mark_as_formal())
    _login(client, "ms@uni.edu")
    preferences = client.get("/api/v1/me/preferences").json()["data"]
    preferred = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": preferences["version"],
            "response_length": "DETAILED",
            "example_order": "EXAMPLE_FIRST",
        },
    )
    assert preferred.status_code == 200, preferred.text
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert attempt.status_code == 201, attempt.text

    forged_event_key = "forged-tutor-check-during-formal-assessment"
    forged_event = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": forged_event_key,
            "course_id": course_id,
            "event_type": "tutor_responded",
            "source_type": "tutor",
            "source_ref": learning["id"],
            "payload": {
                "state_version": learning["state_version"],
                "response_state": "check",
                "correct": True,
                "hint_level": 0,
                "teaching_action": "check",
            },
        },
    )
    assert forged_event.status_code == 403
    assert forged_event.json()["error"]["code"] == "LEARNING_EVENT_SERVER_OWNED"

    async def forged_projection_counts() -> tuple[int, int, int]:
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count()).select_from(LearningEvent).where(
                    LearningEvent.event_key == forged_event_key
                )
            )
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return int(event_count or 0), int(evidence_count or 0), int(mastery_count or 0)

    assert asyncio.run(forged_projection_counts()) == (0, 0, 0)

    blocked = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": learning["state_version"], "content": "从零开始"},
    )

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"
    current = client.get(f"/api/v1/learning-sessions/{learning['id']}")
    assert current.json()["data"]["state_version"] == learning["state_version"]
    assert current.json()["data"]["state"] == learning["state"]


def test_active_practice_assessment_keeps_tutor_available(client) -> None:
    from tests.test_assessment_reliability import (
        OBJECTIVE_QUESTION,
        _create_assessment,
        _create_published_question,
    )

    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    learning = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    assert learning.status_code == 201, learning.text
    _login(client, "mt@uni.edu")
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]], purpose="practice")
    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert attempt.status_code == 201, attempt.text

    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa", "title": "练习后教材学习"},
    )
    assert session.status_code == 201, session.text
    turn = client.post(
        f"/api/v1/chat/sessions/{session.json()['data']['id']}/turns",
        json={"content": "请解释自变量。", "client_turn_id": "practice-turn-0001"},
    )
    assert turn.status_code == 200, turn.text
    assert "当前策略不允许内容型教学支持" not in turn.text
    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "independent variable", "purpose": "course_qa"},
    )
    assert search.status_code == 200, search.text
    home = client.get("/api/v1/student/home")
    assert home.status_code == 200, home.text
    assert "正式测评进行中" not in home.json()["data"]["progress_decision"]["reason"]


def test_learning_session_pins_unique_course_release_assignment(client) -> None:
    import asyncio

    import pytest
    from sqlalchemy import select

    from app.db.base import new_ulid
    from app.db.models import (
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
        DomainRelease,
        LearningEvidence,
        LearningSession,
        Material,
        MaterialVersion,
        PublicationSnapshot,
    )
    from app.db.session import session_factory

    course_id, student_id, version_id = _prepare(client, publish=True)
    teacher = client.get("/api/v1/me").json()["data"]
    teacher_id = teacher["id"]
    foreign_course = client.post(
        "/api/v1/courses", json={"title": "隔离测试课程", "term": "2026秋"}
    )
    assert foreign_course.status_code == 201, foreign_course.text
    other_course_id = foreign_course.json()["data"]["id"]

    async def seed_domain_release() -> str:
        async with session_factory() as db:
            domain_release = DomainRelease(
                course_id=course_id,
                version_no=1,
                manifest={
                    "domain_pack": {
                        "knowledge_points": [],
                        "misconceptions": [],
                        "evidence_bindings": [],
                    }
                },
                pack_sha256="d" * 64,
                status="published",
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(domain_release)
            await db.commit()
            return domain_release.id

    domain_release_id = asyncio.run(seed_domain_release())
    embedded = client.post(
        f"/api/v1/material-versions/{version_id}/embed?domain_release_id={domain_release_id}"
    )
    assert embedded.status_code == 202, embedded.text
    job_id = embedded.json()["data"]["job_id"]
    import time

    deadline = time.time() + 20
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["status"] in {"succeeded", "failed"}:
            assert job["status"] == "succeeded", job
            break
        time.sleep(0.2)
    else:
        raise AssertionError("合成 DomainRelease 索引任务超时")
    republished = client.post(
        f"/api/v1/material-versions/{version_id}/publish?domain_release_id={domain_release_id}"
    )
    assert republished.status_code == 200, republished.text

    _login(client, "ms@uni.edu")
    legacy = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    assert legacy.status_code == 201, legacy.text
    legacy_id = legacy.json()["data"]["id"]

    async def load_legacy_binding() -> tuple[str | None, str | None]:
        async with session_factory() as db:
            learning = await db.get(LearningSession, legacy_id)
            return learning.course_release_assignment_id, learning.course_release_id

    assert asyncio.run(load_legacy_binding()) == (None, None)

    async def seed_assignment() -> tuple[str, str, str, str, str, str, str, str]:
        async with session_factory() as db:
            material_version = await db.get(MaterialVersion, version_id)
            assert material_version is not None
            snapshot = await db.scalar(
                select(PublicationSnapshot).where(
                    PublicationSnapshot.material_version_id == version_id,
                    PublicationSnapshot.superseded_at.is_(None),
                )
            )
            assert snapshot is not None and snapshot.domain_release_id is not None
            pin = {
                "material_id": material_version.material_id,
                "material_version_id": version_id,
                "publication_snapshot_id": snapshot.id,
                "index_job_id": snapshot.index_job_id,
                "embedding_version": snapshot.embedding_version,
                "domain_release_id": snapshot.domain_release_id,
            }
            course_class = CourseClass(
                course_id=course_id,
                code="R3B-ONLY",
                name="R3-B 单班",
                created_by=teacher_id,
            )
            db.add(course_class)
            await db.flush()
            db.add(ClassMember(class_id=course_class.id, user_id=student_id))
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="R3-B release",
                status="published",
                manifest={
                    "materials": [material_version.material_id],
                    "material_version_ids": [version_id],
                    "publication_snapshots": [pin],
                },
                domain_release_id=snapshot.domain_release_id,
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(release)
            await db.flush()
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=course_class.id,
                course_release_id=release.id,
                status="active",
                assigned_by=teacher_id,
            )
            db.add(assignment)

            unpinned_version = MaterialVersion(
                material_id=material_version.material_id,
                version_no=material_version.version_no + 1,
                status="parsed",
                original_filename="synthetic-unpinned.pdf",
                sha256="a" * 64,
                size_bytes=1,
                content_type="application/pdf",
                object_key=f"synthetic/{new_ulid()}.pdf",
                created_by=teacher_id,
            )
            same_course_material = Material(
                course_id=course_id,
                title="合成未发布课程快照的资料",
                material_type="slides",
                visibility="published",
                status="active",
                created_by=teacher_id,
            )
            db.add_all([unpinned_version, same_course_material])
            await db.flush()
            same_course_version = MaterialVersion(
                material_id=same_course_material.id,
                version_no=1,
                status="parsed",
                original_filename="synthetic-other-material.pdf",
                sha256="b" * 64,
                size_bytes=1,
                content_type="application/pdf",
                object_key=f"synthetic/{new_ulid()}.pdf",
                created_by=teacher_id,
            )
            other_course_material = Material(
                course_id=other_course_id,
                title="另一课程合成资料",
                material_type="slides",
                visibility="published",
                status="active",
                created_by=teacher_id,
            )
            db.add_all([same_course_version, other_course_material])
            await db.flush()
            other_course_version = MaterialVersion(
                material_id=other_course_material.id,
                version_no=1,
                status="parsed",
                original_filename="synthetic-foreign-course.pdf",
                sha256="c" * 64,
                size_bytes=1,
                content_type="application/pdf",
                object_key=f"synthetic/{new_ulid()}.pdf",
                created_by=teacher_id,
            )
            db.add(other_course_version)
            await db.commit()
            return (
                course_class.id,
                assignment.id,
                release.id,
                material_version.material_id,
                other_course_id,
                unpinned_version.id,
                same_course_version.id,
                other_course_version.id,
            )

    (
        class_id,
        assignment_id,
        release_id,
        material_id,
        other_course_id,
        unpinned_version_id,
        same_course_version_id,
        other_course_version_id,
    ) = asyncio.run(seed_assignment())
    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    chapter_id = outline.json()["data"][0]["id"]
    _login(client, "ms@uni.edu")
    created = client.post(
        "/api/v1/learning-sessions",
        json={
            "course_id": course_id,
            "material_version_id": version_id,
            "chapter_object_id": chapter_id,
        },
    )
    assert created.status_code == 201
    learning_id = created.json()["data"]["id"]

    for rejected_version_id, expected_error in (
        (unpinned_version_id, "MATERIAL_VERSION_NOT_IN_ASSIGNED_RELEASE"),
        (same_course_version_id, "MATERIAL_VERSION_NOT_IN_ASSIGNED_RELEASE"),
        (other_course_version_id, "MATERIAL_VERSION_NOT_FOUND"),
    ):
        rejected = client.post(
            "/api/v1/learning-sessions",
            json={
                "course_id": course_id,
                "material_version_id": rejected_version_id,
            },
        )
        assert rejected.status_code == 404
        assert rejected.json()["error"]["code"] == expected_error

    cross_course = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": other_course_id, "material_version_id": version_id},
    )
    assert cross_course.status_code == 404

    async def load_binding() -> tuple[str | None, str | None]:
        async with session_factory() as db:
            learning = await db.get(LearningSession, learning_id)
            return learning.course_release_assignment_id, learning.course_release_id

    assert asyncio.run(load_binding()) == (assignment_id, release_id)

    async def reject_mismatched_material() -> None:
        from app.core.errors import ApiError
        from app.modules.tutor.service import resolve_learning_release_binding

        async with session_factory() as db:
            with pytest.raises(ApiError) as exc_info:
                await resolve_learning_release_binding(
                    db,
                    user_id=student_id,
                    course_id=course_id,
                    material_id="not-in-release",
                    material_version_id=version_id,
                )
            assert exc_info.value.status_code == 404
            assert exc_info.value.code == "MATERIAL_VERSION_NOT_IN_ASSIGNED_RELEASE"

    asyncio.run(reject_mismatched_material())

    async def reject_invalid_release_without_legacy_fallback() -> None:
        from app.core.errors import ApiError
        from app.db.models import CourseRelease
        from app.modules.courses.service import resolve_active_student_course_release

        async with session_factory() as db:
            release = await db.get(CourseRelease, release_id)
            assert release is not None
            release.status = "draft"
            await db.flush()
            with pytest.raises(ApiError) as exc_info:
                await resolve_active_student_course_release(
                    db, user_id=student_id, course_id=course_id
                )
            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "COURSE_RELEASE_ASSIGNMENT_INVALID"
            release.status = "published"
            await db.commit()

    asyncio.run(reject_invalid_release_without_legacy_fallback())

    from app.modules.memory.service import record_evidence

    async def record_and_load_evidence() -> tuple[str | None, str | None]:
        async with session_factory() as db:
            await record_evidence(
                db,
                user_id=student_id,
                course_id=course_id,
                knowledge_points=["tutor:release-binding"],
                question_version_id=learning_id,
                attempt_id=learning_id,
                source_type="practice",
                hints_used=0,
                correct=True,
            )
            evidence = await db.scalar(
                select(LearningEvidence).where(LearningEvidence.attempt_id == learning_id)
            )
            assert evidence is not None
            await db.commit()
            return evidence.course_release_assignment_id, evidence.course_release_id

    assert asyncio.run(record_and_load_evidence()) == (assignment_id, release_id)

    async def reject_mismatched_evidence_binding() -> None:
        async with session_factory() as db:
            with pytest.raises(ValueError, match="必须与来源会话绑定一致"):
                await record_evidence(
                    db,
                    user_id=student_id,
                    course_id=course_id,
                    knowledge_points=["tutor:wrong-release"],
                    question_version_id=learning_id,
                    attempt_id=learning_id,
                    source_type="practice",
                    hints_used=0,
                    correct=True,
                    course_release_assignment_id="wrong-assignment",
                    course_release_id="wrong-release",
                )

    asyncio.run(reject_mismatched_evidence_binding())

    async def rotate_assignment() -> None:
        from datetime import UTC, datetime

        async with session_factory() as db:
            previous = await db.get(CourseReleaseAssignment, assignment_id)
            previous_release = await db.get(CourseRelease, release_id)
            assert previous is not None and previous_release is not None
            previous.status = "closed"
            previous.closed_at = datetime.now(UTC)
            previous.close_reason = "R3-B recovery pin test"
            previous_release.status = "deprecated"
            replacement = CourseRelease(
                course_id=course_id,
                version_no=2,
                name="R3-B replacement release",
                status="published",
                manifest={"materials": [material_id]},
                created_by=teacher_id,
                published_by=teacher_id,
            )
            db.add(replacement)
            await db.flush()
            db.add(
                CourseReleaseAssignment(
                    course_id=course_id,
                    class_id=class_id,
                    course_release_id=replacement.id,
                    status="active",
                    assigned_by=teacher_id,
                    supersedes_id=assignment_id,
                )
            )
            await db.commit()

    asyncio.run(rotate_assignment())
    recovered = client.get(f"/api/v1/learning-sessions/{learning_id}")
    assert recovered.status_code == 200
    response = client.post(
        f"/api/v1/learning-sessions/{learning_id}/responses",
        json={
            "state_version": recovered.json()["data"]["state_version"],
            "content": "继续",
        },
    )
    assert response.status_code == 200
    assert asyncio.run(load_binding()) == (assignment_id, release_id)


def test_learning_session_rejects_ambiguous_release_assignment(client) -> None:
    import asyncio

    from app.db.models import (
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
        MaterialVersion,
    )
    from app.db.session import session_factory

    course_id, student_id, version_id = _prepare(client, publish=True)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def seed_assignments() -> None:
        async with session_factory() as db:
            material_version = await db.get(MaterialVersion, version_id)
            assert material_version is not None
            for index in range(2):
                course_class = CourseClass(
                    course_id=course_id,
                    code=f"R3B-{index}",
                    name=f"R3-B 班级 {index}",
                    created_by=teacher_id,
                )
                db.add(course_class)
                await db.flush()
                db.add(ClassMember(class_id=course_class.id, user_id=student_id))
                release = CourseRelease(
                    course_id=course_id,
                    version_no=index + 1,
                    name=f"R3-B release {index}",
                    status="published",
                    manifest={"materials": [material_version.material_id]},
                    created_by=teacher_id,
                    published_by=teacher_id,
                )
                db.add(release)
                await db.flush()
                db.add(
                    CourseReleaseAssignment(
                        course_id=course_id,
                        class_id=course_class.id,
                        course_release_id=release.id,
                        status="active",
                        assigned_by=teacher_id,
                    )
                )
            await db.commit()

    asyncio.run(seed_assignments())
    _login(client, "ms@uni.edu")
    response = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS"


def test_learning_task_rejects_unknown_action(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    created = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    )
    session_id = created.json()["data"]["id"]
    response = client.post(
        f"/api/v1/student/learning/tasks/{session_id}/respond",
        json={
            "state_version": created.json()["data"]["state_version"],
            "content": "继续",
            "action": "complete_task",
        },
    )
    assert response.status_code == 422


def test_learning_task_pause_resume_is_versioned(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    created = client.post(
        "/api/v1/learning-sessions",
        json={"course_id": course_id, "material_version_id": version_id},
    ).json()["data"]
    paused = client.post(
        f"/api/v1/student/learning/tasks/{created['id']}/pause",
        json={"state_version": created["state_version"]},
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "paused"
    assert paused.json()["data"]["allowed_actions"] == ["RESUME"]
    home = client.get("/api/v1/student/home").json()["data"]
    assert home["current_task"]["task_id"] == created["id"]
    assert home["next_actions"] == ["RESUME_TASK"]
    blocked_response = client.post(
        f"/api/v1/student/learning/tasks/{created['id']}/respond",
        json={"state_version": paused.json()["data"]["state_version"], "content": "继续"},
    )
    assert blocked_response.status_code == 409
    assert blocked_response.json()["error"]["code"] == "SESSION_CLOSED"
    stale_resume = client.post(
        f"/api/v1/student/learning/tasks/{created['id']}/resume",
        json={"state_version": created["state_version"]},
    )
    assert stale_resume.status_code == 409
    resumed = client.post(
        f"/api/v1/student/learning/tasks/{created['id']}/resume",
        json={"state_version": paused.json()["data"]["state_version"]},
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["status"] == "active"
    assert resumed.json()["data"]["allowed_actions"] == ["RESPOND_TASK"]


def test_selected_paragraph_turn_uses_pinned_local_context_and_binds_idempotency(
    client, monkeypatch
) -> None:
    import asyncio

    from app.db.models import ChatTurn
    from app.db.session import session_factory
    from app.modules.tutor import service as tutor_service

    course_id, student_id, version_id = _prepare(client, publish=True)
    _, pointer_id, other_pointer_id, figure_pointer_id, excerpt = (
        _seed_pinned_paragraph_chat(
            client, course_id=course_id, student_id=student_id, version_id=version_id
        )
    )
    _login(client, "ms@uni.edu")
    session_response = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["data"]["id"]

    def forbidden_provider(*args, **kwargs):
        raise AssertionError("selected paragraph must stay on deterministic local path")

    monkeypatch.setattr(tutor_service.knowledge_service, "hybrid_search", forbidden_provider)
    monkeypatch.setattr(tutor_service, "generate_grounded_answer", forbidden_provider)
    monkeypatch.setattr(tutor_service, "call_model", forbidden_provider)

    endpoint = f"/api/v1/chat/sessions/{session_id}/turns"
    body = {
        "content": "什么是操作性定义？",
        "client_turn_id": "paragraph-context-0001",
        "selected_evidence_pointer_ids": [pointer_id],
    }
    first = client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    first_events = _parse_sse_events(first.content)
    citation = next(data for name, data in first_events if name == "citation")
    assert citation["evidence_pointer_id"] == pointer_id
    assert citation["provenance"] is None or isinstance(citation["provenance"], dict)
    answer = "".join(data["text"] for name, data in first_events if name == "delta")
    assert excerpt.split("。", maxsplit=1)[0] in answer
    done = next(data for name, data in first_events if name == "done")
    assert done["saved"] is True
    assert done["unsupported_count"] == 0

    saved = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert saved.status_code == 200
    student_turn, tutor_turn = saved.json()["data"]["turns"][-2:]
    assert student_turn["citations"] == [{"evidence_pointer_id": pointer_id}]
    assert tutor_turn["citations"][0]["evidence_pointer_id"] == pointer_id
    assert tutor_turn["verification"]["generation_provider"] == "internal_extractive"
    assert tutor_turn["verification"]["unsupported_count"] == 0
    assert tutor_turn["verification"]["object_context"] == {
        "type": "paragraph",
        "evidence_pointer_id": pointer_id,
        "material_version_id": version_id,
        "publication_snapshot_id": tutor_turn["citations"][0]["publication_snapshot_id"],
        "index_job_id": tutor_turn["citations"][0]["index_job_id"],
    }

    replay = client.post(endpoint, json=body)
    assert replay.status_code == 200, replay.text
    replay_events = _parse_sse_events(replay.content)
    replay_done = next(data for name, data in replay_events if name == "done")
    assert replay_done["replayed"] is True
    assert "".join(data["text"] for name, data in replay_events if name == "delta") == answer

    mismatch = client.post(
        endpoint,
        json={**body, "selected_evidence_pointer_ids": [other_pointer_id]},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "TURN_IDEMPOTENCY_CONFLICT"

    figure = client.post(
        endpoint,
        json={
            "content": "请解释这个图像",
            "client_turn_id": "paragraph-context-figure-0001",
            "selected_evidence_pointer_ids": [figure_pointer_id],
        },
    )
    assert figure.status_code == 200, figure.text
    figure_events = _parse_sse_events(figure.content)
    figure_done = next(data for name, data in figure_events if name == "done")
    assert figure_done["refusal"] is True
    figure_saved = client.get(f"/api/v1/chat/sessions/{session_id}").json()["data"]["turns"][-1]
    assert figure_saved["verification"]["object_context"]["type"] == "figure"

    async def saved_turn_count() -> int:
        async with session_factory() as db:
            return await db.scalar(
                select(func.count()).select_from(ChatTurn).where(
                    ChatTurn.session_id == session_id
                )
            )

    from sqlalchemy import func, select

    assert asyncio.run(saved_turn_count()) == 4


def test_selected_paragraph_turn_rejects_inexact_scope_source_and_build(client) -> None:
    import asyncio
    from copy import deepcopy

    from sqlalchemy import func, select

    from app.db.models import (
        ChatTurn,
        CourseRelease,
        CourseReleaseAssignment,
        EvidencePointer,
        Job,
        KnowledgeObject,
        MaterialVersion,
        PublicationSnapshot,
        RetrievalUnit,
    )
    from app.db.session import session_factory

    course_id, student_id, version_id = _prepare(client, publish=True)
    assignment_id, pointer_id, other_pointer_id, _, _ = _seed_pinned_paragraph_chat(
        client, course_id=course_id, student_id=student_id, version_id=version_id
    )
    foreign_course_id = client.post(
        "/api/v1/courses",
        json={"title": "合成隔离课程", "term": "2026春"},
    ).json()["data"]["id"]
    _login(client, "ms@uni.edu")
    session_response = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["data"]["id"]
    endpoint = f"/api/v1/chat/sessions/{session_id}/turns"

    async def snapshot_state() -> tuple[str, str, str, str]:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            release = await db.scalar(
                select(CourseRelease)
                .join(CourseReleaseAssignment)
                .where(CourseReleaseAssignment.id == assignment_id)
            )
            assert release is not None
            assert pointer.retrieval_unit_id is not None and pointer.index_job_id is not None
            return (
                pointer.retrieval_unit_id,
                pointer.source_object_id,
                release.id,
                pointer.index_job_id,
            )

    retrieval_unit_id, source_object_id, release_id, index_job_id = asyncio.run(snapshot_state())

    async def create_other_material_version() -> str:
        async with session_factory() as db:
            current = await db.get(MaterialVersion, version_id)
            assert current is not None
            other = MaterialVersion(
                material_id=current.material_id,
                version_no=current.version_no + 1,
                status="parsed",
                created_by=current.created_by,
            )
            db.add(other)
            await db.flush()
            other_id = other.id
            await db.commit()
            return other_id

    other_version_id = asyncio.run(create_other_material_version())

    async def pointer_update(**fields) -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            for key, value in fields.items():
                setattr(pointer, key, value)
            await db.commit()

    async def unit_update(**fields) -> None:
        async with session_factory() as db:
            unit = await db.get(RetrievalUnit, retrieval_unit_id)
            assert unit is not None
            for key, value in fields.items():
                setattr(unit, key, value)
            await db.commit()

    async def source_type_update(value: str) -> None:
        async with session_factory() as db:
            source = await db.get(KnowledgeObject, source_object_id)
            assert source is not None
            source.type = value
            await db.commit()

    async def manifest_update(mutator) -> dict:
        async with session_factory() as db:
            release = await db.get(CourseRelease, release_id)
            assert release is not None
            original = deepcopy(release.manifest)
            release.manifest = mutator(deepcopy(release.manifest))
            await db.commit()
            return original

    def request(
        pointer: str,
        suffix: str,
        *,
        expected_status: int = 404,
        expected_code: str = "EVIDENCE_NOT_FOUND",
    ):
        response = client.post(
            endpoint,
            json={
                "content": "请解释这个段落",
                "client_turn_id": f"paragraph-reject-{suffix}",
                "selected_evidence_pointer_ids": [pointer],
            },
        )
        assert response.status_code == expected_status, response.text
        assert response.json()["error"]["code"] == expected_code

    async def clear_pointer_pin() -> None:
        await pointer_update(
            publication_snapshot_id=None,
            index_job_id=None,
            domain_release_id=None,
        )

    asyncio.run(clear_pointer_pin())
    request(pointer_id, "legacy-pointer-pin")
    async def restore_pointer_pin() -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            snapshot = await db.scalar(
                select(PublicationSnapshot).where(
                    PublicationSnapshot.material_version_id == version_id
                )
            )
            assert pointer is not None and snapshot is not None
            pointer.publication_snapshot_id = snapshot.id
            pointer.index_job_id = snapshot.index_job_id
            pointer.domain_release_id = snapshot.domain_release_id
            await db.commit()

    asyncio.run(restore_pointer_pin())

    # Reader publication readability is rechecked for every selected paragraph.
    async def set_index_job_status(status: str) -> None:
        async with session_factory() as db:
            job = await db.get(Job, index_job_id)
            assert job is not None
            job.status = status
            await db.commit()

    asyncio.run(set_index_job_status("failed"))
    request(pointer_id, "reader-index-job-revoked")
    asyncio.run(set_index_job_status("succeeded"))

    original_manifest = asyncio.run(
        manifest_update(lambda manifest: {**manifest, "publication_snapshots": []})
    )
    request(pointer_id, "missing-release-pin")
    asyncio.run(manifest_update(lambda _manifest: original_manifest))

    def partial_pin(manifest):
        pin = dict(manifest["publication_snapshots"][0])
        pin.pop("index_job_id")
        return {**manifest, "publication_snapshots": [pin]}

    partial_original = asyncio.run(manifest_update(partial_pin))
    request(pointer_id, "partial-release-pin")
    asyncio.run(manifest_update(lambda _manifest: partial_original))

    def wrong_pin(manifest):
        pins = list(manifest["publication_snapshots"])
        pins[0] = {**pins[0], "publication_snapshot_id": "x" * 26}
        return {**manifest, "publication_snapshots": pins}

    wrong_pin_original = asyncio.run(manifest_update(wrong_pin))
    request(pointer_id, "wrong-release-pin")
    asyncio.run(manifest_update(lambda _manifest: wrong_pin_original))

    asyncio.run(source_type_update("table"))
    request(pointer_id, "wrong-source-type")
    asyncio.run(source_type_update("paragraph"))

    async def pointer_excerpt_update(value: str) -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            assert pointer is not None
            pointer.excerpt = value
            await db.commit()

    from app.db.models import EvidencePointer as _Pointer

    async def original_excerpt() -> str:
        async with session_factory() as db:
            pointer = await db.get(_Pointer, pointer_id)
            assert pointer is not None
            return pointer.excerpt

    saved_excerpt = asyncio.run(original_excerpt())
    asyncio.run(pointer_excerpt_update(""))
    request(pointer_id, "empty-pointer-excerpt")
    asyncio.run(pointer_excerpt_update(saved_excerpt))

    for label, fields in (
        ("wrong-ru-type", {"unit_type": "table_cells"}),
        ("wrong-ru-version", {"material_version_id": other_version_id}),
        ("wrong-ru-status", {"status": "failed"}),
        ("wrong-ru-build", {"build_version": "v1-unrelated-job"}),
        ("wrong-ru-domain", {"domain_release_id": None}),
    ):
        async def mutate_unit(unit_fields: dict) -> dict:
            async with session_factory() as db:
                unit = await db.get(RetrievalUnit, retrieval_unit_id)
                assert unit is not None
                original = {field: getattr(unit, field) for field in unit_fields}
                for field, value in unit_fields.items():
                    setattr(unit, field, value)
                await db.commit()
                return original

        original = asyncio.run(mutate_unit(fields))
        request(pointer_id, label)
        asyncio.run(unit_update(**original))

    async def set_wrong_ru_source() -> None:
        async with session_factory() as db:
            pointer = await db.get(EvidencePointer, pointer_id)
            other = await db.get(EvidencePointer, other_pointer_id)
            unit = await db.get(RetrievalUnit, retrieval_unit_id)
            assert pointer is not None and other is not None and unit is not None
            unit.source_object_id = other.source_object_id
            await db.commit()

    asyncio.run(set_wrong_ru_source())
    request(pointer_id, "wrong-ru-source")
    async def restore_ru_source() -> None:
        async with session_factory() as db:
            unit = await db.get(RetrievalUnit, retrieval_unit_id)
            assert unit is not None
            unit.source_object_id = source_object_id
            await db.commit()
    asyncio.run(restore_ru_source())

    asyncio.run(pointer_update(course_id=foreign_course_id))
    request(pointer_id, "cross-course-pointer")
    asyncio.run(pointer_update(course_id=course_id))

    async def revoke_assignment() -> None:
        async with session_factory() as db:
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert assignment is not None
            assignment.status = "revoked"
            await db.commit()

    asyncio.run(revoke_assignment())
    request(
        pointer_id,
        "revoked-scope",
        expected_status=404,
        expected_code="CHAT_SESSION_NOT_FOUND",
    )

    async def saved_turn_count() -> int:
        async with session_factory() as db:
            return await db.scalar(
                select(func.count()).select_from(ChatTurn).where(
                    ChatTurn.session_id == session_id
                )
            )

    assert asyncio.run(saved_turn_count()) == 0
