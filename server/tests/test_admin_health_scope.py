from tests.conftest import create_user_sync


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def test_admin_health_aggregates_are_scoped_to_the_admin_organization(client) -> None:
    from app.core.security import hash_password
    from app.db.models import (
        Assessment,
        Attempt,
        Course,
        LearningEvidence,
        MasteryState,
        MemoryItem,
        ModelCallLog,
        Organization,
        User,
    )
    from app.db.session import session_factory

    local_admin_id = create_user_sync(
        email="health-scope-local-admin@uni.edu", is_platform_admin=True
    )
    local_student_id = create_user_sync(email="health-scope-local-student@uni.edu")

    async def create_fixtures() -> None:
        async with session_factory() as session:
            local_admin = await session.get(User, local_admin_id)
            assert local_admin is not None
            foreign_org = Organization(name="健康聚合外部机构")
            session.add(foreign_org)
            await session.flush()
            foreign_admin = User(
                organization_id=foreign_org.id,
                email="health-scope-foreign-admin@uni.edu",
                password_hash=hash_password("correct-password"),
                display_name="外机构管理员",
                is_platform_admin=True,
            )
            foreign_student = User(
                organization_id=foreign_org.id,
                email="health-scope-foreign-student@uni.edu",
                password_hash=hash_password("correct-password"),
                display_name="外机构学生",
            )
            session.add_all([foreign_admin, foreign_student])
            await session.flush()

            local_course = Course(
                organization_id=local_admin.organization_id,
                title="健康聚合本机构课程",
                term="2026 秋",
                created_by=local_admin_id,
            )
            foreign_course = Course(
                organization_id=foreign_org.id,
                title="健康聚合外机构课程",
                term="2026 秋",
                created_by=foreign_admin.id,
            )
            session.add_all([local_course, foreign_course])
            await session.flush()

            for learner_id, course_id, prefix in (
                (local_student_id, local_course.id, "local"),
                (foreign_student.id, foreign_course.id, "foreign"),
            ):
                session.add_all(
                    [
                        LearningEvidence(
                            user_id=learner_id,
                            course_id=course_id,
                            knowledge_point=f"{prefix}-kp",
                            question_version_id=f"{prefix}-question-version",
                            source_type="practice",
                            correct=True,
                            weight=1.0,
                        ),
                        MasteryState(
                            user_id=learner_id,
                            course_id=course_id,
                            knowledge_point=f"{prefix}-kp",
                            state="learning",
                        ),
                        MemoryItem(
                            user_id=learner_id,
                            course_id=course_id,
                            layer="L1",
                            kind="test",
                            content=f"{prefix}-private-memory",
                            source_type="tutor",
                        ),
                        ModelCallLog(
                            purpose="tutor",
                            provider="local",
                            model="test-model",
                            status="ok",
                            latency_ms=1,
                            user_id=learner_id,
                        ),
                    ]
                )
                assessment = Assessment(
                    course_id=course_id,
                    title=f"{prefix}-assessment",
                    created_by=local_admin_id if prefix == "local" else foreign_admin.id,
                    status="published",
                )
                session.add(assessment)
                await session.flush()
                session.add(
                    Attempt(
                        assessment_id=assessment.id,
                        user_id=learner_id,
                        status="in_progress",
                    )
                )
            await session.commit()

    import asyncio

    asyncio.run(create_fixtures())
    _login(client, "health-scope-local-admin@uni.edu")

    response = client.get("/api/v1/admin/health")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["counts"] == {
        "users": 2,
        "learning_evidences": 1,
        "mastery_states": 1,
        "memory_items": 1,
        "model_call_logs": 1,
    }
    assert data["model_calls"] == [{"purpose": "tutor", "status": "ok", "count": 1}]
    assert data["attempts_in_progress"] == 1
