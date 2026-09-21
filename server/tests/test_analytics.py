from tests.test_materials import _login, _setup_course


def test_teacher_course_analytics_is_aggregated_and_scoped(client) -> None:
    course_id, _ = _setup_course(client)

    response = client.get(f"/api/v1/courses/{course_id}/analytics/overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["course_id"] == course_id
    assert data["participation"]["student_count"] == 1
    assert data["scope"]["time_range"] == "all_time"
    assert data["privacy"] == {
        "aggregation_only": True,
        "chat_content_included": False,
        "memory_content_included": False,
    }
    assert "students" not in data
    assert "chat_turns" not in data


def test_student_cannot_read_course_analytics(client) -> None:
    course_id, _ = _setup_course(client)
    _login(client, "ms@uni.edu")

    response = client.get(f"/api/v1/courses/{course_id}/analytics/overview")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"
