import asyncio
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from tests.conftest import create_user_sync
from tests.test_materials import _login, _setup_course, _upload
from tests.test_question_bank import QUESTION_BODY
from tests.test_search import TWO_CHAPTER_PDF, _parse_and_wait


def _prepare_published(client):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    assert _parse_and_wait(client, version_id)["status"] == "succeeded"
    assert _parse_and_wait(client, version_id, kind="embed")["status"] == "succeeded"
    publish = client.post(f"/api/v1/material-versions/{version_id}/publish")
    assert publish.status_code == 200

    created = client.post(f"/api/v1/courses/{course_id}/questions", json=QUESTION_BODY)
    question_id = created.json()["data"]["id"]
    client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "ok"},
    )
    client.post(f"/api/v1/questions/{question_id}/publish")

    assessment = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={"title": "掌握度测验", "question_ids": [question_id]},
    )
    assessment_id = assessment.json()["data"]["id"]
    client.post(f"/api/v1/assessments/{assessment_id}/publish")
    return course_id, student_id, version_id, assessment_id


def test_mastery_state_derived_from_graded_attempt(client) -> None:
    course_id, student_id, version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = attempt.json()["data"]["attempt_id"]
    view = client.get(f"/api/v1/assessments/{assessment_id}")
    qv_id = view.json()["data"]["items"][0]["question_version_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submit.status_code == 200

    mastery = client.get(f"/api/v1/me/mastery?course_id={course_id}")
    assert mastery.status_code == 200
    items = mastery.json()["data"]
    assert len(items) >= 1
    first = items[0]
    assert first["state"] in (
        "not_started",
        "learning",
        "needs_consolidation",
        "proficient",
        "mastered",
    )
    assert first["evidence_count"] >= 1
    assert first["correct_ratio"] > 0

    growth = client.get(f"/api/v1/student/growth/knowledge?course_id={course_id}")
    assert growth.status_code == 200
    assert growth.json()["data"][0]["algorithm_version"] == "mastery-v2-independent-context"
    assert growth.json()["data"][0]["state_reason"]

    from app.db.models import LearningEvent, LearningQualification
    from app.db.session import session_factory

    async def _qualification_rows():
        async with session_factory() as session:
            return (
                await session.execute(
                    select(LearningEvent, LearningQualification)
                    .join(LearningQualification, LearningQualification.event_id == LearningEvent.id)
                    .where(LearningEvent.user_id == student_id)
                )
            ).all()

    qualifications = asyncio.run(_qualification_rows())
    assert len(qualifications) == 1
    event, qualification = qualifications[0]
    assert event.qualification_status == "qualified"
    assert qualification.status == "qualified"
    assert qualification.evidence_ids

    async def _evidence_row():
        from app.db.models import LearningEvidence

        async with session_factory() as session:
            return await session.scalar(
                select(LearningEvidence).where(LearningEvidence.user_id == student_id)
            )

    evidence = asyncio.run(_evidence_row())
    assert evidence.dimension == "understand"
    assert evidence.independence_status == "independent"
    assert evidence.quality_status == "valid"
    assert evidence.context_key.startswith("assessment:")

    _login(client, "mt@uni.edu")
    invalidated = client.post(
        f"/api/v1/courses/{course_id}/learning-evidence/{evidence.id}/invalidate",
        json={"reason": "题目质量复核发现评分依据错误"},
    )
    assert invalidated.status_code == 200
    assert invalidated.json()["data"]["quality_status"] == "invalidated"
    replay = client.post(
        f"/api/v1/courses/{course_id}/learning-evidence/{evidence.id}/invalidate",
        json={"reason": "重复提交"},
    )
    assert replay.status_code == 200
    assert replay.json()["meta"]["idempotent_replay"] is True


def test_memory_summary_and_weakness_candidates(client) -> None:
    course_id, student_id, version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    empty = client.get("/api/v1/me/memory")
    assert empty.status_code == 200

    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = attempt.json()["data"]["attempt_id"]
    view = client.get(f"/api/v1/assessments/{assessment_id}")
    qv_id = view.json()["data"]["items"][0]["question_version_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["C"]}},
    )
    client.post(f"/api/v1/attempts/{attempt_id}/submit")

    # 第二次错误作答：重复出现才形成L1薄弱点候选（单次仅为待确认）
    attempt2 = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id2 = attempt2.json()["data"]["attempt_id"]
    client.put(
        f"/api/v1/attempts/{attempt_id2}/answers/{qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["C"]}},
    )
    client.post(f"/api/v1/attempts/{attempt_id2}/submit")

    summary = client.get("/api/v1/me/memory")
    data = summary.json()["data"]
    assert data["summary"].get("L1:weakness") == 1

    items = client.get("/api/v1/me/memory/items?layer=L1")
    assert items.status_code == 200
    first = items.json()["data"][0]
    assert first["layer"] == "L1"
    assert "不稳定" in first["content"]


def test_privacy_delete_request_creates_recoverable_job_and_reports_retention(
    client, monkeypatch
) -> None:
    course_id, student_id, version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    from app.db.base import new_ulid
    from app.db.models import (
        AuthSession,
        CaseSession,
        ChatSession,
        ChatTurn,
        CurrentLearningTask,
        LearningEpisode,
        LearningEvent,
        LearningEvidence,
        LearningQualification,
        LearningSession,
        MasteryState,
        MemoryItem,
        MiniLabSession,
        Notification,
        PrivacyDeletionRequest,
        TeachingSession,
        UserPreference,
    )
    from app.db.session import session_factory

    task_id = new_ulid()

    async def _seed_personal_data() -> None:
        async with session_factory() as session:
            chat_session_id = new_ulid()
            legacy_session_id = new_ulid()
            teaching_session_id = new_ulid()
            event_id = new_ulid()
            session.add_all(
                [
                    MemoryItem(
                        id=new_ulid(),
                        user_id=student_id,
                        course_id=course_id,
                        layer="L1",
                        kind="weakness",
                        content="个人学习摘要",
                        source_type="quiz",
                        confidence=0.5,
                    ),
                    UserPreference(
                        id=new_ulid(), user_id=student_id, preferences={"font_scale": "large"}
                    ),
                    Notification(
                        id=new_ulid(), user_id=student_id, kind="test", title="标题", body="内容"
                    ),
                    LearningEvidence(
                        id=new_ulid(),
                        user_id=student_id,
                        course_id=course_id,
                        knowledge_point="kp-retained",
                        question_version_id=new_ulid(),
                        source_type="practice",
                        dimension="understand",
                        independence_status="unknown",
                        hints_used=0,
                        correct=False,
                        weight=0.5,
                    ),
                    MasteryState(
                        id=new_ulid(),
                        user_id=student_id,
                        course_id=course_id,
                        knowledge_point="kp-retained",
                        state="learning",
                        evidence_count=1,
                        correct_ratio=0.0,
                        weight_score=0.5,
                        context_count=1,
                        independent_evidence_count=0,
                        last_evidence_id=None,
                        algorithm_version="mastery-test",
                        state_reason="测试数据",
                    ),
                    ChatSession(
                        id=chat_session_id,
                        user_id=student_id,
                        course_id=course_id,
                        mode="tutor",
                        title="学生私聊",
                    ),
                    LearningSession(
                        id=legacy_session_id,
                        user_id=student_id,
                        course_id=course_id,
                        material_version_id=version_id,
                        state="teach",
                        tutor_message="需要删除的任务内容",
                        status="active",
                    ),
                    CaseSession(
                        id=new_ulid(),
                        user_id=student_id,
                        course_id=course_id,
                        case_key="private-case",
                        status="completed",
                        case_snapshot={"case": "private"},
                        response={"reasoning": "private"},
                        outcome={"score": 1},
                    ),
                    MiniLabSession(
                        id=new_ulid(),
                        user_id=student_id,
                        course_id=course_id,
                        lab_key="private-lab",
                        definition_snapshot={"label": "private"},
                        status="completed",
                        phase="summary",
                        trial_data=[{"answer": "private"}],
                    ),
                    LearningEvent(
                        id=event_id,
                        event_key="privacy-test-event",
                        user_id=student_id,
                        course_id=course_id,
                        event_type="answer_submitted",
                        source_type="assessment",
                        source_ref="attempt-test",
                        payload={"private": "answer"},
                        occurred_at=datetime.now(UTC),
                        qualification_status="qualified",
                    ),
                ]
            )
            await session.flush()
            session.add(
                ChatTurn(
                    id=new_ulid(),
                    session_id=chat_session_id,
                    client_turn_id="turn-1",
                    role="student",
                    content="需要删除的对话正文",
                )
            )
            await session.flush()
            session.add(
                CurrentLearningTask(
                    id=task_id,
                    user_id=student_id,
                    course_id=course_id,
                    legacy_session_id=legacy_session_id,
                    material_version_id=version_id,
                    goal={"title": "私有目标"},
                    completion={"done": False},
                    status="active",
                )
            )
            await session.flush()
            session.add(
                TeachingSession(
                    id=teaching_session_id,
                    task_id=task_id,
                    state="teach",
                    status="active",
                    state_version=1,
                    context={"private": "context"},
                    hint_budget=3,
                )
            )
            await session.flush()
            session.add_all(
                [
                    LearningEpisode(
                        id=new_ulid(),
                        task_id=task_id,
                        teaching_session_id=teaching_session_id,
                        episode_no=1,
                        status="active",
                        turn_count=1,
                    ),
                    LearningQualification(
                        id=new_ulid(),
                        event_id=event_id,
                        user_id=student_id,
                        course_id=course_id,
                        status="qualified",
                        reason="测试资格化",
                        algorithm_version="test-v1",
                        evidence_ids=[],
                    ),
                ]
            )
            await session.commit()

    asyncio.run(_seed_personal_data())
    request_id = new_ulid()
    status_credential = secrets.token_urlsafe(32)
    request_body = {"request_id": request_id, "status_credential": status_credential}
    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.modules.memory.tasks.dispatch_privacy_deletion",
        lambda deletion_id: dispatched.append(deletion_id),
    )
    delete_request = client.post("/api/v1/me/privacy/delete-request", json=request_body)
    assert delete_request.status_code == 202
    response = delete_request.json()["data"]
    assert response["status"] == "queued"
    assert response["retryable"] is True
    assert response["processed_counts"]["auth_sessions"] >= 1
    assert "正式测评作答与成绩" in " ".join(response["retained_categories"])
    assert "尚未完成" in response["note"]
    assert response["request_id"] == request_id
    assert response["status_credential"] == status_credential
    assert len(response["status_credential"]) == 43
    assert delete_request.headers["cache-control"] == "no-store"
    assert "Max-Age=0" in delete_request.headers.get("set-cookie", "")

    me = client.get("/api/v1/me")
    assert me.status_code == 401
    status_query = request_body
    status_response = client.post("/api/v1/privacy/deletion-status", json=status_query)
    assert status_response.status_code == 200
    assert status_response.headers["cache-control"] == "no-store"
    assert status_response.json()["data"]["request_id"] == response["request_id"]
    assert status_response.json()["data"]["status"] == "queued"
    redelivery = client.post("/api/v1/privacy/deletion-status/retry", json=status_query)
    assert redelivery.status_code == 202
    assert redelivery.json()["data"]["status"] == "queued"
    assert dispatched == [request_id, request_id]
    invalid_status = client.post(
        "/api/v1/privacy/deletion-status",
        json={**status_query, "status_credential": "x" * 43},
    )
    assert invalid_status.status_code == 404
    malformed_secret = "do-not-echo-this-status-credential"
    malformed_status = client.post(
        "/api/v1/privacy/deletion-status",
        json={**status_query, "status_credential": malformed_secret},
    )
    assert malformed_status.status_code == 404
    assert malformed_secret not in malformed_status.text

    # The caller minted and retained both values before submission, so it can
    # recover the state even when it did not capture the submit response.
    from app.modules.memory.tasks import _execute_privacy_deletion

    asyncio.run(_execute_privacy_deletion(request_id))
    completed_status = client.post("/api/v1/privacy/deletion-status", json=status_query)
    assert completed_status.status_code == 200
    assert completed_status.json()["data"]["status"] == "completed_with_retention"
    assert completed_status.json()["data"]["processed_counts"]["memory_items"] == 1

    async def _check_deletion() -> None:
        async with session_factory() as session:
            assert (
                await session.scalar(select(MemoryItem.id).where(MemoryItem.user_id == student_id))
                is None
            )
            assert (
                await session.scalar(
                    select(UserPreference.id).where(UserPreference.user_id == student_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(Notification.id).where(Notification.user_id == student_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(LearningEvidence.id).where(
                        LearningEvidence.user_id == student_id,
                        LearningEvidence.knowledge_point == "kp-retained",
                    )
                )
                is None
            )
            assert (
                await session.scalar(
                    select(MasteryState.id).where(MasteryState.user_id == student_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(ChatTurn.id).where(ChatTurn.content == "需要删除的对话正文")
                )
                is None
            )
            assert (
                await session.scalar(
                    select(ChatSession.id).where(ChatSession.user_id == student_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(LearningEpisode.id).where(LearningEpisode.task_id == task_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(CaseSession.id).where(CaseSession.user_id == student_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(MiniLabSession.id).where(MiniLabSession.user_id == student_id)
                )
                is None
            )
            assert (
                await session.scalar(
                    select(LearningQualification.id).where(
                        LearningQualification.user_id == student_id
                    )
                )
                is None
            )
            user = await session.get(User, student_id)
            assert user is not None
            assert user.email == f"deleted-{student_id}@invalid.invalid"
            assert user.display_name == "已注销账号"
            auth_sessions = list(
                (
                    await session.execute(
                        select(AuthSession).where(AuthSession.user_id == student_id)
                    )
                ).scalars()
            )
            assert auth_sessions == []
            deletion = await session.get(PrivacyDeletionRequest, response["request_id"])
            assert deletion is not None
            assert deletion.status == "completed_with_retention"
            assert deletion.processed_counts["memory_items"] == 1
            assert deletion.status_credential_hash != response["status_credential"]
            assert deletion.status_credential_expires_at is not None
            deletion.status_credential_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    from app.db.models import User

    asyncio.run(_check_deletion())
    expired_status = client.post("/api/v1/privacy/deletion-status", json=status_query)
    assert expired_status.status_code == 404

    legacy_request_id = new_ulid()

    async def _seed_legacy_receipt() -> None:
        async with session_factory() as session:
            session.add(
                PrivacyDeletionRequest(
                    id=legacy_request_id,
                    subject_user_id=student_id,
                    status="completed_with_retention",
                    processed_counts={},
                    retained_categories=[],
                    completed_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed_legacy_receipt())
    legacy_status = client.post(
        "/api/v1/privacy/deletion-status",
        json={"request_id": legacy_request_id, "status_credential": "A" * 43},
    )
    assert legacy_status.status_code == 404


def test_privacy_delete_failed_job_can_be_retried_with_the_same_secret(client, monkeypatch) -> None:
    _course_id, _student_id = _setup_course(client)
    _login(client, "ms@uni.edu")

    from app.db.base import new_ulid
    from app.modules.memory import tasks as deletion_tasks

    request_id = new_ulid()
    status_credential = secrets.token_urlsafe(32)
    body = {"request_id": request_id, "status_credential": status_credential}

    def fail_dispatch(_request_id: str) -> None:
        raise RuntimeError("broker endpoint must not be returned to caller")

    monkeypatch.setattr(deletion_tasks, "dispatch_privacy_deletion", fail_dispatch)
    accepted = client.post("/api/v1/me/privacy/delete-request", json=body)
    assert accepted.status_code == 202
    assert accepted.json()["data"]["status"] == "failed"
    assert accepted.json()["data"]["last_error_code"] == "dispatch_failed"
    assert accepted.json()["data"]["retryable"] is True
    assert "broker endpoint" not in accepted.text

    monkeypatch.setattr(deletion_tasks, "dispatch_privacy_deletion", lambda _id: None)
    retry = client.post("/api/v1/privacy/deletion-status/retry", json=body)
    assert retry.status_code == 202
    assert retry.json()["data"]["status"] == "queued"

    original_delete = deletion_tasks.delete_personal_learning_data

    async def fail_processing(*_args, **_kwargs):
        raise RuntimeError("database details must not escape")

    monkeypatch.setattr(deletion_tasks, "delete_personal_learning_data", fail_processing)
    asyncio.run(deletion_tasks._execute_privacy_deletion(request_id))
    failed_status = client.post("/api/v1/privacy/deletion-status", json=body)
    assert failed_status.status_code == 200
    assert failed_status.json()["data"]["status"] == "failed"
    assert failed_status.json()["data"]["last_error_code"] == "deletion_processing_failed"
    assert failed_status.json()["data"]["attempt_count"] == 1

    monkeypatch.setattr(deletion_tasks, "delete_personal_learning_data", original_delete)
    retry = client.post("/api/v1/privacy/deletion-status/retry", json=body)
    assert retry.status_code == 202
    asyncio.run(deletion_tasks._execute_privacy_deletion(request_id))
    completed = client.post("/api/v1/privacy/deletion-status", json=body)
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "completed_with_retention"
    assert completed.json()["data"]["retryable"] is False
    assert completed.json()["data"]["attempt_count"] == 2
    replay = client.post("/api/v1/privacy/deletion-status/retry", json=body)
    assert replay.status_code == 200
    assert replay.json()["data"]["status"] == "completed_with_retention"
    assert replay.json()["data"]["attempt_count"] == 2


def test_privacy_delete_rolls_back_if_security_cache_cleanup_fails(client, monkeypatch) -> None:
    course_id, student_id, _, _ = _prepare_published(client)
    _login(client, "ms@uni.edu")

    from app.db.base import new_ulid
    from app.db.models import MemoryItem
    from app.db.session import session_factory
    from app.modules.auth import service as auth_service

    async def _seed_memory() -> None:
        async with session_factory() as session:
            session.add(
                MemoryItem(
                    id=new_ulid(),
                    user_id=student_id,
                    course_id=course_id,
                    layer="L1",
                    kind="weakness",
                    content="回滚测试记忆",
                    source_type="quiz",
                    confidence=0.5,
                )
            )
            await session.commit()

    class FailingRedis:
        async def scan_iter(self, *, match: str):
            raise RuntimeError("cache unavailable")
            yield match

        async def aclose(self) -> None:
            return None

    asyncio.run(_seed_memory())
    monkeypatch.setattr(auth_service, "get_redis_client", lambda: FailingRedis())

    response = client.post(
        "/api/v1/me/privacy/delete-request",
        json={"request_id": new_ulid(), "status_credential": secrets.token_urlsafe(32)},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PRIVACY_DELETE_RETRYABLE"
    assert client.get("/api/v1/me").status_code == 200

    async def _assert_transaction_rolled_back() -> None:
        async with session_factory() as session:
            user = await session.get(User, student_id)
            assert user is not None and user.status == "active"
            memory = await session.scalar(
                select(MemoryItem.id).where(MemoryItem.user_id == student_id)
            )
            assert memory is not None

    from app.db.models import User

    asyncio.run(_assert_transaction_rolled_back())


def test_student_growth_projection_hides_raw_correct_ratio(client) -> None:
    course_id, _, _, _ = _prepare_published(client)
    _login(client, "ms@uni.edu")
    overview = client.get(f"/api/v1/student/growth/overview?course_id={course_id}")
    assert overview.status_code == 200
    assert overview.json()["data"]["course_id"] == course_id
    assert "freshness" in overview.json()["data"]
    knowledge = client.get(f"/api/v1/student/growth/knowledge?course_id={course_id}")
    assert knowledge.status_code == 200
    for item in knowledge.json()["data"]:
        assert "correct_ratio" not in item


def test_student_growth_tabs_are_explainable_and_ratio_free(client) -> None:
    course_id, student_id, _, _ = _prepare_published(client)
    _login(client, "ms@uni.edu")

    from app.db.models import MasteryState
    from app.db.session import session_factory

    async def _seed_knowledge_state() -> None:
        async with session_factory() as session:
            session.add(
                MasteryState(
                    user_id=student_id,
                    course_id=course_id,
                    knowledge_point="合成知识点",
                    state="learning",
                    evidence_count=3,
                    correct_ratio=0.67,
                    weight_score=0.5,
                    context_count=2,
                    independent_evidence_count=1,
                    algorithm_version="mastery-v2-independent-context",
                    state_reason="由合成练习证据更新",
                )
            )
            await session.commit()

    asyncio.run(_seed_knowledge_state())
    response = client.get(f"/api/v1/student/growth/tabs?course_id={course_id}")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert {"knowledge", "skills", "misconceptions", "trajectory"} <= payload.keys()
    assert any(item["knowledge_point"] == "合成知识点" for item in payload["knowledge"])
    assert payload["skills"] == [], "知识点掌握状态不得伪装成独立技能状态"
    assert "correct_ratio" not in str(payload)


def test_privacy_deletion_openapi_exposes_partial_retention_receipt(client) -> None:
    from app.main import app

    response_schema = app.openapi()["paths"]["/api/v1/me/privacy/delete-request"]["post"]
    envelope_ref = response_schema["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert envelope_ref.endswith("/PrivacyDeletionResponse")
    components = app.openapi()["components"]["schemas"]
    envelope = components["PrivacyDeletionResponse"]
    receipt_ref = envelope["properties"]["data"]["$ref"].rsplit("/", 1)[-1]
    receipt = components[receipt_ref]
    assert "completed_with_retention" in receipt["properties"]["status"]["enum"]
    assert {"queued", "failed", "running"} <= set(receipt["properties"]["status"]["enum"])
    assert {
        "attempt_count",
        "retryable",
        "processed_counts",
        "retained_categories",
        "request_id",
        "status_credential",
        "status_credential_expires_at",
    } <= set(receipt["properties"])
    request_schema = response_schema["requestBody"]["content"]["application/json"]["schema"]
    request_ref = request_schema["$ref"].rsplit("/", 1)[-1]
    assert set(components[request_ref]["required"]) == {"request_id", "status_credential"}
    status_schema = app.openapi()["paths"]["/api/v1/privacy/deletion-status"]["post"]
    status_ref = status_schema["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert status_ref.endswith("/PrivacyDeletionStatusResponse")
    query_properties = status_schema["requestBody"]["content"]["application/json"]["schema"][
        "properties"
    ]
    assert query_properties["status_credential"]["pattern"] == r"^[A-Za-z0-9_-]{43}$"
    assert "/api/v1/privacy/deletion-status/retry" in app.openapi()["paths"]


def test_admin_health_and_audit_require_admin(client) -> None:
    create_user_sync(email="plain@uni.edu")
    create_user_sync(email="root@uni.edu", is_platform_admin=True)

    _login(client, "plain@uni.edu")
    denied = client.get("/api/v1/admin/health")
    assert denied.status_code == 403

    _login(client, "root@uni.edu")
    health = client.get("/api/v1/admin/health")
    assert health.status_code == 200
    assert "counts" in health.json()["data"]

    audits = client.get("/api/v1/admin/audit-logs?limit=5")
    assert audits.status_code == 200
    assert len(audits.json()["data"]) <= 5
