import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tests.conftest import create_user_sync

COURSE_BODY = {"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"}


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def _create_observation_request(client, *, course_id: str, body: dict, key: str | None = None):
    return client.post(
        f"/api/v1/courses/{course_id}/observations",
        json=body,
        headers={"Idempotency-Key": key or str(uuid4())},
    )


def _create_observation_class(client, *, course_id: str, teacher_id: str, student_id: str) -> str:
    created = client.post(
        f"/api/v1/courses/{course_id}/classes",
        json={"code": "OBS01", "name": "观察范围班级"},
    )
    assert created.status_code == 201
    class_id = created.json()["data"]["id"]
    assigned = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/teachers",
        json={"teacher_id": teacher_id, "assignment_role": "lead"},
    )
    assert assigned.status_code == 201
    member = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/members",
        json={"user_id": student_id},
    )
    assert member.status_code == 201
    return class_id


def _create_learning_evidence_sync(*, user_id: str, course_id: str, valid: bool = True) -> str:
    from app.db.models import LearningEvidence
    from app.db.session import session_factory

    async def _create() -> str:
        async with session_factory() as session:
            evidence = LearningEvidence(
                user_id=user_id,
                course_id=course_id,
                knowledge_point="experiment:random-assignment",
                question_version_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                source_type="practice",
                dimension="understand",
                independence_status="independent",
                context_key="fixture:observation",
                quality_status="valid" if valid else "invalidated",
                hints_used=0,
                correct=False,
                weight=1.0,
            )
            session.add(evidence)
            await session.flush()
            await session.commit()
            return evidence.id

    return asyncio.run(_create())


def _count_learning_evidence_sync(*, user_id: str, course_id: str) -> int:
    from sqlalchemy import func, select

    from app.db.models import LearningEvidence
    from app.db.session import session_factory

    async def _count() -> int:
        async with session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count(LearningEvidence.id)).where(
                        LearningEvidence.user_id == user_id,
                        LearningEvidence.course_id == course_id,
                    )
                )
                or 0
            )

    return asyncio.run(_count())


def _invalidate_learning_evidence_sync(evidence_id: str) -> None:
    from app.db.models import LearningEvidence
    from app.db.session import session_factory

    async def _invalidate() -> None:
        async with session_factory() as session:
            evidence = await session.get(LearningEvidence, evidence_id)
            assert evidence is not None
            evidence.quality_status = "invalidated"
            evidence.invalidated_reason = "test_source_invalidated"
            await session.commit()

    asyncio.run(_invalidate())


def _create_qualified_learning_event_sync(
    *, user_id: str, course_id: str, context_key: str, attempt_id: str
) -> tuple[str, str]:
    from app.db.models import LearningEvent, LearningEvidence, LearningQualification
    from app.db.session import session_factory

    async def _create() -> tuple[str, str]:
        async with session_factory() as session:
            evidence = LearningEvidence(
                user_id=user_id,
                course_id=course_id,
                knowledge_point="experiment:random-assignment",
                question_version_id="01ARZ3NDEKTSV4RRFFQ69G5FAW",
                attempt_id=attempt_id,
                source_type="practice",
                dimension="apply",
                independence_status="independent",
                context_key=context_key,
                quality_status="valid",
                hints_used=0,
                correct=True,
                weight=1.0,
            )
            event = LearningEvent(
                event_key=f"observation-verify-{attempt_id}",
                user_id=user_id,
                course_id=course_id,
                event_type="answer_submitted",
                source_type="practice",
                source_ref=attempt_id,
                payload={},
                occurred_at=datetime.now(UTC),
                qualification_status="qualified",
                qualification_reason="test_authoritative_activity",
                qualified_at=datetime.now(UTC),
            )
            session.add_all([evidence, event])
            await session.flush()
            qualification = LearningQualification(
                event_id=event.id,
                user_id=user_id,
                course_id=course_id,
                status="qualified",
                reason="test_authoritative_activity",
                algorithm_version="qualification-v1",
                evidence_ids=[evidence.id],
            )
            session.add(qualification)
            await session.commit()
            return event.id, evidence.id

    return asyncio.run(_create())


def _create_pending_learning_event_sync(*, user_id: str, course_id: str) -> str:
    from app.db.models import LearningEvent
    from app.db.session import session_factory

    async def _create() -> str:
        async with session_factory() as session:
            event = LearningEvent(
                event_key="observation-pending-revalidation",
                user_id=user_id,
                course_id=course_id,
                event_type="answer_submitted",
                source_type="practice",
                source_ref="01ARZ3NDEKTSV4RRFFQ69G5FAY",
                payload={},
                occurred_at=datetime.now(UTC),
                qualification_status="pending",
            )
            session.add(event)
            await session.flush()
            await session.commit()
            return event.id

    return asyncio.run(_create())


def test_intervention_lifecycle_freezes_target_and_separates_evaluation(client) -> None:
    create_user_sync(email="intervention-teacher@uni.edu", is_teacher=True)
    _login(client, "intervention-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]

    created = client.post(
        f"/api/v1/courses/{course['id']}/interventions",
        json={
            "title": "操作化变量再练习",
            "activity_type": "practice_set",
            "target_snapshot": {"knowledge_point": "操作化", "evidence_count": 2},
            "plan": {"question_count": 3, "mode": "guided"},
        },
    )
    assert created.status_code == 201
    item = created.json()["data"]
    assert item["status"] == "draft"
    target = item["target_snapshot"]

    scheduled = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{item['id']}/schedule",
        json={
            "version": item["version"],
            "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    item = scheduled.json()["data"]
    assert item["status"] == "scheduled"
    assert item["target_snapshot"] == target

    started = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{item['id']}/start",
        json={"version": item["version"]},
    )
    assert started.status_code == 200
    item = started.json()["data"]
    completed = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{item['id']}/complete",
        json={"version": item["version"]},
    )
    assert completed.status_code == 200
    item = completed.json()["data"]
    assert item["status"] == "completed"
    assert item["outcome"] is None

    evaluated = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{item['id']}/evaluate",
        json={"version": item["version"], "outcome": {"immediate_check": "improved"}},
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["data"]["status"] == "evaluated"
    assert evaluated.json()["data"]["target_snapshot"] == target

    listed = client.get(f"/api/v1/courses/{course['id']}/interventions")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == item["id"]


def test_intervention_rejects_student_and_cross_course_class(client) -> None:
    create_user_sync(email="intervention-owner@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="intervention-student@uni.edu")
    _login(client, "intervention-owner@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    class_response = client.post(
        f"/api/v1/courses/{course['id']}/classes", json={"code": "A01", "name": "一班"}
    )
    assert class_response.status_code == 201
    class_id = class_response.json()["data"]["id"]

    _login(client, "intervention-student@uni.edu")
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/members",
            json={"user_id": student_id, "role": "student"},
        ).status_code
        == 404
    )

    _login(client, "intervention-owner@uni.edu")
    denied = client.post(
        f"/api/v1/courses/{course['id']}/interventions",
        json={
            "title": "学生越权",
            "activity_type": "review",
            "class_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "target_snapshot": {"knowledge_point": "x"},
            "plan": {"mode": "review"},
        },
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "INTERVENTION_CLASS_INVALID"

    created = client.post(
        f"/api/v1/courses/{course['id']}/interventions",
        json={
            "title": "班级复习",
            "activity_type": "review",
            "class_id": class_id,
            "target_snapshot": {"knowledge_point": "x"},
            "plan": {"mode": "review"},
        },
    )
    assert created.status_code == 201


def test_intervention_dispatches_student_run_and_separates_completion(client) -> None:
    teacher_id = create_user_sync(email="run-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="run-student@uni.edu")
    _login(client, "run-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    member = client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert member.status_code == 201
    class_id = _create_observation_class(
        client, course_id=course["id"], teacher_id=teacher_id, student_id=student_id
    )
    created = client.post(
        f"/api/v1/courses/{course['id']}/interventions",
        json={
            "title": "变量映射练习",
            "activity_type": "practice_set",
            "class_id": class_id,
            "target_snapshot": {"knowledge_point": "变量"},
            "plan": {"question_count": 2},
        },
    ).json()["data"]
    scheduled = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{created['id']}/schedule",
        json={
            "version": created["version"],
            "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    ).json()["data"]
    active = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{created['id']}/start",
        json={"version": scheduled["version"]},
    ).json()["data"]
    dispatched = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{created['id']}/dispatch",
        json={"version": active["version"], "user_ids": [student_id]},
    )
    assert dispatched.status_code == 201
    dispatch_data = dispatched.json()["data"]
    assert dispatch_data["runs"][0]["status"] == "scheduled"
    run_id = dispatch_data["runs"][0]["id"]

    replay = client.post(
        f"/api/v1/courses/{course['id']}/interventions/{created['id']}/dispatch",
        json={
            "version": dispatch_data["intervention"]["version"],
            "user_ids": [student_id],
        },
    )
    assert replay.status_code == 200
    assert replay.json()["meta"]["idempotent_replay"] is True
    assert len(replay.json()["data"]["runs"]) == 1

    _login(client, "run-student@uni.edu")
    notifications = client.get("/api/v1/me/notifications?unread_only=true")
    assert notifications.status_code == 200
    assert notifications.json()["data"][0]["kind"] == "intervention.dispatched"
    notification_id = notifications.json()["data"][0]["id"]
    marked = client.post(f"/api/v1/me/notifications/{notification_id}/read")
    assert marked.status_code == 200
    assert marked.json()["data"]["read_at"] is not None
    listed = client.get("/api/v1/student/intervention-runs")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == run_id
    started = client.post(
        f"/api/v1/student/intervention-runs/{run_id}/start",
        json={"version": listed.json()["data"][0]["version"]},
    ).json()["data"]
    completed = client.post(
        f"/api/v1/student/intervention-runs/{run_id}/complete",
        json={
            "version": started["version"],
            "outcome": {"reflection": "能够区分自变量和因变量"},
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "completed"

    _login(client, "run-teacher@uni.edu")
    runs = client.get(f"/api/v1/courses/{course['id']}/interventions/{created['id']}/runs")
    assert runs.status_code == 200
    assert runs.json()["data"][0]["outcome"]["reflection"]
    effect = client.get(f"/api/v1/courses/{course['id']}/interventions/{created['id']}/effect")
    assert effect.status_code == 200
    assert effect.json()["data"]["effect_status"] == "not_measured"
    assert effect.json()["data"]["sample_status"] == "suppressed_small_sample"
    assert effect.json()["data"]["student_count"] is None
    assert effect.json()["data"]["run_count"] is None
    assert effect.json()["data"]["completed_count"] is None
    assert effect.json()["data"]["completion_rate"] is None

    too_wide = client.get(
        f"/api/v1/courses/{course['id']}/interventions/{created['id']}/effect",
        params={"start_at": "2026-01-01T00:00:00Z", "end_at": "2026-04-02T00:00:00Z"},
    )
    assert too_wide.status_code == 422
    assert too_wide.json()["error"]["code"] == "TIME_WINDOW_TOO_WIDE"


def test_teacher_observation_requires_review_and_never_overwrites_evidence(client) -> None:
    teacher_id = create_user_sync(email="observation-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="observation-student@uni.edu")
    _login(client, "observation-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/members",
            json={"user_id": student_id, "role": "student"},
        ).status_code
        == 201
    )
    class_id = _create_observation_class(
        client, course_id=course["id"], teacher_id=teacher_id, student_id=student_id
    )
    evidence_id = _create_learning_evidence_sync(user_id=student_id, course_id=course["id"])
    create_key = str(uuid4())
    created = _create_observation_request(
        client,
        course_id=course["id"],
        key=create_key,
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "misconception",
            "note": "把随机分配和控制变量混为一谈",
            "evidence_refs": [evidence_id],
        },
    )
    assert created.status_code == 201
    observation = created.json()["data"]
    assert observation["qualification_status"] == "pending"
    create_replay = _create_observation_request(
        client,
        course_id=course["id"],
        key=create_key,
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "misconception",
            "note": "把随机分配和控制变量混为一谈",
            "evidence_refs": [evidence_id],
        },
    )
    assert create_replay.status_code == 201
    assert create_replay.json()["meta"]["idempotent_replay"] is True
    assert create_replay.json()["data"]["id"] == observation["id"]
    conflicting_create = _create_observation_request(
        client,
        course_id=course["id"],
        key=create_key,
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "misconception",
            "note": "相同幂等键不能覆盖另一份观察",
            "evidence_refs": [evidence_id],
        },
    )
    assert conflicting_create.status_code == 409
    assert conflicting_create.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    missing_key = client.post(
        f"/api/v1/courses/{course['id']}/observations",
        json={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "misconception",
            "note": "创建请求要求幂等键",
            "evidence_refs": [evidence_id],
        },
    )
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    evidence_count_before_review = _count_learning_evidence_sync(
        user_id=student_id, course_id=course["id"]
    )
    listed = client.get(f"/api/v1/courses/{course['id']}/observations?status=pending")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == observation["id"]
    reviewed = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/review",
        json={
            "version": observation["version"],
            "decision": "qualified",
            "reason": "教师复核确认，但仍需独立学习证据验证",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["qualification_status"] == "pending"
    assert reviewed.json()["data"]["review_decision"] == "accepted"
    replay = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/review",
        json={
            "version": observation["version"],
            "decision": "qualified",
            "reason": "教师复核确认，但仍需独立学习证据验证",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["meta"]["idempotent_replay"] is True
    assert replay.json()["data"]["qualification_status"] == "pending"
    assert (
        _count_learning_evidence_sync(user_id=student_id, course_id=course["id"])
        == evidence_count_before_review
    )

    conflicting_review = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/review",
        json={
            "version": reviewed.json()["data"]["version"],
            "decision": "rejected",
            "reason": "试图覆盖已有决定",
        },
    )
    assert conflicting_review.status_code == 409
    assert conflicting_review.json()["error"]["code"] == "OBSERVATION_ALREADY_REVIEWED"

    _login(client, "observation-student@uni.edu")
    student_denied = client.get(f"/api/v1/courses/{course['id']}/observations")
    assert student_denied.status_code == 404
    _login(client, "observation-teacher@uni.edu")
    pending_event_id = _create_pending_learning_event_sync(
        user_id=student_id, course_id=course["id"]
    )
    pending_verification = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/revalidate",
        json={
            "version": reviewed.json()["data"]["version"],
            "learning_event_id": pending_event_id,
        },
    )
    assert pending_verification.status_code == 409
    assert pending_verification.json()["error"]["code"] == "OBSERVATION_REVALIDATION_NOT_QUALIFIED"

    event_id, verification_evidence_id = _create_qualified_learning_event_sync(
        user_id=student_id,
        course_id=course["id"],
        context_key="fixture:independent-revalidation",
        attempt_id="01ARZ3NDEKTSV4RRFFQ69G5FAY",
    )
    candidates = client.get(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/revalidation-candidates"
    )
    assert candidates.status_code == 200
    assert [item["learning_event_id"] for item in candidates.json()["data"]] == [event_id]
    assert "payload" not in candidates.json()["data"][0]
    evidence_count_before_verification = _count_learning_evidence_sync(
        user_id=student_id, course_id=course["id"]
    )
    verified = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/revalidate",
        json={"version": reviewed.json()["data"]["version"], "learning_event_id": event_id},
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["qualification_status"] == "qualified"
    assert verified.json()["data"]["verification_status"] == "qualified"
    assert verified.json()["data"]["verification_event_id"] == event_id
    assert verified.json()["data"]["verification_evidence_ids"] == [verification_evidence_id]
    assert (
        _count_learning_evidence_sync(user_id=student_id, course_id=course["id"])
        == evidence_count_before_verification
    )

    stale_version = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/revalidate",
        json={"version": observation["version"], "learning_event_id": pending_event_id},
    )
    assert stale_version.status_code == 409
    assert stale_version.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    verification_replay = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/revalidate",
        json={"version": observation["version"], "learning_event_id": event_id},
    )
    assert verification_replay.status_code == 200
    assert verification_replay.json()["meta"]["idempotent_replay"] is True

    review_replay_after_verification = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/review",
        json={
            "version": observation["version"],
            "decision": "qualified",
            "reason": "教师复核确认，但仍需独立学习证据验证",
        },
    )
    assert review_replay_after_verification.status_code == 200
    assert review_replay_after_verification.json()["meta"]["idempotent_replay"] is True
    assert review_replay_after_verification.json()["data"]["verification_status"] == "qualified"

    second_source_id = _create_learning_evidence_sync(user_id=student_id, course_id=course["id"])
    second_observation = _create_observation_request(
        client,
        course_id=course["id"],
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "strategy",
            "note": "另一条独立观察不能重复使用同一验证事件",
            "evidence_refs": [second_source_id],
        },
    ).json()["data"]
    second_review = client.post(
        f"/api/v1/courses/{course['id']}/observations/{second_observation['id']}/review",
        json={
            "version": second_observation["version"],
            "decision": "qualified",
            "reason": "仍需一条新的独立验证",
        },
    )
    assert second_review.status_code == 200
    reused_event = client.post(
        f"/api/v1/courses/{course['id']}/observations/{second_observation['id']}/revalidate",
        json={
            "version": second_review.json()["data"]["version"],
            "learning_event_id": event_id,
        },
    )
    assert reused_event.status_code == 409
    assert reused_event.json()["error"]["code"] == "OBSERVATION_REVALIDATION_EVENT_USED"

    _invalidate_learning_evidence_sync(verification_evidence_id)
    after_invalidation = client.get(f"/api/v1/courses/{course['id']}/observations?status=qualified")
    assert after_invalidation.status_code == 200
    assert after_invalidation.json()["data"][0]["qualification_status"] == "qualified"
    assert after_invalidation.json()["data"][0]["verification_status"] == "invalidated"
    invalidated_replay = client.post(
        f"/api/v1/courses/{course['id']}/observations/{observation['id']}/revalidate",
        json={
            "version": observation["version"],
            "learning_event_id": event_id,
        },
    )
    assert invalidated_replay.status_code == 200
    assert invalidated_replay.json()["meta"]["idempotent_replay"] is True
    assert invalidated_replay.json()["data"]["verification_status"] == "invalidated"


def test_teacher_observation_rejects_missing_or_foreign_evidence(client) -> None:
    teacher_id = create_user_sync(email="observation-source-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="observation-source-student@uni.edu")
    other_student_id = create_user_sync(email="observation-other-student@uni.edu")
    _login(client, "observation-source-teacher@uni.edu")
    course = client.post("/api/v1/courses", json=COURSE_BODY).json()["data"]
    for member_id in (student_id, other_student_id):
        assert (
            client.post(
                f"/api/v1/courses/{course['id']}/members",
                json={"user_id": member_id, "role": "student"},
            ).status_code
            == 201
        )
    class_id = _create_observation_class(
        client, course_id=course["id"], teacher_id=teacher_id, student_id=student_id
    )
    unassigned_teacher_id = create_user_sync(
        email="observation-unassigned-teacher@uni.edu", is_teacher=True
    )
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/members",
            json={"user_id": unassigned_teacher_id, "role": "teacher"},
        ).status_code
        == 201
    )
    target_evidence_id = _create_learning_evidence_sync(user_id=student_id, course_id=course["id"])
    _login(client, "observation-unassigned-teacher@uni.edu")
    unassigned_create = _create_observation_request(
        client,
        course_id=course["id"],
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "progress",
            "note": "未分配班级的课程教师不可观察",
            "evidence_refs": [target_evidence_id],
        },
    )
    assert unassigned_create.status_code == 404
    assert unassigned_create.json()["error"]["code"] == "OBSERVATION_CLASS_NOT_FOUND"
    assert client.get(f"/api/v1/courses/{course['id']}/observations").json()["data"] == []
    _login(client, "observation-source-teacher@uni.edu")

    foreign_evidence_id = _create_learning_evidence_sync(
        user_id=other_student_id, course_id=course["id"]
    )
    response = _create_observation_request(
        client,
        course_id=course["id"],
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "misconception",
            "note": "观察来源不得越过学生边界",
            "evidence_refs": [foreign_evidence_id],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OBSERVATION_EVIDENCE_UNAVAILABLE"

    missing_source = _create_observation_request(
        client,
        course_id=course["id"],
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "progress",
            "note": "缺少可验证来源",
            "evidence_refs": [],
        },
    )
    assert missing_source.status_code == 422

    invalid_evidence_id = _create_learning_evidence_sync(
        user_id=student_id, course_id=course["id"], valid=False
    )
    invalid_source = _create_observation_request(
        client,
        course_id=course["id"],
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "progress",
            "note": "失效证据不能作为观察来源",
            "evidence_refs": [invalid_evidence_id],
        },
    )
    assert invalid_source.status_code == 422
    assert invalid_source.json()["error"]["code"] == "OBSERVATION_EVIDENCE_UNAVAILABLE"

    current_evidence_id = _create_learning_evidence_sync(user_id=student_id, course_id=course["id"])
    current_observation = _create_observation_request(
        client,
        course_id=course["id"],
        body={
            "student_id": student_id,
            "class_id": class_id,
            "observation_type": "progress",
            "note": "原依据会在复核前再次校验",
            "evidence_refs": [current_evidence_id],
        },
    ).json()["data"]
    _invalidate_learning_evidence_sync(current_evidence_id)
    review_invalidated = client.post(
        f"/api/v1/courses/{course['id']}/observations/{current_observation['id']}/review",
        json={
            "version": current_observation["version"],
            "decision": "qualified",
            "reason": "复核来源失效验证",
        },
    )
    assert review_invalidated.status_code == 409
    assert review_invalidated.json()["error"]["code"] == "OBSERVATION_EVIDENCE_INVALIDATED"
