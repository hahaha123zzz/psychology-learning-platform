from datetime import UTC, datetime, timedelta

import pytest

from tests.test_materials import _login, _setup_course

QUESTION_BODY = {
    "type": "single",
    "stem": "下列哪一项是实验中的自变量？",
    "options": [
        {"key": "A", "text": "研究者操纵的变量", "is_correct": True},
        {"key": "B", "text": "被测量的结果变量", "is_correct": False},
        {"key": "C", "text": "无关变量", "is_correct": False},
    ],
    "difficulty": 2,
    "explanation": "自变量是研究者主动操纵的变量。",
    "evidence_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
}


def _prepare_published_question(client, *, course_id=None):
    course_id, _ = _setup_course(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/questions", json=QUESTION_BODY
    )
    assert response.status_code == 201, response.text
    return course_id, response.json()["data"]


def test_question_validation_rules(client) -> None:
    course_id, _ = _setup_course(client)
    bad_single = dict(QUESTION_BODY)
    bad_single["options"] = [
        {"key": "A", "text": "对", "is_correct": True},
        {"key": "B", "text": "错", "is_correct": True},
    ]
    response = client.post(
        f"/api/v1/courses/{course_id}/questions", json=bad_single
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUESTION_INVALID"

    no_rubric = {
        "type": "essay",
        "stem": "论述实验设计的要点",
        "difficulty": 3,
    }
    response = client.post(f"/api/v1/courses/{course_id}/questions", json=no_rubric)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QUESTION_INVALID"

    _login(client, "ms@uni.edu")
    student_only = client.post(
        f"/api/v1/courses/{course_id}/questions",
        json={**QUESTION_BODY, "type": "true_false", "options": None, "answer": {"correct": True}},
    )
    assert student_only.status_code == 404


def test_review_flow_and_publish_requires_evidence(client) -> None:
    course_id, question = _prepare_published_question(client)
    question_id = question["id"]
    _login(client, "mt@uni.edu")

    no_comment = client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "reject", "version": 1},
    )
    assert no_comment.status_code == 422

    approve = client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "题目合理"},
    )
    assert approve.status_code == 200
    assert approve.json()["data"]["status"] == "approved"

    publish = client.post(f"/api/v1/questions/{question_id}/publish")
    assert publish.status_code == 200
    assert publish.json()["data"]["status"] == "published"


def test_publish_blocked_without_evidence(client) -> None:
    course_id, _ = _setup_course(client)
    body = {**QUESTION_BODY, "evidence_ids": []}
    created = client.post(f"/api/v1/courses/{course_id}/questions", json=body)
    question_id = created.json()["data"]["id"]
    client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "ok"},
    )
    publish = client.post(f"/api/v1/questions/{question_id}/publish")
    assert publish.status_code == 409
    assert publish.json()["error"]["code"] == "QUESTION_EVIDENCE_MISSING"


def test_full_assessment_attempt_and_grading(client) -> None:
    course_id, question = _prepare_published_question(client)
    question_id = question["id"]
    _login(client, "mt@uni.edu")
    client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "ok"},
    )
    publish = client.post(f"/api/v1/questions/{question_id}/publish")
    assert publish.status_code == 200

    assessment = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "第一章测验",
            "question_ids": [question_id],
            "ai_policy": "disabled",
            "points_per_question": 5,
        },
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["data"]["id"]

    publish_assessment = client.post(
        f"/api/v1/assessments/{assessment_id}/publish"
    )
    assert publish_assessment.status_code == 200

    _login(client, "ms@uni.edu")
    student_view = client.get(f"/api/v1/assessments/{assessment_id}")
    assert student_view.status_code == 200
    first_item = student_view.json()["data"]["items"][0]
    assert "answer" not in first_item
    assert "rubric" not in first_item
    assert "explanation" not in first_item
    assert first_item["options"][0].get("is_correct") is None

    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert attempt.status_code == 201
    attempt_id = attempt.json()["data"]["attempt_id"]

    qv_id = student_view.json()["data"]["items"][0]["question_version_id"]
    save = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={
            "answer_version": 1,
            "response": {"selected_keys": ["A"]},
            "client_saved_at": "2026-09-18T08:00:00Z",
        },
    )
    assert save.status_code == 200
    assert save.json()["data"]["answer_version"] == 2
    resumed_attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert resumed_attempt.status_code == 200
    resumed_data = resumed_attempt.json()["data"]
    assert resumed_data["attempt_id"] == attempt_id
    assert resumed_data["resumed"] is True
    assert resumed_data["answers"] == [
        {
            "question_version_id": qv_id,
            "response": {"selected_keys": ["A"]},
            "answer_version": save.json()["data"]["answer_version"],
            "flagged": False,
        }
    ]
    assert "answer" not in resumed_data["answers"][0]
    resave = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={
            "answer_version": resumed_data["answers"][0]["answer_version"],
            "response": {"selected_keys": ["A"]},
        },
    )
    assert resave.status_code == 200
    assert resave.json()["data"]["answer_version"] == 3
    flag = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}/flag",
        json={"answer_version": 3, "flagged": True},
    )
    assert flag.status_code == 200
    assert flag.json()["data"] == {"answer_version": 4, "flagged": True}
    resumed_after_flag = client.post(
        f"/api/v1/assessments/{assessment_id}/attempts"
    ).json()["data"]["answers"][0]
    assert resumed_after_flag["flagged"] is True
    assert resumed_after_flag["answer_version"] == 4
    stale = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={
            "answer_version": 99,
            "response": {"selected_keys": ["B"]},
        },
    )
    assert stale.status_code == 409

    coach = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "question_coach"},
    )
    assert coach.status_code == 403
    assert coach.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"

    submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submit.status_code == 200
    result = submit.json()["data"]
    assert result["grading_status"] == "graded"
    assert result["score"] == 5
    locked_flag = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}/flag",
        json={"answer_version": 4, "flagged": False},
    )
    assert locked_flag.status_code == 409
    assert locked_flag.json()["error"]["code"] == "ATTEMPT_SUBMITTED"

    replay = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert replay.status_code == 200
    assert replay.json()["data"].get("idempotent_replay") is True

    result_view = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert result_view.status_code == 200
    item = result_view.json()["data"]["items"][0]
    assert item["is_correct"] is True


def test_attempt_autosave_is_locked_by_server_deadline(client, monkeypatch) -> None:
    course_id, question = _prepare_published_question(client)
    question_id = question["id"]
    _login(client, "mt@uni.edu")
    client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "ok"},
    )
    assert client.post(f"/api/v1/questions/{question_id}/publish").status_code == 200

    closes_at = datetime.now(UTC) + timedelta(minutes=1)
    created = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "截止后不得保存",
            "question_ids": [question_id],
            "closes_at": closes_at.isoformat(),
        },
    )
    assessment_id = created.json()["data"]["id"]
    assert client.post(f"/api/v1/assessments/{assessment_id}/publish").status_code == 200

    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts").json()["data"]
    question_version_id = question["current_version"]["id"]
    saved = client.put(
        f"/api/v1/attempts/{attempt['attempt_id']}/answers/{question_version_id}",
        json={
            "answer_version": 1,
            "response": {"selected_keys": ["A"]},
            "client_saved_at": datetime.now(UTC).isoformat(),
        },
    )
    assert saved.status_code == 200

    from app.modules.assessments import router as assessments_router

    class AfterDeadline(datetime):
        @classmethod
        def now(cls, tz=None):
            return closes_at + timedelta(seconds=1)

    monkeypatch.setattr(assessments_router, "datetime", AfterDeadline)
    late_save = client.put(
        f"/api/v1/attempts/{attempt['attempt_id']}/answers/{question_version_id}",
        json={
            "answer_version": saved.json()["data"]["answer_version"],
            "response": {"selected_keys": ["B"]},
            # 伪造较早的客户端时间不能绕过服务端截止时间。
            "client_saved_at": (closes_at - timedelta(seconds=1)).isoformat(),
        },
    )
    assert late_save.status_code == 409
    assert late_save.json()["error"]["code"] == "ASSESSMENT_CLOSED"


def test_subjective_attempt_teacher_grading_is_versioned_and_idempotent(client) -> None:
    course_id, _ = _setup_course(client)
    essay = client.post(
        f"/api/v1/courses/{course_id}/questions",
        json={
            "type": "essay",
            "stem": "请说明被试内设计如何控制个体差异。",
            "rubric": "说明同一被试接受多个条件，并指出顺序效应控制。",
            "difficulty": 3,
            "evidence_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
        },
    )
    assert essay.status_code == 201, essay.text
    question_id = essay.json()["data"]["id"]
    _login(client, "mt@uni.edu")
    assert client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "rubric checked"},
    ).status_code == 200
    assert client.post(f"/api/v1/questions/{question_id}/publish").status_code == 200

    assessment = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "主观题人工评分",
            "question_ids": [question_id],
            "points_per_question": 5,
        },
    )
    assessment_id = assessment.json()["data"]["id"]
    assert client.post(f"/api/v1/assessments/{assessment_id}/publish").status_code == 200

    _login(client, "ms@uni.edu")
    detail = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    question_version_id = detail["items"][0]["question_version_id"]
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts").json()["data"]
    attempt_id = attempt["attempt_id"]
    assert client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"text": "同一被试体验多个实验条件。"}},
    ).status_code == 200
    assert client.post(f"/api/v1/attempts/{attempt_id}/submit").status_code == 200

    pending_result = client.get(f"/api/v1/attempts/{attempt_id}/result").json()["data"]
    assert pending_result["grading_status"] == "pending_teacher"
    assert pending_result["score"] is None
    assert pending_result["items"][0]["points_earned"] is None

    queue = client.get(f"/api/v1/courses/{course_id}/grading-queue")
    assert queue.status_code == 404
    assert client.get(f"/api/v1/teacher/attempts/{attempt_id}/grading").status_code == 404
    _login(client, "mt@uni.edu")
    queue = client.get(f"/api/v1/courses/{course_id}/grading-queue")
    assert queue.status_code == 200, queue.text
    assert [row["attempt_id"] for row in queue.json()["data"]] == [attempt_id]
    grade_detail = client.get(f"/api/v1/teacher/attempts/{attempt_id}/grading")
    assert grade_detail.status_code == 200, grade_detail.text
    assert grade_detail.json()["data"]["items"][0]["rubric"]

    payload = {
        "expected_score_version": 0,
        "items": [
            {
                "question_version_id": question_version_id,
                "points_awarded": 3,
                "rationale": "识别出同一被试接受多个条件。",
            }
        ],
    }
    headers = {"Idempotency-Key": "manual-grade-first"}
    graded = client.put(
        f"/api/v1/teacher/attempts/{attempt_id}/grading",
        json=payload,
        headers=headers,
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["data"]["score"] == 3
    replay = client.put(
        f"/api/v1/teacher/attempts/{attempt_id}/grading",
        json=payload,
        headers=headers,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["meta"]["idempotent_replay"] is True
    after_grade = client.get(f"/api/v1/teacher/attempts/{attempt_id}/grading").json()["data"]
    assert after_grade["score_version"] == 1
    assert len(after_grade["items"][0]["decisions"]) == 1

    override = {
        **payload,
        "expected_score_version": 1,
        "items": [
            {
                "question_version_id": question_version_id,
                "points_awarded": 4,
                "rationale": "复核后确认还满足顺序效应控制要求。",
            }
        ],
    }
    no_reason = client.put(
        f"/api/v1/teacher/attempts/{attempt_id}/grading", json=override
    )
    assert no_reason.status_code == 422
    override["override_reason"] = "教师复核发现首轮评分遗漏答案中的第二个评分点。"
    updated = client.put(
        f"/api/v1/teacher/attempts/{attempt_id}/grading",
        json=override,
        headers={"Idempotency-Key": "manual-grade-override"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["score_version"] == 2
    assert updated.json()["data"]["score"] == 4
    history = client.get(
        f"/api/v1/courses/{course_id}/grading-queue?include_graded=true"
    )
    assert history.status_code == 200
    assert [row["attempt_id"] for row in history.json()["data"]] == [attempt_id]

    _login(client, "ms@uni.edu")
    released = client.get(f"/api/v1/attempts/{attempt_id}/result").json()["data"]
    assert released["status"] == "graded"
    assert released["score"] == 4
    assert released["items"][0]["points_earned"] == 4


def test_student_assessment_discovery_hides_drafts_and_protects_scheduled_items(
    client,
) -> None:
    course_id, question = _prepare_published_question(client)
    question_id = question["id"]
    client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "ok"},
    )
    client.post(f"/api/v1/questions/{question_id}/publish")
    opens_at = datetime.now(UTC) + timedelta(days=1)
    created = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "明日测验",
            "question_ids": [question_id],
            "opens_at": opens_at.isoformat(),
        },
    )
    assessment_id = created.json()["data"]["id"]

    teacher_list = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert teacher_list.status_code == 200
    assert teacher_list.json()["data"][0]["availability"] == "draft"

    _login(client, "ms@uni.edu")
    hidden_list = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert hidden_list.status_code == 200
    assert hidden_list.json()["data"] == []
    hidden_detail = client.get(f"/api/v1/assessments/{assessment_id}")
    assert hidden_detail.status_code == 404

    _login(client, "mt@uni.edu")
    client.post(f"/api/v1/assessments/{assessment_id}/publish")
    _login(client, "ms@uni.edu")
    scheduled_list = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert scheduled_list.json()["data"][0]["availability"] == "scheduled"
    scheduled_detail = client.get(f"/api/v1/assessments/{assessment_id}")
    assert scheduled_detail.status_code == 409
    assert scheduled_detail.json()["error"]["code"] == "ASSESSMENT_NOT_OPEN"


def test_unpublished_question_rejected_from_assessment(client) -> None:
    course_id, question = _prepare_published_question(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "非法组卷",
            "question_ids": [question["id"]],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "QUESTION_NOT_PUBLISHED"


@pytest.mark.parametrize("ai_policy", ["disabled", "direction_only", "full_after_submit"])
@pytest.mark.parametrize("mode", ["course_qa", "question_coach"])
def test_active_assessment_cannot_be_bypassed_through_existing_chat(
    client, ai_policy: str, mode: str
) -> None:
    course_id, question = _prepare_published_question(client)
    question_id = question["id"]
    _login(client, "mt@uni.edu")
    assert (
        client.post(
            f"/api/v1/questions/{question_id}/review",
            json={"action": "approve", "version": 1, "comment": "ok"},
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/questions/{question_id}/publish").status_code == 200

    _login(client, "ms@uni.edu")
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": mode, "title": "考前会话"},
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["data"]["id"]

    _login(client, "mt@uni.edu")
    assessment = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "正在进行的测验",
            "question_ids": [question_id],
            "ai_policy": ai_policy,
            "points_per_question": 5,
        },
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["data"]["id"]
    assert client.post(f"/api/v1/assessments/{assessment_id}/publish").status_code == 200

    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert attempt.status_code == 201, attempt.text
    attempt_id = attempt.json()["data"]["attempt_id"]

    active_result = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert active_result.status_code == 403
    assert active_result.json()["error"]["code"] == "ASSESSMENT_RESULT_NOT_RELEASED"

    turn = client.post(
        f"/api/v1/chat/sessions/{session_id}/turns",
        json={"content": "这道题答案是什么？", "client_turn_id": "exam-bypass-0001"},
    )
    assert turn.status_code == 403
    assert turn.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"

    history = client.get(f"/api/v1/chat/sessions/{session_id}")
    assert history.status_code == 403
    assert history.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"

    session_list = client.get("/api/v1/chat/sessions")
    assert session_list.status_code == 403

    review_tasks = client.get("/api/v1/review-tasks?due_only=false")
    assert review_tasks.status_code == 403

    branch = client.post(
        f"/api/v1/chat/sessions/{session_id}/branches",
        json={
            "source_turn_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "selection": "这个选项如何判断？",
        },
    )
    assert branch.status_code == 403

    search = client.post(
        "/api/v1/knowledge/search",
        json={"course_id": course_id, "query": "测验题答案"},
    )
    assert search.status_code == 403
    assert search.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"

    new_session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa", "title": "考试中会话"},
    )
    assert new_session.status_code == 403
    assert new_session.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"
