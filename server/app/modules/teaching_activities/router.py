from copy import deepcopy
from datetime import UTC, datetime
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
    CourseRelease,
    CourseReleaseAssignment,
    Intervention,
    LearningEvidence,
    TeacherAnnotation,
    TeacherAssignment,
    TeacherTimelineEvent,
    TeachingActivity,
    TeachingActivityRun,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.teaching_activities import schemas, service

router = APIRouter()


def _now() -> datetime:
    return service.utc_now()


def _utc(value: datetime) -> datetime:
    return service.as_utc(value)


def _time_window(start_at: datetime | None, end_at: datetime | None) -> tuple[datetime, datetime]:
    return service.time_window(start_at, end_at)


def _dump(model: Any, schema: type[schemas.BaseModel]) -> dict[str, Any]:
    return schema.model_validate(model, from_attributes=True).model_dump(mode="json")


def _require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip() or len(value) > 128:
        raise ApiError(
            status_code=422,
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="写操作必须提供有效的 Idempotency-Key",
        )
    return value.strip()


async def _replay(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
    request: Request,
) -> Response | None:
    prior = await course_service.find_idempotent_response(
        db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=request_hash,
    )
    if prior is None:
        return None
    return ok(
        request,
        prior["body"]["data"],
        status_code=prior["status"],
        idempotent_replay=True,
    )


async def _save_response(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
    status: int,
    data: dict[str, Any],
) -> None:
    await course_service.save_idempotent_response(
        db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=request_hash,
        status=status,
        body={"data": data},
    )


async def _scope(
    db: AsyncSession,
    *,
    course_id: str,
    class_id: str,
    teacher_id: str,
    write: bool,
) -> CourseClass:
    course_role = await db.scalar(
        select(CourseMember.id).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == teacher_id,
            CourseMember.role.in_(("teacher", "assistant")),
            CourseMember.status == "active",
        )
    )
    query = (
        select(CourseClass)
        .join(TeacherAssignment, TeacherAssignment.class_id == CourseClass.id)
        .where(
            CourseClass.id == class_id,
            CourseClass.course_id == course_id,
            CourseClass.status == "active",
            TeacherAssignment.teacher_id == teacher_id,
            TeacherAssignment.status == "active",
        )
    )
    if write:
        query = query.where(TeacherAssignment.assignment_role == "lead")
    result = await db.scalar(query.limit(1)) if course_role is not None else None
    if result is None:
        raise ApiError(
            status_code=404,
            code="CLASS_NOT_FOUND",
            message="班级不存在或当前教师没有该班级权限",
        )
    return result


async def _record_event(
    db: AsyncSession,
    *,
    course_id: str,
    class_id: str,
    phase: str,
    event_type: str,
    occurred_at: datetime,
    subject_type: str,
    subject_id: str,
    source_type: str,
    source_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        TeacherTimelineEvent(
            course_id=course_id,
            class_id=class_id,
            phase=phase,
            event_type=event_type,
            occurred_at=occurred_at,
            subject_type=subject_type,
            subject_id=subject_id,
            source_type=source_type,
            source_id=source_id,
            payload=payload or {},
        )
    )


async def _audit(
    db: AsyncSession,
    *,
    actor: User,
    course_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
) -> None:
    await course_service.write_audit(
        db,
        actor_id=actor.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        course_id=course_id,
    )


async def _commit_idempotent(
    db: AsyncSession,
    *,
    request: Request,
    key: str,
    user: User,
    endpoint: str,
    request_hash: str,
    status: int,
    data: dict[str, Any],
) -> Response:
    try:
        await _save_response(
            db,
            key=key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
            status=status,
            data=data,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        response = await _replay(
            db,
            key=key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
            request=request,
        )
        if response is None:
            raise
        return response
    return ok(request, data, status_code=status)


@router.get("/courses/{course_id}/teaching-activities", response_model=None)
async def list_teaching_activities(
    course_id: str,
    request: Request,
    status: str | None = Query(default=None, pattern="^(draft|ready|published|deprecated)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    query = select(TeachingActivity).where(TeachingActivity.course_id == course_id)
    if status is not None:
        query = query.where(TeachingActivity.status == status)
    rows = await db.execute(
        query.order_by(
            TeachingActivity.activity_key.asc(),
            TeachingActivity.version_no.desc(),
            TeachingActivity.id.asc(),
        )
    )
    return ok(
        request,
        [_dump(item, schemas.TeachingActivityOut) for item in rows.scalars()],
        has_more=False,
    )


@router.post("/courses/{course_id}/teaching-activities", response_model=None)
async def create_teaching_activity(
    course_id: str,
    body: schemas.TeachingActivityCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    key = _require_idempotency_key(idempotency_key)
    endpoint = f"POST:/api/v1/courses/{course_id}/teaching-activities"
    request_hash = course_service.canonical_request_hash(
        {"course_id": course_id, **body.model_dump(mode="json")}
    )
    replay = await _replay(
        db, key=key, user_id=user.id, endpoint=endpoint, request_hash=request_hash, request=request
    )
    if replay is not None:
        return replay
    exists = await db.scalar(
        select(TeachingActivity.id).where(
            TeachingActivity.course_id == course_id,
            TeachingActivity.activity_key == body.activity_key,
            TeachingActivity.version_no == 1,
        )
    )
    if exists is not None:
        raise ApiError(status_code=409, code="ACTIVITY_KEY_EXISTS", message="活动标识已存在")
    item = TeachingActivity(
        course_id=course_id,
        activity_key=body.activity_key,
        version_no=1,
        title=body.title.strip(),
        activity_type=body.activity_type,
        manifest=body.manifest,
        status="draft",
        created_by=user.id,
    )
    db.add(item)
    await db.flush()
    await _audit(
        db,
        actor=user,
        course_id=course_id,
        action="teaching_activity.created",
        resource_type="teaching_activity",
        resource_id=item.id,
    )
    await append_event(
        db,
        event_type="teaching_activity.created",
        payload={"course_id": course_id, "activity_id": item.id, "activity_key": item.activity_key},
        producer="teaching_activities.router",
        trace_id=item.id,
    )
    return await _commit_idempotent(
        db,
        request=request,
        key=key,
        user=user,
        endpoint=endpoint,
        request_hash=request_hash,
        status=201,
        data=_dump(item, schemas.TeachingActivityOut),
    )


@router.patch("/courses/{course_id}/teaching-activities/{activity_version_id}", response_model=None)
async def update_teaching_activity(
    course_id: str,
    activity_version_id: str,
    body: schemas.TeachingActivityUpdate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    key = _require_idempotency_key(idempotency_key)
    endpoint = f"PATCH:/api/v1/courses/{course_id}/teaching-activities/{activity_version_id}"
    request_hash = course_service.canonical_request_hash(
        {
            "course_id": course_id,
            "activity_version_id": activity_version_id,
            **body.model_dump(mode="json"),
        }
    )
    item = await db.scalar(
        select(TeachingActivity)
        .where(TeachingActivity.id == activity_version_id, TeachingActivity.course_id == course_id)
        .with_for_update()
    )
    if item is None:
        raise ApiError(
            status_code=404, code="TEACHING_ACTIVITY_NOT_FOUND", message="教学活动版本不存在"
        )
    if item.version != body.expected_version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="教学活动版本已变化"
        )
    if item.status != "draft":
        raise ApiError(
            status_code=409,
            code="TEACHING_ACTIVITY_NOT_EDITABLE",
            message="只有草稿活动可生成新版本",
        )
    next_no = (
        int(
            await db.scalar(
                select(TeachingActivity.version_no)
                .where(
                    TeachingActivity.course_id == course_id,
                    TeachingActivity.activity_key == item.activity_key,
                )
                .order_by(TeachingActivity.version_no.desc())
                .limit(1)
            )
            or item.version_no
        )
        + 1
    )
    status = body.status or "draft"
    new_item = TeachingActivity(
        course_id=course_id,
        activity_key=item.activity_key,
        version_no=next_no,
        title=body.title.strip() if body.title is not None else item.title,
        activity_type=body.activity_type or item.activity_type,
        manifest=body.manifest if body.manifest is not None else deepcopy(item.manifest),
        status=status,
        created_by=user.id,
        published_by=user.id if status == "ready" else None,
        published_at=_now() if status == "ready" else None,
        supersedes_id=item.id,
    )
    item.status = "deprecated"
    item.version += 1
    db.add(new_item)
    await db.flush()
    await _audit(
        db,
        actor=user,
        course_id=course_id,
        action="teaching_activity.version_created",
        resource_type="teaching_activity",
        resource_id=new_item.id,
    )
    await append_event(
        db,
        event_type="teaching_activity.version_created",
        payload={"course_id": course_id, "activity_id": new_item.id, "supersedes_id": item.id},
        producer="teaching_activities.router",
        trace_id=new_item.id,
    )
    return await _commit_idempotent(
        db,
        request=request,
        key=key,
        user=user,
        endpoint=endpoint,
        request_hash=request_hash,
        status=200,
        data=_dump(new_item, schemas.TeachingActivityOut),
    )


@router.post("/courses/{course_id}/classes/{class_id}/teaching-activity-runs", response_model=None)
async def create_teaching_activity_run(
    course_id: str,
    class_id: str,
    body: schemas.TeachingActivityRunCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await _scope(db, course_id=course_id, class_id=class_id, teacher_id=user.id, write=True)
    key = _require_idempotency_key(idempotency_key)
    endpoint = f"POST:/api/v1/courses/{course_id}/classes/{class_id}/teaching-activity-runs"
    request_hash = course_service.canonical_request_hash(
        {"course_id": course_id, "class_id": class_id, **body.model_dump(mode="json")}
    )
    replay = await _replay(
        db, key=key, user_id=user.id, endpoint=endpoint, request_hash=request_hash, request=request
    )
    if replay is not None:
        return replay
    activity = await db.scalar(
        select(TeachingActivity).where(
            TeachingActivity.id == body.activity_version_id,
            TeachingActivity.course_id == course_id,
            TeachingActivity.status.in_(("ready", "published")),
        )
    )
    if activity is None:
        raise ApiError(
            status_code=409, code="TEACHING_ACTIVITY_NOT_READY", message="活动版本尚未就绪"
        )
    members = list(
        (
            await db.execute(
                select(ClassMember.user_id)
                .where(ClassMember.class_id == class_id, ClassMember.status == "active")
                .with_for_update()
            )
        ).scalars()
    )
    active_ids = set(members)
    targets = sorted(body.target_user_ids if body.target_user_ids is not None else active_ids)
    if not targets or not set(targets).issubset(active_ids):
        raise ApiError(
            status_code=409,
            code="TEACHING_ACTIVITY_TARGET_INVALID",
            message="目标必须是当前班级的有效学生",
        )
    assignment = await db.scalar(
        select(CourseReleaseAssignment)
        .where(
            CourseReleaseAssignment.course_id == course_id,
            CourseReleaseAssignment.class_id == class_id,
            CourseReleaseAssignment.status == "active",
        )
        .with_for_update()
    )
    if assignment is None:
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_ASSIGNMENT_REQUIRED",
            message="创建活动运行前必须为班级指派已发布课程版本",
        )
    release = await db.scalar(
        select(CourseRelease)
        .where(
            CourseRelease.id == assignment.course_release_id,
            CourseRelease.course_id == course_id,
            CourseRelease.status == "published",
        )
        .with_for_update()
    )
    if release is None:
        raise ApiError(
            status_code=409, code="COURSE_RELEASE_NOT_AVAILABLE", message="当前课程版本不可运行"
        )
    target_snapshot, target_digest = service.target_roster_snapshot(targets)
    run = TeachingActivityRun(
        activity_version_id=activity.id,
        course_id=course_id,
        class_id=class_id,
        course_release_assignment_id=assignment.id,
        course_release_id=release.id,
        target_snapshot=target_snapshot,
        run_snapshot=service.build_run_snapshot(
            activity=activity,
            release=release,
            assignment=assignment,
            created_by=user.id,
            target_sha256=target_digest,
        ),
        status="ready",
        scheduled_at=body.scheduled_at.astimezone(UTC),
        created_by=user.id,
        idempotency_key=key,
        request_sha256=request_hash,
    )
    db.add(run)
    await db.flush()
    await _record_event(
        db,
        course_id=course_id,
        class_id=class_id,
        phase="planned",
        event_type="activity_run_planned",
        occurred_at=run.scheduled_at,
        subject_type="activity_run",
        subject_id=run.id,
        source_type="activity_run",
        source_id=run.id,
        payload={"activity_key": activity.activity_key, "title": activity.title},
    )
    await _audit(
        db,
        actor=user,
        course_id=course_id,
        action="teaching_activity_run.created",
        resource_type="teaching_activity_run",
        resource_id=run.id,
    )
    await append_event(
        db,
        event_type="teaching_activity_run.created",
        payload={"course_id": course_id, "class_id": class_id, "run_id": run.id},
        producer="teaching_activities.router",
        trace_id=run.id,
    )
    return await _commit_idempotent(
        db,
        request=request,
        key=key,
        user=user,
        endpoint=endpoint,
        request_hash=request_hash,
        status=201,
        data=_dump(run, schemas.TeachingActivityRunOut),
    )


@router.get("/courses/{course_id}/classes/{class_id}/teaching-activity-runs", response_model=None)
async def list_teaching_activity_runs(
    course_id: str,
    class_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await _scope(db, course_id=course_id, class_id=class_id, teacher_id=user.id, write=False)
    rows = await db.execute(
        select(TeachingActivityRun)
        .where(TeachingActivityRun.course_id == course_id, TeachingActivityRun.class_id == class_id)
        .order_by(TeachingActivityRun.created_at.desc(), TeachingActivityRun.id.desc())
        .limit(100)
    )
    return ok(
        request,
        [_dump(item, schemas.TeachingActivityRunOut) for item in rows.scalars()],
        has_more=False,
    )


@router.post(
    "/courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run_id}/actions",
    response_model=None,
)
async def act_on_teaching_activity_run(
    course_id: str,
    class_id: str,
    run_id: str,
    body: schemas.TeachingActivityRunAction,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await _scope(db, course_id=course_id, class_id=class_id, teacher_id=user.id, write=True)
    key = _require_idempotency_key(idempotency_key)
    endpoint = (
        f"POST:/api/v1/courses/{course_id}/classes/{class_id}/"
        f"teaching-activity-runs/{run_id}/actions"
    )
    request_hash = course_service.canonical_request_hash(
        {
            "course_id": course_id,
            "class_id": class_id,
            "run_id": run_id,
            **body.model_dump(mode="json"),
        }
    )
    replay = await _replay(
        db, key=key, user_id=user.id, endpoint=endpoint, request_hash=request_hash, request=request
    )
    if replay is not None:
        return replay
    run = await db.scalar(
        select(TeachingActivityRun)
        .where(
            TeachingActivityRun.id == run_id,
            TeachingActivityRun.course_id == course_id,
            TeachingActivityRun.class_id == class_id,
        )
        .with_for_update()
    )
    if run is None:
        raise ApiError(
            status_code=404, code="TEACHING_ACTIVITY_RUN_NOT_FOUND", message="活动运行不存在"
        )
    if run.version != body.expected_version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="活动运行版本已变化"
        )
    next_status = service.run_transition(body.action, run.status)
    if next_status is None:
        raise ApiError(
            status_code=409,
            code="TEACHING_ACTIVITY_RUN_INVALID_STATE",
            message="当前状态不允许执行该活动操作",
            details={"status": run.status, "action": body.action},
        )
    now = _now()
    run.status = next_status
    if body.action == "start":
        run.started_at = now
    if body.action == "complete":
        run.finished_at = now
    if body.action == "cancel":
        run.finished_at = now
    run.version += 1
    await db.flush()
    await _record_event(
        db,
        course_id=course_id,
        class_id=class_id,
        phase="actual",
        event_type=f"activity_run_{body.action}_v{run.version}",
        occurred_at=now,
        subject_type="activity_run",
        subject_id=run.id,
        source_type="activity_run",
        source_id=run.id,
        payload={"action": body.action},
    )
    await _audit(
        db,
        actor=user,
        course_id=course_id,
        action=f"teaching_activity_run.{body.action}",
        resource_type="teaching_activity_run",
        resource_id=run.id,
    )
    await append_event(
        db,
        event_type=f"teaching_activity_run.{body.action}",
        payload={
            "course_id": course_id,
            "class_id": class_id,
            "run_id": run.id,
            "status": run.status,
        },
        producer="teaching_activities.router",
        trace_id=run.id,
    )
    # Flush/commit paths can leave server-generated timestamp attributes expired.
    # Refresh the persisted row before serializing it so async attribute access does not
    # trigger an implicit lazy load outside SQLAlchemy's greenlet context.
    await db.refresh(run)
    return await _commit_idempotent(
        db,
        request=request,
        key=key,
        user=user,
        endpoint=endpoint,
        request_hash=request_hash,
        status=200,
        data=_dump(run, schemas.TeachingActivityRunOut),
    )


@router.get("/courses/{course_id}/classes/{class_id}/timeline", response_model=None)
async def get_teacher_timeline(
    course_id: str,
    class_id: str,
    request: Request,
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await _scope(db, course_id=course_id, class_id=class_id, teacher_id=user.id, write=False)
    start, end = _time_window(start_at, end_at)
    rows = await db.execute(
        select(TeacherTimelineEvent)
        .where(
            TeacherTimelineEvent.course_id == course_id,
            TeacherTimelineEvent.class_id == class_id,
            TeacherTimelineEvent.occurred_at >= start,
            TeacherTimelineEvent.occurred_at < end,
        )
        .order_by(TeacherTimelineEvent.occurred_at.asc(), TeacherTimelineEvent.id.asc())
    )
    events = [
        {
            "id": item.id,
            "phase": item.phase,
            "event_type": item.event_type,
            "occurred_at": _utc(item.occurred_at).isoformat(),
            "subject_type": item.subject_type,
            "subject_id": item.subject_id,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "delay_seconds": (
                max(0, int((_utc(item.created_at) - _utc(item.occurred_at)).total_seconds()))
                if item.phase == "actual"
                else None
            ),
        }
        for item in rows.scalars()
    ]
    interventions = await db.execute(
        select(Intervention)
        .where(Intervention.course_id == course_id, Intervention.class_id == class_id)
        .order_by(Intervention.id.asc())
    )
    for intervention in interventions.scalars():
        persisted_times = (
            ("planned", "intervention_planned", intervention.scheduled_at),
            ("actual", "intervention_started", intervention.started_at),
            ("actual", "intervention_completed", intervention.completed_at),
            ("actual", "intervention_evaluated", intervention.evaluated_at),
        )
        for phase, event_type, occurred_at in persisted_times:
            if occurred_at is None:
                continue
            occurred = _utc(occurred_at)
            if not (start <= occurred < end):
                continue
            events.append(
                {
                    "id": f"{intervention.id}:{event_type}",
                    "phase": phase,
                    "event_type": event_type,
                    "occurred_at": occurred.isoformat(),
                    "subject_type": "intervention",
                    "subject_id": intervention.id,
                    "source_type": "intervention",
                    "source_id": intervention.id,
                    "delay_seconds": max(
                        0,
                        int((_utc(intervention.updated_at) - occurred).total_seconds()),
                    )
                    if phase == "actual"
                    else None,
                }
            )
    events.sort(key=lambda event: (event["occurred_at"], event["id"]))
    return ok(
        request,
        {
            "class_id": class_id,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "bounds": "[start_at,end_at)",
            "events": events,
        },
        has_more=False,
    )


async def _validate_annotation_target(
    db: AsyncSession,
    *,
    course_id: str,
    class_id: str,
    target_type: str,
    target_id: str,
) -> None:
    if target_type == "activity":
        exists = await db.scalar(
            select(TeachingActivity.id).where(
                TeachingActivity.id == target_id, TeachingActivity.course_id == course_id
            )
        )
    elif target_type == "evidence":
        exists = await db.scalar(
            select(LearningEvidence.id)
            .join(ClassMember, ClassMember.user_id == LearningEvidence.user_id)
            .where(
                LearningEvidence.id == target_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.quality_status == "valid",
                ClassMember.class_id == class_id,
                ClassMember.status == "active",
            )
        )
    elif target_type == "intervention":
        exists = await db.scalar(
            select(Intervention.id).where(
                Intervention.id == target_id,
                Intervention.course_id == course_id,
                Intervention.class_id == class_id,
            )
        )
    else:
        assignment = await db.scalar(
            select(CourseReleaseAssignment).where(
                CourseReleaseAssignment.course_id == course_id,
                CourseReleaseAssignment.class_id == class_id,
                CourseReleaseAssignment.status == "active",
            )
        )
        release = (
            await db.get(CourseRelease, assignment.course_release_id)
            if assignment is not None
            else None
        )
        manifest = (
            release.manifest if release is not None and isinstance(release.manifest, dict) else {}
        )
        domain = manifest.get("domain_pack", {})
        points = domain.get("knowledge_points", []) if isinstance(domain, dict) else []
        exists = (
            target_id
            if any(isinstance(point, dict) and point.get("key") == target_id for point in points)
            else None
        )
    if exists is None:
        raise ApiError(
            status_code=404, code="ANNOTATION_TARGET_NOT_FOUND", message="注释目标不存在或不可用"
        )


@router.post("/courses/{course_id}/classes/{class_id}/teacher-annotations", response_model=None)
async def create_teacher_annotation(
    course_id: str,
    class_id: str,
    body: schemas.TeacherAnnotationCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await _scope(db, course_id=course_id, class_id=class_id, teacher_id=user.id, write=True)
    key = _require_idempotency_key(idempotency_key)
    endpoint = f"POST:/api/v1/courses/{course_id}/classes/{class_id}/teacher-annotations"
    request_hash = course_service.canonical_request_hash(
        {"course_id": course_id, "class_id": class_id, **body.model_dump(mode="json")}
    )
    replay = await _replay(
        db, key=key, user_id=user.id, endpoint=endpoint, request_hash=request_hash, request=request
    )
    if replay is not None:
        return replay
    await _validate_annotation_target(
        db,
        course_id=course_id,
        class_id=class_id,
        target_type=body.target_type,
        target_id=body.target_id,
    )
    service.validate_annotation_visibility(body.visibility, body.status)
    now = _now()
    item = TeacherAnnotation(
        course_id=course_id,
        class_id=class_id,
        target_type=body.target_type,
        target_id=body.target_id,
        visibility=body.visibility,
        status=body.status,
        annotation=body.annotation.strip(),
        created_by=user.id,
        published_at=now if body.status == "published" else None,
    )
    db.add(item)
    await db.flush()
    await _record_event(
        db,
        course_id=course_id,
        class_id=class_id,
        phase="actual",
        event_type="teacher_annotation_created",
        occurred_at=now,
        subject_type="annotation",
        subject_id=item.id,
        source_type="teacher_annotation",
        source_id=item.id,
    )
    await _audit(
        db,
        actor=user,
        course_id=course_id,
        action="teacher_annotation.created",
        resource_type="teacher_annotation",
        resource_id=item.id,
    )
    await append_event(
        db,
        event_type="teacher_annotation.created",
        payload={
            "course_id": course_id,
            "class_id": class_id,
            "annotation_id": item.id,
            "status": item.status,
        },
        producer="teaching_activities.router",
        trace_id=item.id,
    )
    return await _commit_idempotent(
        db,
        request=request,
        key=key,
        user=user,
        endpoint=endpoint,
        request_hash=request_hash,
        status=201,
        data=_dump(item, schemas.TeacherAnnotationOut),
    )


@router.patch("/courses/{course_id}/teacher-annotations/{annotation_id}", response_model=None)
async def update_teacher_annotation(
    course_id: str,
    annotation_id: str,
    body: schemas.TeacherAnnotationUpdate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    key = _require_idempotency_key(idempotency_key)
    endpoint = f"PATCH:/api/v1/courses/{course_id}/teacher-annotations/{annotation_id}"
    request_hash = course_service.canonical_request_hash(
        {"course_id": course_id, "annotation_id": annotation_id, **body.model_dump(mode="json")}
    )
    replay = await _replay(
        db, key=key, user_id=user.id, endpoint=endpoint, request_hash=request_hash, request=request
    )
    if replay is not None:
        return replay
    item = await db.scalar(
        select(TeacherAnnotation)
        .where(TeacherAnnotation.id == annotation_id, TeacherAnnotation.course_id == course_id)
        .with_for_update()
    )
    if item is None:
        raise ApiError(
            status_code=404, code="TEACHER_ANNOTATION_NOT_FOUND", message="教师注释不存在"
        )
    await _scope(db, course_id=course_id, class_id=item.class_id, teacher_id=user.id, write=True)
    replay = await _replay(
        db, key=key, user_id=user.id, endpoint=endpoint, request_hash=request_hash, request=request
    )
    if replay is not None:
        return replay
    if item.version != body.expected_version:
        raise ApiError(
            status_code=409, code="RESOURCE_VERSION_CONFLICT", message="教师注释版本已变化"
        )
    if item.status == "archived":
        raise ApiError(
            status_code=409, code="TEACHER_ANNOTATION_ARCHIVED", message="已归档注释不能再修改"
        )
    next_status = body.status or item.status
    next_visibility = body.visibility or item.visibility
    service.validate_annotation_visibility(next_visibility, next_status)
    if body.annotation is not None:
        item.annotation = body.annotation.strip()
    if body.visibility is not None:
        item.visibility = body.visibility
    if body.status is not None:
        item.status = body.status
        if body.status == "published" and item.published_at is None:
            item.published_at = _now()
        if body.status == "archived":
            item.archived_at = _now()
    item.version += 1
    await db.flush()
    await _record_event(
        db,
        course_id=course_id,
        class_id=item.class_id,
        phase="actual",
        event_type=f"teacher_annotation_{item.status}_v{item.version}",
        occurred_at=_now(),
        subject_type="annotation",
        subject_id=item.id,
        source_type="teacher_annotation",
        source_id=item.id,
        payload={"status": item.status},
    )
    await _audit(
        db,
        actor=user,
        course_id=course_id,
        action=f"teacher_annotation.{item.status}",
        resource_type="teacher_annotation",
        resource_id=item.id,
    )
    await append_event(
        db,
        event_type=f"teacher_annotation.{item.status}",
        payload={"course_id": course_id, "class_id": item.class_id, "annotation_id": item.id},
        producer="teaching_activities.router",
        trace_id=item.id,
    )
    return await _commit_idempotent(
        db,
        request=request,
        key=key,
        user=user,
        endpoint=endpoint,
        request_hash=request_hash,
        status=200,
        data=_dump(item, schemas.TeacherAnnotationOut),
    )
