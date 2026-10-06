import time

import pytest
from pydantic import ValidationError

from app.modules.question_agent.router import BranchMerge
from tests.conftest import make_pdf
from tests.test_materials import _login, _setup_course, _upload
from tests.test_question_bank import QUESTION_BODY

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


def test_branch_merge_rejects_blank_confirmation_note() -> None:
    with pytest.raises(ValidationError, match="合并说明不能为空"):
        BranchMerge(note=" \t ", merge_key="merge-branch-blank", confirmed=True)


def _prepare_indexed(client):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    for kind in ("parse", "embed"):
        response = client.post(f"/api/v1/material-versions/{version_id}/{kind}")
        assert response.status_code == 202
        _wait_job(client, response.json()["data"]["job_id"])
    return course_id, student_id, version_id


def _wait_job(client, job_id, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.3)
    raise AssertionError("任务超时")


def test_question_generation_produces_reviewable_drafts(client) -> None:
    course_id, _, _ = _prepare_indexed(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/question-generation-jobs",
        json={"count": 3, "question_types": ["single"]},
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]

    job = _wait_job(client, job_id)
    assert job["status"] == "succeeded", job

    drafts = client.get(
        f"/api/v1/courses/{course_id}/question-generation-jobs/{job_id}/drafts"
    )
    assert drafts.status_code == 200
    data = drafts.json()["data"]
    assert data["job_status"] == "succeeded"
    assert len(data["drafts"]) >= 1
    first = data["drafts"][0]
    assert first["status"] is not None
    assert first["type"] == "single"
    assert first["evidence_ids"]

    # 候选题不能自动发布：必须是draft
    assert first["status"] == "draft"

    # 重复生成不产生相同题干
    response2 = client.post(
        f"/api/v1/courses/{course_id}/question-generation-jobs",
        json={"count": 3, "question_types": ["single"]},
    )
    job2 = _wait_job(client, response2.json()["data"]["job_id"])
    assert job2["status"] == "succeeded", job2
    drafts2 = client.get(
        f"/api/v1/courses/{course_id}/question-generation-jobs/{response2.json()['data']['job_id']}/drafts"
    ).json()["data"]
    stems1 = {d["stem"] for d in data["drafts"]}
    stems2 = {d["stem"] for d in drafts2["drafts"]}
    assert not (stems1 & stems2), "语义去重失败：跨批次出现相同题干"


def test_generation_requires_teacher_and_parsed_material(client) -> None:
    course_id, _, _ = _prepare_indexed(client)
    _login(client, "ms@uni.edu")
    forbidden = client.post(
        f"/api/v1/courses/{course_id}/question-generation-jobs",
        json={"count": 2},
    )
    assert forbidden.status_code == 404


def test_review_task_created_on_wrong_answer(client) -> None:
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    for kind in ("parse", "embed"):
        response = client.post(f"/api/v1/material-versions/{version_id}/{kind}")
        assert response.status_code == 202
        job = _wait_job(client, response.json()["data"]["job_id"])
        assert job["status"] == "succeeded", job
    client.post(f"/api/v1/material-versions/{version_id}/publish")

    created = client.post(
        f"/api/v1/courses/{course_id}/questions", json=QUESTION_BODY
    )
    question_id = created.json()["data"]["id"]
    client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "ok"},
    )
    client.post(f"/api/v1/questions/{question_id}/publish")

    assessment = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "错题归因测验",
            "question_ids": [question_id],
            "ai_policy": "disabled",
        },
    )
    assessment_id = assessment.json()["data"]["id"]
    client.post(f"/api/v1/assessments/{assessment_id}/publish")

    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = attempt.json()["data"]["attempt_id"]
    student_view = client.get(f"/api/v1/assessments/{assessment_id}")
    qv_id = student_view.json()["data"]["items"][0]["question_version_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["B"]}},
    )
    submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submit.status_code == 200
    assert submit.json()["data"]["score"] == 0

    tasks = client.get("/api/v1/review-tasks?due_only=false")
    assert tasks.status_code == 200
    task_list = tasks.json()["data"]
    assert len(task_list) == 1
    assert task_list[0]["reason"] == "wrong_answer"
    assert task_list[0]["question_version_id"] == qv_id

    complete = client.post(f"/api/v1/review-tasks/{task_list[0]['id']}/complete")
    assert complete.status_code == 200
    assert complete.json()["data"]["status"] == "done"

    remaining = client.get("/api/v1/review-tasks")
    assert remaining.json()["data"] == []


def test_branch_conversation_isolated_and_merge_confirmed_only(client) -> None:
    course_id, _, _ = _prepare_indexed(client)
    _login(client, "mt@uni.edu")
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    turn = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={"content": "internal validity 是什么", "client_turn_id": "branch-base-1"},
    )
    assert turn.status_code == 200
    assert "event: done" in turn.text
    turns = client.get(f"/api/v1/chat/sessions/{session['id']}").json()["data"]["turns"]
    source_turn = next(item for item in turns if item["role"] == "student")
    source_turn_id = source_turn["id"]

    branch = client.post(
        f"/api/v1/chat/sessions/{session['id']}/branches",
        json={
            "source_turn_id": source_turn_id,
            "selection": "internal validity",
            "title": "什么是内部效度",
        },
    )
    assert branch.status_code == 201
    branch_id = branch.json()["data"]["id"]

    branch_turn = client.post(
        f"/api/v1/chat/sessions/{branch_id}/turns",
        json={
            "content": "能举个内部效度的例子吗",
            "client_turn_id": "branch-turn-1",
        },
    )
    assert branch_turn.status_code == 200

    merge = client.post(
        f"/api/v1/chat/sessions/{session['id']}/branches/{branch_id}/merge",
        json={"note": "已理解内部效度概念", "confirmed": True, "merge_key": "merge-branch-001"},
    )
    assert merge.status_code == 200
    receipt = merge.json()["data"]
    assert receipt["result_turn_id"]
    assert receipt["replayed"] is False

    parent_detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    merged_turn = next(
        t for t in parent_detail.json()["data"]["turns"] if t["id"] == receipt["result_turn_id"]
    )
    assert merged_turn["role"] == "student"
    assert "学生确认带回的选区" in merged_turn["content"]
    assert "分支结论" not in merged_turn["content"]

    branch_detail = client.get(f"/api/v1/chat/sessions/{branch_id}")
    assert branch_detail.json()["data"]["status"] == "closed"

    merge_again = client.post(
        f"/api/v1/chat/sessions/{session['id']}/branches/{branch_id}/merge",
        json={"note": "已理解内部效度概念", "confirmed": True, "merge_key": "merge-branch-001"},
    )
    assert merge_again.status_code == 200
    assert merge_again.json()["data"]["replayed"] is True
    assert merge_again.json()["data"]["result_turn_id"] == receipt["result_turn_id"]

    changed_payload = client.post(
        f"/api/v1/chat/sessions/{session['id']}/branches/{branch_id}/merge",
        json={"note": "改写合并文本", "confirmed": True, "merge_key": "merge-branch-001"},
    )
    assert changed_payload.status_code == 409
    assert changed_payload.json()["error"]["code"] == "BRANCH_MERGE_CONFLICT"

    changed_key = client.post(
        f"/api/v1/chat/sessions/{session['id']}/branches/{branch_id}/merge",
        json={"note": "已理解内部效度概念", "confirmed": True, "merge_key": "merge-branch-002"},
    )
    assert changed_key.status_code == 409
    assert changed_key.json()["error"]["code"] == "BRANCH_MERGE_CONFLICT"


def test_branch_rejects_cross_session_source_and_unconfirmed_merge(client) -> None:
    course_id, _, _ = _prepare_indexed(client)
    _login(client, "mt@uni.edu")
    parent = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    other = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]

    parent_turn = client.post(
        f"/api/v1/chat/sessions/{parent['id']}/turns",
        json={"content": "internal validity 是什么", "client_turn_id": "branch-parent-01"},
    )
    other_turn = client.post(
        f"/api/v1/chat/sessions/{other['id']}/turns",
        json={"content": "between subjects design 是什么", "client_turn_id": "branch-other-01"},
    )
    assert parent_turn.status_code == 200
    assert other_turn.status_code == 200

    parent_student_turn = next(
        turn
        for turn in client.get(f"/api/v1/chat/sessions/{parent['id']}").json()["data"]["turns"]
        if turn["role"] == "student"
    )
    other_student_turn = next(
        turn
        for turn in client.get(f"/api/v1/chat/sessions/{other['id']}").json()["data"]["turns"]
        if turn["role"] == "student"
    )

    cross_session_source = client.post(
        f"/api/v1/chat/sessions/{parent['id']}/branches",
        json={"source_turn_id": other_student_turn["id"], "selection": "between subjects"},
    )
    assert cross_session_source.status_code == 404
    assert cross_session_source.json()["error"]["code"] == "BRANCH_SOURCE_NOT_FOUND"

    missing_selection = client.post(
        f"/api/v1/chat/sessions/{parent['id']}/branches",
        json={"source_turn_id": parent_student_turn["id"], "selection": "not in source"},
    )
    assert missing_selection.status_code == 404
    assert missing_selection.json()["error"]["code"] == "BRANCH_SOURCE_NOT_FOUND"

    branch = client.post(
        f"/api/v1/chat/sessions/{parent['id']}/branches",
        json={"source_turn_id": parent_student_turn["id"], "selection": "internal validity"},
    )
    assert branch.status_code == 201
    branch_id = branch.json()["data"]["id"]
    unconfirmed = client.post(
        f"/api/v1/chat/sessions/{parent['id']}/branches/{branch_id}/merge",
        json={"note": "用户尚未确认", "confirmed": False, "merge_key": "merge-branch-no"},
    )
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["error"]["code"] == "BRANCH_MERGE_CONFIRMATION_REQUIRED"


def test_branch_inherits_release_binding_and_keeps_it_after_assignment_rotation(client) -> None:
    import asyncio
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
        Job,
        MaterialVersion,
        PublicationSnapshot,
        RetrievalUnit,
        UserPreference,
    )
    from app.db.session import session_factory
    from tests.conftest import create_user_sync, publish_course_release_for_test

    course_id, student_id, version_id = _prepare_indexed(client)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def read_material_id() -> str:
        async with session_factory() as db:
            version = await db.get(MaterialVersion, version_id)
            assert version is not None
            return version.material_id

    material_id = asyncio.run(read_material_id())

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

    def build_domain_index(domain_release_id: str) -> str:
        response = client.post(
            f"/api/v1/material-versions/{version_id}/embed?domain_release_id={domain_release_id}"
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["data"]["job_id"]
        job = _wait_job(client, job_id)
        assert job["status"] == "succeeded", job
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
    release_response = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "Branch parent pinned release",
            "material_ids": [material_id],
            "domain_release_id": old_domain_id,
        },
    )
    assert release_response.status_code == 201, release_response.text
    parent_release = release_response.json()["data"]
    release_id = parent_release["id"]
    pinned = parent_release["manifest"]["publication_snapshots"][0]
    assert pinned["publication_snapshot_id"] == old_snapshot_id
    assert pinned["index_job_id"] == old_job_id
    publish_course_release_for_test(client, course_id, release_id)

    async def seed_release_assignment() -> tuple[str, str]:
        async with session_factory() as db:
            course_class = CourseClass(
                course_id=course_id,
                code="BRANCH-PIN",
                name="Branch 固定版本班",
                created_by=teacher_id,
            )
            db.add(course_class)
            await db.flush()
            db.add(ClassMember(class_id=course_class.id, user_id=student_id))
            assignment = CourseReleaseAssignment(
                course_id=course_id,
                class_id=course_class.id,
                course_release_id=release_id,
                status="active",
                assigned_by=teacher_id,
            )
            db.add(assignment)
            await db.commit()
            return course_class.id, assignment.id

    class_id, assignment_id = asyncio.run(seed_release_assignment())
    _login(client, "ms@uni.edu")
    parent = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert parent.status_code == 201
    parent_id = parent.json()["data"]["id"]
    parent_turn_response = client.post(
        f"/api/v1/chat/sessions/{parent_id}/turns",
        json={"content": "教材问题", "client_turn_id": "branch-pin-parent-turn"},
    )
    assert parent_turn_response.status_code == 200
    student_turn = next(
        turn
        for turn in client.get(f"/api/v1/chat/sessions/{parent_id}").json()["data"]["turns"]
        if turn["role"] == "student"
    )
    created_branch = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches",
        json={"source_turn_id": student_turn["id"], "selection": "教材问题"},
    )
    assert created_branch.status_code == 201
    branch_id = created_branch.json()["data"]["id"]

    outsider_id = create_user_sync(email="branch-release-outsider@uni.edu")
    _login(client, "branch-release-outsider@uni.edu")
    cross_user = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches",
        json={"source_turn_id": student_turn["id"], "selection": "教材问题"},
    )
    assert cross_user.status_code == 404
    assert cross_user.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"
    assert outsider_id != student_id

    _login(client, "mt@uni.edu")
    new_domain_id = asyncio.run(seed_domain_release(2, old_domain_id))
    new_job_id = build_domain_index(new_domain_id)
    new_snapshot = publish_material(new_domain_id)
    assert new_snapshot["publication_snapshot_id"] != old_snapshot_id
    assert new_snapshot["index_job_id"] == new_job_id
    replacement_response = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "Branch replacement pinned release",
            "material_ids": [material_id],
            "domain_release_id": new_domain_id,
        },
    )
    assert replacement_response.status_code == 201, replacement_response.text
    replacement_release = replacement_response.json()["data"]
    replacement_release_id = replacement_release["id"]
    publish_course_release_for_test(client, course_id, replacement_release_id)

    async def rotate_assignment() -> str:
        async with session_factory() as db:
            old_assignment = await db.get(CourseReleaseAssignment, assignment_id)
            old_release = await db.get(CourseRelease, release_id)
            assert old_assignment is not None and old_release is not None
            old_assignment.status = "closed"
            old_assignment.closed_at = datetime.now(UTC)
            old_assignment.close_reason = "Branch child inheritance test"
            old_release.status = "deprecated"
            db.add(
                CourseReleaseAssignment(
                    course_id=course_id,
                    class_id=class_id,
                    course_release_id=replacement_release_id,
                    status="active",
                    assigned_by=teacher_id,
                    supersedes_id=assignment_id,
                )
            )
            await db.commit()
            new_assignment = await db.scalar(
                select(CourseReleaseAssignment).where(
                    CourseReleaseAssignment.class_id == class_id,
                    CourseReleaseAssignment.status == "active",
                )
            )
            assert new_assignment is not None
            return new_assignment.id

    new_assignment_id = asyncio.run(rotate_assignment())
    _login(client, "ms@uni.edu")
    recovered = client.get(f"/api/v1/chat/sessions/{branch_id}")
    assert recovered.status_code == 200
    branch_turn = client.post(
        f"/api/v1/chat/sessions/{branch_id}/turns",
        json={
            "content": "Explain internal validity in experiments.",
            "client_turn_id": "branch-pin-child-turn",
        },
    )
    assert branch_turn.status_code == 200
    child_data = client.get(f"/api/v1/chat/sessions/{branch_id}").json()["data"]
    claim = child_data["turns"][-1]["verification"]["domain_claim"]
    assert claim["status"] == "supported"
    assert claim["scope"]["course_release_assignment_id"] == assignment_id
    assert claim["scope"]["course_release_id"] == release_id
    assert claim["scope"]["domain_release_id"] == old_domain_id
    assert claim["scope"]["publication_snapshots"] == [pinned]
    assert claim["initial_evidence_refs"]

    async def assert_child_claim_uses_exact_parent_pins() -> None:
        async with session_factory() as db:
            tickets = (
                (
                    await db.execute(
                        select(EvidenceTicket).where(
                            EvidenceTicket.id.in_(claim["initial_evidence_refs"])
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert tickets
            assert all(ticket.pointer_id is not None for ticket in tickets)
            pointer_ids = {ticket.pointer_id for ticket in tickets if ticket.pointer_id}
            pointers = (
                (
                    await db.execute(
                        select(EvidencePointer).where(EvidencePointer.id.in_(pointer_ids))
                    )
                )
                .scalars()
                .all()
            )
            assert pointers
            assert all(
                pointer.material_version_id == version_id
                and pointer.publication_snapshot_id == old_snapshot_id
                and pointer.index_job_id == old_job_id
                and pointer.domain_release_id == old_domain_id
                for pointer in pointers
            )
            units = [await db.get(RetrievalUnit, pointer.retrieval_unit_id) for pointer in pointers]
            assert units and all(unit is not None for unit in units)
            assert all(
                unit.material_version_id == version_id
                and unit.domain_release_id == old_domain_id
                and unit.build_version == f"v1-{old_job_id}"
                and unit.status == "ready"
                for unit in units
            )
            old_domain = await db.get(DomainRelease, old_domain_id)
            old_snapshot_row = await db.get(PublicationSnapshot, old_snapshot_id)
            old_job = await db.get(Job, old_job_id)
            new_snapshot_row = await db.get(
                PublicationSnapshot, new_snapshot["publication_snapshot_id"]
            )
            new_job = await db.get(Job, new_job_id)
            parent_row = await db.get(ChatSession, parent_id)
            child_row = await db.get(ChatSession, branch_id)
            assert old_domain is not None and old_domain.status == "deprecated"
            assert old_snapshot_row is not None
            assert (
                old_snapshot_row.material_id,
                old_snapshot_row.material_version_id,
                old_snapshot_row.index_job_id,
                old_snapshot_row.domain_release_id,
            ) == (material_id, version_id, old_job_id, old_domain_id)
            assert old_snapshot_row.superseded_at is not None
            assert old_job is not None and old_job.status == "succeeded"
            assert old_job.kind == "material_embed"
            assert old_job.payload["material_version_id"] == version_id
            assert old_job.payload["domain_release_id"] == old_domain_id
            assert new_snapshot_row is not None
            assert new_snapshot_row.id != old_snapshot_id
            assert new_snapshot_row.index_job_id == new_job_id
            assert new_snapshot_row.domain_release_id == new_domain_id
            assert new_job is not None and new_job.status == "succeeded"
            assert new_job.payload["material_version_id"] == version_id
            assert new_job.payload["domain_release_id"] == new_domain_id
            assert parent_row is not None and child_row is not None
            assert (
                parent_row.course_release_assignment_id,
                parent_row.course_release_id,
            ) == (assignment_id, release_id)
            assert (
                child_row.course_release_assignment_id,
                child_row.course_release_id,
            ) == (assignment_id, release_id)
            assert replacement_release_id != release_id
            assert new_assignment_id != assignment_id

    asyncio.run(assert_child_claim_uses_exact_parent_pins())

    async def read_child_binding() -> tuple[str | None, str | None]:
        async with session_factory() as db:
            row = await db.get(ChatSession, branch_id)
            assert row is not None
            return row.course_release_assignment_id, row.course_release_id

    assert asyncio.run(read_child_binding()) == (assignment_id, release_id)
    assert replacement_release_id != release_id

    merged = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches/{branch_id}/merge",
        json={"note": "保留分支想法", "confirmed": True, "merge_key": "branch-pin-merge"},
    )
    assert merged.status_code == 200
    assert merged.json()["data"]["replayed"] is False
    assert asyncio.run(read_child_binding()) == (assignment_id, release_id)

    async def tighten_pinned_policy_and_broaden_replacements() -> None:
        async with session_factory() as db:
            pinned_release = await db.get(CourseRelease, release_id)
            replacement = await db.get(CourseRelease, replacement_release_id)
            assert pinned_release is not None and replacement is not None
            pinned_release.manifest = {
                **(pinned_release.manifest or {}),
                "teaching_policy": {
                    "allowed_actions": ["pause", "handoff"],
                    "max_hints": 0,
                },
            }
            replacement.manifest = {
                **(replacement.manifest or {}),
                "teaching_policy": {
                    "allowed_actions": [
                        "diagnose", "teach", "check", "hint", "practice",
                        "summarize", "pause", "handoff",
                    ],
                    "max_hints": 3,
                },
            }
            preference = await db.scalar(
                select(UserPreference).where(UserPreference.user_id == student_id)
            )
            if preference is None:
                db.add(
                    UserPreference(
                        user_id=student_id,
                        preferences={
                            "teaching_policy": {
                                "allowed_actions": [
                                    "diagnose", "teach", "check", "hint", "practice",
                                    "summarize", "pause", "handoff",
                                ],
                                "max_hints": 3,
                            },
                            "response_length": "DETAILED",
                            "example_order": "EXAMPLE_FIRST",
                        },
                    )
                )
            else:
                preference.preferences = {
                    **(preference.preferences or {}),
                    "teaching_policy": {
                        "allowed_actions": [
                            "diagnose", "teach", "check", "hint", "practice",
                            "summarize", "pause", "handoff",
                        ],
                        "max_hints": 3,
                    },
                    "response_length": "DETAILED",
                    "example_order": "EXAMPLE_FIRST",
                }
            await db.commit()

    asyncio.run(tighten_pinned_policy_and_broaden_replacements())
    pinned_policy_turn = client.post(
        f"/api/v1/chat/sessions/{parent_id}/turns",
        json={"content": "受限课程版本的追问", "client_turn_id": "branch-pin-policy-turn"},
    )
    assert pinned_policy_turn.status_code == 403
    assert pinned_policy_turn.json()["error"]["code"] == "TEACHING_POLICY_RESTRICTED"
    pinned_policy_branch = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches",
        json={"source_turn_id": student_turn["id"], "selection": "教材问题"},
    )
    assert pinned_policy_branch.status_code == 403
    assert pinned_policy_branch.json()["error"]["code"] == "TEACHING_POLICY_RESTRICTED"
    pinned_policy_merge = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches/{branch_id}/merge",
        json={"note": "保留分支想法", "confirmed": True, "merge_key": "branch-pin-merge"},
    )
    assert pinned_policy_merge.status_code == 403
    assert pinned_policy_merge.json()["error"]["code"] == "TEACHING_POLICY_RESTRICTED"

    async def revoke_membership() -> None:
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

    asyncio.run(revoke_membership())
    assert client.get(f"/api/v1/chat/sessions/{branch_id}").status_code == 404
    revoked_turn = client.post(
        f"/api/v1/chat/sessions/{branch_id}/turns",
        json={"content": "撤权后尝试继续分支", "client_turn_id": "branch-pin-revoked-turn"},
    )
    assert revoked_turn.status_code == 404
    assert revoked_turn.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"
    revoked_merge = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches/{branch_id}/merge",
        json={"note": "重放", "confirmed": True, "merge_key": "branch-pin-merge"},
    )
    assert revoked_merge.status_code == 404


def test_branch_preserves_null_parent_binding_after_assignment_appears(client) -> None:
    import asyncio

    from app.db.models import (
        ChatSession,
        ClassMember,
        CourseClass,
        CourseRelease,
        CourseReleaseAssignment,
    )
    from app.db.session import session_factory

    course_id, student_id = _setup_course(client)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]
    _login(client, "ms@uni.edu")
    parent = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    assert parent.status_code == 201
    parent_id = parent.json()["data"]["id"]
    assert parent.json()["data"].get("course_release_id") is None
    source_response = client.post(
        f"/api/v1/chat/sessions/{parent_id}/turns",
        json={"content": "历史会话来源文本", "client_turn_id": "branch-null-parent-turn"},
    )
    assert source_response.status_code == 200
    source_turn = next(
        turn
        for turn in client.get(f"/api/v1/chat/sessions/{parent_id}").json()["data"]["turns"]
        if turn["role"] == "student"
    )

    async def assign_current_release() -> None:
        async with session_factory() as db:
            course_class = CourseClass(
                course_id=course_id,
                code="BRANCH-NULL",
                name="NULL 兼容班级",
                created_by=teacher_id,
            )
            db.add(course_class)
            await db.flush()
            db.add(ClassMember(class_id=course_class.id, user_id=student_id))
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="Branch current release",
                status="published",
                manifest={
                    "materials": [],
                    "material_version_ids": [],
                    "publication_snapshots": [],
                },
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

    asyncio.run(assign_current_release())
    branch_response = client.post(
        f"/api/v1/chat/sessions/{parent_id}/branches",
        json={"source_turn_id": source_turn["id"], "selection": "来源文本"},
    )
    assert branch_response.status_code == 201
    branch_id = branch_response.json()["data"]["id"]

    async def read_bindings() -> tuple[
        tuple[str | None, str | None], tuple[str | None, str | None]
    ]:
        async with session_factory() as db:
            parent_row = await db.get(ChatSession, parent_id)
            branch_row = await db.get(ChatSession, branch_id)
            assert parent_row is not None and branch_row is not None
            return (
                (parent_row.course_release_assignment_id, parent_row.course_release_id),
                (branch_row.course_release_assignment_id, branch_row.course_release_id),
            )

    assert asyncio.run(read_bindings()) == ((None, None), (None, None))
