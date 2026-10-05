"""Domain Pack 与 DomainRelease API，挂载在 knowledge 模块内。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    DomainRelease,
    DomainReviewDecision,
    KnowledgeObject,
    Material,
    PublicationSnapshot,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user, require_course_role
from app.modules.courses import service as course_service
from app.modules.knowledge.domain import (
    canonical_json_hash,
    misconception_digest,
    validate_domain_pack_shape,
)

router = APIRouter()


async def _idempotency_replay(
    request: Request,
    db: AsyncSession,
    *,
    user_id: str,
    endpoint: str,
    key: str,
    request_hash: str,
):
    previous = await course_service.find_idempotent_response(
        db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=request_hash,
    )
    if previous is None:
        return None
    return ok(
        request,
        previous["body"]["data"],
        status_code=previous["status"],
        idempotent_replay=True,
    )


async def _save_idempotency(
    db: AsyncSession,
    *,
    user_id: str,
    endpoint: str,
    key: str,
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


class DomainReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: dict[str, Any]
    supersedes_id: str | None = Field(default=None, min_length=26, max_length=26)


class DomainReleaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    manifest: dict[str, Any]


class MisconceptionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected", "changes_requested"]
    reason: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)


def _manifest_pack(manifest: dict[str, Any]) -> dict[str, Any]:
    pack = manifest.get("domain_pack", manifest)
    validate_domain_pack_shape(pack)
    # Reuse the established graph/evidence validator after removing the new
    # misconception fields that the older CourseRelease contract cannot accept.
    legacy_pack = {key: value for key, value in pack.items()}
    legacy_pack["misconceptions"] = [
        {
            key: value
            for key, value in item.items()
            if key in {"key", "title", "knowledge_point_keys", "evidence_binding_keys"}
        }
        for item in pack.get("misconceptions", [])
    ]
    course_service.validate_course_release_pack("domain_pack", legacy_pack)
    return pack


async def _get_release_or_404(db: AsyncSession, course_id: str, release_id: str) -> DomainRelease:
    release = await db.scalar(
        select(DomainRelease).where(
            DomainRelease.id == release_id,
            DomainRelease.course_id == course_id,
        )
    )
    if release is None:
        raise ApiError(404, "DOMAIN_RELEASE_NOT_FOUND", "领域版本不存在或无权访问")
    return release


async def _latest_decisions(db: AsyncSession, release_id: str) -> dict[str, DomainReviewDecision]:
    rows = await db.execute(
        select(DomainReviewDecision)
        .where(
            DomainReviewDecision.domain_release_id == release_id,
            DomainReviewDecision.object_type == "misconception",
        )
        .order_by(DomainReviewDecision.created_at, DomainReviewDecision.id)
    )
    latest: dict[str, DomainReviewDecision] = {}
    for decision in rows.scalars():
        latest[decision.object_key] = decision
    return latest


def _release_out(
    release: DomainRelease, decisions: dict[str, DomainReviewDecision]
) -> dict[str, Any]:
    data = {
        "id": release.id,
        "course_id": release.course_id,
        "version_no": release.version_no,
        "manifest": release.manifest,
        "pack_sha256": release.pack_sha256,
        "status": release.status,
        "version": release.version,
        "created_by": release.created_by,
        "reviewed_by": release.reviewed_by,
        "reviewed_at": release.reviewed_at.isoformat() if release.reviewed_at else None,
        "review_reason": release.review_reason,
        "published_by": release.published_by,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "supersedes_id": release.supersedes_id,
    }
    pack = release.manifest.get("domain_pack", release.manifest)
    misconceptions = []
    for item in pack.get("misconceptions", []):
        decision = decisions.get(item["key"])
        matches = (
            decision is not None
            and decision.decision == "approved"
            and f"manifest_sha256:{misconception_digest(item)}" in decision.evidence_refs
        )
        misconceptions.append(
            {
                **item,
                "review_state": decision.decision if matches or decision else "candidate",
                "canonical": release.status == "published" and matches,
            }
        )
    if isinstance(pack, dict):
        data["misconceptions"] = misconceptions
    return data


@router.post("/courses/{course_id}/domain-releases", response_model=None, status_code=201)
async def create_domain_release(
    course_id: str,
    body: DomainReleaseCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await require_course_role(course_id, user, db, roles={"teacher", "course_designer"})
    endpoint = "POST:/api/v1/courses/{course_id}/domain-releases"
    payload = {"course_id": course_id, **body.model_dump(mode="json")}
    request_hash = course_service.canonical_request_hash(payload)
    replay = await _idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    pack = _manifest_pack(body.manifest)
    latest = await db.scalar(
        select(DomainRelease.version_no)
        .where(DomainRelease.course_id == course_id)
        .order_by(DomainRelease.version_no.desc())
        .limit(1)
    )
    if body.supersedes_id:
        await _get_release_or_404(db, course_id, body.supersedes_id)
    release = DomainRelease(
        course_id=course_id,
        version_no=(latest or 0) + 1,
        manifest=body.manifest,
        pack_sha256=canonical_json_hash(pack),
        status="draft",
        created_by=user.id,
        supersedes_id=body.supersedes_id,
    )
    db.add(release)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(
            409, "DOMAIN_RELEASE_VERSION_CONFLICT", "领域版本号已被并发占用，请重试"
        ) from exc
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="domain.release_created",
        resource_type="domain_release",
        resource_id=release.id,
        course_id=course_id,
        detail={"version_no": release.version_no, "pack_sha256": release.pack_sha256},
    )
    data = _release_out(release, {})
    await _save_idempotency(
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status=201,
        data=data,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(
            409, "DOMAIN_RELEASE_VERSION_CONFLICT", "领域版本号已被并发占用，请重试"
        ) from exc
    await db.refresh(release)
    return ok(request, data, status_code=201)


@router.get("/courses/{course_id}/domain-releases", response_model=None)
async def list_domain_releases(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    role = await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "assistant", "student", "course_designer", "course_publisher"},
    )
    query = select(DomainRelease).where(DomainRelease.course_id == course_id)
    if role in {"student", "assistant"}:
        query = query.where(DomainRelease.status == "published")
    rows = await db.execute(query.order_by(DomainRelease.version_no.desc()))
    result = []
    for release in rows.scalars():
        result.append(_release_out(release, await _latest_decisions(db, release.id)))
    return ok(request, result, has_more=False)


@router.patch("/courses/{course_id}/domain-releases/{release_id}", response_model=None)
async def update_domain_release(
    course_id: str,
    release_id: str,
    body: DomainReleaseUpdate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await require_course_role(course_id, user, db, roles={"teacher", "course_designer"})
    endpoint = "PATCH:/api/v1/courses/{course_id}/domain-releases/{release_id}"
    payload = {"course_id": course_id, "release_id": release_id, **body.model_dump(mode="json")}
    request_hash = course_service.canonical_request_hash(payload)
    replay = await _idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    release = await db.scalar(
        select(DomainRelease)
        .where(DomainRelease.id == release_id, DomainRelease.course_id == course_id)
        .with_for_update()
    )
    if release is None:
        raise ApiError(404, "DOMAIN_RELEASE_NOT_FOUND", "领域版本不存在或无权访问")
    if release.created_by != user.id and not await _is_course_designer(db, course_id, user.id):
        raise ApiError(404, "DOMAIN_RELEASE_NOT_FOUND", "领域版本不存在或无权访问")
    if release.status != "draft":
        raise ApiError(409, "DOMAIN_RELEASE_IMMUTABLE", "非草稿领域版本不可编辑")
    if release.version != body.expected_version:
        raise ApiError(
            409,
            "DOMAIN_RELEASE_VERSION_CONFLICT",
            "领域草稿已更新，请刷新后重试",
            details={"current_version": release.version},
        )
    pack = _manifest_pack(body.manifest)
    release.manifest = body.manifest
    release.pack_sha256 = canonical_json_hash(pack)
    release.version += 1
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="domain.release_updated",
        resource_type="domain_release",
        resource_id=release.id,
        course_id=course_id,
        detail={"version": release.version, "pack_sha256": release.pack_sha256},
    )
    data = _release_out(release, await _latest_decisions(db, release.id))
    await _save_idempotency(
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status=200,
        data=data,
    )
    await db.commit()
    return ok(request, data)


async def _is_course_designer(db: AsyncSession, course_id: str, user_id: str) -> bool:
    from app.db.models import CourseMember, RoleAssignment

    member = await db.scalar(
        select(CourseMember.id).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == user_id,
            CourseMember.status == "active",
            CourseMember.role == "course_designer",
        )
    )
    if member:
        return True
    assignment = await db.scalar(
        select(RoleAssignment.id).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.scope_type == "course",
            RoleAssignment.scope_id == course_id,
            RoleAssignment.role == "course_designer",
            RoleAssignment.status == "active",
        )
    )
    return assignment is not None


@router.post(
    "/courses/{course_id}/domain-releases/{release_id}/misconceptions/{object_key}/review",
    response_model=None,
)
async def review_misconception(
    course_id: str,
    release_id: str,
    object_key: str,
    body: MisconceptionReview,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await require_course_role(course_id, user, db, roles={"teacher", "course_publisher"})
    endpoint = (
        "POST:/api/v1/courses/{course_id}/domain-releases/"
        "{release_id}/misconceptions/{object_key}/review"
    )
    payload = {
        "course_id": course_id,
        "release_id": release_id,
        "object_key": object_key,
        **body.model_dump(mode="json"),
    }
    request_hash = course_service.canonical_request_hash(payload)
    replay = await _idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    release = await _get_release_or_404(db, course_id, release_id)
    if release.status != "draft":
        raise ApiError(409, "DOMAIN_RELEASE_IMMUTABLE", "非草稿领域版本不可审核")
    if release.created_by == user.id:
        raise ApiError(409, "DOMAIN_REVIEW_SELF_APPROVAL", "作者不能审核自己的 Domain Pack")
    pack = _manifest_pack(release.manifest)
    item = next((x for x in pack.get("misconceptions", []) if x.get("key") == object_key), None)
    if item is None:
        raise ApiError(404, "MISCONCEPTION_NOT_FOUND", "误区对象不存在")
    refs = list(body.evidence_refs)
    binding_keys = {x["key"] for x in pack.get("evidence_bindings", [])}
    if any(ref not in binding_keys for ref in refs):
        raise ApiError(
            422,
            "MISCONCEPTION_REVIEW_EVIDENCE_INVALID",
            "审核证据必须引用当前 Domain Pack 的 EvidenceBinding key",
        )
    if body.decision == "approved" and not set(item["evidence_binding_keys"]).issubset(refs):
        raise ApiError(
            422,
            "MISCONCEPTION_REVIEW_EVIDENCE_REQUIRED",
            "批准时须确认误区声明的全部 EvidenceBinding",
        )
    refs.append(f"manifest_sha256:{misconception_digest(item)}")
    decision = DomainReviewDecision(
        domain_release_id=release.id,
        object_type="misconception",
        object_key=object_key,
        decision=body.decision,
        reviewer_id=user.id,
        reason=body.reason.strip(),
        evidence_refs=refs,
    )
    if not decision.reason:
        raise ApiError(422, "DOMAIN_REVIEW_REASON_REQUIRED", "审核理由不能为空")
    db.add(decision)
    await db.flush()
    release.reviewed_by = user.id
    release.reviewed_at = datetime.now(UTC)
    release.review_reason = decision.reason
    data = {"decision_id": decision.id, "object_key": object_key, "decision": body.decision}
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="domain.misconception_reviewed",
        resource_type="domain_release",
        resource_id=release.id,
        course_id=course_id,
        detail={"object_key": object_key, "decision": body.decision, "reason": decision.reason},
    )
    await _save_idempotency(
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status=200,
        data=data,
    )
    await db.commit()
    return ok(request, data)


@router.post("/courses/{course_id}/domain-releases/{release_id}/publish", response_model=None)
async def publish_domain_release(
    course_id: str,
    release_id: str,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    await require_course_role(course_id, user, db, roles={"teacher", "course_publisher"})
    endpoint = "POST:/api/v1/courses/{course_id}/domain-releases/{release_id}/publish"
    payload = {"course_id": course_id, "release_id": release_id}
    request_hash = course_service.canonical_request_hash(payload)
    replay = await _idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    release = await db.scalar(
        select(DomainRelease)
        .where(DomainRelease.id == release_id, DomainRelease.course_id == course_id)
        .with_for_update()
    )
    if release is None:
        raise ApiError(404, "DOMAIN_RELEASE_NOT_FOUND", "领域版本不存在或无权访问")
    if release.status == "published":
        return ok(request, _release_out(release, await _latest_decisions(db, release.id)))
    if release.status != "draft":
        raise ApiError(409, "DOMAIN_RELEASE_IMMUTABLE", "该领域版本不能发布")
    pack = _manifest_pack(release.manifest)
    decisions = await _latest_decisions(db, release.id)
    for item in pack.get("misconceptions", []):
        decision = decisions.get(item["key"])
        if (
            decision is None
            or decision.reviewer_id == release.created_by
            or decision.decision != "approved"
            or f"manifest_sha256:{misconception_digest(item)}" not in decision.evidence_refs
            or not set(item["evidence_binding_keys"]).issubset(decision.evidence_refs)
        ):
            raise ApiError(
                409,
                "DOMAIN_MISCONCEPTION_REVIEW_REQUIRED",
                "所有误区候选均须由非作者审核通过后才能发布",
                details={"object_key": item["key"]},
            )
    await _validate_publish_evidence(db, course_id, pack)
    previous = await db.scalar(
        select(DomainRelease)
        .where(DomainRelease.course_id == course_id, DomainRelease.status == "published")
        .order_by(DomainRelease.version_no.desc())
        .with_for_update()
    )
    if previous is not None:
        previous.status = "deprecated"
    release.status = "published"
    release.published_by = user.id
    release.published_at = datetime.now(UTC)
    release.reviewed_by = user.id if release.reviewed_by is None else release.reviewed_by
    await course_service.write_audit(
        db,
        actor_id=user.id,
        action="domain.release_published",
        resource_type="domain_release",
        resource_id=release.id,
        course_id=course_id,
        detail={"version_no": release.version_no, "pack_sha256": release.pack_sha256},
    )
    data = _release_out(release, decisions)
    await _save_idempotency(
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status=200,
        data=data,
    )
    await db.commit()
    return ok(request, data)


async def _validate_publish_evidence(
    db: AsyncSession, course_id: str, pack: dict[str, Any]
) -> None:
    bindings = pack.get("evidence_bindings", [])
    material_ids = {item["material_id"] for item in bindings}
    versions: dict[str, str] = {}
    if material_ids:
        rows = await db.execute(
            select(PublicationSnapshot.material_id, PublicationSnapshot.material_version_id)
            .join(Material, Material.id == PublicationSnapshot.material_id)
            .where(
                PublicationSnapshot.material_id.in_(material_ids),
                PublicationSnapshot.superseded_at.is_(None),
                Material.course_id == course_id,
            )
        )
        versions = dict(rows.all())
    source_ids = {item["source_object_id"] for item in bindings}
    sources: dict[str, str] = {}
    if source_ids:
        sources = dict(
            (
                await db.execute(
                    select(KnowledgeObject.id, KnowledgeObject.material_version_id).where(
                        KnowledgeObject.id.in_(source_ids)
                    )
                )
            ).all()
        )
    legacy_pack = {key: value for key, value in pack.items()}
    legacy_pack["misconceptions"] = [
        {
            key: value
            for key, value in item.items()
            if key in {"key", "title", "knowledge_point_keys", "evidence_binding_keys"}
        }
        for item in pack.get("misconceptions", [])
    ]
    course_service.validate_course_release_pack(
        "domain_pack",
        legacy_pack,
        for_publish=True,
        material_ids=material_ids,
        material_versions=versions,
        evidence_sources=sources,
    )
