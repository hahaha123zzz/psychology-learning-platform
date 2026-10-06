import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from tests.conftest import create_user_sync

PHASES = ["intro", "predict", "run", "inspect", "explain", "summary"]


def _trials(phases: list[str], *, choice: int = 0) -> list[dict]:
    return [
        {
            "phase": phase,
            "response": choice,
            "rt": 100,
            "recorded_at": "2026-10-02T10:00:00Z",
        }
        for phase in phases
    ]


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def _course_for_student(client, teacher_email: str, student_id: str) -> str:
    _login(client, teacher_email)
    course = client.post(
        "/api/v1/courses",
        json={"title": "实验心理学 Mini Lab", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    assert client.post(
        f"/api/v1/courses/{course['id']}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    return course["id"]


def test_mini_lab_button_completion_is_rejected_as_learning_evidence(client) -> None:
    create_user_sync(email="lab-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="lab-student@uni.edu")
    course_id = _course_for_student(client, "lab-teacher@uni.edu", student_id)
    _login(client, "lab-student@uni.edu")

    catalog = client.get(f"/api/v1/student/labs/catalog?course_id={course_id}")
    assert catalog.status_code == 200
    definition = catalog.json()["data"][0]
    assert definition["lab_key"] == "attention-cue-basic"
    assert definition["source_status"] == "engineering_fixture"
    assert "不对应已获准教材" in definition["source_note"]

    created = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": definition["lab_key"]},
    )
    assert created.status_code == 201
    session = created.json()["data"]
    repeated_create = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": definition["lab_key"]},
    )
    assert repeated_create.status_code == 200
    assert repeated_create.json()["data"]["id"] == session["id"]
    phases = ["intro", "predict", "run", "inspect", "explain", "summary"]
    incomplete = client.post(
        f"/api/v1/student/labs/{session['id']}/result",
        json={
            "version": session["version"],
            "schema_version": "mini-lab.v1",
            "definition_id": definition["id"],
            "runtime": "jspsych",
            "trial_data": [
                {"phase": phase, "response": 0, "rt": 100, "recorded_at": "2026-10-02T10:00:00Z"}
                for phase in phases[:5]
            ],
            "completed_at": "2026-10-02T10:00:00Z",
        },
    )
    assert incomplete.status_code == 422

    for missing_phase in ("predict", "run"):
        missing_required_response = client.post(
            f"/api/v1/student/labs/{session['id']}/result",
            json={
                "version": session["version"],
                "schema_version": "mini-lab.v1",
                "definition_id": definition["id"],
                "runtime": "jspsych",
                "trial_data": [
                    {
                        "phase": phase,
                        "response": None if phase == missing_phase else 0,
                        "rt": 100,
                        "recorded_at": "2026-10-02T10:00:00Z",
                    }
                    for phase in phases
                ],
                "completed_at": "2026-10-02T10:00:00Z",
            },
        )
        assert missing_required_response.status_code == 422
        assert missing_required_response.json()["error"]["code"] == (
            "MINI_LAB_REQUIRED_RESPONSE_MISSING"
        )
        assert missing_required_response.json()["error"]["details"]["phase"] == missing_phase

    from app.db.models import LearningEvent, LearningEvidence, MasteryState, MiniLabSession
    from app.db.session import session_factory

    async def _incomplete_counts():
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count()).select_from(LearningEvent).where(
                    LearningEvent.source_ref == session["id"]
                )
            )
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return event_count, evidence_count, mastery_count

    assert asyncio.run(_incomplete_counts()) == (0, 0, 0)

    valid = client.post(
        f"/api/v1/student/labs/{session['id']}/result",
        json={
            "version": session["version"],
            "schema_version": "mini-lab.v1",
            "definition_id": definition["id"],
            "runtime": "jspsych",
            "trial_data": [
                {"phase": phase, "response": 0, "rt": 100, "recorded_at": "2026-10-02T10:00:00Z"}
                for phase in phases
            ],
            "completed_at": "2026-10-02T10:00:00Z",
        },
    )
    assert valid.status_code == 200
    assert valid.json()["data"]["status"] == "completed"
    assert valid.json()["data"]["derived_measure"]["qualification_status"] == "pending"
    assert valid.json()["data"]["derived_measure"]["explanation_complete"] is False
    assert valid.json()["data"]["derived_measure"]["transfer_complete"] is False

    async def _mark_legacy_flags_true() -> None:
        async with session_factory() as db:
            saved_session = await db.get(MiniLabSession, session["id"])
            event = await db.scalar(
                select(LearningEvent).where(LearningEvent.source_ref == session["id"])
            )
            saved_session.derived_measure = {
                **saved_session.derived_measure,
                "explanation_complete": True,
                "transfer_complete": True,
            }
            event.payload = {
                **event.payload,
                "explanation_complete": True,
                "transfer_complete": True,
            }
            await db.commit()

    asyncio.run(_mark_legacy_flags_true())

    from app.modules.learning_events.qualification import qualify_pending_events

    async def _run_worker():
        async with session_factory() as db:
            return await qualify_pending_events(db, limit=10)

    counts = asyncio.run(_run_worker())
    assert counts["qualified"] == 0
    assert counts["rejected"] == 1
    completed = client.get(f"/api/v1/student/labs/{session['id']}")
    assert completed.json()["data"]["derived_measure"]["qualification_status"] == "rejected"

    async def _projection_counts():
        async with session_factory() as db:
            event = await db.scalar(
                select(LearningEvent).where(LearningEvent.source_ref == session["id"])
            )
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return (
                event.qualification_status,
                event.qualification_reason,
                evidence_count,
                mastery_count,
            )

    assert asyncio.run(_projection_counts()) == (
        "rejected",
        "mini_lab_explanation_or_transfer_unverified",
        0,
        0,
    )


def test_mini_lab_qualification_scopes_source_measure_and_replay(client) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.base import new_ulid
    from app.db.models import LearningEvent, LearningEvidence, LearningQualification, MasteryState
    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_event, qualify_pending_events

    create_user_sync(email="lab-scope-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="lab-scope-student@uni.edu")
    other_student_id = create_user_sync(email="lab-scope-other@uni.edu")
    course_id = _course_for_student(client, "lab-scope-teacher@uni.edu", student_id)
    _login(client, "lab-scope-student@uni.edu")
    session = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": "attention-cue-basic"},
    ).json()["data"]
    completed = client.post(
        f"/api/v1/student/labs/{session['id']}/result",
        json={
            "version": session["version"],
            "schema_version": "mini-lab.v1",
            "definition_id": session["definition_snapshot"]["id"],
            "runtime": "jspsych",
            "trial_data": _trials(PHASES),
            "completed_at": "2026-10-02T10:01:00Z",
        },
    )
    assert completed.status_code == 200

    async def _projection_counts() -> tuple[int, int]:
        async with session_factory() as db:
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return int(evidence_count or 0), int(mastery_count or 0)

    # 完成接口只追加 LearningEvent；它本身不得投影 LearningEvidence 或 MasteryState。
    assert asyncio.run(_projection_counts()) == (0, 0)

    authoritative_payload = {
        "session_id": session["id"],
        "lab_key": session["lab_key"],
        "trial_count": 6,
        "explanation_complete": False,
        "transfer_complete": False,
    }
    mismatch_key = "lab-scope-measure-mismatch"
    other_owner_key = "lab-scope-other-owner"
    other_course_key = "lab-scope-other-course"
    other_source_key = "lab-scope-other-source"
    wrong_course_id = new_ulid()

    async def _seed_scope_mismatch_events() -> str:
        async with session_factory() as db:
            # 让 measure mismatch 先于真实完成事件被处理，确保其明确走字段比较拒绝。
            db.add_all(
                [
                    LearningEvent(
                        event_key=mismatch_key,
                        user_id=student_id,
                        course_id=course_id,
                        event_type="lab_trial_completed",
                        source_type="lab",
                        source_ref=session["id"],
                        payload={**authoritative_payload, "trial_count": 5},
                        occurred_at=datetime.now(UTC) - timedelta(minutes=1),
                    ),
                    LearningEvent(
                        event_key=other_owner_key,
                        user_id=other_student_id,
                        course_id=course_id,
                        event_type="lab_trial_completed",
                        source_type="lab",
                        source_ref=session["id"],
                        payload=authoritative_payload,
                        occurred_at=datetime.now(UTC),
                    ),
                    LearningEvent(
                        event_key=other_course_key,
                        user_id=student_id,
                        course_id=wrong_course_id,
                        event_type="lab_trial_completed",
                        source_type="lab",
                        source_ref=session["id"],
                        payload=authoritative_payload,
                        occurred_at=datetime.now(UTC),
                    ),
                    LearningEvent(
                        event_key=other_source_key,
                        user_id=student_id,
                        course_id=course_id,
                        event_type="lab_trial_completed",
                        source_type="tutor",
                        source_ref=session["id"],
                        payload=authoritative_payload,
                        occurred_at=datetime.now(UTC),
                    ),
                ]
            )
            await db.commit()
            return str(
                await db.scalar(
                    select(LearningEvent.id).where(
                        LearningEvent.event_key == f"lab:{session['id']}:completed"
                    )
                )
            )

    authoritative_event_id = asyncio.run(_seed_scope_mismatch_events())

    async def _qualify_all():
        async with session_factory() as db:
            return await qualify_pending_events(db, limit=20)

    first_counts = asyncio.run(_qualify_all())
    assert first_counts["claimed"] == 5
    assert first_counts["qualified"] == 0
    assert first_counts["rejected"] == 5

    async def _reasons():
        async with session_factory() as db:
            rows = await db.scalars(
                select(LearningQualification).where(
                    LearningQualification.event_id.in_(
                        select(LearningEvent.id).where(
                            LearningEvent.event_key.in_(
                                [
                                    f"lab:{session['id']}:completed",
                                    mismatch_key,
                                    other_owner_key,
                                    other_course_key,
                                    other_source_key,
                                ]
                            )
                        )
                    )
                )
            )
            return {row.reason for row in rows}

    assert asyncio.run(_reasons()) == {
        "mini_lab_measure_mismatch",
        "mini_lab_session_not_completed",
        "event_type_not_evidence_bearing",
        "mini_lab_explanation_or_transfer_unverified",
    }

    duplicate = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": "lab-scope-second-qualified-event",
            "course_id": course_id,
            "event_type": "lab_trial_completed",
            "source_type": "lab",
            "source_ref": session["id"],
            "payload": {
                **authoritative_payload,
                "correct": True,
                "mastery_state": {"state": "mastered", "correct_ratio": 1.0},
            },
        },
    )
    assert duplicate.status_code == 201

    duplicate_counts = asyncio.run(_qualify_all())
    assert duplicate_counts["claimed"] == 1
    assert duplicate_counts["qualified"] == 0
    assert duplicate_counts["rejected"] == 1

    async def _assert_replay_has_no_second_projection():
        async with session_factory() as db:
            event = await db.scalar(
                select(LearningEvent).where(LearningEvent.id == authoritative_event_id)
            )
            qualification, replay = await qualify_event(db, event_id=authoritative_event_id)
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.attempt_id == session["id"],
                )
            )
            state = await db.scalar(
                select(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                    MasteryState.knowledge_point == f"lab:{session['lab_key']}",
                )
            )
            duplicate_qualification = await db.scalar(
                select(LearningQualification).where(
                    LearningQualification.event_id == duplicate.json()["data"]["id"]
                )
            )
            qualification_status = qualification.status
            duplicate_reason = duplicate_qualification.reason
            evidence_projection = None
            mastery_evidence_count = state.evidence_count if state is not None else None
            await db.rollback()
            return (
                event,
                qualification_status,
                replay,
                evidence_count,
                evidence_projection,
                mastery_evidence_count,
                duplicate_reason,
            )

    (
        event,
        qualification_status,
        replay,
        evidence_count,
        evidence_projection,
        mastery_evidence_count,
        duplicate_reason,
    ) = asyncio.run(_assert_replay_has_no_second_projection())
    assert event is not None
    assert qualification_status == "rejected"
    assert replay is True
    assert evidence_count == 0
    assert evidence_projection is None
    assert mastery_evidence_count is None
    assert duplicate_reason == "mini_lab_result_not_pending"


def test_mini_lab_refresh_restores_trials_and_completion_replay_is_idempotent(client) -> None:
    create_user_sync(email="lab-recovery-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="lab-recovery-student@uni.edu")
    course_id = _course_for_student(client, "lab-recovery-teacher@uni.edu", student_id)
    _login(client, "lab-recovery-student@uni.edu")
    created = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": "attention-cue-basic"},
    )
    session = created.json()["data"]

    first = client.post(
        f"/api/v1/student/labs/{session['id']}/trials",
        json={"version": session["version"], "trial_data": _trials(PHASES[:2])},
    )
    assert first.status_code == 200
    persisted = first.json()["data"]
    assert persisted["version"] == session["version"] + 1
    assert persisted["phase"] == "run"
    assert len(persisted["trial_data"]) == 2

    # 模拟页面刷新后不持有旧 React 状态：从服务端活动会话恢复阶段与答案。
    restored = client.get(f"/api/v1/student/labs/active?course_id={course_id}")
    assert restored.status_code == 200
    assert restored.json()["data"]["id"] == session["id"]
    assert restored.json()["data"]["trial_data"] == persisted["trial_data"]

    # 同一个已保存阶段的重试不会再次递增版本；并发重复请求得到相同快照。
    duplicate_body = {"version": session["version"], "trial_data": _trials(PHASES[:2])}
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicates = list(
            pool.map(
                lambda _: client.post(
                    f"/api/v1/student/labs/{session['id']}/trials", json=duplicate_body
                ),
                range(2),
            )
        )
    assert [response.status_code for response in duplicates] == [200, 200]
    assert {response.json()["data"]["version"] for response in duplicates} == {
        persisted["version"]
    }

    # 旧版本的追加即使复用了相同前缀，也必须先恢复新快照，不能隐式越过版本冲突。
    stale_append = client.post(
        f"/api/v1/student/labs/{session['id']}/trials",
        json={
            "version": session["version"],
            "trial_data": _trials(PHASES[:4]),
        },
    )
    assert stale_append.status_code == 409
    assert stale_append.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    appended = client.post(
        f"/api/v1/student/labs/{session['id']}/trials",
        json={
            "version": persisted["version"],
            "trial_data": _trials(PHASES[:4]),
        },
    )
    assert appended.status_code == 200
    assert appended.json()["data"]["phase"] == "explain"
    conflict = client.post(
        f"/api/v1/student/labs/{session['id']}/trials",
        json={
            "version": appended.json()["data"]["version"],
            "trial_data": [
                {**trial, "recorded_at": "2026-10-02T10:00:01Z"}
                for trial in _trials(PHASES[:2])
            ],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "MINI_LAB_TRIAL_CONFLICT"

    latest = appended.json()["data"]
    result_body = {
        "version": latest["version"],
        "schema_version": "mini-lab.v1",
        "definition_id": session["definition_snapshot"]["id"],
        "runtime": "jspsych",
        "trial_data": _trials(PHASES),
        "completed_at": "2026-10-02T10:01:00Z",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        completions = list(
            pool.map(
                lambda _: client.post(
                    f"/api/v1/student/labs/{session['id']}/result", json=result_body
                ),
                range(2),
            )
        )
    assert [response.status_code for response in completions] == [200, 200]
    assert all(response.json()["data"]["status"] == "completed" for response in completions)
    refreshed_completed = client.get(f"/api/v1/student/labs/active?course_id={course_id}")
    assert refreshed_completed.status_code == 200
    assert refreshed_completed.json()["data"]["status"] == "completed"

    from app.db.models import LearningEvent
    from app.db.session import session_factory

    async def _count_events():
        async with session_factory() as db:
            return await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.event_key == f"lab:{session['id']}:completed")
            )

    assert asyncio.run(_count_events()) == 1


def test_mini_lab_invalidation_is_idempotent_terminal_and_never_qualifies(client) -> None:
    create_user_sync(email="lab-invalidate-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="lab-invalidate-student@uni.edu")
    course_id = _course_for_student(client, "lab-invalidate-teacher@uni.edu", student_id)
    _login(client, "lab-invalidate-student@uni.edu")
    created = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": "attention-cue-basic"},
    )
    session = created.json()["data"]
    saved = client.post(
        f"/api/v1/student/labs/{session['id']}/trials",
        json={"version": session["version"], "trial_data": _trials(PHASES[:2])},
    ).json()["data"]

    stale = client.post(
        f"/api/v1/student/labs/{session['id']}/invalidate",
        json={
            "expected_version": session["version"],
            "idempotency_key": "lab-invalidate-stale",
            "reason": "测试并发版本冲突",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    request_body = {
        "expected_version": saved["version"],
        "idempotency_key": "lab-invalidate-one",
        "reason": "浏览器中断后由学生主动结束",
    }
    invalidated = client.post(
        f"/api/v1/student/labs/{session['id']}/invalidate", json=request_body
    )
    assert invalidated.status_code == 200
    response_body = invalidated.json()
    receipt = response_body["data"]
    assert set(response_body) == {"data", "meta"}
    assert set(response_body["meta"]) >= {"request_id", "server_time"}
    assert receipt["status"] == "invalidated"
    assert receipt["version"] == saved["version"] + 1
    assert receipt["trial_data"] == saved["trial_data"]
    assert receipt["invalidation_reason"] == request_body["reason"]
    assert receipt["invalidated_at"]
    assert receipt["version"] == saved["version"] + 1

    replay = client.post(
        f"/api/v1/student/labs/{session['id']}/invalidate", json=request_body
    )
    assert replay.status_code == 200
    assert replay.json()["data"] == receipt

    changed_payload = client.post(
        f"/api/v1/student/labs/{session['id']}/invalidate",
        json={**request_body, "reason": "不同理由"},
    )
    assert changed_payload.status_code == 409
    assert changed_payload.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    active = client.get(f"/api/v1/student/labs/active?course_id={course_id}")
    assert active.json()["data"]["status"] == "invalidated"
    cannot_continue = client.post(
        f"/api/v1/student/labs/{session['id']}/trials",
        json={"version": receipt["version"], "trial_data": _trials(PHASES[:3])},
    )
    assert cannot_continue.status_code == 409
    assert cannot_continue.json()["error"]["code"] == "MINI_LAB_INVALID_STATE"

    cannot_submit = client.post(
        f"/api/v1/student/labs/{session['id']}/result",
        json={
            "version": receipt["version"],
            "schema_version": "mini-lab.v1",
            "definition_id": session["definition_snapshot"]["id"],
            "runtime": "jspsych",
            "trial_data": _trials(PHASES),
            "completed_at": "2026-10-02T10:01:00Z",
        },
    )
    assert cannot_submit.status_code == 409
    assert cannot_submit.json()["error"]["code"] == "MINI_LAB_INVALID_STATE"

    event = client.post(
        "/api/v1/learning-events",
        json={
            "event_key": f"lab:{session['id']}:invalidated-attempt",
            "course_id": course_id,
            "event_type": "lab_trial_completed",
            "source_type": "lab",
            "source_ref": session["id"],
            "payload": {
                "trial_count": 6,
                "explanation_complete": True,
                "transfer_complete": True,
            },
        },
    )
    assert event.status_code == 201

    from app.db.models import LearningEvent, LearningEvidence, LearningQualification, MasteryState
    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_pending_events

    async def _counts():
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.source_ref == session["id"])
            )
            qualification_counts = await qualify_pending_events(db, limit=10)
            evidence_count = await db.scalar(
                select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count()).select_from(MasteryState).where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            qualification = await db.scalar(
                select(LearningQualification).where(
                    LearningQualification.event_id == event.json()["data"]["id"]
                )
            )
            return event_count, qualification_counts, evidence_count, mastery_count, qualification

    event_count, qualification_counts, evidence_count, mastery_count, qualification = asyncio.run(
        _counts()
    )
    assert event_count == 1
    assert qualification_counts["rejected"] == 1
    assert evidence_count == 0
    assert mastery_count == 0
    assert qualification.reason == "mini_lab_session_not_completed"


def test_mini_lab_completed_session_cannot_be_invalidated(client) -> None:
    create_user_sync(email="lab-completed-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="lab-completed-student@uni.edu")
    course_id = _course_for_student(client, "lab-completed-teacher@uni.edu", student_id)
    _login(client, "lab-completed-student@uni.edu")
    session = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": "attention-cue-basic"},
    ).json()["data"]
    result = client.post(
        f"/api/v1/student/labs/{session['id']}/result",
        json={
            "version": session["version"],
            "schema_version": "mini-lab.v1",
            "definition_id": session["definition_snapshot"]["id"],
            "runtime": "jspsych",
            "trial_data": _trials(PHASES),
            "completed_at": "2026-10-02T10:01:00Z",
        },
    )
    assert result.status_code == 200
    invalidation = client.post(
        f"/api/v1/student/labs/{session['id']}/invalidate",
        json={
            "expected_version": result.json()["data"]["version"],
            "idempotency_key": "lab-invalidate-completed",
            "reason": "不能作废已完成记录",
        },
    )
    assert invalidation.status_code == 409
    assert invalidation.json()["error"]["code"] == "MINI_LAB_INVALID_STATE"


def test_formal_assessment_blocks_mini_lab_mutations_but_allows_owner_read(client) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.models import Assessment, Attempt
    from app.db.session import session_factory

    teacher_id = create_user_sync(email="lab-assessment-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="lab-assessment-student@uni.edu")
    course_id = _course_for_student(
        client, "lab-assessment-teacher@uni.edu", student_id
    )

    _login(client, "lab-assessment-student@uni.edu")
    session = client.post(
        "/api/v1/student/labs",
        json={"course_id": course_id, "lab_key": "attention-cue-basic"},
    ).json()["data"]

    async def _create_active_formal_attempt() -> None:
        async with session_factory() as db:
            assessment = Assessment(
                course_id=course_id,
                title="合成正式测评隔离夹具",
                closes_at=datetime.now(UTC) + timedelta(minutes=10),
                ai_policy="disabled",
                status="published",
                purpose="formal",
                result_visibility_policy="after_close",
                created_by=teacher_id,
            )
            db.add(assessment)
            await db.flush()
            db.add(
                Attempt(
                    assessment_id=assessment.id,
                    user_id=student_id,
                    status="in_progress",
                )
            )
            await db.commit()

    asyncio.run(_create_active_formal_attempt())

    blocked_mutations = [
        client.post(
            "/api/v1/student/labs",
            json={"course_id": course_id, "lab_key": "attention-cue-basic"},
        ),
        client.post(
            f"/api/v1/student/labs/{session['id']}/trials",
            json={"version": session["version"], "trial_data": _trials(PHASES[:1])},
        ),
        client.post(
            f"/api/v1/student/labs/{session['id']}/result",
            json={
                "version": session["version"],
                "schema_version": "mini-lab.v1",
                "definition_id": session["definition_snapshot"]["id"],
                "runtime": "jspsych",
                "trial_data": _trials(PHASES),
                "completed_at": "2026-10-02T10:01:00Z",
            },
        ),
        client.post(
            f"/api/v1/student/labs/{session['id']}/invalidate",
            json={
                "expected_version": session["version"],
                "idempotency_key": "lab-assessment-invalidation",
                "reason": "正式测评期间不允许修改 MiniLab",
            },
        ),
    ]
    assert [response.status_code for response in blocked_mutations] == [403] * 4
    assert all(
        response.json()["error"]["code"] == "EXAM_AI_SUPPORT_RESTRICTED"
        for response in blocked_mutations
    )

    owned = client.get(f"/api/v1/student/labs/{session['id']}")
    assert owned.status_code == 200
    assert owned.json()["data"]["status"] == "running"
    assert owned.json()["data"]["trial_data"] == []
