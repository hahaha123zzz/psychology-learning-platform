from tests.conftest import create_user_sync, publish_course_release_for_test


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def test_teaching_asset_registry_validates_and_binds_published_release(client) -> None:
    create_user_sync(email="asset-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="asset-student@uni.edu")
    _login(client, "asset-teacher@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "资产课程", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    course_id = course["id"]
    assert client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    release = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={"name": "资产版本", "material_ids": []},
    ).json()["data"]
    unsafe = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unsafe-demo",
            "template": "explanation",
            "content": {"html": "<script>alert(1)</script>"},
            "fallback_text": "文字解释",
            "allowed_actions": ["SHOW"],
        },
    )
    assert unsafe.status_code == 422
    assert unsafe.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    executable_text = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unsafe-uri",
            "template": "explanation",
            "content": {"title": "说明", "text": "javascript:alert(1)"},
            "fallback_text": "纯文本说明",
            "allowed_actions": ["SHOW"],
        },
    )
    assert executable_text.status_code == 422
    assert executable_text.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    markup_fallback = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "markup-fallback",
            "template": "explanation",
            "content": {"title": "说明", "text": "可读说明"},
            "fallback_text": "<strong>不可作为 HTML 的说明</strong>",
            "allowed_actions": ["SHOW"],
        },
    )
    assert markup_fallback.status_code == 422
    assert markup_fallback.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    unsupported_shape = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unsupported-shape",
            "template": "table",
            "content": {"title": "表格", "html": "<table><tr><td>x</td></tr></table>"},
            "fallback_text": "表格文字说明",
            "allowed_actions": ["SHOW"],
        },
    )
    assert unsupported_shape.status_code == 422
    assert unsupported_shape.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    unknown_field = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unknown-field",
            "template": "explanation",
            "content": {"title": "说明", "text": "可读说明", "src": "https://example.invalid"},
            "fallback_text": "纯文本说明",
            "allowed_actions": ["SHOW"],
        },
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["error"]["code"] == "TEACHING_ASSET_CONTENT_NOT_ALLOWED"

    created = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "attention-explanation",
            "template": "explanation",
            "release_id": release["id"],
            "content": {"title": "观察结果", "text": "先描述差异，再说明证据边界。"},
            "fallback_text": "先描述差异，再说明证据边界。",
            "evidence_refs": ["object:demo:1"],
            "allowed_actions": ["SHOW", "HIGHLIGHT"],
        },
    )
    assert created.status_code == 201
    asset = created.json()["data"]
    assert asset["version_no"] == 1
    assert asset["status"] == "draft"

    edited = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": asset["asset_key"],
            "template": asset["template"],
            "content": {"title": "修订后的观察结果", "text": "保留原版本并另建草稿。"},
            "fallback_text": "修订后的纯文本说明。",
            "evidence_refs": ["object:demo:1"],
            "allowed_actions": ["SHOW"],
        },
    )
    assert edited.status_code == 201
    assert edited.json()["data"]["version_no"] == 2
    listed = client.get(f"/api/v1/courses/{course_id}/teaching-assets").json()["data"]
    by_version = {row["version_no"]: row for row in listed}
    assert by_version[1]["content"]["title"] == "观察结果"
    assert by_version[2]["content"]["title"] == "修订后的观察结果"

    published_release = publish_course_release_for_test(client, course_id, release["id"])
    assert published_release["status"] == "published"

    _login(client, "asset-student@uni.edu")
    assert client.get(f"/api/v1/student/teaching-assets/{asset['id']}").status_code == 404

    _login(client, "asset-teacher@uni.edu")
    published = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets/{asset['id']}/publish",
        json={"version": asset["version"], "release_id": release["id"]},
    )
    assert published.status_code == 200
    published_asset = published.json()["data"]
    assert published_asset["status"] == "published"
    assert published_asset["release_id"] == release["id"]

    _login(client, "asset-student@uni.edu")
    readable = client.get(f"/api/v1/student/teaching-assets/{asset['id']}")
    assert readable.status_code == 200
    assert readable.json()["data"]["content"]["title"] == "观察结果"
