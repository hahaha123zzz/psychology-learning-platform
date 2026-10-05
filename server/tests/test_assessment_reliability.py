"""正式测评关键异常、隔离与重复副作用回归。"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import (
    Attempt,
    ClassMember,
    CourseClass,
    CourseRelease,
    CourseReleaseAssignment,
    LearningEvent,
    LearningEvidence,
    LearningQualification,
    ReviewTask,
    ScoreRecord,
    TeacherGradingDecision,
    WrongAnswerTrace,
)
from app.db.session import session_factory
from tests.conftest import create_user_sync, publish_course_release_for_test
from tests.test_materials import _login, _setup_course

OBJECTIVE_QUESTION = {
    "type": "single",
    "stem": "实验者操纵的变量是什么？",
    "options": [
        {"key": "A", "text": "自变量", "is_correct": True},
        {"key": "B", "text": "因变量", "is_correct": False},
    ],
    "difficulty": 2,
    "explanation": "自变量由实验者操纵。",
    "evidence_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
}

ESSAY_QUESTION = {
    "type": "essay",
    "stem": "简述被试内设计的一个优点。",
    "rubric": "指出同一被试参与多个条件，并说明可控制个体差异。",
    "difficulty": 2,
    "evidence_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
}


def _create_published_question(client, course_id: str, body: dict) -> dict:
    created = client.post(f"/api/v1/courses/{course_id}/questions", json=body)
    assert created.status_code == 201, created.text
    question = created.json()["data"]
    question_id = question["id"]
    reviewed = client.post(
        f"/api/v1/questions/{question_id}/review",
        json={"action": "approve", "version": 1, "comment": "可靠性回归测试审核"},
    )
    assert reviewed.status_code == 200, reviewed.text
    published = client.post(f"/api/v1/questions/{question_id}/publish")
    assert published.status_code == 200, published.text
    return question


def _create_assessment(client, course_id: str, question_ids: list[str], **extra) -> str:
    created = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "正式测评异常回归",
            "question_ids": question_ids,
            "ai_policy": "disabled",
            "points_per_question": 5,
            **extra,
        },
    )
    assert created.status_code == 201, created.text
    assessment_id = created.json()["data"]["id"]
    published = client.post(f"/api/v1/assessments/{assessment_id}/publish")
    assert published.status_code == 200, published.text
    return assessment_id


def _assign_release_to_student_class(
    client,
    course_id: str,
    student_id: str,
    *,
    code: str = "R3E",
    release_name: str = "测评绑定版本",
) -> tuple[str, str, str, int]:
    class_response = client.post(
        f"/api/v1/courses/{course_id}/classes",
        json={"code": code, "name": "测评绑定班"},
    )
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["data"]["id"]
    member_response = client.post(
        f"/api/v1/courses/{course_id}/classes/{class_id}/members",
        json={"user_id": student_id},
    )
    assert member_response.status_code == 201, member_response.text
    release_response = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": release_name,
            "material_ids": [],
            "domain_pack": {"chapters": ["intro"]},
            "pedagogy_pack": {"tasks": ["predict"]},
            "assessment_pack": {"release_ids": []},
        },
    )
    assert release_response.status_code == 201, release_response.text
    release_id = release_response.json()["data"]["id"]
    publish_course_release_for_test(client, course_id, release_id)
    assigned = client.put(
        f"/api/v1/courses/{course_id}/classes/{class_id}/release-assignment",
        headers={"Idempotency-Key": f"r3-e-{code.lower()}-assignment"},
        json={"course_release_id": release_id, "expected_version": 0},
    )
    assert assigned.status_code == 200, assigned.text
    assignment = assigned.json()["data"]
    return assignment["id"], release_id, class_id, assignment["version"]


def _read_attempt_release_binding(attempt_id: str) -> tuple[str | None, str | None]:
    async def _read() -> tuple[str | None, str | None]:
        async with session_factory() as db:
            attempt = await db.get(Attempt, attempt_id)
            assert attempt is not None
            return attempt.course_release_assignment_id, attempt.course_release_id

    return asyncio.run(_read())


def _count_for_attempt(model, attempt_id: str) -> int:
    async def _count() -> int:
        async with session_factory() as db:
            result = await db.execute(
                select(func.count()).select_from(model).where(model.source_attempt_id == attempt_id)
                if model is ReviewTask
                else select(func.count()).select_from(model).where(model.attempt_id == attempt_id)
            )
            return int(result.scalar_one())

    return asyncio.run(_count())


def _count_attempt_events(attempt_id: str) -> int:
    async def _count() -> int:
        async with session_factory() as db:
            result = await db.execute(
                select(func.count())
                .select_from(LearningEvent)
                .where(
                    LearningEvent.source_ref == attempt_id,
                    LearningEvent.source_type == "assessment",
                    LearningEvent.event_type == "answer_submitted",
                )
            )
            return int(result.scalar_one())

    return asyncio.run(_count())


def _count_attempt_qualifications(attempt_id: str) -> int:
    async def _count() -> int:
        async with session_factory() as db:
            result = await db.execute(
                select(func.count())
                .select_from(LearningQualification)
                .join(LearningEvent, LearningEvent.id == LearningQualification.event_id)
                .where(
                    LearningEvent.source_ref == attempt_id,
                    LearningEvent.source_type == "assessment",
                )
            )
            return int(result.scalar_one())

    return asyncio.run(_count())


def test_attempt_answer_version_conflict_and_flag_share_one_version(client) -> None:
    course_id, _student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])

    _login(client, "ms@uni.edu")
    assessment = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    question_version_id = assessment["items"][0]["question_version_id"]
    attempt = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert attempt.status_code == 201, attempt.text
    attempt_id = attempt.json()["data"]["attempt_id"]

    first_tab = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    assert first_tab.status_code == 200, first_tab.text
    assert first_tab.json()["data"]["answer_version"] == 2
    lost_response_retry = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    assert lost_response_retry.status_code == 200, lost_response_retry.text
    assert lost_response_retry.json()["meta"]["idempotent_replay"] is True
    assert lost_response_retry.json()["data"]["answer_version"] == 2
    stale_tab = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["B"]}},
    )
    assert stale_tab.status_code == 409
    assert stale_tab.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    after_stale_write = client.post(
        f"/api/v1/assessments/{assessment_id}/attempts"
    )
    assert after_stale_write.status_code == 200
    assert after_stale_write.json()["data"]["answers"] == [
        {
            "question_version_id": question_version_id,
            "response": {"selected_keys": ["A"]},
            "answer_version": 2,
            "flagged": False,
        }
    ]

    flag_from_second_tab = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}/flag",
        json={"answer_version": 2, "flagged": True},
    )
    assert flag_from_second_tab.status_code == 200, flag_from_second_tab.text
    lost_flag_response_retry = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}/flag",
        json={"answer_version": 2, "flagged": True},
    )
    assert lost_flag_response_retry.status_code == 200, lost_flag_response_retry.text
    assert lost_flag_response_retry.json()["meta"]["idempotent_replay"] is True
    assert lost_flag_response_retry.json()["data"]["answer_version"] == 3
    stale_after_flag = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 2, "response": {"selected_keys": ["B"]}},
    )
    assert stale_after_flag.status_code == 409

    restored = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert restored.status_code == 200
    assert restored.json()["data"]["answers"] == [
        {
            "question_version_id": question_version_id,
            "response": {"selected_keys": ["A"]},
            "answer_version": 3,
            "flagged": True,
        }
    ]


def test_student_assessment_list_exposes_only_current_user_attempt_for_resume(client) -> None:
    course_id, _student_id = _setup_course(client)
    other_student_id = create_user_sync(
        email="other-student@uni.edu", display_name="另一名学生"
    )
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])

    _login(client, "ms@uni.edu")
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]

    listed_by_student = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert listed_by_student.status_code == 200, listed_by_student.text
    assert listed_by_student.json()["data"][0]["current_attempt_id"] == attempt_id

    _login(client, "mt@uni.edu")
    added = client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": other_student_id, "role": "student"},
    )
    assert added.status_code == 201, added.text
    _login(client, "other-student@uni.edu")
    listed_by_other_student = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert listed_by_other_student.status_code == 200, listed_by_other_student.text
    assert listed_by_other_student.json()["data"][0]["current_attempt_id"] is None

    _login(client, "mt@uni.edu")
    listed_by_teacher = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert listed_by_teacher.status_code == 200, listed_by_teacher.text
    assert listed_by_teacher.json()["data"][0]["current_attempt_id"] is None


def test_attempt_binds_one_active_class_release_and_resume_does_not_drift(client) -> None:
    course_id, student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])
    assignment_id, release_id, class_id, assignment_version = _assign_release_to_student_class(
        client, course_id, student_id
    )

    _login(client, "ms@uni.edu")
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]
    assert _read_attempt_release_binding(attempt_id) == (assignment_id, release_id)

    _login(client, "mt@uni.edu")
    next_release = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "测评后续版本",
            "material_ids": [],
            "domain_pack": {"chapters": ["intro", "methods"]},
            "pedagogy_pack": {"tasks": ["predict"]},
            "assessment_pack": {"release_ids": []},
        },
    )
    assert next_release.status_code == 201, next_release.text
    next_release_id = next_release.json()["data"]["id"]
    publish_course_release_for_test(client, course_id, next_release_id)
    assignment_changed = client.put(
        f"/api/v1/courses/{course_id}/classes/{class_id}/release-assignment",
        headers={"Idempotency-Key": "r3-e-attempt-binding-reassignment"},
        json={
            "course_release_id": next_release_id,
            "expected_version": assignment_version,
            "close_reason": "测评回归的课程版本更新",
        },
    )
    assert assignment_changed.status_code == 200, assignment_changed.text
    assert assignment_changed.json()["data"]["id"] != assignment_id
    assert next_release_id != release_id

    _login(client, "ms@uni.edu")
    resumed = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["data"]["attempt_id"] == attempt_id
    assert _read_attempt_release_binding(attempt_id) == (assignment_id, release_id)


def test_attempt_release_binding_fails_closed_for_multiple_class_contexts(client) -> None:
    course_id, student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])
    assignment_id, release_id, _class_id, _version = _assign_release_to_student_class(
        client, course_id, student_id, code="R3E-A"
    )
    second_class = client.post(
        f"/api/v1/courses/{course_id}/classes",
        json={"code": "R3E-C", "name": "测评歧义班"},
    )
    assert second_class.status_code == 201, second_class.text
    second_class_id = second_class.json()["data"]["id"]
    member_response = client.post(
        f"/api/v1/courses/{course_id}/classes/{second_class_id}/members",
        json={"user_id": student_id},
    )
    assert member_response.status_code == 201, member_response.text
    assigned = client.put(
        f"/api/v1/courses/{course_id}/classes/{second_class_id}/release-assignment",
        headers={"Idempotency-Key": "r3-e-ambiguous-third-class"},
        json={"course_release_id": release_id, "expected_version": 0},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["course_release_id"] == release_id

    async def _active_student_assignments() -> list[tuple[str, str]]:
        async with session_factory() as db:
            rows = await db.execute(
                select(CourseReleaseAssignment.id, CourseRelease.status)
                .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
                .join(ClassMember, ClassMember.class_id == CourseClass.id)
                .join(CourseRelease, CourseRelease.id == CourseReleaseAssignment.course_release_id)
                .where(
                    CourseReleaseAssignment.course_id == course_id,
                    CourseReleaseAssignment.status == "active",
                    CourseClass.status == "active",
                    ClassMember.user_id == student_id,
                    ClassMember.status == "active",
                )
            )
            return list(rows.all())

    active_assignments = asyncio.run(_active_student_assignments())
    assert len(active_assignments) == 2, active_assignments
    assert all(status == "published" for _assignment_id, status in active_assignments)
    assert assignment_id in {item_id for item_id, _status in active_assignments}

    _login(client, "ms@uni.edu")
    response = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "COURSE_RELEASE_CONTEXT_AMBIGUOUS"


def test_bound_attempt_reads_stop_after_student_leaves_its_class(client) -> None:
    course_id, student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])
    assignment_id, _release_id, _class_id, _version = _assign_release_to_student_class(
        client, course_id, student_id
    )

    _login(client, "ms@uni.edu")
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]

    async def _remove_class_membership() -> None:
        async with session_factory() as db:
            assignment = await db.get(CourseReleaseAssignment, assignment_id)
            assert assignment is not None
            member = await db.scalar(
                select(ClassMember).where(
                    ClassMember.class_id == assignment.class_id,
                    ClassMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            member.version += 1
            await db.commit()

    asyncio.run(_remove_class_membership())
    resumed = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert resumed.status_code == 404, resumed.text
    result = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert result.status_code == 404, result.text


def test_submit_and_manual_grade_replay_do_not_duplicate_side_effects(client) -> None:
    course_id, _student_id = _setup_course(client)
    objective = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    essay = _create_published_question(client, course_id, ESSAY_QUESTION)
    assessment_id = _create_assessment(
        client, course_id, [objective["id"], essay["id"]]
    )

    _login(client, "ms@uni.edu")
    detail = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    question_versions = {
        item["type"]: item["question_version_id"] for item in detail["items"]
    }
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]
    for question_type, response in (
        ("single", {"selected_keys": ["B"]}),
        ("essay", {"text": "同一批被试参加多个条件，降低个体差异影响。"}),
    ):
        saved = client.put(
            f"/api/v1/attempts/{attempt_id}/answers/{question_versions[question_type]}",
            json={"answer_version": 1, "response": response},
        )
        assert saved.status_code == 200, saved.text

    submitted = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["grading_status"] == "pending_teacher"
    counts_after_first_submit = (
        _count_attempt_events(attempt_id),
        _count_for_attempt(ReviewTask, attempt_id),
        _count_for_attempt(ScoreRecord, attempt_id),
        _count_for_attempt(WrongAnswerTrace, attempt_id),
        _count_for_attempt(LearningEvidence, attempt_id),
        _count_attempt_qualifications(attempt_id),
    )
    assert counts_after_first_submit == (1, 1, 0, 1, 1, 1)

    replayed_submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert replayed_submit.status_code == 200
    assert replayed_submit.json()["data"]["idempotent_replay"] is True
    assert (
        _count_attempt_events(attempt_id),
        _count_for_attempt(ReviewTask, attempt_id),
        _count_for_attempt(ScoreRecord, attempt_id),
        _count_for_attempt(WrongAnswerTrace, attempt_id),
        _count_for_attempt(LearningEvidence, attempt_id),
        _count_attempt_qualifications(attempt_id),
    ) == counts_after_first_submit

    _login(client, "mt@uni.edu")
    grade_payload = {
        "expected_score_version": 0,
        "items": [
            {
                "question_version_id": question_versions["essay"],
                "points_awarded": 4,
                "rationale": "答案准确指出同一被试参与多个条件及其控制作用。",
            }
        ],
    }
    grade_headers = {"Idempotency-Key": "p7-08-grade-once"}
    first_grade = client.put(
        f"/api/v1/teacher/attempts/{attempt_id}/grading",
        json=grade_payload,
        headers=grade_headers,
    )
    assert first_grade.status_code == 200, first_grade.text
    grade_replay = client.put(
        f"/api/v1/teacher/attempts/{attempt_id}/grading",
        json=grade_payload,
        headers=grade_headers,
    )
    assert grade_replay.status_code == 200, grade_replay.text
    assert grade_replay.json()["meta"]["idempotent_replay"] is True
    assert _count_for_attempt(ScoreRecord, attempt_id) == 1
    assert _count_for_attempt(TeacherGradingDecision, attempt_id) == 1
    assert _count_for_attempt(LearningEvidence, attempt_id) == 1
    assert _count_attempt_qualifications(attempt_id) == 1

    _login(client, "ms@uni.edu")
    final_submit_replay = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert final_submit_replay.status_code == 200
    assert _count_attempt_events(attempt_id) == counts_after_first_submit[0]
    assert _count_for_attempt(ReviewTask, attempt_id) == counts_after_first_submit[1]
    assert _count_for_attempt(ScoreRecord, attempt_id) == 1


def test_assessment_and_attempt_are_hidden_from_non_members_and_other_course_users(
    client,
) -> None:
    course_a, _ = _setup_course(client)
    question_a = _create_published_question(client, course_a, OBJECTIVE_QUESTION)
    assessment_a = _create_assessment(client, course_a, [question_a["id"]])

    _login(client, "ms@uni.edu")
    attempt_a = client.post(f"/api/v1/assessments/{assessment_a}/attempts")
    assert attempt_a.status_code == 201
    attempt_a_id = attempt_a.json()["data"]["attempt_id"]

    create_user_sync(email="other-teacher@uni.edu", is_teacher=True)
    create_user_sync(email="outsider@uni.edu")
    _login(client, "other-teacher@uni.edu")
    course_b_response = client.post(
        "/api/v1/courses", json={"title": "另一门课程", "term": "2026秋"}
    )
    assert course_b_response.status_code == 201, course_b_response.text
    course_b = course_b_response.json()["data"]["id"]
    question_b = _create_published_question(client, course_b, OBJECTIVE_QUESTION)
    assessment_b = _create_assessment(client, course_b, [question_b["id"]])

    _login(client, "outsider@uni.edu")
    for response in (
        client.get(f"/api/v1/assessments/{assessment_b}"),
        client.post(f"/api/v1/assessments/{assessment_b}/attempts"),
        client.get(f"/api/v1/attempts/{attempt_a_id}/result"),
        client.post(f"/api/v1/attempts/{attempt_a_id}/submit"),
    ):
        assert response.status_code == 404, response.text

    _login(client, "ms@uni.edu")
    nonmember_access = client.get(f"/api/v1/assessments/{assessment_b}")
    assert nonmember_access.status_code == 404


def test_attempt_start_and_submission_respect_server_time_and_terminal_state(
    client, monkeypatch
) -> None:
    course_id, _ = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    opens_at = datetime.now(UTC) + timedelta(minutes=1)
    closes_at = datetime.now(UTC) + timedelta(minutes=2)
    assessment_id = _create_assessment(
        client,
        course_id,
        [question["id"]],
        opens_at=opens_at.isoformat(),
        closes_at=closes_at.isoformat(),
    )

    _login(client, "ms@uni.edu")
    before_open = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert before_open.status_code == 409
    assert before_open.json()["error"]["code"] == "ASSESSMENT_NOT_OPEN"

    from app.modules.assessments import router as assessments_router

    class OpenedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return opens_at + timedelta(seconds=1)

    monkeypatch.setattr(assessments_router, "datetime", OpenedClock)
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]
    assessment = client.get(f"/api/v1/assessments/{assessment_id}").json()["data"]
    question_version_id = assessment["items"][0]["question_version_id"]
    saved_answer = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    assert saved_answer.status_code == 200, saved_answer.text

    class ClosedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return closes_at + timedelta(seconds=1)

    monkeypatch.setattr(assessments_router, "datetime", ClosedClock)
    listed_after_deadline = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert listed_after_deadline.status_code == 200, listed_after_deadline.text
    listed_assessment = listed_after_deadline.json()["data"][0]
    assert listed_assessment["availability"] == "closed"
    assert listed_assessment["current_attempt_id"] == attempt_id
    closed_detail = client.get(f"/api/v1/assessments/{assessment_id}")
    assert closed_detail.status_code == 409
    assert closed_detail.json()["error"]["code"] == "ASSESSMENT_CLOSED"
    closed_restart = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert closed_restart.status_code == 409
    assert closed_restart.json()["error"]["code"] == "ASSESSMENT_CLOSED"

    # 响应丢失后的原请求重试只确认先前成功，不在截止后写入新答案。
    answer_ack_retry = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    assert answer_ack_retry.status_code == 200, answer_ack_retry.text
    assert answer_ack_retry.json()["meta"]["idempotent_replay"] is True
    assert answer_ack_retry.json()["data"]["answer_version"] == 2

    # 截止后不能再保存；服务端时间优先于客户端时间戳。
    late_save = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={
            "answer_version": 2,
            "response": {"selected_keys": ["B"]},
            "client_saved_at": (closes_at - timedelta(seconds=1)).isoformat(),
        },
    )
    assert late_save.status_code == 409
    assert late_save.json()["error"]["code"] == "ASSESSMENT_CLOSED"

    # 截止锁冻结答案，不妨碍服务端封存仍进行中的 Attempt。
    late_submit = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert late_submit.status_code == 200, late_submit.text
    assert late_submit.json()["data"]["attempt_id"] == attempt_id
    assert late_submit.json()["data"]["grading_status"] == "graded"
    result = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert result.status_code == 200, result.text
    assert result.json()["data"]["score"] == 5
    assert result.json()["data"]["items"][0]["response"] == {"selected_keys": ["A"]}
    replay = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["idempotent_replay"] is True


def test_formal_purpose_gate_and_after_close_result_policy(client, monkeypatch) -> None:
    course_id, _student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    question_version_id = question["current_version"]["id"]
    closes_at = datetime.now(UTC) + timedelta(minutes=2)
    created = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "正式用途与结果策略回归",
            "question_ids": [question["id"]],
            "purpose": "formal",
            "result_visibility_policy": "after_close",
            "opens_at": datetime.now(UTC).isoformat(),
            "closes_at": closes_at.isoformat(),
            "ai_policy": "disabled",
        },
    )
    assert created.status_code == 201, created.text
    assessment_id = created.json()["data"]["id"]
    blocked = client.post(f"/api/v1/assessments/{assessment_id}/publish")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "ASSESSMENT_PUBLISH_BLOCKED"
    assert "FORMAL_PURPOSE_NOT_APPROVED" in {
        issue["code"] for issue in blocked.json()["error"]["details"]["blocking_issues"]
    }

    reviewer_id = create_user_sync(email="assessment-reviewer@uni.edu", is_teacher=True)
    _login(client, "mt@uni.edu")
    added = client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": reviewer_id, "role": "teacher"},
    )
    assert added.status_code == 201, added.text
    _login(client, "assessment-reviewer@uni.edu")
    approved = client.post(
        f"/api/v1/courses/{course_id}/question-versions/{question_version_id}/purpose/formal",
        json={"decision": "approved", "reason": "另一位课程教师已独立复核正式用途。"},
    )
    assert approved.status_code == 201, approved.text
    published = client.post(f"/api/v1/assessments/{assessment_id}/publish")
    assert published.status_code == 200, published.text

    _login(client, "ms@uni.edu")
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["data"]["attempt_id"]
    saved = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    assert saved.status_code == 200, saved.text
    submitted = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["score"] is None
    early_result = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert early_result.status_code == 403
    assert early_result.json()["error"]["code"] == "ASSESSMENT_RESULT_NOT_RELEASED"

    from app.modules.assessments import router as assessment_router

    class AfterCloseClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return closes_at + timedelta(seconds=1)

    monkeypatch.setattr(assessment_router, "datetime", AfterCloseClock)
    released_result = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert released_result.status_code == 200, released_result.text
    assert released_result.json()["data"]["score"] == 1


def test_formal_subjective_assessment_freezes_approved_rubric(client) -> None:
    from app.db.models import AssessmentItem, RubricVersion

    course_id, _student_id = _setup_course(client)
    question = _create_published_question(client, course_id, ESSAY_QUESTION)
    question_version_id = question["current_version"]["id"]
    created_rubric = client.post(
        f"/api/v1/courses/{course_id}/rubrics",
        json={
            "question_version_id": question_version_id,
            "criteria": [
                {
                    "key": "design-benefit",
                    "description": "说明控制个体差异的作用",
                    "points": 5,
                    "anchors": {"0": "没有相关内容", "5": "准确说明作用"},
                }
            ],
            "max_score": 5,
            "evidence_refs": ESSAY_QUESTION["evidence_ids"],
        },
    )
    assert created_rubric.status_code == 201, created_rubric.text
    rubric_id = created_rubric.json()["data"]["id"]
    reviewer_id = create_user_sync(email="rubric-reviewer@uni.edu", is_teacher=True)
    _login(client, "mt@uni.edu")
    added = client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": reviewer_id, "role": "teacher"},
    )
    assert added.status_code == 201, added.text
    _login(client, "rubric-reviewer@uni.edu")
    approved_rubric = client.post(
        f"/api/v1/rubrics/{rubric_id}/approve",
        json={"reason": "评分标准与题目依据一致，等级锚点可操作。"},
    )
    assert approved_rubric.status_code == 200, approved_rubric.text
    approved_purpose = client.post(
        f"/api/v1/courses/{course_id}/question-versions/{question_version_id}/purpose/formal",
        json={"decision": "approved", "reason": "题目适用于正式测评。"},
    )
    assert approved_purpose.status_code == 201, approved_purpose.text

    _login(client, "mt@uni.edu")
    created_assessment = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "绑定 Rubric 的正式测评",
            "question_ids": [question["id"]],
            "rubric_version_ids": {question_version_id: rubric_id},
            "purpose": "formal",
            "result_visibility_policy": "after_grading",
            "ai_policy": "disabled",
        },
    )
    assert created_assessment.status_code == 201, created_assessment.text
    assessment_id = created_assessment.json()["data"]["id"]
    published = client.post(f"/api/v1/assessments/{assessment_id}/publish")
    assert published.status_code == 200, published.text

    async def _read_rubric_binding():
        async with session_factory() as db:
            item = await db.scalar(
                select(AssessmentItem).where(AssessmentItem.assessment_id == assessment_id)
            )
            rubric = await db.get(RubricVersion, item.rubric_version_id)
            return item.points, rubric.version_no

    assert asyncio.run(_read_rubric_binding()) == (5, 1)


def test_rubric_rejects_unbound_evidence_and_incomplete_anchor_range(client) -> None:
    from app.db.models import RubricVersion

    course_id, _student_id = _setup_course(client)
    question = _create_published_question(client, course_id, ESSAY_QUESTION)
    question_version_id = question["current_version"]["id"]
    base = {
        "question_version_id": question_version_id,
        "criteria": [
            {
                "key": "design-benefit",
                "description": "说明控制个体差异的作用",
                "points": 5,
                "anchors": {"0": "未涉及", "5": "准确说明"},
            }
        ],
        "max_score": 5,
        "evidence_refs": ESSAY_QUESTION["evidence_ids"],
    }

    foreign_evidence = client.post(
        f"/api/v1/courses/{course_id}/rubrics",
        json={**base, "evidence_refs": ["unrelated-evidence-id"]},
    )
    assert foreign_evidence.status_code == 422, foreign_evidence.text
    assert foreign_evidence.json()["error"]["code"] == "RUBRIC_EVIDENCE_INVALID"

    missing_zero_anchor = client.post(
        f"/api/v1/courses/{course_id}/rubrics",
        json={
            **base,
            "criteria": [
                {
                    **base["criteria"][0],
                    "anchors": {"1": "部分说明", "5": "准确说明"},
                }
            ],
        },
    )
    assert missing_zero_anchor.status_code == 422, missing_zero_anchor.text
    assert missing_zero_anchor.json()["error"]["code"] == "RUBRIC_ANCHORS_INVALID"

    async def _count_rubrics() -> int:
        from sqlalchemy import func, select

        from app.db.session import session_factory

        async with session_factory() as db:
            result = await db.execute(
                select(func.count())
                .select_from(RubricVersion)
                .where(RubricVersion.question_version_id == question_version_id)
            )
            return int(result.scalar_one())

    assert asyncio.run(_count_rubrics()) == 0


def test_submit_failure_rolls_back_attempt_and_learning_side_effects(client, monkeypatch) -> None:
    from app.db.models import Attempt
    from app.modules.learning_events import service as learning_event_service

    course_id, _student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    assessment_id = _create_assessment(client, course_id, [question["id"]])
    _login(client, "ms@uni.edu")
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = started.json()["data"]["attempt_id"]
    question_version_id = question["current_version"]["id"]
    saved = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["B"]}},
    )
    assert saved.status_code == 200, saved.text

    original_append = learning_event_service.append_event

    async def append_then_fail(*args, **kwargs):
        await original_append(*args, **kwargs)
        raise RuntimeError("simulated failure before submit transaction commit")

    monkeypatch.setattr(learning_event_service, "append_event", append_then_fail)
    with pytest.raises(RuntimeError, match="simulated failure"):
        client.post(f"/api/v1/attempts/{attempt_id}/submit")

    async def _read_after_failure():
        async with session_factory() as db:
            attempt = await db.get(Attempt, attempt_id)
            return attempt.status, await db.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.source_ref == attempt_id)
            )

    assert asyncio.run(_read_after_failure()) == ("in_progress", 0)
    monkeypatch.setattr(learning_event_service, "append_event", original_append)
    retried = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["grading_status"] == "graded"
    assert _count_attempt_events(attempt_id) == 1


def test_manual_result_release_is_versioned_and_student_can_reopen_result(client) -> None:
    course_id, _student_id = _setup_course(client)
    question = _create_published_question(client, course_id, OBJECTIVE_QUESTION)
    question_version_id = question["current_version"]["id"]
    created = client.post(
        f"/api/v1/courses/{course_id}/assessments",
        json={
            "title": "教师手动发布结果回归",
            "question_ids": [question["id"]],
            "purpose": "practice",
            "result_visibility_policy": "manual_release",
            "ai_policy": "disabled",
        },
    )
    assert created.status_code == 201, created.text
    assessment_id = created.json()["data"]["id"]
    published = client.post(f"/api/v1/assessments/{assessment_id}/publish")
    assert published.status_code == 200, published.text

    _login(client, "ms@uni.edu")
    started = client.post(f"/api/v1/assessments/{assessment_id}/attempts")
    attempt_id = started.json()["data"]["attempt_id"]
    saved = client.put(
        f"/api/v1/attempts/{attempt_id}/answers/{question_version_id}",
        json={"answer_version": 1, "response": {"selected_keys": ["A"]}},
    )
    assert saved.status_code == 200, saved.text
    submitted = client.post(f"/api/v1/attempts/{attempt_id}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["score"] is None
    hidden = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert hidden.status_code == 403

    _login(client, "mt@uni.edu")
    released = client.post(
        f"/api/v1/assessments/{assessment_id}/release-results",
        json={"expected_version": published.json()["data"]["version"]},
    )
    assert released.status_code == 200, released.text
    replay = client.post(
        f"/api/v1/assessments/{assessment_id}/release-results",
        json={"expected_version": published.json()["data"]["version"]},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["meta"]["idempotent_replay"] is True

    _login(client, "ms@uni.edu")
    listed = client.get(f"/api/v1/courses/{course_id}/assessments")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"][0]["latest_completed_attempt_id"] == attempt_id
    visible = client.get(f"/api/v1/attempts/{attempt_id}/result")
    assert visible.status_code == 200, visible.text
    assert visible.json()["data"]["score"] == 1

