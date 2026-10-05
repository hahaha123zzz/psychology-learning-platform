from tests.test_materials import _login, _setup_course, _upload


def test_legacy_teacher_material_writes_are_closed_after_scope_check(client, monkeypatch) -> None:
    from app.core.config import get_settings
    from tests.conftest import create_user_sync

    course_id, _ = _setup_course(client)
    uploaded = _upload(client, course_id)
    assert uploaded.status_code == 201
    version_id = uploaded.json()["data"]["version_id"]

    monkeypatch.setattr(get_settings(), "material_legacy_authoring_api_enabled", False)
    writes = [
        _upload(client, course_id),
        client.post(
            f"/api/v1/courses/{course_id}/upload-sessions",
            json={
                "title": "阻断测试",
                "material_type": "textbook",
                "filename": "blocked.pdf",
                "size_bytes": 1,
            },
        ),
        client.post(f"/api/v1/material-versions/{version_id}/parse"),
        client.post(f"/api/v1/material-versions/{version_id}/embed"),
        client.post(f"/api/v1/material-versions/{version_id}/publish"),
        client.delete(f"/api/v1/materials/{uploaded.json()['data']['material_id']}"),
    ]

    assert [response.status_code for response in writes] == [410] * len(writes)
    assert {
        response.json()["error"]["code"] for response in writes
    } == {"LEGACY_MATERIAL_AUTHORING_DISABLED"}

    create_user_sync(email="material-policy-outsider@uni.edu", is_teacher=True)
    _login(client, "material-policy-outsider@uni.edu")
    denied = _upload(client, course_id)
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "COURSE_NOT_FOUND"
