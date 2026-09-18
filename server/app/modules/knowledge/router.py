
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.core.storage import presigned_get_url
from app.db.models import EvidenceTicket, Job, User
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.knowledge import service as knowledge_service
from app.modules.materials import service as materials_service

router = APIRouter()

EMBED_ENDPOINT = "POST:/api/v1/material-versions/embed"


class SearchRequest(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    query: str = Field(min_length=1, max_length=1000)
    chapter_scope: list[str] | None = None
    material_version_ids: list[str] | None = None
    object_types: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    include_neighbors: bool = True
    purpose: str = Field(default="course_qa", max_length=50)


@router.post("/material-versions/{version_id}/embed", response_model=None)
async def trigger_embed(
    version_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    version, material = await materials_service.get_version_with_material_or_404(
        db, version_id
    )
    await require_course_role(material.course_id, user, db, roles={"teacher"})
    if version.status != "parsed":
        raise ApiError(
            status_code=409,
            code="INVALID_VERSION_STATUS",
            message="必须先完成解析才能构建索引",
            details={"status": version.status},
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
            return ok(
                request, {"job_id": existing.id, "status": existing.status}, status_code=202
            )

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
        payload={"material_version_id": version_id},
        idempotency_key=idempotency_key,
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
    knowledge_service.spawn_embed_job(job.id, version_id)
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
    staff = role in ("teacher", "assistant") or user.is_platform_admin
    version_ids = await knowledge_service.resolve_searchable_versions(
        db,
        course_id=body.course_id,
        requested_version_ids=body.material_version_ids or [],
        staff=staff,
    )
    items, warnings = await knowledge_service.hybrid_search(
        db,
        user_id=user.id,
        course_id=body.course_id,
        version_ids=version_ids,
        query=body.query,
        top_k=body.top_k,
        staff=staff,
    )
    await db.commit()
    return ok(
        request,
        {
            "items": items,
            "retrieval_version": knowledge_service.RETRIEVAL_VERSION,
            "warnings": warnings,
        },
    )


@router.get("/evidence/{evidence_id}", response_model=None)
async def get_evidence(
    evidence_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    from datetime import UTC, datetime

    ticket = (
        await db.execute(
            select(EvidenceTicket).where(EvidenceTicket.id == evidence_id).limit(1)
        )
    ).scalar_one_or_none()
    if (
        ticket is None
        or ticket.revoked_at is not None
        or ticket.expires_at < datetime.now(UTC)
        or ticket.user_id != user.id
    ):
        raise ApiError(
            status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已过期"
        )
    await require_course_role(
        ticket.course_id, user, db, roles={"teacher", "assistant", "student"}
    )

    row = (
        await db.execute(
            text(
                "SELECT kc.text, kc.chapter_path, kc.physical_page, "
                "kc.reading_order, mv.object_key, mv.id, m.title, m.id "
                "FROM knowledge_chunks kc "
                "JOIN material_versions mv ON mv.id = kc.material_version_id "
                "JOIN materials m ON m.id = mv.material_id "
                "WHERE kc.id = :chunk_id"
            ),
            {"chunk_id": ticket.chunk_id},
        )
    ).first()
    if row is None:
        raise ApiError(
            status_code=404, code="EVIDENCE_NOT_FOUND", message="证据不存在或已过期"
        )
    preview_url = None
    if row[4]:
        try:
            preview_url = presigned_get_url(key=row[4], expires_seconds=600)
        except Exception:  # noqa: BLE001
            preview_url = None
    return ok(
        request,
        {
            "text": row[0],
            "chapter_path": row[1],
            "physical_page": row[2],
            "anchor": f"p{row[2]}#order{row[3]}",
            "material_title": row[6],
            "material_id": row[7],
            "material_version_id": row[5],
            "preview_url": preview_url,
            "expires_at": ticket.expires_at.isoformat(),
        },
    )
