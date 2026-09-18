from tests.conftest import create_user_sync

COURSE_BODY = {"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"}


def _login(client, email: str, password: str = "correct-password"):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return response


def _create_course(client, body=None, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        "/api/v1/courses", json=body or COURSE_BODY, headers=headers
    )


def test_unauthenticated_cannot_create_course(client) -> None:
    response = _create_course(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_student_cannot_create_course(client) -> None:
    create_user_sync(email="stu@uni.edu")
    _login(client, "stu@uni.edu")
    response = _create_course(client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_teacher_creates_course_with_membership(client) -> None:
    create_user_sync(email="teacher2@uni.edu", display_name="张老师", is_teacher=True)
    _login(client, "teacher2@uni.edu")
    response = _create_course(client)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "实验心理学"
    assert data["version"] == 1
    assert data["created_by"]
    assert response.json()["meta"]["request_id"]


def test_idempotent_replay_returns_same_course(client) -> None:
    create_user_sync(email="teacher3@uni.edu", is_teacher=True)
    _login(client, "teacher3@uni.edu")
    first = _create_course(client, key="course-key-1")
    replay = _create_course(client, key="course-key-1")
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]


def test_idempotency_key_conflict_on_different_body(client) -> None:
    create_user_sync(email="teacher4@uni.edu", is_teacher=True)
    _login(client, "teacher4@uni.edu")
    _create_course(client, key="course-key-2")
    conflict = _create_course(
        client, body={"title": "心理统计", "term": "2026春"}, key="course-key-2"
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_patch_course_requires_version(client) -> None:
    create_user_sync(email="teacher5@uni.edu", is_teacher=True)
    _login(client, "teacher5@uni.edu")
    course = _create_course(client).json()["data"]
    wrong = client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"version": 99, "title": "实验心理学（更新）"},
    )
    assert wrong.status_code == 409
    error = wrong.json()["error"]
    assert error["code"] == "RESOURCE_VERSION_CONFLICT"
    assert error["details"]["actual_version"] == 1

    right = client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"version": 1, "title": "实验心理学（更新）"},
    )
    assert right.status_code == 200
    assert right.json()["data"]["version"] == 2
    assert right.json()["data"]["title"] == "实验心理学（更新）"


def test_student_member_cannot_patch_course(client) -> None:
    create_user_sync(email="t6@uni.edu", is_teacher=True)
    create_user_sync(email="s6@uni.edu", display_name="学生甲")
    _login(client, "t6@uni.edu")
    course = _create_course(client).json()["data"]
    _login(client, "s6@uni.edu")
    student_id = client.get("/api/v1/me").json()["data"]["id"]
    _login(client, "t6@uni.edu")
    added = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert added.status_code == 201
    _login(client, "s6@uni.edu")
    patched = client.patch(
        f"/api/v1/courses/{course['id']}", json={"version": 1, "title": "越权修改"}
    )
    assert patched.status_code == 404
    assert patched.json()["error"]["code"] == "COURSE_NOT_FOUND"


def test_non_member_cannot_see_course(client) -> None:
    create_user_sync(email="t7@uni.edu", is_teacher=True)
    create_user_sync(email="s7@uni.edu")
    _login(client, "t7@uni.edu")
    course = _create_course(client).json()["data"]
    _login(client, "s7@uni.edu")
    response = client.get(f"/api/v1/courses/{course['id']}")
    assert response.status_code == 404
    listing = client.get("/api/v1/courses")
    assert listing.status_code == 200
    assert listing.json()["data"] == []


def test_member_can_see_course(client) -> None:
    create_user_sync(email="t8@uni.edu", is_teacher=True)
    create_user_sync(email="s8@uni.edu")
    _login(client, "t8@uni.edu")
    course = _create_course(client).json()["data"]
    _login(client, "s8@uni.edu")
    student_id = client.get("/api/v1/me").json()["data"]["id"]
    _login(client, "t8@uni.edu")
    client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    _login(client, "s8@uni.edu")
    response = client.get(f"/api/v1/courses/{course['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == course["id"]


def test_add_member_rejects_disabled_and_duplicates(client) -> None:
    create_user_sync(email="t9@uni.edu", is_teacher=True)
    create_user_sync(email="s9@uni.edu")
    create_user_sync(email="disabled9@uni.edu", status="disabled")
    _login(client, "t9@uni.edu")
    course = _create_course(client).json()["data"]

    _login(client, "s9@uni.edu")
    student_id = client.get("/api/v1/me").json()["data"]["id"]

    import asyncio

    from sqlalchemy import select

    from app.db.models import User
    from app.db.session import session_factory

    async def _get_disabled_id():
        async with session_factory() as session:
            row = await session.execute(
                select(User.id).where(User.email == "disabled9@uni.edu")
            )
            return row.scalar_one()

    disabled_id = asyncio.run(_get_disabled_id())

    _login(client, "t9@uni.edu")
    first = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert first.status_code == 201
    duplicate = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "MEMBER_ALREADY_EXISTS"

    disabled = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": disabled_id, "role": "student"},
    )
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "USER_DISABLED"

    unknown = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "role": "student"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "USER_NOT_FOUND"


def test_remove_member_then_readd(client) -> None:
    create_user_sync(email="t10@uni.edu", is_teacher=True)
    create_user_sync(email="s10@uni.edu")
    _login(client, "t10@uni.edu")
    course = _create_course(client).json()["data"]
    _login(client, "s10@uni.edu")
    student_id = client.get("/api/v1/me").json()["data"]["id"]
    _login(client, "t10@uni.edu")
    member = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).json()["data"]
    member_id = member["id"]

    role_conflict = client.patch(
        f"/api/v1/courses/{course['id']}/members/{member_id}",
        json={"version": 99, "role": "assistant"},
    )
    assert role_conflict.status_code == 409

    role_ok = client.patch(
        f"/api/v1/courses/{course['id']}/members/{member_id}",
        json={"version": 1, "role": "assistant"},
    )
    assert role_ok.status_code == 200
    assert role_ok.json()["data"]["role"] == "assistant"

    removed = client.delete(
        f"/api/v1/courses/{course['id']}/members/{member_id}"
    )
    assert removed.status_code == 200

    readded = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert readded.status_code == 201

    listing = client.get(f"/api/v1/courses/{course['id']}/members")
    assert listing.status_code == 200
    roles = {m["user_id"]: m["role"] for m in listing.json()["data"]}
    assert roles[student_id] == "student"
