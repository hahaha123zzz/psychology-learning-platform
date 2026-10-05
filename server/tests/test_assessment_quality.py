"""P7-07 错题追溯、题目质量反馈与证据失效回归。"""

import asyncio

from sqlalchemy import func, select

from tests.conftest import create_user_sync
from tests.test_materials import _login, _setup_course

QUESTION_BODY = {
    "type": "single",
    "stem": "以下哪一项是实验者操纵的变量？",
    "options": [
        {"key": "A", "text": "自变量", "is_correct": True},
        {"key": "B", "text": "因变量", "is_correct": False},
        {"key": "C", "text": "控制变量", "is_correct": False},
    ],
    "difficulty": 2,
    "explanation": "自变量由实验者操纵。",
    "knowledge_point_ids": ["experiment-variable"],
    "evidence_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
}


def _publish_question_and_assessment(client, course_id: str) -> tuple[dict, str]:
    created = client.post(f"/api/v1/courses/{course_id}/questions", json=QUESTION_BODY)
    assert created.status_code == 201, created.text
    question = created.json()["data"]
    question_id = question["id"]
    reviewed = client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "质量测试题"},
    )
    assert reviewed.status_code == 200, reviewed.text
    published = client.post(f"/api/v1/questions/{question_id}/publish")
    assert published.status_code == 200, published.text

    assessment_response = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "题目质量回归测评",
            "question_ids": [question_id],
            "ai_policy": "disabled",
            "points_per_question": 5,
        },
    )
    assert assessment_response.status_code == 201, assessment_response.text
    assessment_id = assessment_response.json()["data"]["id"]
    published_assessment = client.post(
        f"/api/v1/assessments/{assessment_id}/publish"
    )
    assert published_assessment.status_code == 200, published_assessment.text
    return question, assessment_id


def _submit_wrong_answer(client, assessment_id: str) -> tuple[str, str]:
    assessment = client.get(f"/api/v1/assessments/{assessment_id}")
    assert assessment.status_code == 200, assessment.text
    question_version_id = assessment.json()["data"]["items"][0]["question_version_id"]
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]
    saved = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["B"]}},
    )
    assert saved.status_code == 200, saved.text
    submitted = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submitted.status_code == 200, submitted.text
    return attempt_id, question_version_id


def _count_for(model, **filters) -> int:
    async def _count() -> int:
        from app.db.session import session_factory

        async with session_factory() as db:
            result = await db.execute(
                select(func.count())
                .select_from(model)
                .where(*(getattr(model, key) == value for key, value in filters.items()))
            )
            return int(result.scalar_one())

    return asyncio.run(_count())


def test_wrong_answer_trace_is_immutable_minimal_and_submit_replay_safe(client) -> None:
    from app.db.models import WrongAnswerTrace

    course_id, _student_id = _setup_course(client)
    _question, assessment_id = _publish_question_and_assessment(client, course_id)
    _login(client, "ms@uni.edu")
    attempt_id, question_version_id = _submit_wrong_answer(client, assessment_id)

    trace = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert trace.status_code == 200
    assert trace.json()["data"]["idempotent_replay"] is True
    assert _count_for(WrongAnswerTrace, attempt_id=attempt_id) == 1

    async def _read_trace():
        from app.db.session import session_factory

        async with session_factory() as db:
            return await db.scalar(
                select(WrongAnswerTrace).where(WrongAnswerTrace.attempt_id == attempt_id)
            )

    stored = asyncio.run(_read_trace())
    assert stored is not None
    assert stored.question_version_id == question_version_id
    assert stored.answer_present is True
    assert not hasattr(stored, "response")
    assert not hasattr(stored, "answer_text")


def test_student_feedback_is_course_scoped_and_duplicate_safe(client) -> None:
    from app.db.models import QuestionQualityFeedback

    course_id, _student_id = _setup_course(client)
    _question, assessment_id = _publish_question_and_assessment(client, course_id)
    _login(client, "ms@uni.edu")
    attempt_id, question_version_id = _submit_wrong_answer(client, assessment_id)
    feedback_path = (
        f"/api/v1/courses/{course_id}/question-versions/{question_version_id}/quality-feedback"
    )
    body = {
        "attempt_id": attempt_id,
        "category": "answer_key",
        "detail": "我认为题干与当前标准答案存在矛盾，请教师复核。",
    }
    first = client.post(feedback_path, json=body)
    assert first.status_code == 201, first.text
    feedback_id = first.json()["data"]["id"]
    duplicate = client.post(feedback_path, json=body)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["data"]["id"] == feedback_id
    assert duplicate.json()["meta"]["idempotent_replay"] is True
    conflicting_duplicate = client.post(
        feedback_path, json={**body, "detail": "修改同一反馈内容不应覆盖原记录。"}
    )
    assert conflicting_duplicate.status_code == 409
    assert conflicting_duplicate.json()["error"]["code"] == "QUALITY_FEEDBACK_EXISTS"
    assert _count_for(QuestionQualityFeedback, id=feedback_id) == 1

    create_user_sync(email="quality-outsider@uni.edu")
    _login(client, "quality-outsider@uni.edu")
    unauthorized = client.post(feedback_path, json=body)
    assert unauthorized.status_code == 404
    unauthorized_queue = client.get(
        f"/api/v1/courses/{course_id}/question-quality-feedback"
    )
    assert unauthorized_queue.status_code == 404


def test_teacher_resolution_uses_question_version_lock_and_invalidates_evidence(
    client,
) -> None:
    from app.db.models import (
        LearningEvidence,
        MasteryState,
        QuestionQualityFeedback,
        ReviewTask,
        WrongAnswerTrace,
    )

    course_id, _student_id = _setup_course(client)
    question, assessment_id = _publish_question_and_assessment(client, course_id)
    question_id = question["id"]
    feedback_ids: list[str] = []
    question_version_id = question["current_version"]["id"]

    _login(client, "ms@uni.edu")
    for note in (
        "标准答案可能存在问题，请复核。",
        "题目选项含义不够清楚，请复核。",
        "本题的判分依据可能不正确，请复核。",
    ):
        attempt_id, submitted_qv_id = _submit_wrong_answer(client, assessment_id)
        assert submitted_qv_id == question_version_id
        created = client.post(
            f"/api/v1/courses/{course_id}/question-versions/{question_version_id}/quality-feedback",
            json={
                "attempt_id": attempt_id,
                "category": "answer_key",
                "detail": note,
            },
        )
        assert created.status_code == 201, created.text
        feedback_ids.append(created.json()["data"]["id"])

    # 归档发生前已经开始的作答仍按不可变测评快照完成，但不得再派生证据/复习任务。
    assessment_detail = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    active_qv_id = assessment_detail["items"][0]["question_version_id"]
    active_attempt = client.post(
        f"/api/v1/assessments/{assessment_id}/attempts"
    ).json()["data"]["attempt_id"]
    active_save = client.put(
        f"/api/v1/attempts/{active_attempt}/answers/{active_qv_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["B"]}},
    )
    assert active_save.status_code == 200, active_save.text

    assert _count_for(WrongAnswerTrace, question_version_id=question_version_id) == 3
    assert _count_for(ReviewTask, question_version_id=question_version_id) == 3
    assert _count_for(
        LearningEvidence,
        question_version_id=question_version_id,
        quality_status="valid",
    ) == 3

    create_user_sync(email="quality-other-teacher@uni.edu", is_teacher=True)
    _login(client, "quality-other-teacher@uni.edu")
    unauthorized_queue = client.get(
        f"/api/v1/courses/{course_id}/question-quality-feedback"
    )
    assert unauthorized_queue.status_code == 404
    unauthorized_resolution = client.put(
        f"/api/v1/courses/{course_id}/question-quality-feedback/{feedback_ids[0]}/resolve",
        json={
            "expected_question_version": question["version"] + 1,
            "action": "accept",
            "rationale": "无权教师不得处置该课程的反馈。",
        },
    )
    assert unauthorized_resolution.status_code == 404

    _login(client, "mt@uni.edu")
    teacher_queue = client.get(
        f"/api/v1/courses/{course_id}/question-quality-feedback"
    )
    assert teacher_queue.status_code == 200, teacher_queue.text
    assert [row["id"] for row in teacher_queue.json()["data"]] == feedback_ids
    question_view = client.get(f"/api/v1/questions/{question_id}").json()["data"]
    initial_question_version = question_view["version"]

    accept = client.put(
        f"/api/v1/courses/{course_id}/question-quality-feedback/{feedback_ids[0]}/resolve",
        json={
            "expected_question_version": initial_question_version,
            "action": "accept",
            "rationale": "反馈属实，需要作为题目改进事项跟进。",
        },
    )
    assert accept.status_code == 200, accept.text
    accepted_version = accept.json()["data"]["question_version"]

    stale = client.put(
        f"/api/v1/courses/{course_id}/question-quality-feedback/{feedback_ids[1]}/resolve",
        json={
            "expected_question_version": initial_question_version,
            "action": "reject",
            "rationale": "使用过时版本尝试处置。",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    assert _count_for(
        QuestionQualityFeedback, id=feedback_ids[1], status="pending"
    ) == 1

    rejected = client.put(
        f"/api/v1/courses/{course_id}/question-quality-feedback/{feedback_ids[1]}/resolve",
        json={
            "expected_question_version": accepted_version,
            "action": "reject",
            "rationale": "复核后未发现题干或答案存在错误。",
        },
    )
    assert rejected.status_code == 200, rejected.text
    before_invalidation = rejected.json()["data"]["question_version"]

    invalidated = client.put(
        f"/api/v1/courses/{course_id}/question-quality-feedback/{feedback_ids[2]}/resolve",
        json={
            "expected_question_version": before_invalidation,
            "action": "invalidate",
            "rationale": "复核确认本题标准答案错误，停止继续使用。",
        },
    )
    assert invalidated.status_code == 200, invalidated.text
    assert invalidated.json()["data"]["question_status"] == "archived"
    assert invalidated.json()["data"]["invalidated_evidence_count"] == 3

    async def _read_quality_state():
        from app.db.session import session_factory

        async with session_factory() as db:
            evidence = list(
                (
                    await db.execute(
                        select(LearningEvidence).where(
                            LearningEvidence.question_version_id == question_version_id
                        )
                    )
                ).scalars()
            )
            tasks = list(
                (
                    await db.execute(
                        select(ReviewTask).where(
                            ReviewTask.question_version_id == question_version_id
                        )
                    )
                ).scalars()
            )
            mastery = list(
                (
                    await db.execute(
                        select(MasteryState).where(
                            MasteryState.course_id == course_id,
                            MasteryState.knowledge_point == "experiment-variable",
                        )
                    )
                ).scalars()
            )
            return evidence, tasks, mastery

    evidence_rows, review_rows, mastery_rows = asyncio.run(_read_quality_state())
    assert len(evidence_rows) == 3
    assert all(row.quality_status == "invalidated" for row in evidence_rows)
    assert all(row.invalidated_reason for row in evidence_rows)
    assert len(review_rows) == 3
    assert all(row.status == "dismissed" for row in review_rows)
    assert len(mastery_rows) == 1
    assert mastery_rows[0].state == "not_started"
    assert mastery_rows[0].evidence_count == 0

    archived_question = client.get(f"/api/v1/questions/{question_id}").json()["data"]
    assert archived_question["status"] == "archived"
    assert archived_question["current_version"]["id"] == question_version_id
    assessment_snapshot = client.get(f"/api/v1/assessments/{assessment_id}")
    assert assessment_snapshot.status_code == 200
    assert assessment_snapshot.json()["data"]["items"][0]["question_version_id"] == (
        question_version_id
    )
    cannot_start_again = client.post(
        f"/api/v1/assessments/{assessment_id}/attempts"
    )
    assert cannot_start_again.status_code == 409
    assert cannot_start_again.json()["error"]["code"] == "ASSESSMENT_QUESTION_INVALIDATED"

    _login(client, "ms@uni.edu")
    historical_result = client.get(
        f"/api/v1/attempts/{attempt_id}/result"
    )
    assert historical_result.status_code == 200
    assert historical_result.json()["data"]["score"] == 0
    assert historical_result.json()["data"]["items"][0]["response"] == {
        "selected_keys": ["B"]
    }
    completed_after_archive = client.post(
        f"/api/v1/attempts/{active_attempt}/submit"
    )
    assert completed_after_archive.status_code == 200, completed_after_archive.text
    assert _count_for(WrongAnswerTrace, question_version_id=question_version_id) == 4
    assert _count_for(
        LearningEvidence,
        question_version_id=question_version_id,
        quality_status="valid",
    ) == 0
    assert _count_for(ReviewTask, question_version_id=question_version_id) == 3
    memory = client.get("/api/v1/me/memory")
    assert memory.status_code == 200
    assert "L1:weakness" not in memory.json()["data"]["summary"]

