import asyncio
from unittest.mock import patch

from tests.conftest import create_user_sync


def _create_admin_job(*, created_by: str, organization_id: str, kind: str = "material_parse"):
    async def _create() -> tuple[str, str, str]:
        from app.db.models import Course, Job, Material, MaterialVersion
        from app.db.session import session_factory

        async with session_factory() as session:
            course = Course(
                organization_id=organization_id,
                title="管理员任务重试测试课程",
                term="2026 秋",
                created_by=created_by,
            )
            session.add(course)
            await session.flush()
            material = Material(
                course_id=course.id,
                title="测试教材",
                material_type="textbook",
                created_by=created_by,
            )
            session.add(material)
            await session.flush()
            version = MaterialVersion(
                material_id=material.id,
                version_no=1,
                status="failed",
                created_by=created_by,
            )
            session.add(version)
            await session.flush()
            job = Job(
                kind=kind,
                status="failed",
                stage="failed",
                progress=20,
                payload={"material_version_id": version.id, "private_text": "不得返回"},
                error="sensitive provider response must not be returned",
                retryable=True,
                attempt_count=1,
                created_by=created_by,
            )
            session.add(job)
            await session.commit()
            return job.id, version.id, course.id

    return asyncio.run(_create())


def _create_admin_class_course(*, created_by: str, teacher_id: str, include_teacher: bool = True):
    async def _create() -> tuple[str, str]:
        from app.core.config import get_settings
        from app.db.models import Course, CourseClass, CourseMember
        from app.db.session import session_factory

        async with session_factory() as session:
            course = Course(
                organization_id=get_settings().default_organization_id,
                title="管理员班级治理课程",
                term="2026 秋",
                created_by=created_by,
            )
            session.add(course)
            await session.flush()
            course_class = CourseClass(
                course_id=course.id,
                code="A-01",
                name="实验班",
                created_by=created_by,
            )
            session.add(course_class)
            if include_teacher:
                session.add(
                    CourseMember(course_id=course.id, user_id=teacher_id, role="teacher")
                )
            await session.commit()
            return course.id, course_class.id

    return asyncio.run(_create())


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def test_admin_can_read_scoped_role_assignments_without_course_content(client) -> None:
    admin_id = create_user_sync(email="governance-admin@uni.edu", is_platform_admin=True)
    target_id = create_user_sync(email="governance-designer@uni.edu", display_name="课程设计师")

    async def _grant_role() -> None:
        from app.db.models import RoleAssignment
        from app.db.session import session_factory

        async with session_factory() as session:
            session.add(
                RoleAssignment(
                    user_id=target_id,
                    role="course_designer",
                    scope_type="platform",
                    granted_by=admin_id,
                )
            )
            await session.commit()

    asyncio.run(_grant_role())
    _login(client, "governance-admin@uni.edu")
    response = client.get("/api/v1/admin/role-assignments?scope_type=platform")
    assert response.status_code == 200
    assert response.json()["data"][0]["user_id"] == target_id
    assert response.json()["data"][0]["role"] == "course_designer"
    assert "password" not in response.json()["data"][0]


def test_non_admin_cannot_read_role_assignments(client) -> None:
    create_user_sync(email="governance-plain@uni.edu")
    _login(client, "governance-plain@uni.edu")
    response = client.get("/api/v1/admin/role-assignments")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_grants_and_revokes_scoped_role_with_reason_audit_and_idempotency(client) -> None:
    admin_id = create_user_sync(email="governance-write-admin@uni.edu", is_platform_admin=True)
    target_id = create_user_sync(
        email="governance-write-target@uni.edu", display_name="待授权设计师"
    )
    _login(client, "governance-write-admin@uni.edu")
    target_search = client.get(
        "/api/v1/admin/role-assignment-targets?q=governance-write-target"
    )
    assert target_search.status_code == 200
    assert [item["id"] for item in target_search.json()["data"]] == [target_id]
    assert "password_hash" not in target_search.json()["data"][0]
    body = {
        "user_id": target_id,
        "role": "course_designer",
        "scope_type": "platform",
        "scope_id": None,
        "reason": "负责本学期课程结构设计",
    }
    headers = {"Idempotency-Key": "grant-designer-0001"}

    granted = client.post("/api/v1/admin/role-assignments", json=body, headers=headers)
    assert granted.status_code == 201
    assignment = granted.json()["data"]
    assert assignment["user_id"] == target_id
    assert assignment["role"] == "course_designer"
    assert assignment["status"] == "active"
    replay = client.post("/api/v1/admin/role-assignments", json=body, headers=headers)
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == assignment["id"]
    assert replay.json()["meta"]["idempotent_replay"] is True
    conflicting_replay = client.post(
        "/api/v1/admin/role-assignments",
        json={**body, "reason": "改用同一幂等键提交了不同的授权理由"},
        headers=headers,
    )
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    audit = client.get("/api/v1/admin/audit-logs?action=admin.role_assignment.granted")
    assert audit.status_code == 200
    assert len(audit.json()["data"]) == 1

    _login(client, "governance-write-target@uni.edu")
    granted_roles = client.get("/api/v1/me").json()["data"]["platform_roles"]
    assert "course_designer" in granted_roles
    assert client.get("/api/v1/courses").json()["data"] == []

    _login(client, "governance-write-admin@uni.edu")
    revoked = client.post(
        f"/api/v1/admin/role-assignments/{assignment['id']}/revoke",
        json={"version": assignment["version"], "reason": "本阶段设计工作已结束"},
        headers={"Idempotency-Key": "revoke-designer-0001"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"
    assert revoked.json()["data"]["version"] == assignment["version"] + 1
    revoke_audits = client.get(
        "/api/v1/admin/audit-logs?action=admin.role_assignment.revoked"
    ).json()["data"]
    assert revoke_audits

    _login(client, "governance-write-target@uni.edu")
    roles = client.get("/api/v1/me").json()["data"]["platform_roles"]
    assert "course_designer" not in roles
    assert target_id != admin_id


def test_role_assignment_writes_are_admin_only_and_reject_unsupported_scope(client) -> None:
    admin_id = create_user_sync(email="governance-validation-admin@uni.edu", is_platform_admin=True)
    target_id = create_user_sync(email="governance-validation-target@uni.edu")
    body = {
        "user_id": target_id,
        "role": "assistant",
        "scope_type": "platform",
        "scope_id": None,
        "reason": "负责当前课程的辅导答疑",
    }
    _login(client, "governance-validation-target@uni.edu")
    denied = client.post(
        "/api/v1/admin/role-assignments",
        json=body,
        headers={"Idempotency-Key": "nonadmin-grant-0001"},
    )
    assert denied.status_code == 403

    _login(client, "governance-validation-admin@uni.edu")
    self_grant = {**body, "user_id": admin_id}
    conflict = client.post(
        "/api/v1/admin/role-assignments",
        json=self_grant,
        headers={"Idempotency-Key": "admin-self-grant-0001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ROLE_SELF_ASSIGNMENT_FORBIDDEN"

    unsupported = {**body, "scope_type": "class", "scope_id": target_id}
    invalid = client.post(
        "/api/v1/admin/role-assignments",
        json=unsupported,
        headers={"Idempotency-Key": "class-scope-grant-001"},
    )
    assert invalid.status_code == 422


def test_course_role_assignment_grants_only_selected_course_and_revocation_is_immediate(
    client,
) -> None:
    admin_id = create_user_sync(email="governance-course-admin@uni.edu", is_platform_admin=True)
    target_id = create_user_sync(
        email="governance-course-target@uni.edu", display_name="课程任课人"
    )

    async def _create_course() -> str:
        from app.core.config import get_settings
        from app.db.models import Course
        from app.db.session import session_factory

        async with session_factory() as session:
            course = Course(
                organization_id=get_settings().default_organization_id,
                title="受限 Scope 测试课程",
                term="2026 秋",
                created_by=admin_id,
            )
            session.add(course)
            await session.commit()
            return course.id

    course_id = asyncio.run(_create_course())
    _login(client, "governance-course-admin@uni.edu")
    response = client.post(
        "/api/v1/admin/role-assignments",
        json={
            "user_id": target_id,
            "role": "teacher",
            "scope_type": "course",
            "scope_id": course_id,
            "reason": "负责该课程本学期教学工作",
        },
        headers={"Idempotency-Key": "course-teacher-grant-001"},
    )
    assert response.status_code == 201
    assignment = response.json()["data"]

    _login(client, "governance-course-target@uni.edu")
    courses = client.get("/api/v1/courses").json()["data"]
    assert [course["id"] for course in courses] == [course_id]
    assert client.get(f"/api/v1/courses/{course_id}").status_code == 200

    _login(client, "governance-course-admin@uni.edu")
    revoked = client.post(
        f"/api/v1/admin/role-assignments/{assignment['id']}/revoke",
        json={"version": assignment["version"], "reason": "课程任课任务已经交接完成"},
        headers={"Idempotency-Key": "course-teacher-revoke-001"},
    )
    assert revoked.status_code == 200

    _login(client, "governance-course-target@uni.edu")
    assert client.get("/api/v1/courses").json()["data"] == []
    assert client.get(f"/api/v1/courses/{course_id}").status_code == 404


def test_admin_role_assignment_search_and_grants_cannot_cross_organization(client) -> None:
    create_user_sync(email="governance-tenant-admin@uni.edu", is_platform_admin=True)

    async def _create_foreign_user() -> str:
        from app.core.security import hash_password
        from app.db.models import Organization, RoleAssignment, User
        from app.db.session import session_factory

        async with session_factory() as session:
            organization = Organization(name="隔离测试机构")
            session.add(organization)
            await session.flush()
            target = User(
                organization_id=organization.id,
                email="foreign-target@other.edu",
                password_hash=hash_password("correct-password"),
                display_name="外机构账号",
            )
            session.add(target)
            await session.commit()
            session.add(
                RoleAssignment(
                    user_id=target.id,
                    role="course_designer",
                    scope_type="platform",
                    status="active",
                    granted_by=target.id,
                )
            )
            await session.commit()
            return target.id

    foreign_id = asyncio.run(_create_foreign_user())
    _login(client, "governance-tenant-admin@uni.edu")
    search = client.get("/api/v1/admin/role-assignment-targets?q=foreign-target")
    assert search.status_code == 200
    assert search.json()["data"] == []
    assignments = client.get("/api/v1/admin/role-assignments?status=all")
    assert assignments.status_code == 200
    assert all(row["user_id"] != foreign_id for row in assignments.json()["data"])
    filtered = client.get(
        f"/api/v1/admin/role-assignments?status=all&user_id={foreign_id}"
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"] == []
    grant = client.post(
        "/api/v1/admin/role-assignments",
        json={
            "user_id": foreign_id,
            "role": "course_designer",
            "scope_type": "platform",
            "scope_id": None,
            "reason": "跨机构授权必须被拒绝",
        },
        headers={"Idempotency-Key": "cross-tenant-grant-01"},
    )
    assert grant.status_code == 404
    assert grant.json()["error"]["code"] == "USER_NOT_FOUND"


def test_admin_governance_lists_support_stable_cursor_pagination(client) -> None:
    admin_id = create_user_sync(email="governance-cursor-admin@uni.edu", is_platform_admin=True)
    target_id = create_user_sync(email="governance-cursor-target@uni.edu")

    async def _seed() -> None:
        from app.core.config import get_settings
        from app.db.models import AuditLog, Course, Job, Material, MaterialVersion, RoleAssignment
        from app.db.session import session_factory

        async with session_factory() as session:
            for role in ("student", "teacher", "assistant"):
                session.add(
                    RoleAssignment(
                        user_id=target_id,
                        role=role,
                        scope_type="platform",
                        status="active",
                        granted_by=admin_id,
                    )
                )
            session.add_all(
                [
                    AuditLog(
                        actor_id=admin_id,
                        action="r2.cursor.test",
                        resource_type="cursor_fixture",
                    )
                    for _ in range(3)
                ]
            )
            for index in range(3):
                course = Course(
                    organization_id=get_settings().default_organization_id,
                    title=f"分页任务课程 {index}",
                    term="2026 秋",
                    created_by=admin_id,
                )
                session.add(course)
                await session.flush()
                material = Material(
                    course_id=course.id,
                    title=f"分页教材 {index}",
                    material_type="textbook",
                    created_by=admin_id,
                )
                session.add(material)
                await session.flush()
                version = MaterialVersion(
                    material_id=material.id,
                    version_no=1,
                    status="failed",
                    created_by=admin_id,
                )
                session.add(version)
                await session.flush()
                session.add(
                    Job(
                        kind="material_parse",
                        status="failed",
                        stage="failed",
                        progress=100,
                        payload={"material_version_id": version.id},
                        retryable=True,
                        attempt_count=1,
                        created_by=admin_id,
                    )
                )
            await session.commit()

    asyncio.run(_seed())
    _login(client, "governance-cursor-admin@uni.edu")

    cases = (
        (
            f"/api/v1/admin/role-assignments?status=all&user_id={target_id}",
            3,
        ),
        ("/api/v1/admin/audit-logs?action=r2.cursor.test", 3),
        ("/api/v1/admin/jobs?status=failed", 3),
    )
    for path, expected_count in cases:
        seen: list[str] = []
        cursor: str | None = None
        while True:
            separator = "&" if "?" in path else "?"
            cursor_query = f"&cursor={cursor}" if cursor else ""
            response = client.get(f"{path}{separator}limit=2{cursor_query}")
            assert response.status_code == 200
            payload = response.json()
            page = [row["id"] for row in payload["data"]]
            assert not (set(page) & set(seen))
            seen.extend(page)
            if payload["meta"]["has_more"]:
                assert payload["meta"]["next_cursor"]
                cursor = payload["meta"]["next_cursor"]
            else:
                assert payload["meta"].get("next_cursor") is None
                break
        assert len(seen) == expected_count
        assert len(set(seen)) == expected_count


def test_admin_governance_lists_reject_malformed_cursor(client) -> None:
    create_user_sync(email="governance-cursor-invalid-admin@uni.edu", is_platform_admin=True)
    _login(client, "governance-cursor-invalid-admin@uni.edu")
    for path in (
        "/api/v1/admin/role-assignments?cursor=not-a-valid-cursor",
        "/api/v1/admin/audit-logs?cursor=not-a-valid-cursor",
        "/api/v1/admin/jobs?cursor=not-a-valid-cursor",
    ):
        response = client.get(path)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_CURSOR"


def test_admin_manages_course_and_class_members_with_audit_version_and_idempotency(client) -> None:
    admin_id = create_user_sync(email="governance-roster-admin@uni.edu", is_platform_admin=True)
    teacher_id = create_user_sync(
        email="governance-roster-teacher@uni.edu", is_teacher=True, display_name="任课教师"
    )
    student_id = create_user_sync(
        email="governance-roster-student@uni.edu", display_name="班级学生"
    )
    course_id, class_id = _create_admin_class_course(
        created_by=admin_id,
        teacher_id=teacher_id,
    )
    _login(client, "governance-roster-admin@uni.edu")

    courses = client.get("/api/v1/admin/courses?status=all&limit=1")
    assert courses.status_code == 200
    assert courses.json()["data"][0]["id"] == course_id
    classes = client.get(f"/api/v1/admin/courses/{course_id}/classes?status=all")
    assert classes.status_code == 200
    assert classes.json()["data"][0]["id"] == class_id
    assert classes.json()["data"][0]["member_count"] == 0
    assert classes.json()["data"][0]["active_teacher_count"] == 0

    created_class = client.post(
        f"/api/v1/admin/courses/{course_id}/classes",
        json={"code": "B-02", "name": "对照班", "reason": "按课程教学安排新增班级"},
        headers={"Idempotency-Key": "admin-class-create-0001"},
    )
    assert created_class.status_code == 201
    assert created_class.json()["data"]["code"] == "B-02"
    assert created_class.json()["data"]["member_count"] == 0
    replay_class = client.post(
        f"/api/v1/admin/courses/{course_id}/classes",
        json={"code": "B-02", "name": "对照班", "reason": "按课程教学安排新增班级"},
        headers={"Idempotency-Key": "admin-class-create-0001"},
    )
    assert replay_class.status_code == 201
    assert replay_class.json()["data"]["id"] == created_class.json()["data"]["id"]
    assert replay_class.json()["meta"]["idempotent_replay"] is True

    course_member = client.post(
        f"/api/v1/admin/courses/{course_id}/members",
        json={"user_id": student_id, "role": "student", "reason": "完成本学期课程选课登记"},
        headers={"Idempotency-Key": "admin-course-member-add-01"},
    )
    assert course_member.status_code == 201
    member_row = course_member.json()["data"]
    assert member_row["role"] == "student"
    assert member_row["status"] == "active"
    course_members = client.get(f"/api/v1/admin/courses/{course_id}/members?status=all")
    assert any(item["id"] == member_row["id"] for item in course_members.json()["data"])

    class_member = client.post(
        f"/api/v1/admin/classes/{class_id}/members",
        json={"user_id": student_id, "reason": "按课程分班方案编入实验班"},
        headers={"Idempotency-Key": "admin-class-member-add-01"},
    )
    assert class_member.status_code == 201
    class_member_row = class_member.json()["data"]
    assert class_member_row["status"] == "active"
    assert client.get(f"/api/v1/admin/classes/{class_id}/members").json()["data"][0][
        "user_id"
    ] == student_id

    stale_remove = client.post(
        f"/api/v1/admin/classes/{class_id}/members/{class_member_row['id']}/remove",
        json={"version": 99, "reason": "修正学生班级归属信息"},
        headers={"Idempotency-Key": "admin-class-member-remove-stale"},
    )
    assert stale_remove.status_code == 409
    assert stale_remove.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    removed = client.post(
        f"/api/v1/admin/courses/{course_id}/members/{member_row['id']}/remove",
        json={"version": member_row["version"], "reason": "学生已办理本课程退选"},
        headers={"Idempotency-Key": "admin-course-member-remove-01"},
    )
    assert removed.status_code == 200
    assert removed.json()["data"] == {
        "id": member_row["id"],
        "status": "removed",
        "version": member_row["version"] + 1,
    }
    roster = client.get(f"/api/v1/admin/classes/{class_id}/members?status=all")
    withdrawn = next(item for item in roster.json()["data"] if item["id"] == class_member_row["id"])
    assert withdrawn["status"] == "removed"
    assert withdrawn["version"] == class_member_row["version"] + 1
    replay_remove = client.post(
        f"/api/v1/admin/courses/{course_id}/members/{member_row['id']}/remove",
        json={"version": member_row["version"], "reason": "学生已办理本课程退选"},
        headers={"Idempotency-Key": "admin-course-member-remove-01"},
    )
    assert replay_remove.status_code == 200
    assert replay_remove.json()["meta"]["idempotent_replay"] is True

    admin_self_join = client.post(
        f"/api/v1/admin/courses/{course_id}/members",
        json={"user_id": admin_id, "role": "teacher", "reason": "管理员自我提权测试"},
        headers={"Idempotency-Key": "admin-self-course-member-01"},
    )
    assert admin_self_join.status_code == 409
    assert admin_self_join.json()["error"]["code"] == "ROLE_SELF_ASSIGNMENT_FORBIDDEN"


def test_admin_course_and_roster_governance_cannot_cross_organization(client) -> None:
    admin_id = create_user_sync(
        email="governance-roster-scope-admin@uni.edu", is_platform_admin=True
    )
    local_teacher_id = create_user_sync(
        email="governance-roster-scope-teacher@uni.edu", is_teacher=True
    )
    local_course_id, local_class_id = _create_admin_class_course(
        created_by=admin_id,
        teacher_id=local_teacher_id,
    )

    async def _create_foreign_scope() -> tuple[str, str, str]:
        from app.core.security import hash_password
        from app.db.models import ClassMember, Course, CourseClass, CourseMember, Organization, User
        from app.db.session import session_factory

        async with session_factory() as session:
            foreign_org = Organization(name="R2 管理隔离机构")
            session.add(foreign_org)
            await session.flush()
            foreign_user = User(
                organization_id=foreign_org.id,
                email="governance-roster-foreign-student@other.edu",
                password_hash=hash_password("correct-password"),
                display_name="外机构学生",
            )
            session.add(foreign_user)
            await session.flush()
            foreign_course = Course(
                organization_id=foreign_org.id,
                title="外机构课程",
                term="2026 秋",
                created_by=foreign_user.id,
            )
            session.add(foreign_course)
            await session.flush()
            foreign_class = CourseClass(
                course_id=foreign_course.id,
                code="X-01",
                name="外机构班级",
                created_by=foreign_user.id,
            )
            session.add(foreign_class)
            session.add(
                CourseMember(course_id=foreign_course.id, user_id=foreign_user.id, role="student")
            )
            await session.flush()
            session.add(ClassMember(class_id=foreign_class.id, user_id=foreign_user.id))
            await session.commit()
            return foreign_user.id, foreign_course.id, foreign_class.id

    foreign_user_id, foreign_course_id, foreign_class_id = asyncio.run(_create_foreign_scope())
    _login(client, "governance-roster-scope-admin@uni.edu")

    courses = client.get("/api/v1/admin/courses?status=all")
    assert courses.status_code == 200
    assert all(row["id"] != foreign_course_id for row in courses.json()["data"])
    assert (
        client.get(f"/api/v1/admin/courses/{foreign_course_id}/classes?status=all").status_code
        == 404
    )
    assert client.get(f"/api/v1/admin/courses/{foreign_course_id}/members").status_code == 404
    assert client.get(f"/api/v1/admin/classes/{foreign_class_id}/members").status_code == 404

    foreign_add = client.post(
        f"/api/v1/admin/courses/{local_course_id}/members",
        json={"user_id": foreign_user_id, "role": "student", "reason": "机构范围回归验证"},
        headers={"Idempotency-Key": "admin-foreign-member-add-01"},
    )
    assert foreign_add.status_code == 404
    assert foreign_add.json()["error"]["code"] == "USER_NOT_FOUND"

    local_classes = client.get(f"/api/v1/admin/courses/{local_course_id}/classes?status=all")
    assert local_classes.status_code == 200
    assert any(row["id"] == local_class_id for row in local_classes.json()["data"])


def test_admin_lists_only_minimal_same_organization_job_metadata(client) -> None:
    from app.core.config import get_settings

    admin_id = create_user_sync(email="job-list-admin@uni.edu", is_platform_admin=True)
    job_id, _version_id, course_id = _create_admin_job(
        created_by=admin_id,
        organization_id=get_settings().default_organization_id,
    )
    _login(client, "job-list-admin@uni.edu")

    response = client.get("/api/v1/admin/jobs?status=failed")

    assert response.status_code == 200
    row = next(item for item in response.json()["data"] if item["id"] == job_id)
    assert row["course_id"] == course_id
    assert row["has_error"] is True
    assert "error" not in row
    assert "payload" not in row
    assert "private_text" not in str(row)
    assert "sensitive provider response" not in str(row)


def test_admin_retries_failed_job_with_version_reason_audit_and_idempotency(client) -> None:
    from app.core.config import get_settings

    admin_id = create_user_sync(email="job-retry-admin@uni.edu", is_platform_admin=True)
    job_id, _version_id, course_id = _create_admin_job(
        created_by=admin_id,
        organization_id=get_settings().default_organization_id,
    )
    _login(client, "job-retry-admin@uni.edu")
    body = {"version": 1, "reason": "解析服务短暂故障，确认后重新执行"}
    headers = {"Idempotency-Key": "admin-job-retry-0001"}

    with patch("app.modules.memory.router.dispatch_parse_job") as dispatch:
        response = client.post(f"/api/v1/admin/jobs/{job_id}/retry", json=body, headers=headers)
        replay = client.post(f"/api/v1/admin/jobs/{job_id}/retry", json=body, headers=headers)

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"
    assert response.json()["data"]["version"] == 2
    assert replay.status_code == 202
    assert replay.json()["meta"]["idempotent_replay"] is True
    assert dispatch.call_count == 1
    assert dispatch.call_args.args[0] == job_id
    already_queued = client.post(
        f"/api/v1/admin/jobs/{job_id}/retry",
        json={**body, "version": 2},
        headers={"Idempotency-Key": "admin-job-retry-second"},
    )
    assert already_queued.status_code == 409
    assert already_queued.json()["error"]["code"] == "JOB_NOT_RETRYABLE"

    audit = client.get("/api/v1/admin/audit-logs?action=admin.job.retry_requested")
    assert audit.status_code == 200
    assert len(audit.json()["data"]) == 1
    assert audit.json()["data"][0]["course_id"] == course_id


def test_admin_retry_rejects_nonretryable_stale_and_nonadmin_requests(client) -> None:
    from app.core.config import get_settings
    from app.db.models import Job
    from app.db.session import session_factory

    admin_id = create_user_sync(email="job-invalid-admin@uni.edu", is_platform_admin=True)
    create_user_sync(email="job-invalid-plain@uni.edu")
    job_id, _version_id, _course_id = _create_admin_job(
        created_by=admin_id,
        organization_id=get_settings().default_organization_id,
    )

    async def _disable_retry() -> None:
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            job.retryable = False
            job.version += 1
            await session.commit()

    asyncio.run(_disable_retry())
    body = {"version": 2, "reason": "仅用于验证不可重试任务保护"}
    headers = {"Idempotency-Key": "admin-job-retry-invalid"}

    _login(client, "job-invalid-plain@uni.edu")
    denied = client.post(f"/api/v1/admin/jobs/{job_id}/retry", json=body, headers=headers)
    assert denied.status_code == 403

    _login(client, "job-invalid-admin@uni.edu")
    stale = client.post(
        f"/api/v1/admin/jobs/{job_id}/retry",
        json={**body, "version": 1},
        headers={"Idempotency-Key": "admin-job-retry-stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    not_retryable = client.post(
        f"/api/v1/admin/jobs/{job_id}/retry",
        json=body,
        headers={"Idempotency-Key": "admin-job-retry-not-retryable"},
    )
    assert not_retryable.status_code == 409
    assert not_retryable.json()["error"]["code"] == "JOB_NOT_RETRYABLE"

    async def _exhaust_attempts() -> None:
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            job.retryable = True
            job.attempt_count = 5
            job.version += 1
            await session.commit()

    asyncio.run(_exhaust_attempts())
    exhausted = client.post(
        f"/api/v1/admin/jobs/{job_id}/retry",
        json={**body, "version": 3},
        headers={"Idempotency-Key": "admin-job-retry-exhausted"},
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["error"]["code"] == "JOB_RETRY_LIMIT_REACHED"


def test_admin_cannot_list_or_retry_jobs_from_another_organization(client) -> None:
    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.db.models import Organization, User
    from app.db.session import session_factory

    create_user_sync(email="job-tenant-admin@uni.edu", is_platform_admin=True)

    async def _create_foreign_job() -> tuple[str, str]:
        async with session_factory() as session:
            organization = Organization(name="任务隔离机构")
            session.add(organization)
            await session.flush()
            foreign_user = User(
                organization_id=organization.id,
                email="job-owner@foreign.edu",
                password_hash=hash_password("correct-password"),
                display_name="任务创建人",
            )
            session.add(foreign_user)
            await session.flush()
            course = Course(
                organization_id=organization.id,
                title="外机构课程",
                term="2026 秋",
                created_by=foreign_user.id,
            )
            session.add(course)
            await session.flush()
            material = Material(
                course_id=course.id,
                title="外机构教材",
                material_type="textbook",
                created_by=foreign_user.id,
            )
            session.add(material)
            await session.flush()
            version = MaterialVersion(
                material_id=material.id,
                version_no=1,
                status="failed",
                created_by=foreign_user.id,
            )
            session.add(version)
            await session.flush()
            job = Job(
                kind="material_embed",
                status="failed",
                stage="failed",
                payload={"material_version_id": version.id},
                retryable=True,
                attempt_count=1,
                created_by=foreign_user.id,
            )
            session.add(job)
            await session.commit()
            return job.id, organization.id

    from app.db.models import Course, Job, Material, MaterialVersion

    foreign_job_id, foreign_organization_id = asyncio.run(_create_foreign_job())
    assert foreign_organization_id != get_settings().default_organization_id
    _login(client, "job-tenant-admin@uni.edu")

    listed = client.get("/api/v1/admin/jobs")
    assert listed.status_code == 200
    assert all(item["id"] != foreign_job_id for item in listed.json()["data"])

    with patch("app.modules.memory.router.dispatch_embed_job") as dispatch:
        hidden = client.post(
            f"/api/v1/admin/jobs/{foreign_job_id}/retry",
            json={"version": 1, "reason": "不得跨机构操作其他机构的任务"},
            headers={"Idempotency-Key": "foreign-job-retry-0001"},
        )
    assert hidden.status_code == 404
    dispatch.assert_not_called()


def test_admin_dispatch_failure_is_recorded_as_retryable_and_idempotent(client) -> None:
    from app.core.config import get_settings
    from app.db.models import Job
    from app.db.session import session_factory

    create_user_sync(email="job-dispatch-admin@uni.edu", is_platform_admin=True)
    job_id, _version_id, _course_id = _create_admin_job(
        created_by=create_user_sync(email="job-dispatch-owner@uni.edu"),
        organization_id=get_settings().default_organization_id,
    )
    _login(client, "job-dispatch-admin@uni.edu")
    body = {"version": 1, "reason": "验证调度器暂时不可用时的恢复处理"}
    headers = {"Idempotency-Key": "admin-job-dispatch-fail"}

    with patch(
        "app.modules.memory.router.dispatch_parse_job",
        side_effect=RuntimeError("private broker address must not be logged"),
    ) as dispatch:
        failed = client.post(f"/api/v1/admin/jobs/{job_id}/retry", json=body, headers=headers)
        replay = client.post(f"/api/v1/admin/jobs/{job_id}/retry", json=body, headers=headers)

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "JOB_DISPATCH_FAILED"
    assert replay.status_code == 202
    assert replay.json()["data"]["status"] == "failed"
    assert replay.json()["data"]["retryable"] is True
    assert replay.json()["meta"]["idempotent_replay"] is True
    assert dispatch.call_count == 1

    async def _read_job() -> tuple[str, str | None, int]:
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            return job.status, job.error, job.version

    status, error, version = asyncio.run(_read_job())
    assert status == "failed"
    assert error == "任务派发失败，请稍后重试"
    assert version == 3


def test_admin_assigns_and_ends_class_teacher_with_audit_and_idempotency(client) -> None:
    admin_id = create_user_sync(email="class-admin@uni.edu", is_platform_admin=True)
    teacher_id = create_user_sync(
        email="class-admin-target@uni.edu", is_teacher=True, display_name="班级任课教师"
    )
    course_id, class_id = _create_admin_class_course(
        created_by=admin_id,
        teacher_id=teacher_id,
    )
    _login(client, "class-admin@uni.edu")
    options = client.get(f"/api/v1/admin/class-assignment-options?course_id={course_id}")
    assert options.status_code == 200
    assert [item["id"] for item in options.json()["data"]["classes"]] == [class_id]
    assert [item["id"] for item in options.json()["data"]["teachers"]] == [teacher_id]
    assert "email" not in options.json()["data"]["teachers"][0]

    body = {
        "class_id": class_id,
        "teacher_id": teacher_id,
        "assignment_role": "lead",
        "reason": "负责该班本学期实验教学与学生支持",
    }
    headers = {"Idempotency-Key": "admin-class-assign-0001"}
    assigned = client.post(
        "/api/v1/admin/class-teacher-assignments", json=body, headers=headers
    )
    replay = client.post(
        "/api/v1/admin/class-teacher-assignments", json=body, headers=headers
    )
    assert assigned.status_code == 201
    assignment = assigned.json()["data"]
    assert assignment["teacher_id"] == teacher_id
    assert assignment["status"] == "active"
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == assignment["id"]
    assert replay.json()["meta"]["idempotent_replay"] is True

    conflicting_replay = client.post(
        "/api/v1/admin/class-teacher-assignments",
        json={**body, "reason": "同一幂等键不能用于不同授权理由"},
        headers=headers,
    )
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    _login(client, "class-admin-target@uni.edu")
    visible = client.get(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teachers"
    )
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["data"]] == [assignment["id"]]

    _login(client, "class-admin@uni.edu")
    end_body = {"version": assignment["version"], "reason": "班级任课任务交接完成"}
    end_headers = {"Idempotency-Key": "admin-class-end-0001"}
    ended = client.post(
        f"/api/v1/admin/class-teacher-assignments/{assignment['id']}/end",
        json=end_body,
        headers=end_headers,
    )
    end_replay = client.post(
        f"/api/v1/admin/class-teacher-assignments/{assignment['id']}/end",
        json=end_body,
        headers=end_headers,
    )
    assert ended.status_code == 200
    assert ended.json()["data"]["status"] == "ended"
    assert ended.json()["data"]["version"] == assignment["version"] + 1
    assert end_replay.json()["meta"]["idempotent_replay"] is True

    stale_end = client.post(
        f"/api/v1/admin/class-teacher-assignments/{assignment['id']}/end",
        json=end_body,
        headers={"Idempotency-Key": "admin-class-end-stale"},
    )
    assert stale_end.status_code == 409
    assert stale_end.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    _login(client, "class-admin-target@uni.edu")
    no_longer_assigned = client.get(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teachers"
    )
    assert no_longer_assigned.status_code == 200
    assert no_longer_assigned.json()["data"] == []

    _login(client, "class-admin@uni.edu")
    assigned_audit = client.get(
        "/api/v1/admin/audit-logs?action=admin.class.teacher_assigned"
    ).json()["data"]
    ended_audit = client.get(
        "/api/v1/admin/audit-logs?action=admin.class.teacher_assignment_ended"
    ).json()["data"]
    assert len(assigned_audit) == len(ended_audit) == 1


def test_admin_class_assignment_rejects_nonmember_nonadmin_and_foreign_scope(client) -> None:
    from app.core.security import hash_password
    from app.db.models import Course, CourseClass, Organization, User
    from app.db.session import session_factory

    admin_id = create_user_sync(email="class-guard-admin@uni.edu", is_platform_admin=True)
    other_id = create_user_sync(email="class-guard-other@uni.edu", is_teacher=True)
    course_id, class_id = _create_admin_class_course(
        created_by=admin_id,
        teacher_id=other_id,
        include_teacher=False,
    )

    async def _create_foreign_class() -> tuple[str, str]:
        async with session_factory() as session:
            organization = Organization(name="外机构班级治理组织")
            session.add(organization)
            await session.flush()
            owner = User(
                organization_id=organization.id,
                email="class-foreign-owner@other.edu",
                password_hash=hash_password("correct-password"),
                display_name="外机构课程负责人",
            )
            session.add(owner)
            await session.flush()
            foreign_course = Course(
                organization_id=organization.id,
                title="外机构班级课程",
                term="2026 秋",
                created_by=owner.id,
            )
            session.add(foreign_course)
            await session.flush()
            foreign_class = CourseClass(
                course_id=foreign_course.id,
                code="F-01",
                name="外机构班级",
                created_by=owner.id,
            )
            session.add(foreign_class)
            await session.commit()
            return foreign_course.id, foreign_class.id

    foreign_course_id, foreign_class_id = asyncio.run(_create_foreign_class())
    body = {
        "class_id": class_id,
        "teacher_id": other_id,
        "assignment_role": "assistant",
        "reason": "不得将未加入课程的账号设为任课教师",
    }
    headers = {"Idempotency-Key": "class-nonmember-assign"}
    _login(client, "class-guard-other@uni.edu")
    denied = client.get(f"/api/v1/admin/class-assignment-options?course_id={course_id}")
    assert denied.status_code == 403

    _login(client, "class-guard-admin@uni.edu")
    options = client.get(
        f"/api/v1/admin/class-assignment-options?course_id={foreign_course_id}"
    )
    assert options.status_code == 404
    not_member = client.post(
        "/api/v1/admin/class-teacher-assignments", json=body, headers=headers
    )
    assert not_member.status_code == 409
    assert not_member.json()["error"]["code"] == "TEACHER_NOT_COURSE_MEMBER"
    foreign_scope = client.post(
        "/api/v1/admin/class-teacher-assignments",
        json={**body, "class_id": foreign_class_id},
        headers={"Idempotency-Key": "foreign-class-assign-001"},
    )
    assert foreign_scope.status_code == 404
    assert foreign_scope.json()["error"]["code"] == "CLASS_NOT_FOUND"
