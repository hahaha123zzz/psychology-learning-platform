from tests.conftest import create_user_sync

COURSE_BODY = {"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"}


def _login(client, email: str, password: str = "correct-password"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response


def _create_course(client, body=None, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/api/v1/courses", json=body or COURSE_BODY, headers=headers)


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


def test_platform_admin_cannot_become_course_teacher_via_course_creation(client) -> None:
    create_user_sync(email="plain-admin-course@uni.edu", is_platform_admin=True)
    _login(client, "plain-admin-course@uni.edu")
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

    import asyncio

    from sqlalchemy import select

    from app.db.models import OutboxEvent
    from app.db.session import session_factory

    async def _get_events():
        async with session_factory() as session:
            result = await session.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "course.created")
            )
            return result.scalars().all()

    events = asyncio.run(_get_events())
    assert len(events) == 1
    assert events[0].payload["course_id"] == data["id"]


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
            row = await session.execute(select(User.id).where(User.email == "disabled9@uni.edu"))
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

    removed = client.delete(f"/api/v1/courses/{course['id']}/members/{member_id}")
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


def test_teacher_creates_class_and_assigns_explicit_course_teacher(client) -> None:
    create_user_sync(email="class-owner@uni.edu", is_teacher=True)
    assigned_teacher_id = create_user_sync(
        email="assigned-teacher@uni.edu", is_teacher=True, display_name="任课教师"
    )
    unassigned_teacher_id = create_user_sync(email="unassigned-teacher@uni.edu", is_teacher=True)
    _login(client, "class-owner@uni.edu")
    course = _create_course(client).json()["data"]
    added = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": assigned_teacher_id, "role": "teacher"},
    )
    assert added.status_code == 201

    created = client.post(
        f"/api/v1/courses/{course['id']}/classes",
        json={"code": "A01", "name": "实验心理学一班"},
    )
    assert created.status_code == 201
    class_data = created.json()["data"]
    assert class_data["code"] == "A01"

    duplicate = client.post(
        f"/api/v1/courses/{course['id']}/classes",
        json={"code": "A01", "name": "重复班级"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CLASS_CODE_ALREADY_EXISTS"

    not_member = client.post(
        f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/teachers",
        json={"teacher_id": unassigned_teacher_id, "assignment_role": "lead"},
    )
    assert not_member.status_code == 409
    assert not_member.json()["error"]["code"] == "TEACHER_NOT_COURSE_MEMBER"

    assigned = client.post(
        f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/teachers",
        json={"teacher_id": assigned_teacher_id, "assignment_role": "lead"},
    )
    assert assigned.status_code == 201
    assert assigned.json()["data"]["teacher_name"] == "任课教师"

    repeated = client.post(
        f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/teachers",
        json={"teacher_id": assigned_teacher_id, "assignment_role": "assistant"},
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "TEACHER_ALREADY_ASSIGNED"

    teachers = client.get(f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/teachers")
    assert teachers.status_code == 200
    assert len(teachers.json()["data"]) == 1


def test_student_cannot_create_course_class(client) -> None:
    create_user_sync(email="class-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="class-student@uni.edu")
    _login(client, "class-teacher@uni.edu")
    course = _create_course(client).json()["data"]
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/members",
            json={"user_id": student_id, "role": "student"},
        ).status_code
        == 201
    )
    _login(client, "class-student@uni.edu")
    response = client.post(
        f"/api/v1/courses/{course['id']}/classes",
        json={"code": "S01", "name": "学生越权班级"},
    )
    assert response.status_code == 404


def test_teacher_manages_independent_class_membership(client) -> None:
    create_user_sync(email="class-member-owner@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="class-member-student@uni.edu")
    _login(client, "class-member-owner@uni.edu")
    course = _create_course(client).json()["data"]
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/members",
            json={"user_id": student_id, "role": "student"},
        ).status_code
        == 201
    )
    class_data = client.post(
        f"/api/v1/courses/{course['id']}/classes",
        json={"code": "CM01", "name": "班级成员测试"},
    ).json()["data"]
    added = client.post(
        f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/members",
        json={"user_id": student_id},
    )
    assert added.status_code == 201
    assert added.json()["data"]["display_name"]
    listed = client.get(f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/members")
    assert listed.status_code == 200
    assert [item["user_id"] for item in listed.json()["data"]] == [student_id]
    repeated = client.post(
        f"/api/v1/courses/{course['id']}/classes/{class_data['id']}/members",
        json={"user_id": student_id},
    )
    assert repeated.status_code == 409


def test_course_release_is_versioned_and_legacy_publish_requires_contract(client) -> None:
    create_user_sync(email="release-owner@uni.edu", is_teacher=True)
    _login(client, "release-owner@uni.edu")
    course = _create_course(client).json()["data"]

    first = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "春季首发",
            "material_ids": [],
            "domain_pack": {"chapters": ["intro"]},
            "pedagogy_pack": {"tasks": ["predict"]},
            "assessment_pack": {"release_ids": []},
        },
    )
    assert first.status_code == 201
    first_data = first.json()["data"]
    assert first_data["version_no"] == 1
    assert first_data["status"] == "draft"
    assert first_data["manifest"]["domain_pack"]["chapters"] == ["intro"]

    edited = client.patch(
        f"/api/v1/courses/{course['id']}/releases/{first_data['id']}",
        json={
            "version": first_data["version"],
            "name": "春季首发（修订）",
            "pedagogy_pack": {"tasks": ["predict", "explain"]},
        },
    )
    assert edited.status_code == 200
    first_data = edited.json()["data"]
    assert first_data["name"] == "春季首发（修订）"
    assert first_data["manifest"]["pedagogy_pack"]["tasks"] == ["predict", "explain"]

    published = client.post(f"/api/v1/courses/{course['id']}/releases/{first_data['id']}/publish")
    assert published.status_code == 422
    assert published.json()["error"]["code"] == "RELEASE_PUBLISH_REQUEST_REQUIRED"

    replay = client.post(f"/api/v1/courses/{course['id']}/releases/{first_data['id']}/publish")
    assert replay.status_code == 422
    assert replay.json()["error"]["code"] == "RELEASE_PUBLISH_REQUEST_REQUIRED"

    still_a_draft = client.patch(
        f"/api/v1/courses/{course['id']}/releases/{first_data['id']}",
        json={"version": first_data["version"], "name": "不应修改"},
    )
    assert still_a_draft.status_code == 200
    assert still_a_draft.json()["data"]["name"] == "不应修改"

    second = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={"name": "春季修订", "material_ids": []},
    )
    second_data = second.json()["data"]
    assert second_data["version_no"] == 2
    published_second = client.post(
        f"/api/v1/courses/{course['id']}/releases/{second_data['id']}/publish"
    )
    assert published_second.status_code == 422
    assert published_second.json()["error"]["code"] == "RELEASE_PUBLISH_REQUEST_REQUIRED"

    releases = client.get(f"/api/v1/courses/{course['id']}/releases")
    assert releases.status_code == 200
    by_version = {item["version_no"]: item for item in releases.json()["data"]}
    assert by_version[1]["status"] == "draft"
    assert by_version[2]["status"] == "draft"


def test_course_release_rejects_material_from_another_course(client) -> None:
    create_user_sync(email="release-owner-a@uni.edu", is_teacher=True)
    create_user_sync(email="release-owner-b@uni.edu", is_teacher=True)
    _login(client, "release-owner-a@uni.edu")
    first_course = _create_course(client).json()["data"]
    _login(client, "release-owner-b@uni.edu")
    second_course = _create_course(client).json()["data"]
    _login(client, "release-owner-a@uni.edu")
    response = client.post(
        f"/api/v1/courses/{first_course['id']}/releases",
        json={"name": "跨课程组合", "material_ids": [second_course["id"]]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RELEASE_CROSS_COURSE_ASSET"


def test_course_release_pack_requires_structured_domain_objects(client) -> None:
    create_user_sync(email="release-pack-validator@uni.edu", is_teacher=True)
    _login(client, "release-pack-validator@uni.edu")
    course = _create_course(client).json()["data"]
    invalid = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "结构化校验",
            "domain_pack": {
                "knowledge_points": [{"title": "缺少稳定键"}],
                "relations": "必须是数组",
            },
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "RELEASE_PACK_INVALID"
    valid = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "结构化校验",
            "domain_pack": {
                "knowledge_points": [
                    {"key": "kp-1", "title": "注意"},
                    {"key": "kp-2", "title": "知觉"},
                ],
                "relations": [
                    {
                        "key": "rel-1",
                        "source_key": "kp-1",
                        "target_key": "kp-2",
                        "relation_type": "prerequisite",
                    }
                ],
            },
        },
    )
    assert valid.status_code == 201

    cyclic = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "循环关系应被拒绝",
            "domain_pack": {
                "knowledge_points": [
                    {"key": "kp-a", "title": "A"},
                    {"key": "kp-b", "title": "B"},
                ],
                "relations": [
                    {
                        "key": "rel-a",
                        "source_key": "kp-a",
                        "target_key": "kp-b",
                        "relation_type": "prerequisite",
                    },
                    {
                        "key": "rel-b",
                        "source_key": "kp-b",
                        "target_key": "kp-a",
                        "relation_type": "prerequisite",
                    },
                ],
            },
        },
    )
    assert cyclic.status_code == 422
    assert cyclic.json()["error"]["code"] == "RELEASE_DOMAIN_GRAPH_INVALID"
    assert any(
        issue["code"] == "DOMAIN_RELATION_CYCLE"
        for issue in cyclic.json()["error"]["details"]["issues"]
    )


def test_course_release_legacy_publish_is_rejected_before_domain_validation(client) -> None:
    create_user_sync(email="release-evidence-gate@uni.edu", is_teacher=True)
    _login(client, "release-evidence-gate@uni.edu")
    course = _create_course(client).json()["data"]
    draft = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "证据门禁",
            "domain_pack": {"knowledge_points": [{"key": "kp-a", "title": "A"}]},
        },
    )
    assert draft.status_code == 201
    release_id = draft.json()["data"]["id"]

    published = client.post(f"/api/v1/courses/{course['id']}/releases/{release_id}/publish")

    assert published.status_code == 422
    assert published.json()["error"]["code"] == "RELEASE_PUBLISH_REQUEST_REQUIRED"


def test_course_designer_can_edit_release_pack_but_not_publish(client) -> None:
    create_user_sync(email="release-teacher-designer@uni.edu", is_teacher=True)
    designer_id = create_user_sync(email="release-designer@uni.edu")
    _login(client, "release-teacher-designer@uni.edu")
    course = _create_course(client).json()["data"]
    import asyncio

    from app.db.models import RoleAssignment
    from app.db.session import session_factory

    async def _assign() -> None:
        async with session_factory() as session:
            session.add(
                RoleAssignment(
                    user_id=designer_id,
                    role="course_designer",
                    scope_type="course",
                    scope_id=course["id"],
                )
            )
            await session.commit()

    asyncio.run(_assign())
    draft = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={"name": "设计草稿", "domain_pack": {"chapters": []}},
    ).json()["data"]
    _login(client, "release-designer@uni.edu")
    stale = client.patch(
        f"/api/v1/courses/{course['id']}/releases/{draft['id']}",
        json={"version": draft["version"] + 1, "domain_pack": {"chapters": ["intro"]}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["actual_version"] == draft["version"]
    edited = client.patch(
        f"/api/v1/courses/{course['id']}/releases/{draft['id']}",
        json={"version": draft["version"], "domain_pack": {"chapters": ["intro"]}},
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["manifest"]["domain_pack"]["chapters"] == ["intro"]
    assert (
        client.post(f"/api/v1/courses/{course['id']}/releases/{draft['id']}/publish").status_code
        == 404
    )
