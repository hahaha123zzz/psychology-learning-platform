import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from tests.test_mastery_memory import _prepare_published
from tests.test_materials import _login


def test_due_review_verification_generates_retention_evidence(client) -> None:
    course_id, _student_id, _version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts").json()["data"]
    question = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]["items"][0]
    assert client.put(
        f"/api/v1/attempts/{attempt['attempt_id']}/answers/{question['question_version_id']}",
        json={"answer_version": 1, "response": {"selected_keys": ["C"]}},
    ).status_code == 200
    assert client.post(f"/api/v1/attempts/{attempt['attempt_id']}/submit").status_code == 200

    from app.db.models import LearningEvent, LearningEvidence, MasteryState, ReviewTask
    from app.db.session import session_factory

    async def _make_due() -> None:
        async with session_factory() as db:
            await db.execute(
                update(ReviewTask)
                .where(ReviewTask.course_id == course_id)
                .values(due_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await db.commit()

    asyncio.run(_make_due())
    tasks = client.get("/api/v1/review-tasks?due_only=true")
    assert tasks.status_code == 200
    task = tasks.json()["data"][0]
    assert task["question"]["options"]

    body = {"version": task["version"], "response": {"selected_keys": ["A"]}}
    verify_url = f"/api/v1/review-tasks/{task['id']}/verify"

    async def _set_review_status(status: str) -> None:
        async with session_factory() as db:
            stored_task = await db.scalar(select(ReviewTask).where(ReviewTask.id == task["id"]))
            assert stored_task is not None
            stored_task.status = status
            await db.commit()

    # A completed task alone is not evidence that a verify event was committed.
    asyncio.run(_set_review_status("done"))
    missing_event = client.post(verify_url, json=body)
    assert missing_event.status_code == 409
    assert missing_event.json()["error"]["code"] == "REVIEW_TASK_NOT_PENDING"
    asyncio.run(_set_review_status("pending"))

    verified = client.post(verify_url, json=body)
    assert verified.status_code == 200
    assert verified.json()["data"]["pending_qualification"] is True
    original_data = verified.json()["data"]
    event_key = f"review:{task['id']}:verify"

    async def _side_effect_snapshot() -> tuple:
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.user_id == _student_id, LearningEvent.event_key == event_key)
            )
            evidence_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvidence)
                .where(
                    LearningEvidence.user_id == _student_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.source_type == "review",
                    LearningEvidence.attempt_id == task["id"],
                )
            )
            review_task_count = await db.scalar(
                select(func.count())
                .select_from(ReviewTask)
                .where(ReviewTask.user_id == _student_id, ReviewTask.course_id == course_id)
            )
            mastery_rows = list(
                (
                    await db.execute(
                        select(MasteryState)
                        .where(
                            MasteryState.user_id == _student_id,
                            MasteryState.course_id == course_id,
                        )
                        .order_by(MasteryState.knowledge_point)
                    )
                ).scalars()
            )
            mastery_snapshot = tuple(
                (row.knowledge_point, row.version, row.state, row.evidence_count)
                for row in mastery_rows
            )
            return event_count, evidence_count, review_task_count, mastery_snapshot

    before_replays = asyncio.run(_side_effect_snapshot())
    replayed = client.post(verify_url, json=body)
    assert replayed.status_code == 200
    assert replayed.json()["data"] == original_data
    assert replayed.json()["meta"]["idempotent_replay"] is True
    assert asyncio.run(_side_effect_snapshot()) == before_replays

    changed_answer = client.post(
        verify_url,
        json={"version": task["version"], "response": {"selected_keys": ["B"]}},
    )
    assert changed_answer.status_code == 409
    assert changed_answer.json()["error"]["code"] == "LEARNING_EVENT_KEY_CONFLICT"
    assert asyncio.run(_side_effect_snapshot()) == before_replays

    from app.modules.learning_events.qualification import qualify_pending_events

    async def _qualify() -> dict[str, int]:
        async with session_factory() as db:
            return await qualify_pending_events(db, limit=20)

    counts = asyncio.run(_qualify())
    assert counts["qualified"] >= 1

    async def _read_task() -> ReviewTask | None:
        async with session_factory() as db:
            return await db.scalar(select(ReviewTask).where(ReviewTask.id == task["id"]))

    stored = asyncio.run(_read_task())
    assert stored is not None
    assert stored.qualification_status == "qualified"

    # Qualification changes separately; a later HTTP retry still replays the original response.
    after_qualification = asyncio.run(_side_effect_snapshot())
    qualified_replay = client.post(verify_url, json=body)
    assert qualified_replay.status_code == 200
    assert qualified_replay.json()["data"] == original_data
    assert qualified_replay.json()["meta"]["idempotent_replay"] is True
    assert asyncio.run(_side_effect_snapshot()) == after_qualification

    changed_after_qualification = client.post(
        verify_url,
        json={"version": task["version"], "response": {"selected_keys": ["B"]}},
    )
    assert changed_after_qualification.status_code == 409
    assert changed_after_qualification.json()["error"]["code"] == "LEARNING_EVENT_KEY_CONFLICT"
    assert asyncio.run(_side_effect_snapshot()) == after_qualification


def test_review_answer_shape_qualifies_only_supported_pinned_objective_types(client) -> None:
    course_id, student_id, _version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    from app.db.base import new_ulid
    from app.db.models import (
        LearningEvent,
        LearningEvidence,
        MasteryState,
        Question,
        QuestionVersion,
        ReviewTask,
    )
    from app.db.session import session_factory

    assessment = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    source_question_version_id = assessment["items"][0]["question_version_id"]

    async def _seed_tasks() -> list[tuple[str, str, dict]]:
        async with session_factory() as db:
            source = await db.scalar(
                select(QuestionVersion).where(QuestionVersion.id == source_question_version_id)
            )
            assert source is not None
            cases = [
                (
                    "multiple",
                    [{"key": "A"}, {"key": "B"}, {"key": "C"}],
                    {"correct_keys": ["A", "C"]},
                    {"selected_keys": ["A", "C"]},
                ),
                (
                    "true_false",
                    None,
                    {"correct": True},
                    {"selected_keys": True},
                ),
                (
                    "multiple",
                    [{"key": "A"}, {"key": "B"}],
                    {"correct_keys": ["A"]},
                    {"selected_keys": "A"},
                ),
                (
                    "true_false",
                    None,
                    {"correct": False},
                    {"selected_keys": [False]},
                ),
                (
                    "essay",
                    None,
                    None,
                    {"selected_keys": ["A"]},
                ),
            ]
            latest_version_no = await db.scalar(
                select(func.max(QuestionVersion.version_no)).where(
                    QuestionVersion.question_id == source.question_id
                )
            )
            first_version_no = (latest_version_no or source.version_no) + 1
            seeded: list[tuple[str, str, dict]] = []
            now = datetime.now(UTC)
            for offset, (question_type, options, answer, response) in enumerate(
                cases, start=first_version_no
            ):
                question_version_id = new_ulid()
                task_id = new_ulid()
                db.add(
                    QuestionVersion(
                        id=question_version_id,
                        question_id=source.question_id,
                        version_no=offset,
                        type=question_type,
                        stem=f"合成复习题 {offset}",
                        options=options,
                        answer=answer,
                        rubric="合成评分规则" if question_type == "essay" else None,
                        explanation=None,
                        difficulty=2,
                        knowledge_point_ids=[f"synthetic-review-{offset}"],
                        evidence_ids=[],
                        created_by=student_id,
                    )
                )
                db.add(
                    ReviewTask(
                        id=task_id,
                        user_id=student_id,
                        course_id=course_id,
                        question_version_id=question_version_id,
                        source_attempt_id=None,
                        reason="review_schedule",
                        due_at=now - timedelta(minutes=1),
                        status="pending",
                        qualification_status="pending",
                    )
                )
                seeded.append((task_id, question_version_id, response))
            question = await db.scalar(select(Question).where(Question.id == source.question_id))
            assert question is not None
            # Move the mutable pointer past these task pins; each review must use its exact QV.
            latest_id = new_ulid()
            db.add(
                QuestionVersion(
                    id=latest_id,
                    question_id=source.question_id,
                    version_no=first_version_no + len(cases),
                    type="single",
                    stem="后续合成版本，不属于复习任务 pin",
                    options=[{"key": "Z"}],
                    answer={"correct_keys": ["Z"]},
                    explanation=None,
                    difficulty=2,
                    knowledge_point_ids=["synthetic-latest-version"],
                    evidence_ids=[],
                    created_by=student_id,
                )
            )
            question.current_version_id = latest_id
            await db.commit()
            return seeded

    tasks = asyncio.run(_seed_tasks())
    outcomes: list[tuple[str, str, str]] = []
    for task_id, _question_version_id, response in tasks:
        verified = client.post(
            f"/api/v1/review-tasks/{task_id}/verify",
            json={"version": 1, "response": response},
        )
        assert verified.status_code == 200, verified.text
        event_id = verified.json()["data"]["event_id"]

        from app.modules.learning_events.qualification import qualify_event

        async def _qualify(event_id: str = event_id):
            async with session_factory() as db:
                qualification, replayed = await qualify_event(db, event_id=event_id)
                await db.commit()
                return qualification.id, qualification.status, qualification.reason, replayed

        qualification_id, status, reason, replayed = asyncio.run(_qualify())
        assert replayed is False
        outcomes.append((qualification_id, status, reason))

    assert [item[1] for item in outcomes] == [
        "qualified",
        "qualified",
        "rejected",
        "rejected",
        "rejected",
    ]
    assert outcomes[0][2] == "authoritative_review_answer"
    assert outcomes[1][2] == "authoritative_review_answer"
    assert outcomes[2][2] == "review_response_shape_invalid"
    assert outcomes[3][2] == "review_response_shape_invalid"
    assert outcomes[4][2] == "review_question_not_objective"

    async def _read_results() -> tuple[list[LearningEvidence], list[LearningEvent], list[str]]:
        async with session_factory() as db:
            events = list(
                (
                    await db.execute(
                        select(LearningEvent)
                        .where(LearningEvent.source_ref.in_([item[0] for item in tasks]))
                        .order_by(LearningEvent.event_key)
                    )
                ).scalars()
            )
            evidence = list(
                (
                    await db.execute(
                        select(LearningEvidence).where(
                            LearningEvidence.source_type == "review",
                            LearningEvidence.attempt_id.in_([item[0] for item in tasks]),
                        )
                    )
                ).scalars()
            )
            mastery_points = list(
                (
                    await db.execute(
                        select(MasteryState.knowledge_point).where(
                            MasteryState.user_id == student_id,
                            MasteryState.course_id == course_id,
                        )
                    )
                ).scalars()
            )
            return evidence, events, mastery_points

    evidence, events, mastery_points = asyncio.run(_read_results())
    assert len(events) == 5
    assert [event.qualification_status for event in events].count("qualified") == 2
    assert len(evidence) == 2
    assert {item.question_version_id for item in evidence} == {
        tasks[0][1],
        tasks[1][1],
    }
    assert "synthetic-review-4" not in mastery_points
    assert "synthetic-review-5" not in mastery_points
    assert "synthetic-review-6" not in mastery_points


def test_review_draft_recovers_with_version_and_revoked_scope_hides_task(client) -> None:
    course_id, student_id, _version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    from app.db.base import new_ulid
    from app.db.models import (
        CourseMember,
        LearningEvent,
        LearningEvidence,
        MasteryState,
        ReviewTask,
    )
    from app.db.session import session_factory

    assessment = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    question_version_id = assessment["items"][0]["question_version_id"]
    task_id = new_ulid()

    async def _seed() -> None:
        async with session_factory() as db:
            db.add(
                ReviewTask(
                    id=task_id,
                    user_id=student_id,
                    course_id=course_id,
                    question_version_id=question_version_id,
                    source_attempt_id=None,
                    reason="review_schedule",
                    due_at=datetime.now(UTC) + timedelta(days=1),
                    status="pending",
                    qualification_status="pending",
                )
            )
            await db.commit()

    asyncio.run(_seed())
    listing = client.get("/api/v1/review-tasks?due_only=false")
    assert listing.status_code == 200
    task = next(item for item in listing.json()["data"] if item["id"] == task_id)
    assert task["response_draft"] is None
    assert task["version"] == 1

    draft_body = {"version": 1, "response": {"selected_keys": ["A"]}}
    draft_url = f"/api/v1/review-tasks/{task_id}/draft"
    saved = client.put(draft_url, json=draft_body)
    assert saved.status_code == 200
    assert saved.json()["data"] == {
        "id": task_id,
        "response_draft": draft_body["response"],
        "version": 2,
    }
    replay = client.put(draft_url, json=draft_body)
    assert replay.status_code == 200
    assert replay.json()["data"] == saved.json()["data"]
    assert replay.json()["meta"]["idempotent_replay"] is True

    stale = client.put(
        draft_url,
        json={"version": 1, "response": {"selected_keys": ["B"]}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    assert stale.json()["error"]["details"] == {"expected_version": 1, "actual_version": 2}

    recovered = client.get("/api/v1/review-tasks?due_only=false")
    recovered_task = next(item for item in recovered.json()["data"] if item["id"] == task_id)
    assert recovered_task["version"] == 2
    assert recovered_task["response_draft"] == draft_body["response"]

    async def _revoke_and_counts() -> tuple[int, int, int]:
        async with session_factory() as db:
            member = await db.scalar(
                select(CourseMember).where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            await db.commit()
            event_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.user_id == student_id, LearningEvent.source_ref == task_id)
            )
            evidence_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvidence)
                .where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.attempt_id == task_id,
                )
            )
            mastery_count = await db.scalar(
                select(func.count())
                .select_from(MasteryState)
                .where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            return event_count or 0, evidence_count or 0, mastery_count or 0

    assert asyncio.run(_revoke_and_counts()) == (0, 0, 0)
    assert client.get("/api/v1/review-tasks?due_only=false").json()["data"] == []
    assert client.put(
        draft_url,
        json={"version": 2, "response": {"selected_keys": ["C"]}},
    ).status_code == 404
    assert client.post(
        f"/api/v1/review-tasks/{task_id}/verify",
        json={"version": 2, "response": {"selected_keys": ["A"]}},
    ).status_code == 404
    assert client.post(
        f"/api/v1/review-tasks/{task_id}/complete",
        json={"version": 2, "reason": "unsupported_question_type"},
    ).status_code == 404

    async def _stored_task() -> tuple[str, int, dict | None, str]:
        async with session_factory() as db:
            stored = await db.scalar(select(ReviewTask).where(ReviewTask.id == task_id))
            assert stored is not None
            return (
                stored.status,
                stored.version,
                stored.response_draft,
                stored.qualification_status,
            )

    assert asyncio.run(_stored_task()) == (
        "pending",
        2,
        draft_body["response"],
        "pending",
    )


def test_review_subjective_close_is_versioned_due_and_has_no_evidence(client) -> None:
    course_id, student_id, _version_id, assessment_id = _prepare_published(client)
    _login(client, "ms@uni.edu")

    from app.db.base import new_ulid
    from app.db.models import (
        LearningEvent,
        LearningEvidence,
        MasteryState,
        QuestionVersion,
        ReviewTask,
    )
    from app.db.session import session_factory

    assessment = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    objective_question_version_id = assessment["items"][0]["question_version_id"]
    close_task_id = new_ulid()
    objective_task_id = new_ulid()

    async def _seed() -> None:
        async with session_factory() as db:
            source = await db.scalar(
                select(QuestionVersion).where(QuestionVersion.id == objective_question_version_id)
            )
            assert source is not None
            latest_version_no = await db.scalar(
                select(func.max(QuestionVersion.version_no)).where(
                    QuestionVersion.question_id == source.question_id
                )
            )
            subjective_id = new_ulid()
            db.add(
                QuestionVersion(
                    id=subjective_id,
                    question_id=source.question_id,
                    version_no=(latest_version_no or source.version_no) + 1,
                    type="essay",
                    stem="合成主观题",
                    options=None,
                    answer=None,
                    rubric="合成评分标准",
                    explanation=None,
                    difficulty=2,
                    knowledge_point_ids=["synthetic-subjective-review"],
                    evidence_ids=[],
                    created_by=student_id,
                )
            )
            now = datetime.now(UTC)
            db.add_all(
                [
                    ReviewTask(
                        id=close_task_id,
                        user_id=student_id,
                        course_id=course_id,
                        question_version_id=subjective_id,
                        source_attempt_id=None,
                        reason="review_schedule",
                        due_at=now + timedelta(hours=1),
                        status="pending",
                        qualification_status="pending",
                    ),
                    ReviewTask(
                        id=objective_task_id,
                        user_id=student_id,
                        course_id=course_id,
                        question_version_id=objective_question_version_id,
                        source_attempt_id=None,
                        reason="review_schedule",
                        due_at=now - timedelta(minutes=1),
                        status="pending",
                        qualification_status="pending",
                    ),
                ]
            )
            await db.commit()

    asyncio.run(_seed())
    complete_url = f"/api/v1/review-tasks/{close_task_id}/complete"
    close_v1 = {"version": 1, "reason": "unsupported_question_type"}
    too_early = client.post(complete_url, json=close_v1)
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "REVIEW_TASK_NOT_DUE"

    objective_close = client.post(
        f"/api/v1/review-tasks/{objective_task_id}/complete",
        json={"version": 1, "reason": "unsupported_question_type"},
    )
    assert objective_close.status_code == 409
    assert objective_close.json()["error"]["code"] == "REVIEW_ANSWER_SUPPORTED"

    saved_draft = client.put(
        f"/api/v1/review-tasks/{close_task_id}/draft",
        json={"version": 1, "response": {"text": "合成的未完成草稿"}},
    )
    assert saved_draft.status_code == 200
    stale_close = client.post(complete_url, json=close_v1)
    assert stale_close.status_code == 409
    assert stale_close.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    assert stale_close.json()["error"]["details"] == {
        "expected_version": 1,
        "actual_version": 2,
    }

    from app.db.models import ReviewTask as ReviewTaskModel

    async def _make_due() -> None:
        async with session_factory() as db:
            task = await db.scalar(
                select(ReviewTaskModel).where(ReviewTaskModel.id == close_task_id)
            )
            assert task is not None
            task.due_at = datetime.now(UTC) - timedelta(minutes=1)
            await db.commit()

    asyncio.run(_make_due())
    body = {"version": 2, "reason": "unsupported_question_type"}
    closed = client.post(complete_url, json=body)
    assert closed.status_code == 200
    assert closed.json()["data"] == {"id": close_task_id, "status": "done", "version": 3}
    repeated = client.post(complete_url, json=body)
    assert repeated.status_code == 200
    assert repeated.json()["data"] == closed.json()["data"]
    assert repeated.json()["meta"]["idempotent_replay"] is True

    async def _assert_no_effects() -> tuple[int, int, int, tuple[str, int, dict | None]]:
        async with session_factory() as db:
            event_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(
                    LearningEvent.user_id == student_id,
                    LearningEvent.source_ref.in_([close_task_id, objective_task_id]),
                )
            )
            evidence_count = await db.scalar(
                select(func.count())
                .select_from(LearningEvidence)
                .where(
                    LearningEvidence.user_id == student_id,
                    LearningEvidence.attempt_id.in_([close_task_id, objective_task_id]),
                )
            )
            mastery_count = await db.scalar(
                select(func.count())
                .select_from(MasteryState)
                .where(
                    MasteryState.user_id == student_id,
                    MasteryState.course_id == course_id,
                )
            )
            objective_task = await db.scalar(
                select(ReviewTaskModel).where(ReviewTaskModel.id == objective_task_id)
            )
            assert objective_task is not None
            subjective_task = await db.scalar(
                select(ReviewTaskModel).where(ReviewTaskModel.id == close_task_id)
            )
            assert subjective_task is not None
            return (
                event_count or 0,
                evidence_count or 0,
                mastery_count or 0,
                (objective_task.status, objective_task.version, subjective_task.response_draft),
            )

    assert asyncio.run(_assert_no_effects()) == (0, 0, 0, ("pending", 1, None))
