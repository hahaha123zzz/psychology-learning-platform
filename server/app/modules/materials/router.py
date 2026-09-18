
from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.core.storage import put_object
from app.db.models import Job, Material, MaterialVersion, User
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.materials import service as materials_service
from app.modules.materials.schemas import MaterialUploadForm, MaterialUploadOut

router = APIRouter()

MATERIALS_UPLOAD_ENDPOINT = "POST:/api/v1/courses/{course_id}/materials"


@router.post("/courses/{course_id}/materials", response_model=None)
async def upload_material(
    course_id: str,
    request: Request,
    title: str = Form(min_length=1, max_length=200),
    material_type: str = Form(
        pattern="^(textbook|slides|handout|exercise|reference|other)$"
    ),
    visibility: str = Form(default="draft", pattern="^(draft|published)$"),
    file: UploadFile = File(),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    await materials_service.get_course_or_404(db, course_id)

    form = MaterialUploadForm(
        title=title, material_type=material_type, visibility=visibility
    )
    request_hash = course_service.canonical_request_hash(
        {**form.model_dump(), "filename": file.filename}
    )

    if idempotency_key:
        previous = await course_service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=MATERIALS_UPLOAD_ENDPOINT,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(request, previous["body"]["data"], status_code=previous["status"])

    validated = await materials_service.validate_and_hash(file)

    duplicate = await materials_service.find_duplicate(
        db, course_id=course_id, sha256=validated.sha256
    )
    if duplicate is not None:
        raise ApiError(
            status_code=409,
            code="DUPLICATE_MATERIAL",
            message="课程中已存在内容相同的文件，可直接复用",
            details={
                "material_id": duplicate.material_id,
                "version_id": duplicate.id,
            },
        )

    await materials_service.check_course_quota(db, course_id, validated.size_bytes)

    material = Material(
        course_id=course_id,
        title=form.title,
        material_type=form.material_type,
        visibility=form.visibility,
        created_by=user.id,
    )
    db.add(material)
    await db.flush()
    version_no = await materials_service.next_version_no(db, material.id)
    version = MaterialVersion(
        material_id=material.id,
        version_no=version_no,
        status="uploading",
        original_filename=(file.filename or "")[:255],
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
        content_type=validated.content_type,
        created_by=user.id,
    )
    db.add(version)
    await db.flush()

    extension = (file.filename or "bin").rsplit(".", 1)[-1].lower()
    object_key = materials_service.material_object_key(
        course_id=course_id,
        material_id=material.id,
        version_id=version.id,
        extension=extension,
    )

    await file.seek(0)
    try:
        await put_object(
            key=object_key,
            data=file.file,
            length=validated.size_bytes,
            content_type=validated.content_type,
        )
    except Exception as exc:  # noqa: BLE001
        version.status = "failed"
        await db.commit()
        raise ApiError(
            status_code=502,
            code="STORAGE_UNAVAILABLE",
            message="对象存储暂时不可用，请稍后重试",
            retryable=True,
        ) from exc

    version.object_key = object_key
    version.status = "uploaded"
    material.current_version_id = version.id
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.uploaded",
        resource_type="material_version",
        resource_id=version.id,
        course_id=course_id,
        detail={
            "material_id": material.id,
            "sha256": validated.sha256,
            "size_bytes": validated.size_bytes,
        },
    )

    body_data = MaterialUploadOut(
        material_id=material.id,
        version_id=version.id,
        status=version.status,
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
    ).model_dump(mode="json")

    if idempotency_key:
        try:
            await course_service.save_idempotent_response(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=MATERIALS_UPLOAD_ENDPOINT,
                request_hash=request_hash,
                status=201,
                body={"data": body_data},
            )
            await db.commit()
        except Exception:
            await db.rollback()
            previous = await course_service.find_idempotent_response(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=MATERIALS_UPLOAD_ENDPOINT,
                request_hash=request_hash,
            )
            if previous is None:
                raise
            return ok(request, previous["body"]["data"], status_code=previous["status"])
    else:
        await db.commit()

    return ok(request, body_data, status_code=201)


@router.post("/material-versions/{version_id}/parse", response_model=None)
async def trigger_parse(
    version_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    version, material = await materials_service.get_version_with_material_or_404(
        db, version_id
    )
    await require_course_role(
        material.course_id, user, db, roles={"teacher"}
    )
    if idempotency_key:
        existing = await materials_service.find_parse_job_by_idempotency_key(
            db, idempotency_key
        )
        if existing is not None:
            return ok(
                request,
                {"job_id": existing.id, "status": existing.status},
                status_code=202,
            )

    active = await materials_service.find_active_parse_job(db, version_id)
    if active is not None:
        raise ApiError(
            status_code=409,
            code="PARSE_JOB_ALREADY_ACTIVE",
            message="该版本已有进行中的解析任务",
            details={"job_id": active.id},
        )

    if version.status not in ("uploaded", "failed"):
        raise ApiError(
            status_code=409,
            code="INVALID_VERSION_STATUS",
            message="当前版本状态不可触发解析",
            details={"status": version.status},
        )

    job = Job(
        kind="material_parse",
        status="queued",
        stage="queued",
        payload={"material_version_id": version_id},
        idempotency_key=idempotency_key,
        created_by=user.id,
    )
    db.add(job)
    version.status = "parsing"
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.parse_triggered",
        resource_type="material_version",
        resource_id=version_id,
        course_id=material.course_id,
        detail={"job_kind": job.kind},
    )
    await db.commit()
    await db.refresh(job, attribute_names=["id"])
    materials_service.spawn_parse_job(job.id, version_id)
    return ok(
        request, {"job_id": job.id, "status": "queued"}, status_code=202
    )


@router.get("/jobs/{job_id}", response_model=None)
async def get_job_status(
    job_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    job = (
        await db.execute(select(Job).where(Job.id == job_id).limit(1))
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(status_code=404, code="JOB_NOT_FOUND", message="任务不存在")
    if job.created_by != user.id and not user.is_platform_admin:
        version_id = (job.payload or {}).get("material_version_id")
        if version_id:
            version, material = await materials_service.get_version_with_material_or_404(
                db, version_id
            )
            await require_course_role(
                material.course_id, user, db, roles={"teacher"}
            )
        else:
            raise ApiError(status_code=404, code="JOB_NOT_FOUND", message="任务不存在")
    return ok(request, materials_service.job_out(job))


@router.get("/courses/{course_id}/materials", response_model=None)
async def list_materials(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    role = await require_course_role(
        course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    is_staff = role in ("teacher", "assistant") or user.is_platform_admin
    query = (
        select(Material, MaterialVersion)
        .outerjoin(MaterialVersion, Material.current_version_id == MaterialVersion.id)
        .where(Material.course_id == course_id)
        .order_by(Material.created_at.desc())
    )
    if not is_staff:
        query = query.where(
            Material.visibility == "published", Material.status == "active"
        )
    else:
        query = query.where(Material.status.in_(("active", "archived")))
    result = await db.execute(query)
    items = []
    for material, version in result.all():
        item: dict = {
            "id": material.id,
            "title": material.title,
            "material_type": material.material_type,
            "status": material.status,
            "created_at": material.created_at.isoformat(),
            "current_version": None,
        }
        if is_staff:
            item["visibility"] = material.visibility
        if version is not None:
            item["current_version"] = {
                "id": version.id,
                "version_no": version.version_no,
                "status": version.status,
                "size_bytes": version.size_bytes,
                "content_type": version.content_type,
            }
        items.append(item)
    return ok(request, items, has_more=False)


@router.post("/material-versions/{version_id}/publish", response_model=None)
async def publish_version(
    version_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    from datetime import UTC, datetime

    version, material = await materials_service.get_version_with_material_or_404(
        db, version_id
    )
    await require_course_role(
        material.course_id, user, db, roles={"teacher"}
    )
    if version.status != "parsed":
        raise ApiError(
            status_code=409,
            code="MATERIAL_NOT_PARSED",
            message="资料必须解析成功后才能发布",
            details={"status": version.status},
        )
    if material.status != "active":
        raise ApiError(
            status_code=409,
            code="MATERIAL_ARCHIVED",
            message="已归档资料不能发布",
        )
    material.visibility = "published"
    material.current_version_id = version.id
    published_at = datetime.now(UTC)
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.published",
        resource_type="material_version",
        resource_id=version.id,
        course_id=material.course_id,
        detail={"published_at": published_at.isoformat()},
    )
    await db.commit()
    return ok(
        request,
        {
            "material_id": material.id,
            "version_id": version.id,
            "published_at": published_at.isoformat(),
            "index_job_id": None,
        },
    )


@router.delete("/materials/{material_id}", response_model=None)
async def archive_material(
    material_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    material = (
        await db.execute(select(Material).where(Material.id == material_id).limit(1))
    ).scalar_one_or_none()
    if material is None:
        raise ApiError(
            status_code=404, code="MATERIAL_NOT_FOUND", message="资料不存在或无权访问"
        )
    await require_course_role(
        material.course_id, user, db, roles={"teacher"}
    )
    if material.status == "archived":
        raise ApiError(
            status_code=409, code="MATERIAL_ALREADY_ARCHIVED", message="资料已归档"
        )
    material.status = "archived"
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.archived",
        resource_type="material",
        resource_id=material.id,
        course_id=material.course_id,
        detail=None,
    )
    await db.commit()
    return ok(request, {"id": material.id, "status": material.status})
