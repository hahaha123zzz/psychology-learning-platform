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
    assert coach.json()["error"]["code"] == "COACH_DISABLED_FOR_EXAM"

    submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submit.status_code == 200
    result = submit.json()["data"]
    assert result["grading_status"] == "graded"
    assert result["score"] == 5

    replay = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert replay.status_code == 200
    assert replay.json()["data"].get("idempotent_replay") is True

    result_view = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert result_view.status_code == 200
    item = result_view.json()["data"]["items"][0]
    assert item["is_correct"] is True


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
