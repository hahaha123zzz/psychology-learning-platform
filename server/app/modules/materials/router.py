from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.embedding import get_embedding_client
from app.core.errors import ApiError
from app.core.response import ok
from app.core.storage import put_object
from app.core.task_dispatcher import dispatch_parse_job
from app.db.models import (
    Job,
    Material,
    MaterialVersion,
    ParseReviewIssue,
    PublicationSnapshot,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.materials import service as materials_service
from app.modules.materials import uploads as uploads_service
from app.modules.materials import workflow as workflow_service
from app.modules.materials.schemas import (
    KnowledgeObjectCorrection,
    MaterialUploadForm,
    MaterialUploadOut,
    ParseReviewIssueResolution,
    UploadPartComplete,
    UploadSessionCreate,
)

router = APIRouter()

MATERIALS_UPLOAD_ENDPOINT = "POST:/api/v1/courses/{course_id}/materials"


@router.post("/courses/{course_id}/upload-sessions", response_model=None)
async def create_upload_session(
    course_id: str,
    body: UploadSessionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    await materials_service.get_course_or_404(db, course_id)
    session = await uploads_service.create_session(
        db,
        course_id=course_id,
        title=body.title,
        material_type=body.material_type,
        filename=body.filename,
        size_bytes=body.size_bytes,
        created_by=user.id,
    )
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.upload_session_created",
        resource_type="upload_session",
        resource_id=session.id,
        course_id=course_id,
        detail={"filename": body.filename, "size_bytes": body.size_bytes},
    )
    await db.commit()
    return ok(request, uploads_service.session_out(session), status_code=201)


@router.get("/upload-sessions/{session_id}", response_model=None)
async def get_upload_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session = await uploads_service.get_session_or_404(db, session_id)
    await require_course_role(session.course_id, user, db, roles={"teacher"})
    await uploads_service.expire_if_needed(db, session)
    parts = list(
        (
            await db.execute(
                select(uploads_service.UploadPart)
                .where(uploads_service.UploadPart.upload_session_id == session.id)
                .order_by(uploads_service.UploadPart.part_number)
            )
        ).scalars()
    )
    await db.commit()
    return ok(request, uploads_service.session_out(session, parts))


@router.post("/upload-sessions/{session_id}/parts/{part_number}/url", response_model=None)
async def get_upload_part_url(
    session_id: str,
    part_number: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session = await uploads_service.get_session_or_404(db, session_id)
    await require_course_role(session.course_id, user, db, roles={"teacher"})
    data = await uploads_service.get_part_url(db, session, part_number)
    await db.commit()
    return ok(request, data)


@router.put("/upload-sessions/{session_id}/parts/{part_number}", response_model=None)
async def complete_upload_part(
    session_id: str,
    part_number: int,
    body: UploadPartComplete,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session = await uploads_service.get_session_or_404(db, session_id)
    await require_course_role(session.course_id, user, db, roles={"teacher"})
    await uploads_service.record_part(
        db, session, part_number=part_number, etag=body.etag, size_bytes=body.size_bytes
    )
    await db.commit()
    return ok(
        request,
        {"upload_session_id": session.id, "part_number": part_number, "status": session.status},
    )


@router.post("/upload-sessions/{session_id}/complete", response_model=None)
async def complete_upload_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session = await uploads_service.get_session_or_404(db, session_id)
    await require_course_role(session.course_id, user, db, roles={"teacher"})
    material, version = await uploads_service.complete_session(db, session, user.id)
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.uploaded",
        resource_type="material_version",
        resource_id=version.id,
        course_id=material.course_id,
        detail={
            "material_id": material.id,
            "sha256": version.sha256,
            "size_bytes": version.size_bytes,
            "upload_session_id": session.id,
        },
    )
    await db.commit()
    return ok(
        request,
        {
            "material_id": material.id,
            "version_id": version.id,
            "status": version.status,
            "sha256": version.sha256,
            "size_bytes": version.size_bytes,
        },
    )


@router.delete("/upload-sessions/{session_id}", response_model=None)
async def cancel_upload_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    session = await uploads_service.get_session_or_404(db, session_id)
    await require_course_role(session.course_id, user, db, roles={"teacher"})
    await uploads_service.cancel_session(db, session)
    await db.commit()
    return ok(request, {"upload_session_id": session.id, "status": session.status})


@router.post("/courses/{course_id}/materials", response_model=None)
async def upload_material(
    course_id: str,
    request: Request,
    title: str = Form(min_length=1, max_length=200),
    material_type: str = Form(pattern="^(textbook|slides|handout|exercise|reference|other)$"),
    visibility: str = Form(default="draft", pattern="^(draft|published)$"),
    file: UploadFile = File(),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    await materials_service.get_course_or_404(db, course_id)

    form = MaterialUploadForm(title=title, material_type=material_type, visibility=visibility)
    if form.visibility != "draft":
        raise ApiError(
            status_code=422,
            code="MATERIAL_REQUIRES_REVIEW",
            message="资料上传后必须完成解析和教师审核，不能直接发布",
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
    version, material = await materials_service.get_version_with_material_or_404(db, version_id)
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    if idempotency_key:
        existing = await materials_service.find_parse_job_by_idempotency_key(db, idempotency_key)
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

    if version.status == "parsed" and material.visibility != "draft":
        raise ApiError(
            status_code=409,
            code="PUBLISHED_VERSION_IMMUTABLE",
            message="已发布版本不能原地重解析，请创建新版本",
        )
    if version.status not in ("uploaded", "failed", "parsed"):
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
        worker_backend=get_settings().task_backend,
        created_by=user.id,
    )
    db.add(job)
    version.status = "parsing"
    version.quality_gate_status = "pending"
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
    dispatch_parse_job(job.id, version_id)
    return ok(request, {"job_id": job.id, "status": "queued"}, status_code=202)


@router.get("/jobs/{job_id}", response_model=None)
async def get_job_status(
    job_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    job = (await db.execute(select(Job).where(Job.id == job_id).limit(1))).scalar_one_or_none()
    if job is None:
        raise ApiError(status_code=404, code="JOB_NOT_FOUND", message="任务不存在")
    if job.created_by != user.id and not user.is_platform_admin:
        version_id = (job.payload or {}).get("material_version_id")
        if version_id:
            version, material = await materials_service.get_version_with_material_or_404(
                db, version_id
            )
            await require_course_role(material.course_id, user, db, roles={"teacher"})
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
    role = await require_course_role(course_id, user, db, roles={"teacher", "assistant", "student"})
    is_staff = role in ("teacher", "assistant") or user.is_platform_admin
    query = (
        select(Material, MaterialVersion)
        .outerjoin(MaterialVersion, Material.current_version_id == MaterialVersion.id)
        .where(Material.course_id == course_id)
        .order_by(Material.created_at.desc())
    )
    if not is_staff:
        query = query.where(
            Material.visibility == "published",
            Material.status == "active",
            MaterialVersion.status == "parsed",
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
            if is_staff:
                item["current_version"]["quality_gate_status"] = version.quality_gate_status
                workflow = await workflow_service.build_workflow(
                    db, material=material, version=version
                )
                item["current_version"]["workflow_state"] = workflow["state"]
                item["current_version"]["published_snapshot_id"] = (
                    workflow["publication"]["id"] if workflow["publication"] else None
                )
        items.append(item)
    return ok(request, items, has_more=False)


@router.get("/material-versions/{version_id}/workflow", response_model=None)
async def get_material_workflow(
    version_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    version, material = await materials_service.get_version_with_material_or_404(db, version_id)
    await require_course_role(material.course_id, user, db, roles={"teacher", "assistant"})
    return ok(
        request,
        await workflow_service.build_workflow(db, material=material, version=version),
    )


@router.get("/courses/{course_id}/material-jobs", response_model=None)
async def list_material_jobs(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    rows = (
        await db.execute(
            select(Job, MaterialVersion, Material)
            .join(
                MaterialVersion,
                Job.payload["material_version_id"].as_string() == MaterialVersion.id,
            )
            .join(Material, Material.id == MaterialVersion.material_id)
            .where(
                Material.course_id == course_id,
                Job.kind.in_(("material_parse", "material_embed")),
            )
            .order_by(Job.created_at.desc())
            .limit(50)
        )
    ).all()
    return ok(
        request,
        [
            {
                **materials_service.job_out(job),
                "material_id": material.id,
                "material_title": material.title,
                "material_version_id": version.id,
                "version_no": version.version_no,
            }
            for job, version, material in rows
        ],
        has_more=False,
    )


@router.post("/material-versions/{version_id}/publish", response_model=None)
async def publish_version(
    version_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    from datetime import UTC, datetime

    version, material = await materials_service.get_version_with_material_or_404(db, version_id)
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    # 发布事务重新锁定事实，避免并发审核、归档或发布产生半新半旧状态。
    version = (
        await db.execute(
            select(MaterialVersion).where(MaterialVersion.id == version_id).with_for_update()
        )
    ).scalar_one()
    material = (
        await db.execute(
            select(Material).where(Material.id == version.material_id).with_for_update()
        )
    ).scalar_one()
    if version.status != "parsed":
        raise ApiError(
            status_code=409,
            code="MATERIAL_NOT_PARSED",
            message="资料必须解析成功后才能发布",
            details={"status": version.status},
        )
    report = version.quality_report or {}
    issues = report.get("issues") or []
    blocking = [i for i in issues if i in ("no_text_extracted", "parser_unavailable")]
    if blocking:
        raise ApiError(
            status_code=409,
            code="QUALITY_GATE_FAILED",
            message="解析质量未达标，不能发布（如扫描件缺少文本层）",
            details={"issues": blocking, "quality_report": report},
        )
    open_blocking = await db.scalar(
        select(func.count(ParseReviewIssue.id)).where(
            ParseReviewIssue.material_version_id == version_id,
            ParseReviewIssue.severity == "blocking",
            ParseReviewIssue.status == "open",
        )
    )
    if open_blocking:
        raise ApiError(
            status_code=409,
            code="QUALITY_REVIEW_REQUIRED",
            message="仍有未处理的阻塞解析问题，不能发布",
            details={"open_blocking_issue_count": int(open_blocking)},
        )
    if material.status != "active":
        raise ApiError(
            status_code=409,
            code="MATERIAL_ARCHIVED",
            message="已归档资料不能发布",
        )
    try:
        embedding_version = get_embedding_client().version
    except ValueError as exc:
        raise ApiError(
            status_code=503,
            code="EMBEDDING_CONFIGURATION_INVALID",
            message="Embedding 配置无效，暂时不能发布",
            retryable=False,
        ) from exc
    indexed_chunks = await db.scalar(
        text(
            "SELECT count(*) FROM knowledge_chunks "
            "WHERE material_version_id = :version_id "
            "AND embedding_version = :embedding_version "
            "AND embedding IS NOT NULL"
        ),
        {"version_id": version_id, "embedding_version": embedding_version},
    )
    if not indexed_chunks:
        raise ApiError(
            status_code=409,
            code="MATERIAL_INDEX_NOT_READY",
            message="当前模型版本的教材索引尚未就绪，请先构建索引",
            details={"embedding_version": embedding_version},
        )
    index_job_id = await db.scalar(
        select(Job.id)
        .where(
            Job.kind == "material_embed",
            Job.status == "succeeded",
            Job.payload["material_version_id"].as_string() == version_id,
        )
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    if index_job_id is None:
        raise ApiError(
            status_code=409,
            code="MATERIAL_INDEX_JOB_NOT_READY",
            message="未找到当前教材版本成功完成的索引任务",
        )
    parse_job_id = await db.scalar(
        select(Job.id)
        .where(
            Job.kind == "material_parse",
            Job.status == "succeeded",
            Job.payload["material_version_id"].as_string() == version_id,
        )
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    current_snapshot = (
        await db.execute(
            select(PublicationSnapshot)
            .where(
                PublicationSnapshot.material_id == material.id,
                PublicationSnapshot.superseded_at.is_(None),
            )
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        current_snapshot is not None
        and current_snapshot.material_version_id == version.id
        and current_snapshot.embedding_version == embedding_version
    ):
        return ok(
            request,
            {
                "material_id": material.id,
                "version_id": version.id,
                "published_at": current_snapshot.published_at.isoformat(),
                "index_job_id": current_snapshot.index_job_id,
                "publication_snapshot_id": current_snapshot.id,
            },
        )
    material.visibility = "published"
    material.current_version_id = version.id
    version.quality_gate_status = "approved"
    published_at = datetime.now(UTC)
    if current_snapshot is not None:
        current_snapshot.superseded_at = published_at
    snapshot = PublicationSnapshot(
        material_id=material.id,
        material_version_id=version.id,
        parse_job_id=parse_job_id,
        index_job_id=index_job_id,
        embedding_version=embedding_version,
        published_by=user.id,
        published_at=published_at,
    )
    db.add(snapshot)
    await db.flush()
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
            "index_job_id": index_job_id,
            "publication_snapshot_id": snapshot.id,
        },
    )


@router.get("/material-versions/{version_id}/review-issues", response_model=None)
async def list_parse_review_issues(
    version_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    version, material = await materials_service.get_version_with_material_or_404(db, version_id)
    await require_course_role(material.course_id, user, db, roles={"teacher", "assistant"})
    issues = list(
        (
            await db.execute(
                select(ParseReviewIssue)
                .where(ParseReviewIssue.material_version_id == version.id)
                .order_by(
                    ParseReviewIssue.severity.asc(),
                    ParseReviewIssue.created_at.asc(),
                )
            )
        ).scalars()
    )
    return ok(
        request,
        [
            {
                "id": issue.id,
                "knowledge_object_id": issue.knowledge_object_id,
                "severity": issue.severity,
                "code": issue.code,
                "detail": issue.detail,
                "status": issue.status,
                "resolution": issue.resolution,
                "resolved_by": issue.resolved_by,
                "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
            }
            for issue in issues
        ],
        has_more=False,
    )


@router.patch("/parse-review-issues/{issue_id}", response_model=None)
async def resolve_parse_review_issue(
    issue_id: str,
    body: ParseReviewIssueResolution,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    from datetime import UTC, datetime

    issue = await materials_service.get_parse_review_issue_or_404(db, issue_id)
    version, material = await materials_service.get_version_with_material_or_404(
        db, issue.material_version_id
    )
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    if issue.status != "open":
        raise ApiError(
            status_code=409,
            code="PARSE_REVIEW_ISSUE_ALREADY_CLOSED",
            message="解析审核问题已处理",
            details={"status": issue.status},
        )
    if issue.severity == "blocking":
        raise ApiError(
            status_code=409,
            code="BLOCKING_ISSUE_REQUIRES_REPARSE",
            message="阻塞问题必须修复源文件或解析配置并重新解析，不能手工关闭",
        )
    issue.status = body.status
    issue.resolution = body.resolution
    issue.resolved_by = user.id
    issue.resolved_at = datetime.now(UTC)
    remaining = await db.scalar(
        select(func.count(ParseReviewIssue.id)).where(
            ParseReviewIssue.material_version_id == version.id,
            ParseReviewIssue.severity == "blocking",
            ParseReviewIssue.status == "open",
            ParseReviewIssue.id != issue.id,
        )
    )
    version.quality_gate_status = "blocked" if remaining else "pending"
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.parse_issue_resolved",
        resource_type="parse_review_issue",
        resource_id=issue.id,
        course_id=material.course_id,
        detail={"status": body.status, "severity": issue.severity},
    )
    await db.commit()
    return ok(
        request,
        {
            "id": issue.id,
            "status": issue.status,
            "quality_gate_status": version.quality_gate_status,
        },
    )


@router.get("/material-versions/{version_id}/outline", response_model=None)
async def get_outline(
    version_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    version, material = await materials_service.get_version_with_material_or_404(db, version_id)
    role = await require_course_role(
        material.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if role == "student" and (
        material.visibility != "published"
        or material.status != "active"
        or version.status != "parsed"
        or material.current_version_id != version.id
    ):
        raise ApiError(
            status_code=404,
            code="MATERIAL_VERSION_NOT_FOUND",
            message="资料版本不存在或无权访问",
        )
    outline = await materials_service.build_outline(db, version_id, version.page_count)
    return ok(request, outline, has_more=False)


@router.patch("/knowledge-objects/{object_id}", response_model=None)
async def correct_knowledge_object(
    object_id: str,
    request: Request,
    body: KnowledgeObjectCorrection,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    from datetime import UTC, datetime

    knowledge_object = await materials_service.get_object_or_404(db, object_id)
    version, material = await materials_service.get_version_with_material_or_404(
        db, knowledge_object.material_version_id
    )
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    if knowledge_object.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="知识对象已被其他人修改，请刷新后重试",
            details={
                "expected_version": body.version,
                "actual_version": knowledge_object.version,
            },
        )

    changes: dict = {}
    if body.title is not None:
        changes["title"] = body.title
    if body.normalized_content is not None:
        changes["normalized_content"] = body.normalized_content
    if body.reading_order is not None:
        changes["reading_order"] = body.reading_order
    if body.review_status is not None:
        changes["review_status"] = body.review_status
    if not changes:
        raise ApiError(status_code=422, code="VALIDATION_ERROR", message="没有需要修正的字段")

    override_entry = {
        "reason": body.reason,
        "changes": changes,
        "by": user.id,
        "at": datetime.now(UTC).isoformat(),
    }
    override_list = list(knowledge_object.override or [])
    override_list.append(override_entry)
    knowledge_object.override = override_list
    for field_name, value in changes.items():
        setattr(knowledge_object, field_name, value)
    if "normalized_content" in changes and body.review_status is None:
        knowledge_object.review_status = "corrected"
    knowledge_object.version += 1
    # 教师修订会使候选索引失效；必须重新构建后才能发布。
    await db.execute(
        text("DELETE FROM knowledge_chunks WHERE material_version_id = :version_id"),
        {"version_id": version.id},
    )
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="knowledge_object.corrected",
        resource_type="knowledge_object",
        resource_id=knowledge_object.id,
        course_id=material.course_id,
        detail={"reason": body.reason, "fields": sorted(changes)},
    )
    await db.commit()
    return ok(
        request,
        {"id": knowledge_object.id, "version": knowledge_object.version},
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
        raise ApiError(status_code=404, code="MATERIAL_NOT_FOUND", message="资料不存在或无权访问")
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    if material.status == "archived":
        raise ApiError(status_code=409, code="MATERIAL_ALREADY_ARCHIVED", message="资料已归档")
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
