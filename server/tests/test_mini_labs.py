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


def test_mini_lab_result_is_server_validated_and_qualifies(client) -> None:
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

    from app.db.session import session_factory
    from app.modules.learning_events.qualification import qualify_pending_events

    async def _run_worker():
        async with session_factory() as db:
            return await qualify_pending_events(db, limit=10)

    counts = asyncio.run(_run_worker())
    assert counts["qualified"] == 1
    completed = client.get(f"/api/v1/student/labs/{session['id']}")
    assert completed.json()["data"]["derived_measure"]["qualification_status"] == "qualified"


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

    from app.db.models import LearningEvent
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
            return event_count, qualification_counts

    event_count, qualification_counts = asyncio.run(_counts())
    assert event_count == 0
    assert qualification_counts["qualified"] == 0


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
