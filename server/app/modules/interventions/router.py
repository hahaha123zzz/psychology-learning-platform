from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.outbox import append_event
from app.core.response import ok
from app.db.models import (
    ClassMember,
    CourseClass,
    CourseMember,
    Intervention,
    InterventionRun,
    LearningEvent,
    LearningEvidence,
    LearningQualification,
    Notification,
    TeacherAssignment,
    TeacherObservation,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.interventions import schemas

router = APIRouter()


def _out(item: Intervention) -> dict:
    return schemas.InterventionOut.model_validate(item, from_attributes=True).model_dump(
        mode="json"
    )


def _run_out(item: InterventionRun) -> dict:
    return schemas.InterventionRunOut.model_validate(item, from_attributes=True).model_dump(
        mode="json"
    )


def _observation_out(item: TeacherObservation) -> dict:
    result = schemas.TeacherObservationOut.model_validate(item, from_attributes=True).model_dump(
        mode="json"
    )
    result["review_decision"] = item.review_decision
    return result


async def _observation_sources_are_current(
    db: AsyncSession, item: TeacherObservation, *, lock: bool = False
) -> bool:
    references = list(dict.fromkeys(item.evidence_refs or []))
    if not references:
        return False
    query = select(LearningEvidence.id).where(
        LearningEvidence.id.in_(references),
        LearningEvidence.user_id == item.student_id,
        LearningEvidence.course_id == item.course_id,
        LearningEvidence.quality_status == "valid",
    )
    if lock:
        query = query.with_for_update()
    found = list((await db.execute(query)).scalars())
    return len(found) == len(references)


async def _teacher_has_class_scope(
    db: AsyncSession,
    *,
    course_id: str,
    class_id: str,
    teacher_id: str,
    write: bool,
) -> bool:
    assignment_query = (
        select(TeacherAssignment.id)
        .join(CourseClass, CourseClass.id == TeacherAssignment.class_id)
        .where(
            TeacherAssignment.class_id == class_id,
            TeacherAssignment.teacher_id == teacher_id,
            TeacherAssignment.status == "active",
            CourseClass.course_id == course_id,
            CourseClass.status == "active",
        )
    )
    if write:
        assignment_query = assignment_query.where(TeacherAssignment.assignment_role == "lead")
    return (await db.scalar(assignment_query.limit(1))) is not None


async def _student_is_active_in_class(
    db: AsyncSession, *, course_id: str, class_id: str, student_id: str
) -> bool:
    result = await db.scalar(
        select(ClassMember.id)
        .join(CourseClass, CourseClass.id == ClassMember.class_id)
        .where(
            ClassMember.class_id == class_id,
            ClassMember.user_id == student_id,
            ClassMember.status == "active",
            CourseClass.course_id == course_id,
            CourseClass.status == "active",
        )
        .limit(1)
    )
    return result is not None


async def _observation_outputs(db: AsyncSession, items: list[TeacherObservation]) -> list[dict]:
    evidence_ids = {
        evidence_id
        for item in items
        for evidence_id in [*(item.evidence_refs or []), *(item.verification_evidence_ids or [])]
    }
    if not evidence_ids:
        return [_observation_out(item) for item in items]
    rows = await db.execute(
        select(LearningEvidence.id, LearningEvidence.quality_status).where(
            LearningEvidence.id.in_(evidence_ids)
        )
    )
    statuses = dict(rows.all())
    outputs: list[dict] = []
    for item in items:
        result = _observation_out(item)
        source_ids = set(item.evidence_refs or [])
        verified_ids = set(item.verification_evidence_ids or [])
        result["source_evidence_status"] = (
            "unavailable"
            if not source_ids
            else "valid"
            if all(statuses.get(evidence_id) == "valid" for evidence_id in source_ids)
            else "invalidated"
        )
        if item.verification_status == "qualified" and (
            not verified_ids
            or any(statuses.get(evidence_id) != "valid" for evidence_id in verified_ids)
        ):
            result["verification_status"] = "invalidated"
        outputs.append(result)
    return outputs


async def _get_for_course(
    db: AsyncSession,
    *,
    course_id: str,
    intervention_id: str,
    user: User,
    roles: set[str],
) -> Intervention:
    await require_course_role(course_id, user, db, roles=roles)
    item = await db.scalar(
        select(Intervention).where(
            Intervention.id == intervention_id,
            Intervention.course_id == course_id,
        )
    )
    if item is None:
        raise ApiError(status_code=404, code="INTERVENTION_NOT_FOUND", message="干预活动不存在")
    return item


@router.post("/courses/{course_id}/interventions", response_model=None)
async def create_intervention(
    course_id: str,
    body: schemas.InterventionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    if body.class_id is not None:
        class_row = await db.scalar(
            select(CourseClass).where(
                CourseClass.id == body.class_id,
                CourseClass.course_id == course_id,
                CourseClass.status == "active",
            )
        )
        if class_row is None:
            raise ApiError(
                status_code=409,
                code="INTERVENTION_CLASS_INVALID",
                message="班级不属于当前课程或已归档",
            )
    item = Intervention(
        course_id=course_id,
        class_id=body.class_id,
        created_by=user.id,
        title=body.title,
        activity_type=body.activity_type,
        target_snapshot=body.target_snapshot,
        plan=body.plan,
    )
    db.add(item)
    await db.flush()
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="intervention.created",
        resource_type="intervention",
        resource_id=item.id,
        course_id=course_id,
        detail={"status": item.status, "activity_type": item.activity_type},
    )
    await append_event(
        db,
        event_type="intervention.created",
        payload={"intervention_id": item.id, "course_id": course_id},
        producer="interventions.router",
        trace_id=item.id,
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item), status_code=201)


@router.get("/courses/{course_id}/interventions", response_model=None)
async def list_interventions(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    rows = await db.execute(
        select(Intervention)
        .where(Intervention.course_id == course_id)
        .order_by(Intervention.created_at.desc(), Intervention.id.desc())
    )
    return ok(request, [_out(item) for item in rows.scalars()], has_more=False)


@router.post(
    "/courses/{course_id}/interventions/{intervention_id}/dispatch",
    response_model=None,
)
async def dispatch_intervention_runs(
    course_id: str,
    intervention_id: str,
    body: schemas.InterventionDispatch,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _get_for_course(
        db, course_id=course_id, intervention_id=intervention_id, user=user, roles={"teacher"}
    )
    if item.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="干预活动版本已变化"
        )
    user_ids = list(dict.fromkeys(body.user_ids))
    members = list(
        (
            await db.execute(
                select(CourseMember.user_id).where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id.in_(user_ids),
                    CourseMember.role == "student",
                    CourseMember.status == "active",
                )
            )
        ).scalars()
    )
    missing = sorted(set(user_ids) - set(members))
    if missing:
        raise ApiError(
            status_code=409,
            code="INTERVENTION_TARGET_INVALID",
            message="干预目标必须是当前课程的有效学生",
            details={"user_ids": missing},
        )
    if item.status not in ("scheduled", "active"):
        raise ApiError(
            status_code=409,
            code="INTERVENTION_INVALID_STATE",
            message="只有已排程或进行中的干预可以派发",
        )
    existing = list(
        (
            await db.execute(
                select(InterventionRun).where(
                    InterventionRun.intervention_id == item.id,
                    InterventionRun.user_id.in_(user_ids),
                )
            )
        ).scalars()
    )
    existing_by_user = {run.user_id: run for run in existing}
    created: list[InterventionRun] = []
    for user_id in user_ids:
        if user_id in existing_by_user:
            continue
        run = InterventionRun(
            intervention_id=item.id,
            course_id=course_id,
            user_id=user_id,
        )
        db.add(run)
        db.add(
            Notification(
                user_id=user_id,
                kind="intervention.dispatched",
                title="收到新的学习干预",
                body=f"教师已为你安排“{item.title}”，请在学习空间查看。",
                payload={"course_id": course_id, "intervention_id": item.id},
            )
        )
        created.append(run)
    if created:
        item.version += 1
        await db.flush()
        await course_service.write_audit(
            db,
            actor_id=user.id,
            action="intervention.dispatched",
            resource_type="intervention",
            resource_id=item.id,
            course_id=course_id,
            detail={"user_count": len(created)},
        )
        await append_event(
            db,
            event_type="intervention.dispatched",
            payload={"intervention_id": item.id, "run_ids": [run.id for run in created]},
            producer="interventions.router",
            trace_id=item.id,
        )
    await db.commit()
    await db.refresh(item)
    all_runs = list(
        (
            await db.execute(
                select(InterventionRun)
                .where(InterventionRun.intervention_id == item.id)
                .order_by(InterventionRun.created_at.asc(), InterventionRun.id.asc())
            )
        ).scalars()
    )
    return ok(
        request,
        {"intervention": _out(item), "runs": [_run_out(run) for run in all_runs]},
        status_code=201 if created else 200,
        idempotent_replay=not bool(created),
    )


@router.get(
    "/courses/{course_id}/interventions/{intervention_id}/runs",
    response_model=None,
)
async def list_intervention_runs(
    course_id: str,
    intervention_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _get_for_course(
        db,
        course_id=course_id,
        intervention_id=intervention_id,
        user=user,
        roles={"teacher", "assistant"},
    )
    rows = await db.execute(
        select(InterventionRun)
        .where(InterventionRun.intervention_id == item.id)
        .order_by(InterventionRun.created_at.asc(), InterventionRun.id.asc())
    )
    return ok(request, [_run_out(run) for run in rows.scalars()], has_more=False)


@router.get(
    "/courses/{course_id}/interventions/{intervention_id}/effect",
    response_model=None,
)
async def intervention_effect_read_model(
    course_id: str,
    intervention_id: str,
    request: Request,
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """按已授权班级和半开 UTC 窗口提供有小样本保护的描述性投影。"""
    item = await _get_for_course(
        db,
        course_id=course_id,
        intervention_id=intervention_id,
        user=user,
        roles={"teacher", "assistant"},
    )
    if item.class_id is None or not await _teacher_has_class_scope(
        db,
        course_id=course_id,
        class_id=item.class_id,
        teacher_id=user.id,
        write=False,
    ):
        raise ApiError(
            status_code=404,
            code="INTERVENTION_NOT_FOUND",
            message="干预活动不存在或当前教师没有该班级权限",
        )
    now = datetime.now(UTC)
    start, end = _intervention_window(start_at, end_at, now=now)
    runs = list(
        (
            await db.execute(
                select(InterventionRun)
                .where(
                    InterventionRun.intervention_id == item.id,
                    InterventionRun.created_at >= start,
                    InterventionRun.created_at < end,
                )
                .order_by(InterventionRun.created_at.asc(), InterventionRun.id.asc())
            )
        ).scalars()
    )
    completed = [run for run in runs if run.status == "completed"]
    student_count = len({run.user_id for run in runs})
    effect_metrics = _effect_count_metrics(
        student_count=student_count,
        run_count=len(runs),
        completed_count=len(completed),
    )
    immediate_ids: set[str] = set()
    delayed_ids: set[str] = set()
    run_for_evidence: dict[str, InterventionRun] = {}
    for run in completed:
        outcome = run.outcome if isinstance(run.outcome, dict) else {}
        for key, destination in (
            ("immediate_recheck_evidence_ids", immediate_ids),
            ("delayed_recheck_evidence_ids", delayed_ids),
        ):
            references = outcome.get(key)
            if not isinstance(references, list):
                continue
            for evidence_id in references:
                if isinstance(evidence_id, str) and len(evidence_id) == 26:
                    destination.add(evidence_id)
                    run_for_evidence.setdefault(evidence_id, run)

    # 同一条证据不能同时充当即时与延迟复测。
    delayed_ids.difference_update(immediate_ids)
    evidence_ids = immediate_ids | delayed_ids
    evidence_rows = []
    if evidence_ids:
        evidence_rows = list(
            (
                await db.execute(
                    select(LearningEvidence).where(
                        LearningEvidence.id.in_(evidence_ids),
                        LearningEvidence.course_id == course_id,
                        LearningEvidence.quality_status == "valid",
                        LearningEvidence.independence_status == "independent",
                        LearningEvidence.created_at >= start,
                        LearningEvidence.created_at < end,
                    )
                )
            ).scalars()
        )
    immediate = _summarize_recheck_evidence(
        evidence_rows,
        evidence_ids=immediate_ids,
        run_for_evidence=run_for_evidence,
        window="immediate",
    )
    delayed = _summarize_recheck_evidence(
        evidence_rows,
        evidence_ids=delayed_ids,
        run_for_evidence=run_for_evidence,
        window="delayed",
    )
    immediate_by_user = immediate.pop("_accuracy_by_user")
    delayed_by_user = delayed.pop("_accuracy_by_user")
    measured = immediate["status"] == "measured" and delayed["status"] == "measured"
    small_sample = student_count < 5
    immediate_suppressed = immediate["student_count"] < 5
    delayed_suppressed = delayed["student_count"] < 5
    immediate = _suppress_recheck_small_sample(immediate)
    delayed = _suppress_recheck_small_sample(delayed)
    paired_students = set(immediate_by_user) & set(delayed_by_user)
    can_compare = (
        measured
        and not small_sample
        and not immediate_suppressed
        and not delayed_suppressed
        and len(paired_students) >= 5
    )
    descriptive_change = (
        round(
            sum(delayed_by_user[item] - immediate_by_user[item] for item in paired_students)
            / len(paired_students),
            4,
        )
        if can_compare
        else None
    )
    return ok(
        request,
        {
            "intervention_id": item.id,
            "course_id": course_id,
            "class_id": item.class_id,
            "time_window": {
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
                "bounds": "[start_at,end_at)",
            },
            **effect_metrics,
            "immediate_recheck": immediate,
            "delayed_recheck": delayed,
            "effect_status": "measured" if can_compare else "not_measured",
            "paired_student_count": len(paired_students) if can_compare else None,
            "descriptive_change": descriptive_change,
            "causal_claim": False,
            "interpretation": (
                "样本不足，已隐藏人数、计数、比例和复测差异。"
                if small_sample or immediate_suppressed or delayed_suppressed
                else "复测差异仅为描述性统计，不表示干预造成因果效果。"
                if can_compare
                else "缺少两窗口内各至少两项合格、独立且跨情境的复测证据；保持 not_measured。"
            ),
        },
    )


def _summarize_recheck_evidence(
    rows: list[LearningEvidence],
    *,
    evidence_ids: set[str],
    run_for_evidence: dict[str, InterventionRun],
    window: str,
) -> dict[str, Any]:
    eligible: dict[str, LearningEvidence] = {}
    for evidence in rows:
        run = run_for_evidence.get(evidence.id)
        if run is None or evidence.user_id != run.user_id:
            continue
        if evidence.quality_status != "valid" or evidence.independence_status != "independent":
            continue
        if run.completed_at is None or evidence.context_key is None:
            continue
        completed_at = _as_utc(run.completed_at)
        measured_at = _as_utc(evidence.created_at)
        elapsed = measured_at - completed_at
        if window == "immediate" and not (timedelta(0) <= elapsed < timedelta(days=7)):
            continue
        if window == "delayed" and not (timedelta(days=7) <= elapsed <= timedelta(days=30)):
            continue
        if evidence.id in evidence_ids:
            eligible[evidence.id] = evidence
    contexts = {item.context_key for item in eligible.values() if item.context_key}
    by_user: dict[str, list[bool]] = {}
    for item in eligible.values():
        by_user.setdefault(item.user_id, []).append(item.correct)
    accuracy_by_user = {
        user_id: sum(1 for correct in values if correct) / len(values)
        for user_id, values in by_user.items()
    }
    measured = len(eligible) >= 2 and len(contexts) >= 2
    values = list(eligible.values())
    return {
        "status": "measured" if measured else "not_measured",
        "evidence_count": len(values),
        "student_count": len({item.user_id for item in values}),
        "context_count": len(contexts),
        "accuracy_rate": (
            round(sum(1 for item in values if item.correct) / len(values), 4) if measured else None
        ),
        "_accuracy_by_user": accuracy_by_user,
    }


def _suppress_recheck_small_sample(summary: dict[str, Any]) -> dict[str, Any]:
    if summary["student_count"] >= 5:
        return summary
    return {
        **summary,
        "status": "suppressed_small_sample",
        "evidence_count": None,
        "student_count": None,
        "context_count": None,
        "accuracy_rate": None,
    }


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _intervention_window(
    start_at: datetime | None,
    end_at: datetime | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    end = end_at or now or datetime.now(UTC)
    start = start_at or (_as_utc(end) - timedelta(days=30))
    if (start_at is not None and (start.tzinfo is None or start.utcoffset() is None)) or (
        end_at is not None and (end.tzinfo is None or end.utcoffset() is None)
    ):
        raise ApiError(
            status_code=422,
            code="TIME_WINDOW_TIMEZONE_REQUIRED",
            message="start_at 和 end_at 必须包含时区",
        )
    start = _as_utc(start)
    end = _as_utc(end)
    if start >= end:
        raise ApiError(
            status_code=422,
            code="TIME_WINDOW_INVALID",
            message="start_at 必须早于 end_at",
        )
    if end - start > timedelta(days=90):
        raise ApiError(
            status_code=422,
            code="TIME_WINDOW_TOO_WIDE",
            message="统计时间范围不能超过 90 天",
        )
    return start, end


def _effect_count_metrics(
    *, student_count: int, run_count: int, completed_count: int
) -> dict[str, Any]:
    suppressed = student_count < 5
    return {
        "sample_status": "suppressed_small_sample" if suppressed else "available",
        "student_count": None if suppressed else student_count,
        "run_count": None if suppressed else run_count,
        "completed_count": None if suppressed else completed_count,
        "completion_rate": (
            None if suppressed or run_count == 0 else round(completed_count / run_count, 4)
        ),
    }


@router.post("/courses/{course_id}/observations", response_model=None)
async def create_teacher_observation(
    course_id: str,
    body: schemas.TeacherObservationCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    if idempotency_key is None or not idempotency_key.strip() or len(idempotency_key) > 128:
        raise ApiError(
            status_code=422,
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="创建教师观察必须提供有效的 Idempotency-Key",
        )
    has_scope = await _teacher_has_class_scope(
        db, course_id=course_id, class_id=body.class_id, teacher_id=user.id, write=True
    )
    if not has_scope:
        raise ApiError(
            status_code=404,
            code="OBSERVATION_CLASS_NOT_FOUND",
            message="班级不存在或当前教师没有该班级的主责范围",
        )
    student = await db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == body.student_id,
            CourseMember.role == "student",
            CourseMember.status == "active",
        )
    )
    if student is None:
        raise ApiError(
            status_code=404,
            code="OBSERVATION_STUDENT_NOT_FOUND",
            message="观察对象不是当前课程的有效学生",
        )
    if not await _student_is_active_in_class(
        db, course_id=course_id, class_id=body.class_id, student_id=body.student_id
    ):
        raise ApiError(
            status_code=404,
            code="OBSERVATION_STUDENT_NOT_FOUND",
            message="观察对象不是当前班级的有效学生",
        )
    request_payload = {"course_id": course_id, **body.model_dump(mode="json")}
    request_hash = course_service.canonical_request_hash(request_payload)
    endpoint = f"POST:/api/v1/courses/{course_id}/observations"
    previous = await course_service.find_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=endpoint,
        request_hash=request_hash,
    )
    if previous is not None:
        return ok(
            request,
            previous["body"]["data"],
            status_code=previous["status"],
            idempotent_replay=True,
        )
    evidence_refs = list(dict.fromkeys(body.evidence_refs))
    evidence_rows = list(
        (
            await db.execute(
                select(LearningEvidence.id).where(
                    LearningEvidence.id.in_(evidence_refs),
                    LearningEvidence.user_id == body.student_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.quality_status == "valid",
                )
            )
        ).scalars()
    )
    if len(evidence_rows) != len(evidence_refs):
        raise ApiError(
            status_code=422,
            code="OBSERVATION_EVIDENCE_UNAVAILABLE",
            message="观察必须引用当前课程该学生可用的有效学习证据",
        )
    item = TeacherObservation(
        course_id=course_id,
        class_id=body.class_id,
        student_id=body.student_id,
        teacher_id=user.id,
        observation_type=body.observation_type,
        note=body.note,
        evidence_refs=evidence_refs,
    )
    db.add(item)
    await db.flush()
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="teacher.observation.created",
        resource_type="teacher_observation",
        resource_id=item.id,
        course_id=course_id,
        detail={"student_id": body.student_id, "observation_type": body.observation_type},
    )
    await append_event(
        db,
        event_type="teacher.observation.created",
        payload={"course_id": course_id, "observation_id": item.id},
        producer="interventions.router",
        trace_id=item.id,
    )
    response_data = (await _observation_outputs(db, [item]))[0]
    try:
        await course_service.save_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
            status=201,
            body={"data": response_data},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
        )
        if previous is None:
            raise
        return ok(
            request,
            previous["body"]["data"],
            status_code=previous["status"],
            idempotent_replay=True,
        )
    await db.refresh(item)
    return ok(request, response_data, status_code=201)


@router.get("/courses/{course_id}/observations", response_model=None)
async def list_teacher_observations(
    course_id: str,
    request: Request,
    status: str | None = Query(default=None, pattern="^(pending|qualified|rejected)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    class_ids = list(
        (
            await db.execute(
                select(TeacherAssignment.class_id)
                .join(CourseClass, CourseClass.id == TeacherAssignment.class_id)
                .where(
                    TeacherAssignment.teacher_id == user.id,
                    TeacherAssignment.status == "active",
                    CourseClass.course_id == course_id,
                    CourseClass.status == "active",
                )
            )
        ).scalars()
    )
    query = select(TeacherObservation).where(
        TeacherObservation.course_id == course_id,
        TeacherObservation.class_id.in_(class_ids) if class_ids else False,
    )
    if status is not None:
        query = query.where(TeacherObservation.qualification_status == status)
    rows = await db.execute(
        query.order_by(TeacherObservation.created_at.desc(), TeacherObservation.id.desc()).limit(
            200
        )
    )
    return ok(request, await _observation_outputs(db, list(rows.scalars())), has_more=False)


@router.post("/courses/{course_id}/observations/{observation_id}/review", response_model=None)
async def review_teacher_observation(
    course_id: str,
    observation_id: str,
    body: schemas.TeacherObservationReview,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    item = await db.scalar(
        select(TeacherObservation)
        .where(
            TeacherObservation.id == observation_id,
            TeacherObservation.course_id == course_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ApiError(status_code=404, code="OBSERVATION_NOT_FOUND", message="教师观察不存在")
    if item.class_id is None or not await _teacher_has_class_scope(
        db, course_id=course_id, class_id=item.class_id, teacher_id=user.id, write=True
    ):
        raise ApiError(status_code=404, code="OBSERVATION_NOT_FOUND", message="教师观察不存在")
    if not await _student_is_active_in_class(
        db, course_id=course_id, class_id=item.class_id, student_id=item.student_id
    ):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_STUDENT_SCOPE_CHANGED",
            message="学生已不在原班级",
        )
    if (
        item.reviewed_at is not None
        and item.reviewed_by == user.id
        and item.review_decision == ("rejected" if body.decision == "rejected" else "accepted")
        and item.review_reason == body.reason
    ):
        return ok(
            request,
            (await _observation_outputs(db, [item]))[0],
            idempotent_replay=True,
        )
    if item.reviewed_at is not None:
        raise ApiError(
            status_code=409,
            code="OBSERVATION_ALREADY_REVIEWED",
            message="教师观察已复核；不同决定不能覆盖历史复核",
            details={"actual_version": item.version},
        )
    if item.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="教师观察已变化，请刷新后再审核",
            details={"actual_version": item.version},
        )
    if item.qualification_status != "pending":
        raise ApiError(
            status_code=409,
            code="OBSERVATION_NOT_REVIEWABLE",
            message="当前教师观察状态不允许复核",
        )
    if item.review_decision != "pending":
        raise ApiError(
            status_code=409,
            code="OBSERVATION_ALREADY_REVIEWED",
            message="教师观察已复核；不同决定不能覆盖历史复核",
            details={"actual_version": item.version},
        )
    if body.decision == "qualified" and not await _observation_sources_are_current(
        db, item, lock=True
    ):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_EVIDENCE_INVALIDATED",
            message="原观察依据已失效；请先检查当前学习证据，再决定是否继续",
        )
    # 教师接受异议只代表同意复核，不是学习证据资格化。
    # 只有独立再验证活动进入 LearningQualification 后，观察才能转为 qualified。
    if body.decision == "rejected":
        item.qualification_status = "rejected"
        item.verification_status = "rejected"
    item.review_decision = "accepted" if body.decision == "qualified" else "rejected"
    item.algorithm_version = "teacher-review-v2-pending-revalidation"
    item.reviewed_by = user.id
    item.review_reason = body.reason
    item.reviewed_at = datetime.now(UTC)
    item.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="teacher.observation.reviewed",
        resource_type="teacher_observation",
        resource_id=item.id,
        course_id=course_id,
        detail={"decision": body.decision, "student_id": item.student_id},
    )
    await append_event(
        db,
        event_type="teacher.observation.reviewed",
        payload={
            "course_id": course_id,
            "observation_id": item.id,
            "review_decision": body.decision,
            "qualification_status": item.qualification_status,
        },
        producer="interventions.router",
        trace_id=item.id,
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, (await _observation_outputs(db, [item]))[0])


@router.post("/courses/{course_id}/observations/{observation_id}/revalidate", response_model=None)
async def revalidate_teacher_observation(
    course_id: str,
    observation_id: str,
    body: schemas.TeacherObservationRevalidation,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    item = await db.scalar(
        select(TeacherObservation)
        .where(
            TeacherObservation.id == observation_id,
            TeacherObservation.course_id == course_id,
        )
        .with_for_update()
    )
    if (
        item is None
        or item.class_id is None
        or not await _teacher_has_class_scope(
            db,
            course_id=course_id,
            class_id=item.class_id if item is not None and item.class_id else "",
            teacher_id=user.id,
            write=True,
        )
    ):
        raise ApiError(status_code=404, code="OBSERVATION_NOT_FOUND", message="教师观察不存在")
    if not await _student_is_active_in_class(
        db, course_id=course_id, class_id=item.class_id, student_id=item.student_id
    ):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_STUDENT_SCOPE_CHANGED",
            message="学生已不在原班级",
        )

    if (
        item.verification_status == "qualified"
        and item.verification_event_id == body.learning_event_id
    ):
        data = (await _observation_outputs(db, [item]))[0]
        return ok(request, data, idempotent_replay=True)
    if item.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="教师观察已变化，请刷新后再复核",
            details={"actual_version": item.version},
        )
    if item.review_decision != "accepted" or item.verification_status != "pending":
        raise ApiError(
            status_code=409,
            code="OBSERVATION_NOT_REVALIDATABLE",
            message="观察须先通过教师复核且尚未完成再验证",
        )
    if not await _observation_sources_are_current(db, item, lock=True):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_EVIDENCE_INVALIDATED",
            message="原观察依据已失效，不能继续按旧依据再验证",
        )

    event = await db.scalar(
        select(LearningEvent)
        .where(
            LearningEvent.id == body.learning_event_id,
            LearningEvent.user_id == item.student_id,
            LearningEvent.course_id == course_id,
        )
        .with_for_update()
    )
    if event is None:
        raise ApiError(
            status_code=404,
            code="OBSERVATION_REVALIDATION_EVENT_NOT_FOUND",
            message="再验证学习事件不存在或不属于当前学生与课程",
        )
    already_used = await db.scalar(
        select(TeacherObservation.id)
        .where(
            TeacherObservation.verification_event_id == event.id,
            TeacherObservation.id != item.id,
        )
        .limit(1)
    )
    if already_used is not None:
        raise ApiError(
            status_code=409,
            code="OBSERVATION_REVALIDATION_EVENT_USED",
            message="该学习事件已用于另一条观察的再验证",
        )
    if event.occurred_at <= item.created_at:
        raise ApiError(
            status_code=409,
            code="OBSERVATION_REVALIDATION_NOT_INDEPENDENT",
            message="再验证必须来自观察创建后的独立学习活动",
        )
    qualification = await db.scalar(
        select(LearningQualification).where(
            LearningQualification.event_id == event.id,
            LearningQualification.user_id == item.student_id,
            LearningQualification.course_id == course_id,
        )
    )
    if (
        event.qualification_status != "qualified"
        or event.qualified_at is None
        or event.qualified_at <= item.created_at
        or qualification is None
        or qualification.status != "qualified"
        or not isinstance(qualification.evidence_ids, list)
        or not qualification.evidence_ids
        or qualification.evaluated_at <= item.created_at
    ):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_REVALIDATION_NOT_QUALIFIED",
            message="再验证活动尚未通过现有学习资格化流程",
        )
    evidence_rows = list(
        (
            await db.execute(
                select(LearningEvidence).where(
                    LearningEvidence.id.in_(qualification.evidence_ids),
                    LearningEvidence.user_id == item.student_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.quality_status == "valid",
                    LearningEvidence.independence_status == "independent",
                    LearningEvidence.created_at > item.created_at,
                )
            )
        ).scalars()
    )
    original_rows = list(
        (
            await db.execute(
                select(LearningEvidence).where(
                    LearningEvidence.id.in_(item.evidence_refs),
                    LearningEvidence.user_id == item.student_id,
                    LearningEvidence.course_id == course_id,
                )
            )
        ).scalars()
    )
    original_attempt_ids = {row.attempt_id for row in original_rows if row.attempt_id}
    new_attempt_ids = {row.attempt_id for row in evidence_rows if row.attempt_id}
    new_contexts = {row.context_key for row in evidence_rows}
    original_contexts = {row.context_key for row in original_rows if row.context_key}
    original_points = {row.knowledge_point for row in original_rows}
    new_points = {row.knowledge_point for row in evidence_rows}
    if (
        len(set(qualification.evidence_ids)) != len(qualification.evidence_ids)
        or len(evidence_rows) != len(set(qualification.evidence_ids))
        or set(qualification.evidence_ids).intersection(item.evidence_refs or [])
        or event.source_ref in original_attempt_ids
        or not new_attempt_ids.isdisjoint(original_attempt_ids)
        or None in new_contexts
        or not new_contexts.isdisjoint(original_contexts)
        or not new_points
        or not new_points.issubset(original_points)
    ):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_REVALIDATION_NOT_INDEPENDENT",
            message="再验证证据必须有效、独立且来自不同学习情境",
        )

    evidence_ids = sorted(row.id for row in evidence_rows)
    item.qualification_status = "qualified"
    item.verification_status = "qualified"
    item.verification_event_id = event.id
    item.verification_qualification_id = qualification.id
    item.verification_evidence_ids = evidence_ids
    item.verification_algorithm_version = "teacher-observation-revalidation-v1"
    item.verification_reason = "existing_independent_learning_qualification"
    item.verified_at = datetime.now(UTC)
    item.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="teacher.observation.revalidated",
        resource_type="teacher_observation",
        resource_id=item.id,
        course_id=course_id,
        detail={
            "class_id": item.class_id,
            "student_id": item.student_id,
            "learning_event_id": event.id,
            "qualification_id": qualification.id,
            "evidence_ids": evidence_ids,
        },
    )
    await append_event(
        db,
        event_type="teacher.observation.revalidated",
        payload={
            "course_id": course_id,
            "class_id": item.class_id,
            "observation_id": item.id,
            "learning_event_id": event.id,
            "qualification_id": qualification.id,
        },
        producer="interventions.router",
        trace_id=item.id,
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, (await _observation_outputs(db, [item]))[0])


@router.get(
    "/courses/{course_id}/observations/{observation_id}/revalidation-candidates",
    response_model=None,
)
async def list_teacher_observation_revalidation_candidates(
    course_id: str,
    observation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    item = await db.scalar(
        select(TeacherObservation).where(
            TeacherObservation.id == observation_id,
            TeacherObservation.course_id == course_id,
        )
    )
    if (
        item is None
        or item.class_id is None
        or not await _teacher_has_class_scope(
            db,
            course_id=course_id,
            class_id=item.class_id if item is not None and item.class_id else "",
            teacher_id=user.id,
            write=False,
        )
    ):
        raise ApiError(status_code=404, code="OBSERVATION_NOT_FOUND", message="教师观察不存在")
    if not await _student_is_active_in_class(
        db, course_id=course_id, class_id=item.class_id, student_id=item.student_id
    ):
        raise ApiError(
            status_code=409,
            code="OBSERVATION_STUDENT_SCOPE_CHANGED",
            message="学生已不在原班级",
        )
    if (
        item.review_decision != "accepted"
        or item.verification_status != "pending"
        or not await _observation_sources_are_current(db, item)
    ):
        return ok(request, [], has_more=False)

    source_rows = list(
        (
            await db.execute(
                select(LearningEvidence).where(
                    LearningEvidence.id.in_(item.evidence_refs),
                    LearningEvidence.user_id == item.student_id,
                    LearningEvidence.course_id == course_id,
                    LearningEvidence.quality_status == "valid",
                )
            )
        ).scalars()
    )
    source_attempt_ids = {row.attempt_id for row in source_rows if row.attempt_id}
    source_contexts = {row.context_key for row in source_rows if row.context_key}
    source_points = {row.knowledge_point for row in source_rows}
    qualifications = await db.execute(
        select(LearningQualification, LearningEvent)
        .join(LearningEvent, LearningEvent.id == LearningQualification.event_id)
        .where(
            LearningQualification.user_id == item.student_id,
            LearningQualification.course_id == course_id,
            LearningQualification.status == "qualified",
            LearningQualification.evaluated_at > item.created_at,
            LearningEvent.qualification_status == "qualified",
            LearningEvent.qualified_at > item.created_at,
            LearningEvent.occurred_at > item.created_at,
        )
        .order_by(LearningQualification.evaluated_at.desc(), LearningQualification.id.desc())
        .limit(100)
    )
    event_rows = list(qualifications.all())
    event_ids = [event.id for _qualification, event in event_rows]
    used_ids = (
        set(
            (
                await db.execute(
                    select(TeacherObservation.verification_event_id).where(
                        TeacherObservation.verification_event_id.in_(event_ids),
                        TeacherObservation.id != item.id,
                    )
                )
            ).scalars()
        )
        if event_ids
        else set()
    )

    candidates: list[dict] = []
    for qualification, event in event_rows:
        evidence_ids = qualification.evidence_ids
        if (
            event.id in used_ids
            or event.source_ref in source_attempt_ids
            or not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(set(evidence_ids)) != len(evidence_ids)
            or set(evidence_ids).intersection(item.evidence_refs or [])
        ):
            continue
        evidence_rows = list(
            (
                await db.execute(
                    select(LearningEvidence).where(
                        LearningEvidence.id.in_(evidence_ids),
                        LearningEvidence.user_id == item.student_id,
                        LearningEvidence.course_id == course_id,
                        LearningEvidence.quality_status == "valid",
                        LearningEvidence.independence_status == "independent",
                        LearningEvidence.created_at > item.created_at,
                    )
                )
            ).scalars()
        )
        contexts = {row.context_key for row in evidence_rows}
        attempts = {row.attempt_id for row in evidence_rows if row.attempt_id}
        points = {row.knowledge_point for row in evidence_rows}
        if (
            len(evidence_rows) != len(evidence_ids)
            or None in contexts
            or not contexts.isdisjoint(source_contexts)
            or not attempts.isdisjoint(source_attempt_ids)
            or not points
            or not points.issubset(source_points)
        ):
            continue
        candidates.append(
            schemas.TeacherObservationRevalidationCandidate(
                learning_event_id=event.id,
                qualification_id=qualification.id,
                event_type=event.event_type,
                source_type=event.source_type,
                occurred_at=event.occurred_at,
                qualified_at=event.qualified_at,
                evidence_count=len(evidence_ids),
                evidence_ids=sorted(evidence_ids),
            ).model_dump(mode="json")
        )
    return ok(request, candidates, has_more=False)


async def _get_student_run(db: AsyncSession, run_id: str, user: User) -> InterventionRun:
    run = await db.scalar(select(InterventionRun).where(InterventionRun.id == run_id))
    if run is None or run.user_id != user.id:
        raise ApiError(status_code=404, code="INTERVENTION_RUN_NOT_FOUND", message="活动执行不存在")
    await require_course_role(run.course_id, user, db, roles={"student"})
    return run


@router.get("/student/intervention-runs", response_model=None)
async def list_student_intervention_runs(
    request: Request,
    course_id: str | None = Query(default=None, min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    rows = await db.execute(
        select(InterventionRun)
        .where(
            InterventionRun.user_id == user.id,
            InterventionRun.status.in_(("scheduled", "in_progress", "paused")),
            *([InterventionRun.course_id == course_id] if course_id else []),
        )
        .order_by(InterventionRun.updated_at.desc(), InterventionRun.id.desc())
        .limit(50)
    )
    visible: list[dict] = []
    for run in rows.scalars():
        try:
            await require_course_role(run.course_id, user, db, roles={"student"})
        except ApiError:
            continue
        visible.append(_run_out(run))
    return ok(request, visible, has_more=False)


@router.post("/student/intervention-runs/{run_id}/start", response_model=None)
async def start_student_intervention_run(
    run_id: str,
    body: schemas.InterventionTransition,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    run = await _get_student_run(db, run_id, user)
    if run.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="活动执行版本已变化"
        )
    if run.status == "in_progress":
        return ok(request, _run_out(run))
    if run.status != "scheduled":
        raise ApiError(
            status_code=409,
            code="INTERVENTION_RUN_INVALID_STATE",
            message="当前活动不能开始",
        )
    run.status = "in_progress"
    run.started_at = datetime.now(UTC)
    run.version += 1
    await db.commit()
    await db.refresh(run)
    return ok(request, _run_out(run))


@router.post("/student/intervention-runs/{run_id}/complete", response_model=None)
async def complete_student_intervention_run(
    run_id: str,
    body: schemas.InterventionRunComplete,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    run = await _get_student_run(db, run_id, user)
    if run.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="活动执行版本已变化"
        )
    if run.status == "completed":
        return ok(request, _run_out(run))
    if run.status != "in_progress":
        raise ApiError(
            status_code=409,
            code="INTERVENTION_RUN_INVALID_STATE",
            message="只有进行中的活动可以完成",
        )
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    run.outcome = body.outcome
    run.version += 1
    await db.commit()
    await db.refresh(run)
    return ok(request, _run_out(run))


@router.post("/courses/{course_id}/interventions/{intervention_id}/schedule", response_model=None)
async def schedule_intervention(
    course_id: str,
    intervention_id: str,
    body: schemas.InterventionSchedule,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _get_for_course(
        db, course_id=course_id, intervention_id=intervention_id, user=user, roles={"teacher"}
    )
    if item.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="干预活动版本已变化"
        )
    if item.status == "scheduled":
        return ok(request, _out(item))
    if item.status != "draft":
        raise ApiError(
            status_code=409, code="INTERVENTION_INVALID_STATE", message="只有草稿可以排程"
        )
    if body.scheduled_at.tzinfo is None:
        body.scheduled_at = body.scheduled_at.replace(tzinfo=UTC)
    if body.scheduled_at < datetime.now(UTC):
        raise ApiError(
            status_code=422, code="INTERVENTION_TIME_INVALID", message="排程时间必须晚于当前时间"
        )
    item.status = "scheduled"
    item.scheduled_at = body.scheduled_at
    item.approved_by = user.id
    item.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="intervention.scheduled",
        resource_type="intervention",
        resource_id=item.id,
        course_id=course_id,
    )
    await append_event(
        db,
        event_type="intervention.scheduled",
        payload={"intervention_id": item.id, "course_id": course_id},
        producer="interventions.router",
        trace_id=item.id,
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))


@router.post("/courses/{course_id}/interventions/{intervention_id}/start", response_model=None)
async def start_intervention(
    course_id: str,
    intervention_id: str,
    body: schemas.InterventionTransition,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _get_for_course(
        db, course_id=course_id, intervention_id=intervention_id, user=user, roles={"teacher"}
    )
    if item.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="干预活动版本已变化"
        )
    if item.status == "active":
        return ok(request, _out(item))
    if item.status != "scheduled":
        raise ApiError(
            status_code=409, code="INTERVENTION_INVALID_STATE", message="只有已排程干预可以开始"
        )
    item.status = "active"
    item.started_at = datetime.now(UTC)
    item.version += 1
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))


@router.post("/courses/{course_id}/interventions/{intervention_id}/complete", response_model=None)
async def complete_intervention(
    course_id: str,
    intervention_id: str,
    body: schemas.InterventionTransition,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _get_for_course(
        db, course_id=course_id, intervention_id=intervention_id, user=user, roles={"teacher"}
    )
    if item.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="干预活动版本已变化"
        )
    if item.status == "completed":
        return ok(request, _out(item))
    if item.status not in ("scheduled", "active"):
        raise ApiError(
            status_code=409, code="INTERVENTION_INVALID_STATE", message="当前状态不能完成干预"
        )
    item.status = "completed"
    item.completed_at = datetime.now(UTC)
    item.version += 1
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))


@router.post("/courses/{course_id}/interventions/{intervention_id}/evaluate", response_model=None)
async def evaluate_intervention(
    course_id: str,
    intervention_id: str,
    body: schemas.InterventionEvaluate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await _get_for_course(
        db, course_id=course_id, intervention_id=intervention_id, user=user, roles={"teacher"}
    )
    if item.version != body.version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="干预活动版本已变化"
        )
    if item.status == "evaluated":
        return ok(request, _out(item))
    if item.status != "completed":
        raise ApiError(
            status_code=409, code="INTERVENTION_INVALID_STATE", message="只有已完成干预可以评估"
        )
    item.status = "evaluated"
    item.evaluated_at = datetime.now(UTC)
    item.outcome = body.outcome
    item.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="intervention.evaluated",
        resource_type="intervention",
        resource_id=item.id,
        course_id=course_id,
        detail={"outcome_keys": sorted(body.outcome)},
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))
