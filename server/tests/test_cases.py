from tests.conftest import create_user_sync


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def test_case_session_requires_structured_reasoning_and_qualifies_later(client) -> None:
    create_user_sync(email="case-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="case-student@uni.edu")
    _login(client, "case-teacher@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    assert client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    _login(client, "case-student@uni.edu")
    catalog = client.get("/api/v1/student/cases/catalog")
    assert catalog.status_code == 200
    assert {item["case_key"] for item in catalog.json()["data"]} == {
        "confound-basic",
        "experiment-decomposer",
        "design-board",
        "result-interpreter",
        "critique",
    }
    created = client.post(
        "/api/v1/student/cases", json={"course_id": course["id"], "case_key": "confound-basic"}
    )
    assert created.status_code == 201
    item = created.json()["data"]
    assert set(item["case_snapshot"]) == {"title", "prompt", "options", "knowledge_point"}
    listed = client.get(f"/api/v1/student/cases?course_id={course['id']}")
    assert listed.status_code == 200
    assert set(listed.json()["data"][0]["case_snapshot"]) == set(item["case_snapshot"])
    fetched = client.get(f"/api/v1/student/cases/{item['id']}")
    assert fetched.status_code == 200
    assert set(fetched.json()["data"]["case_snapshot"]) == set(item["case_snapshot"])
    response = client.post(
        f"/api/v1/student/cases/{item['id']}/respond",
        json={
            "version": item["version"],
            "selected_confound": "screen_brightness",
            "reasoning": "屏幕亮度随组别变化，会同时影响反应时，无法归因于音乐。",
            "design_change": "固定两组屏幕亮度，并在随机分配后只改变背景音乐条件。",
        },
    )
    assert response.status_code == 200
    outcome = response.json()["data"]["outcome"]
    assert outcome["points"] == 3
    assert outcome["qualification_status"] == "pending"
    replay = client.post(
        f"/api/v1/student/cases/{item['id']}/respond",
        json={
            "version": response.json()["data"]["version"],
            "selected_confound": "screen_brightness",
            "reasoning": "重复提交不应覆盖原始作答。",
            "design_change": "重复提交不应覆盖原始作答。",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["outcome"]["points"] == 3

    import asyncio

    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_pending_events

    async def _run_worker():
        async with session_factory() as session:
            return await qualify_pending_events(session, limit=10)

    counts = asyncio.run(_run_worker())
    assert counts["qualified"] == 1
    qualified = client.get(f"/api/v1/student/cases/{item['id']}")
    assert qualified.status_code == 200
    assert qualified.json()["data"]["outcome"]["qualification_status"] == "qualified"


def test_case_score_reports_response_completeness_without_claiming_semantic_quality(client) -> None:
    create_user_sync(email="case-score-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="case-score-student@uni.edu")
    _login(client, "case-score-teacher@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "推理评分", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    assert client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    _login(client, "case-score-student@uni.edu")
    created = client.post(
        "/api/v1/student/cases", json={"course_id": course["id"], "case_key": "confound-basic"}
    )
    item = created.json()["data"]
    submitted = client.post(
        f"/api/v1/student/cases/{item['id']}/respond",
        json={
            "version": item["version"],
            "selected_confound": "sample_size",
            "reasoning": "这个因素可能影响两组表现，让差异无法清楚归因于音乐条件变化。",
            "design_change": "固定环境设置后只改变音乐条件，并保持记录流程一致。",
        },
    )
    assert submitted.status_code == 200, submitted.text
    outcome = submitted.json()["data"]["outcome"]
    assert outcome["points"] == 3
    assert outcome["score_basis"] == "response_completeness"
    assert "不判断答案正确性或推理质量" in outcome["feedback"]
    assert outcome["components"] == {
        "selection_points": 1,
        "reasoning_completion_points": 1,
        "design_completion_points": 1,
    }


def test_case_draft_is_versioned_restorable_and_immutable_after_submit(client) -> None:
    create_user_sync(email="case-draft-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="case-draft-student@uni.edu")
    create_user_sync(email="case-draft-outsider@uni.edu")
    _login(client, "case-draft-teacher@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "草稿恢复", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    assert client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    _login(client, "case-draft-student@uni.edu")
    created = client.post(
        "/api/v1/student/cases", json={"course_id": course["id"], "case_key": "confound-basic"}
    )
    initial = created.json()["data"]
    draft_payload = {
        "version": initial["version"],
        "draft": True,
        "selected_confound": "screen_brightness",
        "reasoning": "屏幕亮度和结论的关系",
        "design_change": "",
    }
    saved = client.post(
        f"/api/v1/student/cases/{initial['id']}/respond", json=draft_payload
    )
    assert saved.status_code == 200, saved.text
    saved_data = saved.json()["data"]
    assert saved_data["status"] == "active"
    assert saved_data["version"] == initial["version"] + 1
    assert saved_data["response"] == {
        "selected_confound": "screen_brightness",
        "reasoning": "屏幕亮度和结论的关系",
        "design_change": "",
    }
    listed = client.get(f"/api/v1/student/cases?course_id={course['id']}")
    restored = client.get(f"/api/v1/student/cases/{initial['id']}")
    assert listed.json()["data"][0]["response"] == saved_data["response"]
    assert restored.json()["data"]["response"] == saved_data["response"]
    stale = client.post(
        f"/api/v1/student/cases/{initial['id']}/respond", json=draft_payload
    )
    assert stale.status_code == 409
    restored_after_conflict = client.get(
        f"/api/v1/student/cases/{initial['id']}"
    ).json()["data"]
    assert restored_after_conflict["response"] == saved_data["response"]

    submitted = client.post(
        f"/api/v1/student/cases/{initial['id']}/respond",
        json={
            "version": saved_data["version"],
            "selected_confound": "screen_brightness",
            "reasoning": "屏幕亮度在两组间变化，会同时影响反应时，不能归因于音乐。",
            "design_change": "固定两组屏幕亮度，并在随机分配后只改变背景音乐条件。",
        },
    )
    assert submitted.status_code == 200, submitted.text
    completed = submitted.json()["data"]
    late_draft = client.post(
        f"/api/v1/student/cases/{initial['id']}/respond",
        json={
            "version": completed["version"],
            "draft": True,
            "selected_confound": "sample_size",
            "reasoning": "尝试覆盖已提交的理由",
            "design_change": "尝试覆盖已提交的设计",
        },
    )
    assert late_draft.status_code == 200
    assert late_draft.json()["data"]["status"] == "completed"
    assert late_draft.json()["data"]["response"] == completed["response"]

    _login(client, "case-draft-outsider@uni.edu")
    assert client.get(f"/api/v1/student/cases/{initial['id']}").status_code == 404
    assert client.get(f"/api/v1/student/cases?course_id={course['id']}").status_code == 404
