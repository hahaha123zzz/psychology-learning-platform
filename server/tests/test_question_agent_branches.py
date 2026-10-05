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
    )
    from app.db.session import session_factory
    from tests.conftest import create_user_sync

    course_id, student_id = _setup_course(client)
    teacher_id = client.get("/api/v1/me").json()["data"]["id"]

    async def seed_release_assignment() -> tuple[str, str, str]:
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
            release = CourseRelease(
                course_id=course_id,
                version_no=1,
                name="Branch parent release",
                status="published",
                manifest={
                    "materials": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
                    "material_version_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAW"],
                    "publication_snapshots": [
                        {
                            "material_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                            "material_version_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
                            "publication_snapshot_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
                            "index_job_id": "01ARZ3NDEKTSV4RRFFQ69G5FAY",
                            "embedding_version": "hash-v1",
                            "domain_release_id": "01ARZ3NDEKTSV4RRFFQ69G5FAZ",
                        }
                    ],
                },
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
            return course_class.id, assignment.id, release.id

    class_id, assignment_id, release_id = asyncio.run(seed_release_assignment())
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

    async def rotate_assignment() -> str:
        async with session_factory() as db:
            old_assignment = await db.get(CourseReleaseAssignment, assignment_id)
            old_release = await db.get(CourseRelease, release_id)
            assert old_assignment is not None and old_release is not None
            old_assignment.status = "closed"
            old_assignment.closed_at = datetime.now(UTC)
            old_assignment.close_reason = "Branch child inheritance test"
            old_release.status = "deprecated"
            replacement = CourseRelease(
                course_id=course_id,
                version_no=2,
                name="Branch replacement release",
                status="published",
                manifest={
                        "materials": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
                        "material_version_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAW"],
                        "publication_snapshots": [
                            {
                                "material_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                                "material_version_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
                                "publication_snapshot_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
                                "index_job_id": "01ARZ3NDEKTSV4RRFFQ69G5FAY",
                                "embedding_version": "hash-v1",
                                "domain_release_id": "01ARZ3NDEKTSV4RRFFQ69G5FAZ",
                            }
                        ],
                },
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
            return replacement.id

    replacement_release_id = asyncio.run(rotate_assignment())
    _login(client, "ms@uni.edu")
    recovered = client.get(f"/api/v1/chat/sessions/{branch_id}")
    assert recovered.status_code == 200
    branch_turn = client.post(
        f"/api/v1/chat/sessions/{branch_id}/turns",
        json={"content": "继续讨论", "client_turn_id": "branch-pin-child-turn"},
    )
    assert branch_turn.status_code == 200
    child_data = client.get(f"/api/v1/chat/sessions/{branch_id}").json()["data"]
    claim = child_data["turns"][-1]["verification"]["domain_claim"]
    assert claim["scope"]["course_release_assignment_id"] == assignment_id
    assert claim["scope"]["course_release_id"] == release_id
    assert claim["refusal_reason"] == "release_domain_snapshot_missing"

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
