import json
import math

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from minio.error import S3Error
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.response import ok
from app.core.storage import presigned_get_url
from app.core.task_dispatcher import dispatch_embed_job
from app.db.models import (
    DomainRelease,
    EvidencePointer,
    EvidenceTicket,
    Job,
    Material,
    MaterialVersion,
    ParseReviewIssue,
    PublicationSnapshot,
    User,
)
from app.db.session import get_db_session
from app.modules.assessments.policy import ensure_ai_support_available
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.knowledge import service as knowledge_service
from app.modules.knowledge.query import analyze_query
from app.modules.materials import service as materials_service
from app.modules.materials.policy import ensure_legacy_material_authoring_api_enabled
from app.modules.materials.reader import MaterialVersionIntegrityError, get_or_create_pdf_page
from app.modules.materials.renderers.base import RendererUnavailableError

router = APIRouter()


def _pointer_anchors(pointer: EvidencePointer) -> list[dict]:
    if isinstance(pointer.anchors, list):
        return [anchor for anchor in pointer.anchors if isinstance(anchor, dict)]
    if pointer.physical_page is not None and pointer.bbox is not None:
        return [
            {
                "physical_page": pointer.physical_page,
                "bbox": pointer.bbox,
                "coordinate_space": pointer.coordinate_space,
                "precision": "legacy_pointer_bbox",
            }
        ]
    return []


EMBED_ENDPOINT = "POST:/api/v1/material-versions/embed"


class SearchRequest(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    query: str = Field(min_length=1, max_length=1000)
    chapter_scope: list[str] | None = None
    material_version_ids: list[str] | None = None
    domain_release_id: str | None = Field(default=None, min_length=26, max_length=26)
    object_types: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    include_neighbors: bool = True
    purpose: str = Field(default="course_qa", max_length=50)


@router.post("/material-versions/{version_id}/embed", response_model=None)
async def trigger_embed(
    version_id: str,
    request: Request,
    domain_release_id: str | None = Query(default=None, min_length=26, max_length=26),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    version, material = await materials_service.get_version_with_material_or_404(db, version_id)
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    ensure_legacy_material_authoring_api_enabled()
    version, material = await materials_service.get_version_with_material_or_404(
        db, version_id, lock=True
    )
    if version.status != "parsed":
        raise ApiError(
            status_code=409,
            code="INVALID_VERSION_STATUS",
            message="必须先完成解析才能构建索引",
            details={"status": version.status},
        )
    if domain_release_id is not None:
        domain_release = await db.scalar(
            select(DomainRelease).where(
                DomainRelease.id == domain_release_id,
                DomainRelease.course_id == material.course_id,
                DomainRelease.status == "published",
            )
        )
        if domain_release is None:
            raise ApiError(404, "DOMAIN_RELEASE_NOT_FOUND", "已发布领域版本不存在或无权访问")
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
            message="仍有阻塞解析问题，修复并重新解析后才能构建索引",
            details={"open_blocking_issue_count": int(open_blocking)},
        )

    if idempotency_key:
        result = await db.execute(
            select(Job).where(
                Job.kind == "material_embed",
                Job.idempotency_key == idempotency_key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return ok(request, {"job_id": existing.id, "status": existing.status}, status_code=202)

    active = await knowledge_service.find_active_embed_job(db, version_id)
    if active is not None:
        raise ApiError(
            status_code=409,
            code="EMBED_JOB_ALREADY_ACTIVE",
            message="该版本已有进行中的索引任务",
            details={"job_id": active.id},
        )

    job = Job(
        kind="material_embed",
        status="queued",
        stage="queued",
        payload={"material_version_id": version_id, "domain_release_id": domain_release_id},
        idempotency_key=idempotency_key,
        worker_backend=get_settings().task_backend,
        created_by=user.id,
    )
    db.add(job)
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="material.embed_triggered",
        resource_type="material_version",
        resource_id=version_id,
        course_id=material.course_id,
        detail=None,
    )
    await db.commit()
    await db.refresh(job, attribute_names=["id"])
    dispatch_embed_job(job.id, version_id)
    return ok(request, {"job_id": job.id, "status": "queued"}, status_code=202)


@router.post("/knowledge/search", response_model=None)
async def search_knowledge(
    body: SearchRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    role = await require_course_role(
        body.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if role == "student":
        await ensure_ai_support_available(db, user_id=user.id)
    staff = role in ("teacher", "assistant")
    version_ids = await knowledge_service.resolve_searchable_versions(
        db,
        course_id=body.course_id,
        requested_version_ids=body.material_version_ids or [],
        staff=staff,
    )
    domain_release = None
    domain_index_job_ids: dict[str, str] | None = None
    if body.domain_release_id:
        domain_release = await db.scalar(
            select(DomainRelease).where(
                DomainRelease.id == body.domain_release_id,
                DomainRelease.course_id == body.course_id,
                DomainRelease.status.in_(("published", "deprecated")),
            )
        )
        if domain_release is None:
            raise ApiError(404, "DOMAIN_RELEASE_NOT_FOUND", "已发布领域版本不存在或无权访问")
        snapshot_query = (
            select(
                PublicationSnapshot.material_id,
                PublicationSnapshot.material_version_id,
                PublicationSnapshot.id,
                PublicationSnapshot.index_job_id,
                PublicationSnapshot.embedding_version,
                PublicationSnapshot.domain_release_id,
            )
            .join(Material, Material.id == PublicationSnapshot.material_id)
            .where(
                Material.course_id == body.course_id,
                PublicationSnapshot.domain_release_id == domain_release.id,
                PublicationSnapshot.material_version_id.in_(version_ids or [""]),
            )
        )
        if role == "student":
            snapshot_query = snapshot_query.where(
                Material.status == "active",
                Material.visibility == "published",
                Material.current_version_id == PublicationSnapshot.material_version_id,
                PublicationSnapshot.superseded_at.is_(None),
            )
        snapshot_rows = (
            await db.execute(snapshot_query.order_by(PublicationSnapshot.published_at.asc()))
        ).all()
        publication_snapshots = [
            {
                "material_id": material_id,
                "material_version_id": material_version_id,
                "publication_snapshot_id": snapshot_id,
                "index_job_id": index_job_id,
                "embedding_version": embedding_version,
                "domain_release_id": snapshot_domain_release_id,
            }
            for (
                material_id,
                material_version_id,
                snapshot_id,
                index_job_id,
                embedding_version,
                snapshot_domain_release_id,
            ) in snapshot_rows
        ]
        domain_index_job_ids = {
            snapshot["material_version_id"]: snapshot["index_job_id"]
            for snapshot in publication_snapshots
        }
        if role != "student":
            jobs = await db.execute(
                select(Job)
                .where(
                    Job.kind == "material_embed",
                    Job.status == "succeeded",
                    Job.payload["material_version_id"].as_string().in_(version_ids or [""]),
                )
                .order_by(Job.finished_at.asc())
            )
            for job in jobs.scalars():
                payload = job.payload or {}
                version_id = payload.get("material_version_id")
                if (
                    payload.get("domain_release_id") == domain_release.id
                    and version_id in version_ids
                    and version_id not in domain_index_job_ids
                ):
                    domain_index_job_ids[version_id] = job.id
        if role == "student":
            version_ids = [
                version_id for version_id in version_ids if version_id in domain_index_job_ids
            ]
    plan = analyze_query(body.query)
    effective_top_k = min(body.top_k, plan.retrieval_budget)
    items, warnings = await knowledge_service.hybrid_search(
        db,
        user_id=user.id,
        course_id=body.course_id,
        version_ids=version_ids,
        query=body.query,
        top_k=effective_top_k,
        staff=staff,
        include_neighbors=body.include_neighbors,
        chapter_scope=body.chapter_scope,
        object_types=body.object_types,
        channel_priors=plan.channel_priors,
        domain_release_id=body.domain_release_id,
        domain_index_job_ids=domain_index_job_ids,
    )
    await db.commit()
    return ok(
        request,
        {
            "items": items,
            "query_plan": plan.as_dict(),
            "retrieval_budget": {
                "requested_top_k": body.top_k,
                "plan_top_k": plan.retrieval_budget,
                "effective_top_k": effective_top_k,
            },
            "fusion": knowledge_service.retrieval_fusion_summary(plan.channel_priors),
            "retrieval_version": knowledge_service.RETRIEVAL_VERSION,
            "domain_release": (
                {
                    "id": domain_release.id,
                    "version_no": domain_release.version_no,
                    "pack_sha256": domain_release.pack_sha256,
                    "index_job_ids": domain_index_job_ids,
                    "publication_snapshots": publication_snapshots,
                }
                if domain_release is not None
                else None
            ),
            "warnings": warnings,
        },
    )


from app.modules.knowledge.domain_router import router as domain_router  # noqa: E402

router.include_router(domain_router)


@router.get("/evidence/{evidence_id}", response_model=None)
async def get_evidence(
    evidence_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    from datetime import UTC, datetime

    ticket = (
        await db.execute(select(EvidenceTicket).where(EvidenceTicket.id == evidence_id).limit(1))
    ).scalar_one_or_none()
    if (
        ticket is None
        or ticket.revoked_at is not None
        or ticket.expires_at < datetime.now(UTC)
        or ticket.user_id != user.id
    ):
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已过期")
    role = await require_course_role(
        ticket.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if role == "student":
        await ensure_ai_support_available(db, user_id=user.id)

    row = (
        await db.execute(
            text(
                "SELECT kc.text, kc.chapter_path, kc.physical_page, "
                "kc.reading_order, mv.object_key, mv.id, m.title, m.id, "
                "m.visibility, m.status, m.current_version_id, kc.source_object_id, "
                "kc.retrieval_unit_id, ko.type, ko.bbox, ko.parser "
                "FROM knowledge_chunks kc "
                "JOIN material_versions mv ON mv.id = kc.material_version_id "
                "JOIN materials m ON m.id = mv.material_id "
                "LEFT JOIN knowledge_objects ko ON ko.id = kc.source_object_id "
                "WHERE kc.id = :chunk_id"
            ),
            {"chunk_id": ticket.chunk_id},
        )
    ).first()
    if row is None:
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已过期")
    if ticket.material_version_id != row[5]:
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已过期")
    if role == "student" and (row[8] != "published" or row[9] != "active" or row[10] != row[5]):
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已过期")
    preview_url = None
    if row[4]:
        try:
            preview_url = presigned_get_url(key=row[4], expires_seconds=600)
        except Exception:  # noqa: BLE001
            preview_url = None
    physical_page = row[2]
    bbox = row[14]
    if row[15] == "docx-xml" and bbox is None:
        physical_page = None
    return ok(
        request,
        {
            "text": row[0],
            "chapter_path": row[1],
            "physical_page": physical_page,
            "anchor": f"p{physical_page}#order{row[3]}" if physical_page is not None else None,
            "material_title": row[6],
            "material_id": row[7],
            "material_version_id": row[5],
            "source_object_id": row[11],
            "retrieval_unit_id": row[12],
            "object_type": row[13] or "paragraph",
            "bbox": bbox,
            "coordinate_space": "pdf_user_bottom_left" if bbox is not None else "unavailable",
            "evidence_pointer_id": ticket.pointer_id,
            "preview_url": preview_url,
            "expires_at": ticket.expires_at.isoformat(),
        },
    )


@router.get("/evidence-pointers/{pointer_id}", response_model=None)
async def get_evidence_pointer(
    pointer_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """恢复持久教材引用；指针保存来源快照，但不保存访问授权。"""
    pointer = await db.get(EvidencePointer, pointer_id)
    if pointer is None:
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已撤回")
    role = await require_course_role(
        pointer.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if role == "student":
        await ensure_ai_support_available(db, user_id=user.id)
        material_state = (
            await db.execute(
                select(Material.course_id, Material.status, Material.visibility)
                .join(MaterialVersion, MaterialVersion.material_id == Material.id)
                .join(
                    PublicationSnapshot,
                    PublicationSnapshot.material_version_id == MaterialVersion.id,
                )
                .where(
                    Material.id == pointer.material_id,
                    MaterialVersion.id == pointer.material_version_id,
                    PublicationSnapshot.material_id == pointer.material_id,
                )
                .limit(1)
            )
        ).first()
        if (
            material_state is None
            or material_state[0] != pointer.course_id
            or material_state[1] != "active"
            or material_state[2] != "published"
        ):
            raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已撤回")
    return ok(
        request,
        {
            "evidence_pointer_id": pointer.id,
            "course_id": pointer.course_id,
            "material_title": pointer.material_title,
            "material_id": pointer.material_id,
            "material_version_id": pointer.material_version_id,
            "source_object_id": pointer.source_object_id,
            "retrieval_unit_id": pointer.retrieval_unit_id,
            "chapter_path": pointer.chapter_path,
            "physical_page": pointer.physical_page,
            "reading_order": pointer.reading_order,
            "anchor": (
                f"p{pointer.physical_page}#order{pointer.reading_order}"
                if pointer.physical_page is not None and pointer.reading_order is not None
                else None
            ),
            "object_type": pointer.object_type,
            "coordinate_space": pointer.coordinate_space,
            "bbox": pointer.bbox,
            "anchors": _pointer_anchors(pointer),
            "excerpt": pointer.excerpt,
            "excerpt_sha256": pointer.excerpt_sha256,
            "restored": True,
        },
    )


@router.get("/evidence-pointers/{pointer_id}/page-image", response_model=None)
async def get_evidence_pointer_page_image(
    pointer_id: str,
    physical_page: int | None = Query(default=None, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """获取引用对应的固定 PDF 页图；每次请求都重新验证课程与发布权限。"""
    pointer = await db.get(EvidencePointer, pointer_id)
    if pointer is None:
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已撤回")

    role = await require_course_role(
        pointer.course_id, user, db, roles={"teacher", "assistant", "student"}
    )
    if role == "student":
        await ensure_ai_support_available(db, user_id=user.id)

    material_state = (
        await db.execute(
            select(Material.course_id, Material.status, Material.visibility)
            .join(MaterialVersion, MaterialVersion.material_id == Material.id)
            .where(
                Material.id == pointer.material_id,
                MaterialVersion.id == pointer.material_version_id,
            )
            .limit(1)
        )
    ).first()
    version = await db.get(MaterialVersion, pointer.material_version_id)
    if (
        material_state is None
        or version is None
        or material_state[0] != pointer.course_id
        or material_state[1] != "active"
    ):
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已撤回")

    if role == "student":
        published_snapshot = await db.scalar(
            select(PublicationSnapshot.id)
            .where(
                PublicationSnapshot.material_id == pointer.material_id,
                PublicationSnapshot.material_version_id == pointer.material_version_id,
            )
            .limit(1)
        )
        if material_state[2] != "published" or published_snapshot is None:
            raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已撤回")

    anchors = _pointer_anchors(pointer)
    selected_page = physical_page if physical_page is not None else pointer.physical_page
    anchor = next(
        (item for item in anchors if item.get("physical_page") == selected_page),
        None,
    )
    if physical_page is not None and anchor is None:
        raise ApiError(
            status_code=404,
            code="EVIDENCE_ANCHOR_NOT_FOUND",
            message="该引用没有此物理页的定位锚点",
        )
    if anchor is None and anchors:
        anchor = anchors[0]
        selected_page = anchor.get("physical_page")
    anchor_bbox = anchor.get("bbox") if anchor is not None else None
    anchor_coordinate_space = anchor.get("coordinate_space") if anchor is not None else None
    if (
        selected_page == pointer.physical_page
        and anchor is not None
        and (anchor_bbox != pointer.bbox or anchor_coordinate_space != pointer.coordinate_space)
    ):
        raise ApiError(
            status_code=409,
            code="READER_LAYOUT_UNAVAILABLE",
            message="引用主锚点与来源快照不一致；请使用文字来源快照",
        )
    if (
        version.content_type != "application/pdf"
        or type(selected_page) is not int
        or anchor_coordinate_space != "pdf_user_bottom_left"
        or anchor_bbox is None
    ):
        raise ApiError(
            status_code=409,
            code="READER_LAYOUT_UNAVAILABLE",
            message="该教材版本没有可验证的 PDF 页内坐标；请使用文字来源快照",
        )
    if selected_page < 1 or (version.page_count is not None and selected_page > version.page_count):
        raise ApiError(status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已撤回")

    try:
        bbox = [float(value) for value in anchor_bbox]
        if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
            raise ValueError("bbox 格式无效")
        source_key = version.canonical_pdf_key or version.object_key
        if not source_key:
            raise MaterialVersionIntegrityError("教材版本缺少 PDF 对象键")
        page = await get_or_create_pdf_page(
            course_id=pointer.course_id,
            material_id=pointer.material_id,
            version_id=pointer.material_version_id,
            source_object_key=source_key,
            expected_source_sha256=version.sha256,
            physical_page=selected_page,
        )
        if not (
            0 <= bbox[0] < bbox[2] <= page.transform.pdf_width
            and 0 <= bbox[1] < bbox[3] <= page.transform.pdf_height
        ):
            raise ValueError("bbox 超出 PDF 页面边界")
        bbox_pixels = page.transform.pdf_bbox_to_pixels(bbox)
    except RendererUnavailableError as exc:
        raise ApiError(
            status_code=409,
            code="READER_LAYOUT_UNAVAILABLE",
            message="该教材页无法由本地渲染器可靠呈现；文字来源快照仍可用",
        ) from exc
    except MaterialVersionIntegrityError as exc:
        raise ApiError(
            status_code=409,
            code="MATERIAL_VERSION_INTEGRITY_FAILED",
            message="教材版本完整性校验失败，暂不能打开页图",
        ) from exc
    except S3Error as exc:
        raise ApiError(
            status_code=503,
            code="READER_STORAGE_UNAVAILABLE",
            message="教材页图暂时不可用，请稍后重试",
            retryable=True,
        ) from exc
    except (TypeError, ValueError) as exc:
        raise ApiError(
            status_code=409,
            code="READER_LAYOUT_UNAVAILABLE",
            message="引用坐标无效；请使用文字来源快照",
        ) from exc

    return Response(
        content=page.content,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-Reader-Transform": json.dumps(page.transform.manifest(), separators=(",", ":")),
            "X-Reader-Bbox-Pixels": json.dumps(bbox_pixels, separators=(",", ":")),
            "X-Reader-Physical-Page": str(selected_page),
        },
    )
