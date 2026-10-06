from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import CourseRelease, TeachingAssetVersion, User
from app.db.session import get_db_session
from app.modules.assessments.policy import ensure_ai_support_available
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.teaching_assets import schemas, service

router = APIRouter()


def _out(item: TeachingAssetVersion) -> dict:
    return schemas.TeachingAssetOut(
        id=item.id,
        course_id=item.course_id,
        release_id=item.release_id,
        asset_key=item.asset_key,
        version_no=item.version_no,
        template=item.template,
        status=item.status,
        content=item.content,
        fallback_text=item.fallback_text,
        evidence_refs=item.evidence_refs,
        allowed_actions=item.allowed_actions,
        version=item.version,
        created_by=item.created_by,
        published_by=item.published_by,
        published_at=item.published_at.isoformat() if item.published_at else None,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    ).model_dump(mode="json")


@router.get("/courses/{course_id}/teaching-assets", response_model=None)
async def list_assets(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id, user, db, roles={"teacher", "assistant", "course_designer", "course_publisher"}
    )
    rows = await db.execute(
        select(TeachingAssetVersion)
        .where(TeachingAssetVersion.course_id == course_id)
        .order_by(
            TeachingAssetVersion.asset_key.asc(),
            TeachingAssetVersion.version_no.desc(),
        )
    )
    return ok(request, [_out(item) for item in rows.scalars()], has_more=False)


@router.post("/courses/{course_id}/teaching-assets", response_model=None)
async def create_asset(
    course_id: str,
    body: schemas.TeachingAssetCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "course_designer"})
    service.validate_asset_payload(
        content=body.content,
        template=body.template,
        fallback_text=body.fallback_text,
        evidence_refs=body.evidence_refs,
        allowed_actions=body.allowed_actions,
    )
    if body.release_id:
        release = await db.scalar(
            select(CourseRelease).where(
                CourseRelease.id == body.release_id,
                CourseRelease.course_id == course_id,
                CourseRelease.status == "draft",
            )
        )
        if release is None:
            raise ApiError(
                status_code=409,
                code="ASSET_RELEASE_INVALID",
                message="教学资产只能绑定当前课程的草稿版本",
            )
    latest = await db.scalar(
        select(TeachingAssetVersion.version_no)
        .where(
            TeachingAssetVersion.course_id == course_id,
            TeachingAssetVersion.asset_key == body.asset_key,
        )
        .order_by(TeachingAssetVersion.version_no.desc())
        .limit(1)
    )
    item = TeachingAssetVersion(
        course_id=course_id,
        release_id=body.release_id,
        asset_key=body.asset_key,
        version_no=(latest or 0) + 1,
        template=body.template,
        content=body.content,
        fallback_text=body.fallback_text,
        evidence_refs=body.evidence_refs,
        allowed_actions=list(dict.fromkeys(body.allowed_actions)),
        created_by=user.id,
    )
    db.add(item)
    await db.flush()
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="teaching_asset.created",
        resource_type="teaching_asset_version",
        resource_id=item.id,
        course_id=course_id,
        detail={"asset_key": item.asset_key, "version_no": item.version_no},
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item), status_code=201)


@router.post("/courses/{course_id}/teaching-assets/{asset_id}/publish", response_model=None)
async def publish_asset(
    course_id: str,
    asset_id: str,
    body: schemas.TeachingAssetPublish,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "course_publisher"})
    item = await db.scalar(
        select(TeachingAssetVersion)
        .where(TeachingAssetVersion.id == asset_id, TeachingAssetVersion.course_id == course_id)
        .with_for_update()
    )
    if item is None:
        raise ApiError(
            status_code=404,
            code="TEACHING_ASSET_NOT_FOUND",
            message="教学资产不存在或无权访问",
        )
    if item.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="教学资产已变化，请刷新后重试",
        )
    if item.status == "published":
        return ok(request, _out(item))
    if item.status != "draft":
        raise ApiError(
            status_code=409,
            code="TEACHING_ASSET_NOT_EDITABLE",
            message="教学资产不能发布",
        )
    release = await db.scalar(
        select(CourseRelease).where(
            CourseRelease.id == body.release_id,
            CourseRelease.course_id == course_id,
            CourseRelease.status == "published",
        )
    )
    if release is None:
        raise ApiError(
            status_code=409,
            code="ASSET_RELEASE_NOT_PUBLISHED",
            message="必须绑定已发布课程版本",
        )
    service.validate_evidence_refs_for_release(
        evidence_refs=item.evidence_refs,
        release_manifest=release.manifest if isinstance(release.manifest, dict) else {},
    )
    item.release_id = release.id
    item.status = "published"
    item.published_by = user.id
    item.published_at = datetime.now(UTC)
    item.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="teaching_asset.published",
        resource_type="teaching_asset_version",
        resource_id=item.id,
        course_id=course_id,
        detail={"release_id": release.id, "asset_key": item.asset_key},
    )
    await db.commit()
    await db.refresh(item)
    return ok(request, _out(item))


@router.get("/student/teaching-assets/{asset_id}", response_model=None)
async def get_published_asset(
    asset_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    item = await db.scalar(
        select(TeachingAssetVersion).where(
            TeachingAssetVersion.id == asset_id,
            TeachingAssetVersion.status == "published",
        )
    )
    if item is None:
        raise ApiError(
            status_code=404,
            code="TEACHING_ASSET_NOT_FOUND",
            message="教学资产不存在或不可用",
        )
    await require_course_role(item.course_id, user, db, roles={"student"})
    await ensure_ai_support_available(db, user_id=user.id)
    if item.release_id is None or await db.scalar(
        select(CourseRelease.id).where(
            CourseRelease.id == item.release_id,
            CourseRelease.status == "published",
        )
    ) is None:
        raise ApiError(
            status_code=404,
            code="TEACHING_ASSET_NOT_FOUND",
            message="教学资产当前版本不可用",
        )
    return ok(request, _out(item))
