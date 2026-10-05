import json

from tests.test_materials import _login, _setup_course, _upload
from tests.test_search import TWO_CHAPTER_PDF


def _prepare(client, *, publish=True):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
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
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

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
    assert "回到教材" in repair["message"]
    assert respond("Independent variable control improves internal validity in experiments.")[
        "state"
    ] == "check"
    repair = respond("我不知道")
    assert repair["state"] == "hint"
    assert "不急着判断对错" in repair["message"]
    example = respond("我不知道")
    assert example["state"] == "practice"
    assert example["action"] == "show_example"
    assert "当前教材段落没有明确标记的例子" in example["message"]
    assert "研究者控制参与者" not in example["message"]


def test_active_formal_assessment_fails_closed_for_learning_response(client) -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.db.models import Assessment
    from app.db.session import session_factory
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
    ).json()["data"]

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
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert attempt.status_code == 201, attempt.text

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

    from app.db.models import (
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
        LearningEvidence,
        LearningSession,
        MaterialVersion,
    )
    from app.db.session import session_factory

    course_id, student_id, version_id = _prepare(client, publish=True)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def seed_assignment() -> tuple[str, str, str, str]:
        async with session_factory() as db:
            material_version = await db.get(MaterialVersion, version_id)
            assert material_version is not None
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
                manifest={"materials": [material_version.material_id]},
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
            return course_class.id, assignment.id, release.id, material_version.material_id

    class_id, assignment_id, release_id, material_id = asyncio.run(seed_assignment())
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
                )
            assert exc_info.value.status_code == 404
            assert exc_info.value.code == "MATERIAL_VERSION_NOT_IN_ASSIGNED_RELEASE"

    asyncio.run(reject_mismatched_material())

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
