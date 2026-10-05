from tests.conftest import create_user_sync


def _assign_platform_role_sync(user_id: str, role: str) -> None:
    import asyncio

    from app.db.models import RoleAssignment
    from app.db.session import session_factory

    async def _assign() -> None:
        async with session_factory() as session:
            session.add(
                RoleAssignment(
                    user_id=user_id,
                    role=role,
                    scope_type="platform",
                    scope_id=None,
                    status="active",
                    granted_by=None,
                )
            )
            await session.commit()

    asyncio.run(_assign())


def _revoke_platform_role_sync(user_id: str, role: str) -> None:
    import asyncio

    from sqlalchemy import update

    from app.db.models import RoleAssignment
    from app.db.session import session_factory

    async def _revoke() -> None:
        async with session_factory() as session:
            await session.execute(
                update(RoleAssignment)
                .where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.role == role,
                    RoleAssignment.scope_type == "platform",
                )
                .values(status="revoked")
            )
            await session.commit()

    asyncio.run(_revoke())


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
    assert data["capabilities"]["teacher_teaching"] is True
    assert data["capabilities"]["course_publish"] is True


def test_me_includes_active_platform_role_assignment(client) -> None:
    user_id = create_user_sync(email="designer@uni.edu")
    _assign_platform_role_sync(user_id, "course_designer")
    _login(client, "designer@uni.edu")

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert "course_designer" in response.json()["data"]["platform_roles"]

    _revoke_platform_role_sync(user_id, "course_designer")
    response = client.get("/api/v1/me")
    assert "course_designer" not in response.json()["data"]["platform_roles"]


def test_user_preferences_are_explicit_and_versioned(client) -> None:
    create_user_sync(email="preferences@uni.edu")
    _login(client, "preferences@uni.edu")
    defaults = client.get("/api/v1/me/preferences")
    assert defaults.status_code == 200
    assert defaults.json()["data"]["preferences"]["font_scale"] == "100"
    assert defaults.json()["data"]["preferences"]["response_length"] == "BALANCED"
    assert defaults.json()["data"]["preferences"]["example_order"] == "CONCEPT_FIRST"
    updated = client.patch(
        "/api/v1/me/preferences",
        json={
            "version": defaults.json()["data"]["version"],
            "hint_density": "guided",
            "font_scale": "115",
            "reduced_motion": True,
            "notification_in_app": False,
            "response_length": "DETAILED",
            "example_order": "EXAMPLE_FIRST",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["preferences"]["hint_density"] == "guided"
    assert updated.json()["data"]["preferences"]["response_length"] == "DETAILED"
    assert updated.json()["data"]["preferences"]["example_order"] == "EXAMPLE_FIRST"
    stale = client.patch(
        "/api/v1/me/preferences",
        json={"version": defaults.json()["data"]["version"], "font_scale": "130"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"


def test_user_preferences_reject_unknown_tutor_presentation_values(client) -> None:
    create_user_sync(email="invalid-preferences@uni.edu")
    _login(client, "invalid-preferences@uni.edu")
    invalid = client.patch(
        "/api/v1/me/preferences",
        json={"version": 1, "response_length": "UNLIMITED"},
    )
    assert invalid.status_code == 422


def test_platform_admin_does_not_inherit_course_teaching_scope(client) -> None:
    create_user_sync(email="course-owner@uni.edu", is_teacher=True)
    _login(client, "course-owner@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "范围隔离课程", "term": "2026秋"},
    )
    assert course.status_code == 201
    course_id = course.json()["data"]["id"]

    create_user_sync(email="platform-admin@uni.edu", is_platform_admin=True)
    _login(client, "platform-admin@uni.edu")
    response = client.get(f"/api/v1/courses/{course_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COURSE_NOT_FOUND"
    listing = client.get("/api/v1/courses")
    assert listing.status_code == 200
    assert listing.json()["data"] == []


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
