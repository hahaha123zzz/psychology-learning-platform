from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import LearningEvent, User
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, has_course_scope, require_course_role
from app.modules.learning_events import schemas, service

router = APIRouter()


@router.post("/learning-events", response_model=None)
async def append_learning_event(
    body: schemas.LearningEventCreate | schemas.ResourceOpenedEventCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if isinstance(body, schemas.ResourceOpenedEventCreate):
        await require_course_role(body.course_id, user, db, roles={"student"})
        payload = await service.derive_resource_open_event(
            db,
            user_id=user.id,
            course_id=body.course_id,
            pointer_id=body.evidence_pointer_id,
        )
        event, replay = await service.append_event(
            db,
            user_id=user.id,
            event_key=body.event_key,
            course_id=body.course_id,
            event_type="RESOURCE_OPENED",
            source_type="resource",
            source_ref=body.evidence_pointer_id,
            payload=payload,
            occurred_at=None,
            qualification_status="rejected",
            qualification_reason="resource_usage_non_evidence",
        )
        await db.commit()
        await db.refresh(event)
        data = schemas.LearningEventOut.model_validate(
            event, from_attributes=True
        ).model_dump(mode="json")
        return ok(request, data, status_code=200 if replay else 201, idempotent_replay=replay)

    if not await has_course_scope(user, body.course_id, db):
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    if body.event_type == "tutor_responded":
        raise ApiError(
            status_code=403,
            code="LEARNING_EVENT_SERVER_OWNED",
            message="Tutor 回合事件由服务端在状态转换时记录",
        )
    event, replay = await service.append_event(
        db,
        user_id=user.id,
        event_key=body.event_key,
        course_id=body.course_id,
        event_type=body.event_type,
        source_type=body.source_type,
        source_ref=body.source_ref,
        payload=body.payload,
        occurred_at=body.occurred_at,
    )
    await db.commit()
    await db.refresh(event)
    data = schemas.LearningEventOut.model_validate(
        event, from_attributes=True
    ).model_dump(mode="json")
    return ok(request, data, status_code=200 if replay else 201, idempotent_replay=replay)


@router.get("/me/learning-events", response_model=None)
async def list_learning_events(
    request: Request,
    course_id: str = Query(min_length=26, max_length=26),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"student"})
    result = await db.execute(
        select(LearningEvent)
        .where(LearningEvent.user_id == user.id, LearningEvent.course_id == course_id)
        .order_by(LearningEvent.occurred_at.desc(), LearningEvent.id.desc())
        .limit(limit)
    )
    items = [
        schemas.LearningEventOut.model_validate(item, from_attributes=True).model_dump(mode="json")
        for item in result.scalars()
    ]
    return ok(request, items, has_more=False)
