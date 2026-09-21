import json
import time

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
    events = turn.content.decode("utf-8").split("\n\n")
    done_block = [b for b in events if '"done"' in b or "done" in b.split("\n")[0]][0]
    done_data = None
    for line in done_block.split("\n"):
        if line.startswith("data: "):
            done_data = line[6:]
    done = json.loads(done_data)
    source_turn_id = done["turn_id"]

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
        json={"note": "已理解内部效度概念"},
    )
    assert merge.status_code == 200

    parent_detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    contents = [t["content"] for t in parent_detail.json()["data"]["turns"]]
    assert any("分支结论（用户确认）" in c for c in contents)

    branch_detail = client.get(f"/api/v1/chat/sessions/{branch_id}")
    assert branch_detail.json()["data"]["status"] == "closed"

    merge_again = client.post(
        f"/api/v1/chat/sessions/{session['id']}/branches/{branch_id}/merge",
        json={"note": "重复合并"},
    )
    assert merge_again.status_code == 409
    assert merge_again.json()["error"]["code"] == "BRANCH_ALREADY_MERGED"
