from tests.conftest import create_user_sync
from tests.test_materials import _login, _setup_course, _upload
from tests.test_question_bank import QUESTION_BODY
from tests.test_search import TWO_CHAPTER_PDF


def _prepare_published(client):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    client.post(f"/api/v1/material-versions/{version_id}/parse")
    client.post(f"/api/v1/material-versions/{version_id}/embed")
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
        json={"title": "掌握度测验", "question_ids": [question_id]},
    )
    assessment_id = assessment.json()["data"]["id"]
    client.post(f"/api/v1/assessments/{assessment_id}/publish")
    return course_id, student_id, version_id, assessment_id


def test_mastery_state_derived_from_graded_attempt(client) -> None:
    course_id, student_id, version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = attempt.json()["data"]["attempt_id"]
    view = client.get(f"/api/v1/assessments/{assessment_id}")
    qv_id = view.json()["data"]["items"][0]["question_version_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submit.status_code == 200

    mastery = client.get(f"/api/v1/me/mastery?course_id={course_id}")
    assert mastery.status_code == 200
    items = mastery.json()["data"]
    assert len(items) >= 1
    first = items[0]
    assert first["state"] in (
        "not_started",
        "learning",
        "needs_consolidation",
        "proficient",
        "mastered",
    )
    assert first["evidence_count"] >= 1
    assert first["correct_ratio"] > 0


def test_memory_summary_and_weakness_candidates(client) -> None:
    course_id, student_id, version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    empty = client.get("/api/v1/me/memory")
    assert empty.status_code == 200

    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = attempt.json()["data"]["attempt_id"]
    view = client.get(f"/api/v1/assessments/{assessment_id}")
    qv_id = view.json()["data"]["items"][0]["question_version_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["C"]}},
    )
    client.post(f"/api/v1/attempts/{attempt_id}/submit")

    # 第二次错误作答：重复出现才形成L1薄弱点候选（单次仅为待确认）
    attempt2 = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id2 = attempt2.json()["data"]["attempt_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id2}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["C"]}},
    )
    client.post(f"/api/v1/attempts/{attempt_id2}/submit")

    summary = client.get("/api/v1/me/memory")
    data = summary.json()["data"]
    assert data["summary"].get("L1:weakness") == 1

    items = client.get("/api/v1/me/memory/items?layer=L1")
    assert items.status_code == 200
    first = items.json()["data"][0]
    assert first["layer"] == "L1"
    assert "不稳定" in first["content"]


def test_privacy_delete_request_disables_and_hides(client) -> None:
    course_id, student_id, version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")
    delete_request = client.post("/api/v1/me/privacy/delete-request")
    assert delete_request.status_code == 200
    assert delete_request.json()["data"]["status"] == "scheduled"

    me = client.get("/api/v1/me")
    assert me.status_code == 401


def test_admin_health_and_audit_require_admin(client) -> None:
    create_user_sync(email="plain@uni.edu")
    create_user_sync(email="root@uni.edu", is_platform_admin=True)

    _login(client, "plain@uni.edu")
    denied = client.get("/api/v1/admin/health")
    assert denied.status_code == 403

    _login(client, "root@uni.edu")
    health = client.get("/api/v1/admin/health")
    assert health.status_code == 200
    assert "counts" in health.json()["data"]

    audits = client.get("/api/v1/admin/audit-logs?limit=5")
    assert audits.status_code == 200
    assert len(audits.json()["data"]) <= 5
