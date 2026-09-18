from tests.conftest import create_user_sync


def _login(client, email: str, password: str = "correct-password"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def test_login_success_sets_httponly_cookies_and_roles(client) -> None:
    create_user_sync(
        email="teacher@uni.edu",
        display_name="王老师",
        is_teacher=True,
    )
    response = _login(client, "teacher@uni.edu")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["email"] == "teacher@uni.edu"
    assert "teacher" in data["platform_roles"]
    assert "session_expires_at" in data
    set_cookies = "; ".join(response.headers.get_list("set-cookie"))
    assert "pl_access=" in set_cookies
    assert "HttpOnly" in set_cookies
    assert "pl_refresh=" in set_cookies
    assert "Path=/api/v1/auth" in set_cookies


def test_login_wrong_password_and_unknown_email_same_error(client) -> None:
    create_user_sync(email="student@uni.edu")
    wrong_password = _login(client, "student@uni.edu", "bad-password")
    unknown_email = _login(client, "ghost@uni.edu")
    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert unknown_email.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_rate_limited_after_repeated_failures(client) -> None:
    create_user_sync(email="locked@uni.edu")
    for _ in range(5):
        _login(client, "locked@uni.edu", "bad-password")
    blocked = _login(client, "locked@uni.edu", "correct-password")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "LOGIN_RATE_LIMITED"
    assert blocked.json()["error"]["retryable"] is True


def test_me_requires_authentication(client) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_returns_platform_roles_and_memberships(client) -> None:
    create_user_sync(email="me-teacher@uni.edu", display_name="李老师", is_teacher=True)
    _login(client, "me-teacher@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "实验心理学", "term": "2026春"},
    )
    assert course.status_code == 201
    me = client.get("/api/v1/me")
    assert me.status_code == 200
    data = me.json()["data"]
    assert data["display_name"] == "李老师"
    assert "teacher" in data["platform_roles"]
    assert len(data["course_memberships"]) == 1
    assert data["course_memberships"][0]["role"] == "teacher"


def test_refresh_rotates_token_and_rejects_reuse(client) -> None:
    create_user_sync(email="rotate@uni.edu", is_teacher=True)
    _login(client, "rotate@uni.edu")
    old_refresh_cookie = next(
        c.value for c in client.cookies.jar if c.name == "pl_refresh"
    )

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    new_refresh_cookie = next(
        c.value for c in client.cookies.jar if c.name == "pl_refresh"
    )
    assert new_refresh_cookie != old_refresh_cookie

    client.cookies.set("pl_refresh", old_refresh_cookie)
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "UNAUTHENTICATED"


def test_logout_revokes_session(client) -> None:
    create_user_sync(email="bye@uni.edu")
    _login(client, "bye@uni.edu")
    refresh_before = next(c.value for c in client.cookies.jar if c.name == "pl_refresh")
    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["data"]["logged_out"] is True
    client.cookies.set("pl_refresh", refresh_before)
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "UNAUTHENTICATED"
