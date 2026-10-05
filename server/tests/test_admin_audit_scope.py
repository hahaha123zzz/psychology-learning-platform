import asyncio

from tests.conftest import create_user_sync


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def test_admin_audit_logs_are_scoped_to_the_admin_organization(client) -> None:
    from app.core.security import hash_password
    from app.db.models import AuditLog, Course, Organization, User
    from app.db.session import session_factory

    local_admin_id = create_user_sync(
        email="audit-scope-local-admin@uni.edu", is_platform_admin=True
    )

    async def create_fixtures() -> tuple[str, list[str]]:
        async with session_factory() as session:
            foreign_org = Organization(name="审计隔离外部机构")
            session.add(foreign_org)
            await session.flush()
            foreign_admin = User(
                organization_id=foreign_org.id,
                email="audit-scope-foreign-admin@uni.edu",
                password_hash=hash_password("correct-password"),
                display_name="外机构管理员",
                is_platform_admin=True,
            )
            session.add(foreign_admin)
            await session.flush()

            local_course = Course(
                organization_id=(
                    await session.get(User, local_admin_id)
                ).organization_id,
                title="本机构审计课程",
                term="2026 秋",
                created_by=local_admin_id,
            )
            foreign_course = Course(
                organization_id=foreign_org.id,
                title="外机构审计课程",
                term="2026 秋",
                created_by=foreign_admin.id,
            )
            session.add_all([local_course, foreign_course])
            await session.flush()

            actions = [
                "audit.scope.local_global",
                "audit.scope.foreign_global",
                "audit.scope.local_course",
                "audit.scope.foreign_course",
                "audit.scope.local_actor_foreign_course",
            ]
            session.add_all(
                [
                    AuditLog(
                        actor_id=local_admin_id,
                        action=actions[0],
                        resource_type="test_global",
                    ),
                    AuditLog(
                        actor_id=foreign_admin.id,
                        action=actions[1],
                        resource_type="test_global",
                    ),
                    AuditLog(
                        actor_id=local_admin_id,
                        action=actions[2],
                        resource_type="test_course",
                        course_id=local_course.id,
                    ),
                    AuditLog(
                        actor_id=foreign_admin.id,
                        action=actions[3],
                        resource_type="test_course",
                        course_id=foreign_course.id,
                    ),
                    AuditLog(
                        actor_id=local_admin_id,
                        action=actions[4],
                        resource_type="test_course",
                        course_id=foreign_course.id,
                    ),
                ]
            )
            await session.commit()
            return foreign_admin.id, actions

    _foreign_admin_id, actions = asyncio.run(create_fixtures())
    _login(client, "audit-scope-local-admin@uni.edu")

    response = client.get("/api/v1/admin/audit-logs?limit=200")

    assert response.status_code == 200
    visible_actions = {entry["action"] for entry in response.json()["data"]}
    assert actions[0] in visible_actions
    assert actions[2] in visible_actions
    assert actions[1] not in visible_actions
    assert actions[3] not in visible_actions
    assert actions[4] not in visible_actions
