import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.response import ok
from app.db.models import (
    AuditLog,
    ClassMember,
    Course,
    CourseClass,
    CourseMember,
    CourseRelease,
    CourseReleaseAssignment,
    DomainRelease,
    Job,
    KnowledgeObject,
    Material,
    PublicationSnapshot,
    RetrievalUnit,
    RoleAssignment,
    TeacherAssignment,
    User,
)
from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    get_current_user,
    has_course_scope,
    require_course_role,
)
from app.modules.courses import service
from app.modules.courses.schemas import (
    AdminClassMemberCreate,
    AdminClassTeacherAssignmentCreate,
    AdminClassTeacherAssignmentEnd,
    AdminCourseClassCreate,
    AdminCourseMemberCreate,
    AdminMembershipRemove,
    ClassCreate,
    ClassMemberAdd,
    ClassMemberOut,
    ClassOut,
    CourseCreate,
    CourseUpdate,
    MemberAdd,
    MemberOut,
    MemberRoleUpdate,
    ReleaseAssignmentOut,
    ReleaseAssignmentSet,
    ReleaseCreate,
    ReleaseOut,
    ReleasePreviewOut,
    ReleasePublishRequest,
    ReleaseReviewCreate,
    ReleaseUpdate,
    TeacherAssignmentCreate,
    TeacherAssignmentOut,
)

router = APIRouter()

COURSE_LIST_PAGE_SIZE = 50
COURSES_CREATE_ENDPOINT = "POST:/api/v1/courses"
ADMIN_CLASS_ASSIGN_ENDPOINT = "POST:/api/v1/admin/class-teacher-assignments"
ADMIN_CLASS_END_ENDPOINT = "POST:/api/v1/admin/class-teacher-assignments/{id}/end"
ADMIN_CLASS_CREATE_ENDPOINT = "POST:/api/v1/admin/courses/{course_id}/classes"
ADMIN_COURSE_MEMBER_ADD_ENDPOINT = "POST:/api/v1/admin/courses/{course_id}/members"
ADMIN_COURSE_MEMBER_REMOVE_ENDPOINT = (
    "POST:/api/v1/admin/courses/{course_id}/members/{member_id}/remove"
)
ADMIN_CLASS_MEMBER_ADD_ENDPOINT = "POST:/api/v1/admin/classes/{class_id}/members"
ADMIN_CLASS_MEMBER_REMOVE_ENDPOINT = (
    "POST:/api/v1/admin/classes/{class_id}/members/{member_id}/remove"
)


def _apply_admin_id_cursor(query, model, cursor: str | None):
    if cursor:
        query = query.where(model.id < cursor)
    return query


def _admin_page(rows: list, *, limit: int) -> tuple[list, str | None, bool]:
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1].id if has_more and page else None
    return page, next_cursor, has_more


async def _admin_idempotency_replay(
    request: Request,
    db: AsyncSession,
    *,
    user_id: str,
    endpoint: str,
    key: str,
    request_hash: str,
) -> Response | None:
    previous = await service.find_idempotent_response(
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


async def _commit_admin_idempotent_write(
    request: Request,
    db: AsyncSession,
    *,
    user_id: str,
    endpoint: str,
    key: str,
    request_hash: str,
    status_code: int,
    data: dict,
    conflict_code: str,
) -> Response | None:
    await service.save_idempotent_response(
        db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=request_hash,
        status=status_code,
        body={"data": data},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        replay = await _admin_idempotency_replay(
            request,
            db,
            user_id=user_id,
            endpoint=endpoint,
            key=key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay
        raise ApiError(
            status_code=409,
            code=conflict_code,
            message="资源已被其他管理员更新，请刷新后重试",
        ) from exc
    return None


def _require_platform_admin(user: User) -> None:
    if not user.is_platform_admin:
        raise ApiError(status_code=403, code="FORBIDDEN", message="仅平台管理员可管理机构课程信息")


def _course_release_manifest_sha256(release: CourseRelease) -> str:
    snapshot = {
        "course_id": release.course_id,
        "id": release.id,
        "version_no": release.version_no,
        "version": release.version,
        "name": release.name,
        "domain_release_id": release.domain_release_id,
        "manifest": release.manifest,
    }
    canonical = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


_DOMAIN_SNAPSHOT_KEYS = (
    "knowledge_points",
    "experiments",
    "misconceptions",
    "relations",
    "evidence_bindings",
)


def _domain_pack_from_release(domain_release: DomainRelease) -> dict[str, Any]:
    manifest = domain_release.manifest if isinstance(domain_release.manifest, dict) else {}
    pack = manifest.get("domain_pack", manifest)
    return pack if isinstance(pack, dict) else {}


async def _resolve_domain_release_for_draft(
    db: AsyncSession,
    *,
    course_id: str,
    domain_release_id: str | None,
    domain_pack: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    if domain_release_id is None:
        return None, domain_pack
    domain_release = await db.scalar(
        select(DomainRelease)
        .where(
            DomainRelease.id == domain_release_id,
            DomainRelease.course_id == course_id,
            DomainRelease.status == "published",
        )
        .with_for_update()
    )
    if domain_release is None:
        raise ApiError(
            status_code=409,
            code="RELEASE_DOMAIN_SNAPSHOT_INVALID",
            message="所选 DomainRelease 不存在、未发布或不属于当前课程",
        )
    canonical_pack = _domain_pack_from_release(domain_release)
    if domain_pack and domain_pack != canonical_pack:
        raise ApiError(
            status_code=409,
            code="RELEASE_DOMAIN_SNAPSHOT_MISMATCH",
            message="课程版本领域内容必须与所选 DomainRelease 完全一致",
        )
    return domain_release.id, canonical_pack


def _domain_pack_requires_snapshot(domain_pack: dict[str, Any]) -> bool:
    return any(domain_pack.get(key) for key in _DOMAIN_SNAPSHOT_KEYS)


def _flatten_release_value(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            path = f"{prefix}/{key.replace('~', '~0').replace('/', '~1')}"
            flattened.update(_flatten_release_value(value[key], path))
        return flattened
    return {prefix or "/": value}


def _release_review_rows(release: CourseRelease, rows: list[AuditLog]) -> list[dict[str, Any]]:
    current_hash = _course_release_manifest_sha256(release)
    return [
        {
            "id": row.id,
            "reviewer_id": row.actor_id,
            "reviewer_role": (row.detail or {}).get("reviewer_role"),
            "decision": (row.detail or {}).get("decision"),
            "reason": (row.detail or {}).get("reason"),
            "expected_version": (row.detail or {}).get("expected_version"),
            "manifest_sha256": (row.detail or {}).get("manifest_sha256"),
            "current": (
                (row.detail or {}).get("expected_version") == release.version
                and (row.detail or {}).get("manifest_sha256") == current_hash
            ),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


async def _get_release_reviews(db: AsyncSession, release_id: str) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.action == "course.release_reviewed",
            AuditLog.resource_type == "course_release",
            AuditLog.resource_id == release_id,
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    )
    return list(result.scalars())


async def _pin_current_publication_snapshots(
    db: AsyncSession, *, course_id: str, material_ids: list[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """把草稿当前选中的资料绑定到真实、当前可见的发布快照。"""
    if not material_ids:
        return [], []
    rows = (
        await db.execute(
            select(PublicationSnapshot)
            .join(Material, Material.id == PublicationSnapshot.material_id)
            .where(
                Material.course_id == course_id,
                Material.status == "active",
                Material.visibility == "published",
                Material.current_version_id == PublicationSnapshot.material_version_id,
                Material.id.in_(material_ids),
                PublicationSnapshot.superseded_at.is_(None),
            )
            .with_for_update()
        )
    ).scalars().all()
    by_material_id = {snapshot.material_id: snapshot for snapshot in rows}
    if set(by_material_id) != set(material_ids):
        # 不生成部分版本映射；门禁会给出缺失/未发布资料错误。
        return [], []
    ordered = [by_material_id[material_id] for material_id in material_ids]
    return (
        [snapshot.material_version_id for snapshot in ordered],
        [
            {
                "material_id": snapshot.material_id,
                "material_version_id": snapshot.material_version_id,
                "publication_snapshot_id": snapshot.id,
                "index_job_id": snapshot.index_job_id,
                "embedding_version": snapshot.embedding_version,
                "domain_release_id": snapshot.domain_release_id,
            }
            for snapshot in ordered
        ],
    )


async def _release_gate_report(
    db: AsyncSession, course_id: str, release: CourseRelease
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    manifest = release.manifest if isinstance(release.manifest, dict) else {}
    raw_material_ids = manifest.get("materials", [])
    material_ids_valid = (
        isinstance(raw_material_ids, list)
        and all(isinstance(value, str) and value for value in raw_material_ids)
        and len(set(raw_material_ids)) == len(raw_material_ids)
    )
    material_ids = list(raw_material_ids) if material_ids_valid else []
    material_version_ids = manifest.get("material_version_ids")
    pinned_snapshots = manifest.get("publication_snapshots")
    material_versions: dict[str, str] = {}
    publication_snapshots: list[PublicationSnapshot] = []
    if not material_ids_valid:
        errors.append(
            {
                "code": "RELEASE_MATERIAL_SNAPSHOT_INVALID",
                "message": "课程版本资料 ID 必须是唯一且有效的字符串列表",
            }
        )
    if material_ids:
        if (
            not isinstance(material_version_ids, list)
            or len(material_version_ids) != len(material_ids)
            or any(not isinstance(value, str) or not value for value in material_version_ids)
            or not isinstance(pinned_snapshots, list)
            or len(pinned_snapshots) != len(material_ids)
        ):
            errors.append(
                {
                    "code": "RELEASE_MATERIAL_SNAPSHOT_REQUIRED",
                    "message": (
                        "发布组合必须显式固定每份资料的版本与 PublicationSnapshot；"
                        "请重新选择资料快照"
                    ),
                    "material_ids": material_ids,
                }
            )
        else:
            malformed = False
            for index, material_id in enumerate(material_ids):
                pinned = pinned_snapshots[index]
                if (
                    not isinstance(pinned, dict)
                    or pinned.get("material_id") != material_id
                    or pinned.get("material_version_id") != material_version_ids[index]
                    or not isinstance(pinned.get("publication_snapshot_id"), str)
                    or not isinstance(pinned.get("index_job_id"), str)
                    or not isinstance(pinned.get("embedding_version"), str)
                ):
                    malformed = True
                    break
            if malformed:
                errors.append(
                    {
                        "code": "RELEASE_MATERIAL_SNAPSHOT_INVALID",
                        "message": "课程版本资料快照映射不完整或顺序不匹配",
                        "material_ids": material_ids,
                    }
                )
            else:
                snapshot_ids = [item["publication_snapshot_id"] for item in pinned_snapshots]
                if len(set(snapshot_ids)) != len(snapshot_ids):
                    errors.append(
                        {
                            "code": "RELEASE_MATERIAL_SNAPSHOT_INVALID",
                            "message": "课程版本不能重复引用同一 PublicationSnapshot",
                            "material_ids": material_ids,
                        }
                    )
                else:
                    result = await db.execute(
                        select(PublicationSnapshot)
                        .join(Material, Material.id == PublicationSnapshot.material_id)
                        .where(
                            PublicationSnapshot.id.in_(snapshot_ids),
                            Material.course_id == course_id,
                            Material.status == "active",
                            Material.visibility == "published",
                        )
                        .with_for_update()
                    )
                    snapshots_by_id = {row.id: row for row in result.scalars()}
                    current_snapshot_ids = await db.execute(
                        select(PublicationSnapshot.id)
                        .join(Material, Material.id == PublicationSnapshot.material_id)
                        .where(
                            Material.course_id == course_id,
                            Material.status == "active",
                            Material.visibility == "published",
                            Material.id.in_(material_ids),
                            PublicationSnapshot.superseded_at.is_(None),
                            Material.current_version_id == PublicationSnapshot.material_version_id,
                        )
                    )
                    current_ids = set(current_snapshot_ids.scalars())
                    for index, pinned in enumerate(pinned_snapshots):
                        snapshot = snapshots_by_id.get(pinned["publication_snapshot_id"])
                        if (
                            snapshot is not None
                            and release.domain_release_id is not None
                            and snapshot.domain_release_id != release.domain_release_id
                        ):
                            errors.append(
                                {
                                    "code": "RELEASE_PUBLICATION_DOMAIN_SNAPSHOT_MISMATCH",
                                    "message": "教材发布快照未绑定课程版本指定的 DomainRelease",
                                    "material_id": material_ids[index],
                                    "publication_snapshot_id": snapshot.id,
                                }
                            )
                        if (
                            snapshot is None
                            or snapshot.material_id != material_ids[index]
                            or snapshot.material_version_id != material_version_ids[index]
                            or snapshot.index_job_id != pinned["index_job_id"]
                            or snapshot.embedding_version != pinned["embedding_version"]
                            or snapshot.domain_release_id != pinned.get("domain_release_id")
                            or snapshot.superseded_at is not None
                            or snapshot.id not in current_ids
                        ):
                            errors.append(
                                {
                                    "code": "RELEASE_MATERIAL_SNAPSHOT_STALE",
                                    "message": (
                                        "课程版本固定的资料快照已变化或不再是当前可发布快照；"
                                        "请重新选择资料并复审"
                                    ),
                                    "material_id": material_ids[index],
                                    "publication_snapshot_id": pinned.get(
                                        "publication_snapshot_id"
                                    ),
                                }
                            )
                            continue
                        publication_snapshots.append(snapshot)
                        material_versions[material_id] = snapshot.material_version_id
                    missing_materials = sorted(set(material_ids) - set(material_versions))
                    if missing_materials:
                        errors.append(
                            {
                                "code": "RELEASE_MATERIAL_NOT_PUBLISHED",
                                "message": "发布组合中存在未发布、已停用或不属于当前课程的资料",
                                "material_ids": missing_materials,
                            }
                        )

    domain_pack = manifest.get("domain_pack", {})
    domain = domain_pack if isinstance(domain_pack, dict) else {}
    requires_domain_snapshot = _domain_pack_requires_snapshot(domain)
    if requires_domain_snapshot:
        if not release.domain_release_id:
            errors.append(
                {
                    "code": "RELEASE_DOMAIN_SNAPSHOT_REQUIRED",
                    "message": "包含领域对象的课程版本必须固定一个已发布 DomainRelease",
                }
            )
        else:
            domain_release = await db.scalar(
                select(DomainRelease)
                .where(
                    DomainRelease.id == release.domain_release_id,
                    DomainRelease.course_id == course_id,
                    DomainRelease.status == "published",
                )
                .with_for_update()
            )
            if domain_release is None:
                errors.append(
                    {
                        "code": "RELEASE_DOMAIN_SNAPSHOT_INVALID",
                        "message": "绑定的 DomainRelease 不存在、未发布或不属于当前课程",
                    }
                )
            elif _domain_pack_from_release(domain_release) != domain_pack:
                errors.append(
                    {
                        "code": "RELEASE_DOMAIN_SNAPSHOT_MISMATCH",
                        "message": "课程版本中的领域内容与绑定的 DomainRelease 快照不一致",
                    }
                )

    if requires_domain_snapshot and release.domain_release_id:
        for snapshot in publication_snapshots:
            if snapshot.domain_release_id != release.domain_release_id:
                errors.append(
                    {
                        "code": "RELEASE_PUBLICATION_DOMAIN_SNAPSHOT_MISMATCH",
                        "message": "教材发布快照未绑定课程版本指定的 DomainRelease",
                        "material_id": snapshot.material_id,
                        "publication_snapshot_id": snapshot.id,
                    }
                )
                continue
            index_job = await db.get(Job, snapshot.index_job_id)
            payload = (
                index_job.payload
                if index_job is not None and isinstance(index_job.payload, dict)
                else {}
            )
            if (
                index_job is None
                or index_job.kind != "material_embed"
                or index_job.status != "succeeded"
                or payload.get("material_version_id") != snapshot.material_version_id
                or payload.get("domain_release_id") != release.domain_release_id
            ):
                errors.append(
                    {
                        "code": "RELEASE_DOMAIN_INDEX_JOB_MISMATCH",
                        "message": "教材发布快照未绑定指定领域版本的成功索引任务",
                        "material_id": snapshot.material_id,
                        "publication_snapshot_id": snapshot.id,
                    }
                )
                continue
            unit_count = await db.scalar(
                select(func.count(RetrievalUnit.id)).where(
                    RetrievalUnit.material_version_id == snapshot.material_version_id,
                    RetrievalUnit.domain_release_id == release.domain_release_id,
                    RetrievalUnit.build_version == f"v1-{index_job.id}",
                    RetrievalUnit.status == "ready",
                )
            )
            if not unit_count:
                errors.append(
                    {
                        "code": "RELEASE_DOMAIN_RETRIEVAL_SNAPSHOT_MISSING",
                        "message": "指定领域版本的可检索单元快照不存在",
                        "material_id": snapshot.material_id,
                        "publication_snapshot_id": snapshot.id,
                    }
                )

    source_object_ids = {
        binding.get("source_object_id")
        for binding in domain.get("evidence_bindings", [])
        if isinstance(binding, dict) and isinstance(binding.get("source_object_id"), str)
    }
    evidence_sources: dict[str, str] = {}
    if source_object_ids:
        sources = await db.execute(
            select(KnowledgeObject.id, KnowledgeObject.material_version_id).where(
                KnowledgeObject.id.in_(source_object_ids)
            )
        )
        evidence_sources = dict(sources.all())

    for pack_type in ("domain_pack", "pedagogy_pack", "assessment_pack"):
        try:
            service.validate_course_release_pack(
                pack_type,
                manifest.get(pack_type, {}),
                for_publish=True,
                material_ids=set(material_ids),
                material_versions=material_versions,
                evidence_sources=evidence_sources,
            )
        except ApiError as exc:
            errors.append(
                {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            )

    if release.status != "draft":
        warnings.append(
            {
                "code": "RELEASE_NOT_DRAFT",
                "message": "该版本已离开草稿状态；本门禁仅用于发布前核对",
            }
        )

    review_rows = await _get_release_reviews(db, release.id)
    reviews = _release_review_rows(release, review_rows)
    latest_by_reviewer: dict[str, dict[str, Any]] = {}
    for review in reviews:
        reviewer_id = review["reviewer_id"]
        if reviewer_id and review["current"]:
            latest_by_reviewer[reviewer_id] = review
    approvals = [
        review
        for reviewer_id, review in latest_by_reviewer.items()
        if reviewer_id != release.created_by and review["decision"] == "approved"
    ]
    blocking_reviews = [
        review
        for reviewer_id, review in latest_by_reviewer.items()
        if reviewer_id != release.created_by and review["decision"] != "approved"
    ]
    if not approvals:
        errors.append(
            {
                "code": "RELEASE_REVIEW_REQUIRED",
                "message": "当前草稿版本尚无非作者课程发布者的有效通过审核",
            }
        )
    if blocking_reviews:
        errors.append(
            {
                "code": "RELEASE_REVIEW_BLOCKED",
                "message": "至少一位审核者对当前版本的最新决定尚未通过",
                "review_ids": [review["id"] for review in blocking_reviews],
            }
        )

    return {
        "release_id": release.id,
        "version": release.version,
        "manifest_sha256": _course_release_manifest_sha256(release),
        "errors": errors,
        "warnings": warnings,
        "can_publish": not errors and release.status == "draft",
        "reviews": reviews,
    }


@router.get("/admin/courses", response_model=None)
async def admin_list_courses(
    request: Request,
    status: str = Query(default="active", pattern="^(active|archived|all)$"),
    cursor: str | None = Query(default=None, min_length=26, max_length=26),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """机构内课程治理元数据；不授予管理员教学内容访问权。"""
    _require_platform_admin(user)
    query = select(Course).where(Course.organization_id == user.organization_id)
    if status != "all":
        query = query.where(Course.status == status)
    query = _apply_admin_id_cursor(query, Course, cursor).order_by(Course.id.desc())
    rows = list((await db.execute(query.limit(limit + 1))).scalars())
    page, next_cursor, has_more = _admin_page(rows, limit=limit)
    return ok(
        request,
        [
            {
                "id": course.id,
                "title": course.title,
                "term": course.term,
                "status": course.status,
                "version": course.version,
                "created_at": course.created_at.isoformat(),
            }
            for course in page
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/admin/courses/{course_id}/classes", response_model=None)
async def admin_list_course_classes(
    course_id: str,
    request: Request,
    status: str = Query(default="active", pattern="^(active|archived|all)$"),
    cursor: str | None = Query(default=None, min_length=26, max_length=26),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    course = await db.scalar(
        select(Course.id).where(
            Course.id == course_id,
            Course.organization_id == user.organization_id,
        )
    )
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="同机构课程不存在")
    members = (
        select(ClassMember.class_id.label("class_id"), func.count(ClassMember.id).label("count"))
        .where(ClassMember.status == "active")
        .group_by(ClassMember.class_id)
        .subquery()
    )
    teachers = (
        select(
            TeacherAssignment.class_id.label("class_id"),
            func.count(TeacherAssignment.id).label("count"),
        )
        .where(TeacherAssignment.status == "active")
        .group_by(TeacherAssignment.class_id)
        .subquery()
    )
    query = (
        select(
            CourseClass,
            func.coalesce(members.c.count, 0),
            func.coalesce(teachers.c.count, 0),
        )
        .outerjoin(members, members.c.class_id == CourseClass.id)
        .outerjoin(teachers, teachers.c.class_id == CourseClass.id)
        .where(CourseClass.course_id == course_id)
    )
    if status != "all":
        query = query.where(CourseClass.status == status)
    query = _apply_admin_id_cursor(query, CourseClass, cursor).order_by(CourseClass.id.desc())
    rows = list((await db.execute(query.limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1][0].id if has_more and page else None
    return ok(
        request,
        [
            {
                "id": course_class.id,
                "course_id": course_class.course_id,
                "code": course_class.code,
                "name": course_class.name,
                "status": course_class.status,
                "version": course_class.version,
                "member_count": member_count,
                "active_teacher_count": teacher_count,
                "created_at": course_class.created_at.isoformat(),
                "updated_at": course_class.updated_at.isoformat(),
            }
            for course_class, member_count, teacher_count in page
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/admin/courses/{course_id}/members", response_model=None)
async def admin_list_course_members(
    course_id: str,
    request: Request,
    status: str = Query(default="active", pattern="^(active|removed|all)$"),
    cursor: str | None = Query(default=None, min_length=26, max_length=26),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    course_org_id = await db.scalar(select(Course.organization_id).where(Course.id == course_id))
    if course_org_id != user.organization_id:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="同机构课程不存在")
    query = (
        select(CourseMember, User.display_name)
        .join(User, User.id == CourseMember.user_id)
        .where(
            CourseMember.course_id == course_id,
            User.organization_id == user.organization_id,
        )
    )
    if status != "all":
        query = query.where(CourseMember.status == status)
    if cursor:
        query = query.where(CourseMember.id < cursor)
    query = query.order_by(CourseMember.id.desc())
    rows = list((await db.execute(query.limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return ok(
        request,
        [
            {
                "id": member.id,
                "user_id": member.user_id,
                "display_name": display_name,
                "role": member.role,
                "status": member.status,
                "version": member.version,
                "created_at": member.created_at.isoformat(),
                "updated_at": member.updated_at.isoformat(),
            }
            for member, display_name in page
        ],
        next_cursor=page[-1][0].id if has_more and page else None,
        has_more=has_more,
    )


@router.get("/admin/classes/{class_id}/members", response_model=None)
async def admin_list_class_members(
    class_id: str,
    request: Request,
    status: str = Query(default="active", pattern="^(active|removed|all)$"),
    cursor: str | None = Query(default=None, min_length=26, max_length=26),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    class_org_id = await db.scalar(
        select(Course.organization_id)
        .join(CourseClass, CourseClass.course_id == Course.id)
        .where(CourseClass.id == class_id)
    )
    if class_org_id != user.organization_id:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="同机构班级不存在")
    query = (
        select(ClassMember, User.display_name)
        .join(User, User.id == ClassMember.user_id)
        .where(ClassMember.class_id == class_id, User.organization_id == user.organization_id)
    )
    if status != "all":
        query = query.where(ClassMember.status == status)
    if cursor:
        query = query.where(ClassMember.id < cursor)
    query = query.order_by(ClassMember.id.desc())
    rows = list((await db.execute(query.limit(limit + 1))).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return ok(
        request,
        [
            {
                "id": member.id,
                "user_id": member.user_id,
                "display_name": display_name,
                "status": member.status,
                "version": member.version,
                "created_at": member.created_at.isoformat(),
                "updated_at": member.updated_at.isoformat(),
            }
            for member, display_name in page
        ],
        next_cursor=page[-1][0].id if has_more and page else None,
        has_more=has_more,
    )


@router.post("/admin/courses/{course_id}/classes", response_model=None)
async def admin_create_course_class(
    course_id: str,
    body: AdminCourseClassCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    endpoint = ADMIN_CLASS_CREATE_ENDPOINT.format(course_id=course_id)
    payload = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    course = await db.scalar(
        select(Course)
        .where(
            Course.id == course_id,
            Course.organization_id == user.organization_id,
            Course.status == "active",
        )
        .with_for_update()
    )
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="同机构有效课程不存在")
    duplicate = await db.scalar(
        select(CourseClass.id).where(
            CourseClass.course_id == course_id,
            CourseClass.code == body.code,
        )
    )
    if duplicate is not None:
        raise ApiError(status_code=409, code="CLASS_CODE_ALREADY_EXISTS", message="班级编码已存在")
    course_class = CourseClass(
        course_id=course_id,
        code=body.code,
        name=body.name,
        created_by=user.id,
    )
    db.add(course_class)
    await db.flush()
    await db.refresh(course_class)
    data = {
        "id": course_class.id,
        "course_id": course_id,
        "code": course_class.code,
        "name": course_class.name,
        "status": course_class.status,
        "version": course_class.version,
        "member_count": 0,
        "active_teacher_count": 0,
        "created_at": course_class.created_at.isoformat(),
        "updated_at": course_class.updated_at.isoformat(),
    }
    await service.write_audit(
        db,
        actor_id=user.id,
        action="admin.course_class.created",
        resource_type="course_class",
        resource_id=course_class.id,
        course_id=course_id,
        detail={"code": body.code, "reason": body.reason},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.class_created",
        payload={"class_id": course_class.id, "course_id": course_id, "created_by": user.id},
        producer="courses.admin_governance",
        trace_id=course_class.id,
    )
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=201,
        data=data,
        conflict_code="ADMIN_CLASS_CREATE_CONFLICT",
    )
    return conflict or ok(request, data, status_code=201)


@router.post("/admin/courses/{course_id}/members", response_model=None)
async def admin_add_course_member(
    course_id: str,
    body: AdminCourseMemberCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    if body.user_id == user.id:
        raise ApiError(
            status_code=409,
            code="ROLE_SELF_ASSIGNMENT_FORBIDDEN",
            message="管理员不能通过成员管理为自己新增课程访问权",
        )
    endpoint = ADMIN_COURSE_MEMBER_ADD_ENDPOINT.format(course_id=course_id)
    payload = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    course = await db.scalar(
        select(Course)
        .where(
            Course.id == course_id,
            Course.organization_id == user.organization_id,
            Course.status == "active",
        )
        .with_for_update()
    )
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="同机构有效课程不存在")
    target = await db.scalar(
        select(User).where(
            User.id == body.user_id,
            User.organization_id == user.organization_id,
            User.status == "active",
        )
    )
    if target is None:
        raise ApiError(status_code=404, code="USER_NOT_FOUND", message="同机构有效账号不存在")
    member = await db.scalar(
        select(CourseMember)
        .where(CourseMember.course_id == course_id, CourseMember.user_id == target.id)
        .with_for_update()
    )
    if member is not None and member.status == "active":
        raise ApiError(status_code=409, code="MEMBER_ALREADY_EXISTS", message="该用户已是课程成员")
    if member is None:
        member = CourseMember(course_id=course_id, user_id=target.id, role=body.role)
        db.add(member)
    else:
        member.status = "active"
        member.role = body.role
        member.version += 1
    await db.flush()
    await db.refresh(member)
    data = {
        "id": member.id,
        "user_id": member.user_id,
        "display_name": target.display_name,
        "role": member.role,
        "status": member.status,
        "version": member.version,
        "created_at": member.created_at.isoformat(),
        "updated_at": member.updated_at.isoformat(),
    }
    await service.write_audit(
        db,
        actor_id=user.id,
        action="admin.course_member.added",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course_id,
        detail={"target_user_id": target.id, "role": member.role, "reason": body.reason},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.member_added",
        payload={"course_id": course_id, "user_id": target.id, "role": member.role},
        producer="courses.admin_governance",
        trace_id=member.id,
    )
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=201,
        data=data,
        conflict_code="ADMIN_MEMBER_ADD_CONFLICT",
    )
    return conflict or ok(request, data, status_code=201)


@router.post("/admin/courses/{course_id}/members/{member_id}/remove", response_model=None)
async def admin_remove_course_member(
    course_id: str,
    member_id: str,
    body: AdminMembershipRemove,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    endpoint = ADMIN_COURSE_MEMBER_REMOVE_ENDPOINT.format(course_id=course_id, member_id=member_id)
    payload = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    row = await db.execute(
        select(CourseMember, Course)
        .join(Course, Course.id == CourseMember.course_id)
        .where(
            CourseMember.id == member_id,
            CourseMember.course_id == course_id,
            Course.organization_id == user.organization_id,
        )
        .with_for_update(of=CourseMember)
    )
    member, course = row.one_or_none() or (None, None)
    if member is None:
        raise ApiError(status_code=404, code="COURSE_MEMBER_NOT_FOUND", message="同机构成员不存在")
    if member.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="课程成员信息已更新，请刷新后重试",
            details={"expected_version": body.version, "actual_version": member.version},
        )
    if member.status != "active":
        raise ApiError(status_code=409, code="MEMBER_NOT_ACTIVE", message="成员已移除")
    member.status = "removed"
    member.version += 1
    removed_class_members = 0
    ended_teacher_assignments = 0
    if member.role == "student":
        class_members = list(
            (
                await db.execute(
                    select(ClassMember)
                    .join(CourseClass, CourseClass.id == ClassMember.class_id)
                    .where(
                        CourseClass.course_id == course_id,
                        ClassMember.user_id == member.user_id,
                        ClassMember.status == "active",
                    )
                    .with_for_update(of=ClassMember)
                )
            ).scalars()
        )
        for class_member in class_members:
            class_member.status = "removed"
            class_member.version += 1
        removed_class_members = len(class_members)
    elif member.role in {"teacher", "assistant"}:
        assignments = list(
            (
                await db.execute(
                    select(TeacherAssignment)
                    .join(CourseClass, CourseClass.id == TeacherAssignment.class_id)
                    .where(
                        CourseClass.course_id == course_id,
                        TeacherAssignment.teacher_id == member.user_id,
                        TeacherAssignment.status == "active",
                    )
                    .with_for_update(of=TeacherAssignment)
                )
            ).scalars()
        )
        for assignment in assignments:
            assignment.status = "ended"
            assignment.version += 1
        ended_teacher_assignments = len(assignments)
    data = {"id": member.id, "status": member.status, "version": member.version}
    await service.write_audit(
        db,
        actor_id=user.id,
        action="admin.course_member.removed",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course_id,
        detail={
            "target_user_id": member.user_id,
            "role": member.role,
            "reason": body.reason,
            "removed_class_members": removed_class_members,
            "ended_teacher_assignments": ended_teacher_assignments,
        },
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.member_removed",
        payload={"course_id": course_id, "user_id": member.user_id, "member_id": member.id},
        producer="courses.admin_governance",
        trace_id=member.id,
    )
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=200,
        data=data,
        conflict_code="ADMIN_MEMBER_REMOVE_CONFLICT",
    )
    return conflict or ok(request, data)


@router.post("/admin/classes/{class_id}/members", response_model=None)
async def admin_add_class_member(
    class_id: str,
    body: AdminClassMemberCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    endpoint = ADMIN_CLASS_MEMBER_ADD_ENDPOINT.format(class_id=class_id)
    payload = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    row = await db.execute(
        select(CourseClass, Course)
        .join(Course, Course.id == CourseClass.course_id)
        .where(
            CourseClass.id == class_id,
            CourseClass.status == "active",
            Course.status == "active",
            Course.organization_id == user.organization_id,
        )
        .with_for_update(of=CourseClass)
    )
    course_class, course = row.one_or_none() or (None, None)
    if course_class is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="同机构有效班级不存在")
    membership = await db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course.id,
            CourseMember.user_id == body.user_id,
            CourseMember.role == "student",
            CourseMember.status == "active",
        )
    )
    if membership is None:
        raise ApiError(
            status_code=409,
            code="STUDENT_NOT_COURSE_MEMBER",
            message="学生必须先加入该课程",
        )
    target = await db.scalar(
        select(User).where(
            User.id == body.user_id,
            User.organization_id == user.organization_id,
            User.status == "active",
        )
    )
    if target is None:
        raise ApiError(status_code=404, code="USER_NOT_FOUND", message="同机构有效学生不存在")
    member = await db.scalar(
        select(ClassMember)
        .where(ClassMember.class_id == class_id, ClassMember.user_id == target.id)
        .with_for_update()
    )
    if member is not None and member.status == "active":
        raise ApiError(
            status_code=409,
            code="CLASS_MEMBER_ALREADY_EXISTS",
            message="学生已在该班级",
        )
    if member is None:
        member = ClassMember(class_id=class_id, user_id=target.id)
        db.add(member)
    else:
        member.status = "active"
        member.version += 1
    await db.flush()
    await db.refresh(member)
    data = {
        "id": member.id,
        "user_id": member.user_id,
        "display_name": target.display_name,
        "status": member.status,
        "version": member.version,
        "created_at": member.created_at.isoformat(),
        "updated_at": member.updated_at.isoformat(),
    }
    await service.write_audit(
        db,
        actor_id=user.id,
        action="admin.class_member.added",
        resource_type="class_member",
        resource_id=member.id,
        course_id=course.id,
        detail={"class_id": class_id, "target_user_id": target.id, "reason": body.reason},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.class_member_added",
        payload={"class_id": class_id, "course_id": course.id, "user_id": target.id},
        producer="courses.admin_governance",
        trace_id=member.id,
    )
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=201,
        data=data,
        conflict_code="ADMIN_CLASS_MEMBER_ADD_CONFLICT",
    )
    return conflict or ok(request, data, status_code=201)


@router.post("/admin/classes/{class_id}/members/{member_id}/remove", response_model=None)
async def admin_remove_class_member(
    class_id: str,
    member_id: str,
    body: AdminMembershipRemove,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    endpoint = ADMIN_CLASS_MEMBER_REMOVE_ENDPOINT.format(class_id=class_id, member_id=member_id)
    payload = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    row = await db.execute(
        select(ClassMember, Course.id)
        .join(CourseClass, CourseClass.id == ClassMember.class_id)
        .join(Course, Course.id == CourseClass.course_id)
        .where(
            ClassMember.id == member_id,
            ClassMember.class_id == class_id,
            Course.organization_id == user.organization_id,
        )
        .with_for_update(of=ClassMember)
    )
    member, course_id = row.one_or_none() or (None, None)
    if member is None:
        raise ApiError(
            status_code=404,
            code="CLASS_MEMBER_NOT_FOUND",
            message="同机构班级成员不存在",
        )
    if member.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="班级成员信息已更新，请刷新后重试",
            details={"expected_version": body.version, "actual_version": member.version},
        )
    if member.status != "active":
        raise ApiError(status_code=409, code="MEMBER_NOT_ACTIVE", message="成员已移除")
    member.status = "removed"
    member.version += 1
    data = {"id": member.id, "status": member.status, "version": member.version}
    await service.write_audit(
        db,
        actor_id=user.id,
        action="admin.class_member.removed",
        resource_type="class_member",
        resource_id=member.id,
        course_id=course_id,
        detail={"class_id": class_id, "target_user_id": member.user_id, "reason": body.reason},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.class_member_removed",
        payload={"class_id": class_id, "course_id": course_id, "user_id": member.user_id},
        producer="courses.admin_governance",
        trace_id=member.id,
    )
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=200,
        data=data,
        conflict_code="ADMIN_CLASS_MEMBER_REMOVE_CONFLICT",
    )
    return conflict or ok(request, data)


@router.post("/courses", response_model=None)
async def create_course(
    body: CourseCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    if not user.is_teacher:
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="仅已启用教师身份的账号可创建课程",
        )
    payload: dict[str, Any] = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(payload)

    if idempotency_key:
        previous = await service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=COURSES_CREATE_ENDPOINT,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(
                request,
                previous["body"]["data"],
                status_code=previous["status"],
            )

    course = await service.create_course_with_membership(
        db,
        creator=user,
        title=body.title,
        term=body.term,
        description=body.description,
        timezone=body.timezone,
    )
    body_data = service.course_out(course)

    if idempotency_key:
        try:
            await service.save_idempotent_response(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=COURSES_CREATE_ENDPOINT,
                request_hash=request_hash,
                status=201,
                body={"data": body_data},
            )
            await db.commit()
        except IntegrityError:
            await db.rollback()
            previous = await service.find_idempotent_response(
                db,
                key=idempotency_key,
                user_id=user.id,
                endpoint=COURSES_CREATE_ENDPOINT,
                request_hash=request_hash,
            )
            if previous is None:
                raise
            return ok(request, previous["body"]["data"], status_code=previous["status"])
    else:
        await db.commit()

    return ok(request, body_data, status_code=201)


@router.get("/courses", response_model=None)
async def list_courses(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=COURSE_LIST_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    query = select(Course).where(Course.status == "active").order_by(Course.id.desc())
    member_courses = select(CourseMember.course_id).where(
        CourseMember.user_id == user.id,
        CourseMember.status == "active",
    )
    scoped_courses = select(RoleAssignment.scope_id).where(
        RoleAssignment.user_id == user.id,
        RoleAssignment.scope_type == "course",
        RoleAssignment.status == "active",
    )
    query = query.where(Course.id.in_(member_courses.union(scoped_courses)))
    if cursor:
        query = query.where(Course.id < cursor)
    result = await db.execute(query.limit(limit + 1))
    courses = list(result.scalars())
    has_more = len(courses) > limit
    items = [service.course_out(c) for c in courses[:limit]]
    next_cursor = courses[:limit][-1].id if has_more and courses else None
    return ok(request, items, next_cursor=next_cursor, has_more=has_more)


@router.get("/courses/{course_id}", response_model=None)
async def get_course(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    course = await service.get_course_or_404(db, course_id)
    if not await has_course_scope(user, course.id, db):
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    return ok(request, service.course_out(course))


@router.patch("/courses/{course_id}", response_model=None)
async def update_course(
    course_id: str,
    body: CourseUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    course = await service.get_course_or_404(db, course_id)
    if course.status == "archived" and body.status != "active":
        raise ApiError(status_code=409, code="COURSE_ARCHIVED", message="课程已归档")
    if course.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="课程已被其他人修改，请刷新后重试",
            details={"expected_version": body.version, "actual_version": course.version},
        )
    updates = body.model_dump(exclude={"version"}, exclude_none=True)
    for field, value in updates.items():
        setattr(course, field, value)
    course.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.updated",
        resource_type="course",
        resource_id=course.id,
        course_id=course.id,
        detail={"fields": sorted(updates), "new_version": course.version},
    )
    await db.commit()
    await db.refresh(course)
    return ok(request, service.course_out(course))


@router.post("/courses/{course_id}/members", response_model=None)
async def add_member(
    course_id: str,
    body: MemberAdd,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    course = await service.get_course_or_404(db, course_id)
    target_result = await db.execute(select(User).where(User.id == body.user_id).limit(1))
    target = target_result.scalar_one_or_none()
    if target is None:
        raise ApiError(status_code=404, code="USER_NOT_FOUND", message="用户不存在")
    if target.status != "active":
        raise ApiError(status_code=409, code="USER_DISABLED", message="不能添加已停用的账号")
    existing = await service.get_active_membership(db, course_id=course.id, user_id=body.user_id)
    if existing is not None:
        raise ApiError(
            status_code=409,
            code="MEMBER_ALREADY_EXISTS",
            message="该用户已是课程成员",
        )
    existing_row_result = await db.execute(
        select(CourseMember).where(
            CourseMember.course_id == course.id,
            CourseMember.user_id == body.user_id,
        )
    )
    existing_row = existing_row_result.scalar_one_or_none()
    if existing_row is not None:
        existing_row.status = "active"
        existing_row.role = body.role
        existing_row.version += 1
        member = existing_row
    else:
        member = CourseMember(
            course_id=course.id,
            user_id=body.user_id,
            role=body.role,
            status="active",
        )
        db.add(member)
    await db.flush()
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.member_added",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course.id,
        detail={"target_user_id": body.user_id, "role": body.role},
    )
    await db.commit()
    data = MemberOut(
        id=member.id,
        user_id=member.user_id,
        display_name=target.display_name,
        role=member.role,
        status=member.status,
        joined_at=member.created_at,
    ).model_dump(mode="json")
    return ok(request, data, status_code=201)


@router.patch("/courses/{course_id}/members/{member_id}", response_model=None)
async def update_member_role(
    course_id: str,
    member_id: str,
    body: MemberRoleUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    member = await service.get_member_or_404(db, course_id=course_id, member_id=member_id)
    if member.status != "active":
        raise ApiError(status_code=409, code="MEMBER_NOT_ACTIVE", message="成员已不在课程中")
    if member.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="成员信息已被修改，请刷新后重试",
            details={"expected_version": body.version, "actual_version": member.version},
        )
    old_role = member.role
    member.role = body.role
    member.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.member_role_changed",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course_id,
        detail={"old_role": old_role, "new_role": body.role},
    )
    await db.commit()
    return ok(
        request,
        {
            "id": member.id,
            "user_id": member.user_id,
            "role": member.role,
            "version": member.version,
        },
    )


@router.delete("/courses/{course_id}/members/{member_id}", response_model=None)
async def remove_member(
    course_id: str,
    member_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    member = await service.get_member_or_404(db, course_id=course_id, member_id=member_id)
    if member.status == "removed":
        raise ApiError(status_code=409, code="MEMBER_NOT_ACTIVE", message="成员已移除")
    member.status = "removed"
    member.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.member_removed",
        resource_type="course_member",
        resource_id=member.id,
        course_id=course_id,
        detail={"target_user_id": member.user_id},
    )
    await db.commit()
    return ok(request, {"id": member.id, "status": member.status})


@router.get("/courses/{course_id}/members", response_model=None)
async def list_members(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant", "student"})
    result = await db.execute(
        select(CourseMember, User.display_name)
        .join(User, User.id == CourseMember.user_id)
        .where(CourseMember.course_id == course_id, CourseMember.status == "active")
        .order_by(CourseMember.created_at.asc())
    )
    items = [
        MemberOut(
            id=member.id,
            user_id=member.user_id,
            display_name=display_name,
            role=member.role,
            status=member.status,
            joined_at=member.created_at,
        ).model_dump(mode="json")
        for member, display_name in result.all()
    ]
    return ok(request, items, has_more=False)


@router.post("/courses/{course_id}/classes", response_model=None)
async def create_class(
    course_id: str,
    body: ClassCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    await service.get_course_or_404(db, course_id)
    duplicate = await db.scalar(
        select(CourseClass).where(CourseClass.course_id == course_id, CourseClass.code == body.code)
    )
    if duplicate is not None:
        raise ApiError(status_code=409, code="CLASS_CODE_ALREADY_EXISTS", message="班级编码已存在")
    item = CourseClass(course_id=course_id, code=body.code, name=body.name, created_by=user.id)
    db.add(item)
    await db.flush()
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.class_created",
        resource_type="course_class",
        resource_id=item.id,
        course_id=course_id,
        detail={"code": body.code, "name": body.name},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.class_created",
        payload={"class_id": item.id, "course_id": course_id, "created_by": user.id},
        producer="courses.router",
        trace_id=item.id,
    )
    await db.commit()
    await db.refresh(item)
    data = ClassOut.model_validate(item, from_attributes=True).model_dump(mode="json")
    return ok(request, data, status_code=201)


@router.get("/courses/{course_id}/classes", response_model=None)
async def list_classes(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant", "student"})
    result = await db.execute(
        select(CourseClass)
        .where(CourseClass.course_id == course_id, CourseClass.status == "active")
        .order_by(CourseClass.code.asc(), CourseClass.id.asc())
    )
    items = [
        ClassOut.model_validate(item, from_attributes=True).model_dump(mode="json")
        for item in result.scalars()
    ]
    return ok(request, items, has_more=False)


@router.post("/courses/{course_id}/classes/{class_id}/teachers", response_model=None)
async def assign_teacher(
    course_id: str,
    class_id: str,
    body: TeacherAssignmentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    course_class = await db.scalar(
        select(CourseClass).where(CourseClass.id == class_id, CourseClass.course_id == course_id)
    )
    if course_class is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    target = await db.scalar(select(User).where(User.id == body.teacher_id))
    if target is None or target.status != "active":
        raise ApiError(status_code=404, code="TEACHER_NOT_FOUND", message="教师账号不存在或不可用")
    membership = await db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == body.teacher_id,
            CourseMember.role.in_({"teacher", "assistant"}),
            CourseMember.status == "active",
        )
    )
    if membership is None:
        raise ApiError(
            status_code=409,
            code="TEACHER_NOT_COURSE_MEMBER",
            message="任课教师必须先加入课程",
        )
    assignment = await db.scalar(
        select(TeacherAssignment).where(
            TeacherAssignment.class_id == class_id, TeacherAssignment.teacher_id == body.teacher_id
        )
    )
    if assignment is not None and assignment.status == "active":
        raise ApiError(
            status_code=409,
            code="TEACHER_ALREADY_ASSIGNED",
            message="该教师已分配到此班级",
        )
    if assignment is None:
        assignment = TeacherAssignment(
            class_id=class_id,
            teacher_id=body.teacher_id,
            assignment_role=body.assignment_role,
            assigned_by=user.id,
        )
        db.add(assignment)
    else:
        assignment.assignment_role = body.assignment_role
        assignment.status = "active"
        assignment.assigned_by = user.id
        assignment.version += 1
    await db.flush()
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.teacher_assigned",
        resource_type="teacher_assignment",
        resource_id=assignment.id,
        course_id=course_id,
        detail={"class_id": class_id, "teacher_id": body.teacher_id, "role": body.assignment_role},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.teacher_assigned",
        payload={"class_id": class_id, "teacher_id": body.teacher_id, "assigned_by": user.id},
        producer="courses.router",
        trace_id=assignment.id,
    )
    await db.commit()
    await db.refresh(assignment)
    return ok(
        request,
        TeacherAssignmentOut(
            id=assignment.id,
            class_id=assignment.class_id,
            teacher_id=assignment.teacher_id,
            teacher_name=target.display_name,
            assignment_role=assignment.assignment_role,
            status=assignment.status,
            version=assignment.version,
            assigned_by=assignment.assigned_by,
            created_at=assignment.created_at,
        ).model_dump(mode="json"),
        status_code=201,
    )


@router.get("/courses/{course_id}/classes/{class_id}/teachers", response_model=None)
async def list_class_teachers(
    course_id: str,
    class_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant", "student"})
    class_exists = await db.scalar(
        select(CourseClass.id).where(CourseClass.id == class_id, CourseClass.course_id == course_id)
    )
    if class_exists is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    result = await db.execute(
        select(TeacherAssignment, User.display_name)
        .join(User, User.id == TeacherAssignment.teacher_id)
        .where(TeacherAssignment.class_id == class_id, TeacherAssignment.status == "active")
        .order_by(TeacherAssignment.created_at.asc(), TeacherAssignment.id.asc())
    )
    items = [
        TeacherAssignmentOut(
            id=item.id,
            class_id=item.class_id,
            teacher_id=item.teacher_id,
            teacher_name=name,
            assignment_role=item.assignment_role,
            status=item.status,
            version=item.version,
            assigned_by=item.assigned_by,
            created_at=item.created_at,
        ).model_dump(mode="json")
        for item, name in result.all()
    ]
    return ok(request, items, has_more=False)


@router.post("/courses/{course_id}/classes/{class_id}/members", response_model=None)
async def add_class_member(
    course_id: str,
    class_id: str,
    body: ClassMemberAdd,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher"})
    class_exists = await db.scalar(
        select(CourseClass.id).where(
            CourseClass.id == class_id,
            CourseClass.course_id == course_id,
            CourseClass.status == "active",
        )
    )
    if class_exists is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    membership = await db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == body.user_id,
            CourseMember.role == "student",
            CourseMember.status == "active",
        )
    )
    if membership is None:
        raise ApiError(
            status_code=409,
            code="STUDENT_NOT_COURSE_MEMBER",
            message="学生必须先加入课程",
        )
    target = await db.scalar(select(User).where(User.id == body.user_id))
    item = await db.scalar(
        select(ClassMember).where(
            ClassMember.class_id == class_id, ClassMember.user_id == body.user_id
        )
    )
    if item is not None and item.status == "active":
        raise ApiError(
            status_code=409, code="CLASS_MEMBER_ALREADY_EXISTS", message="学生已在该班级"
        )
    if item is None:
        item = ClassMember(class_id=class_id, user_id=body.user_id)
        db.add(item)
    else:
        item.status = "active"
        item.version += 1
    await db.commit()
    await db.refresh(item)
    return ok(
        request,
        ClassMemberOut(
            id=item.id,
            class_id=item.class_id,
            user_id=item.user_id,
            display_name=target.display_name,
            status=item.status,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
        ).model_dump(mode="json"),
        status_code=201,
    )


@router.get("/courses/{course_id}/classes/{class_id}/members", response_model=None)
async def list_class_members(
    course_id: str,
    class_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "assistant"})
    class_exists = await db.scalar(
        select(CourseClass.id).where(CourseClass.id == class_id, CourseClass.course_id == course_id)
    )
    if class_exists is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    rows = await db.execute(
        select(ClassMember, User.display_name)
        .join(User, User.id == ClassMember.user_id)
        .where(ClassMember.class_id == class_id, ClassMember.status == "active")
        .order_by(User.display_name.asc(), ClassMember.id.asc())
    )
    items = [
        ClassMemberOut(
            id=item.id,
            class_id=item.class_id,
            user_id=item.user_id,
            display_name=name,
            status=item.status,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
        ).model_dump(mode="json")
        for item, name in rows.all()
    ]
    return ok(request, items, has_more=False)


@router.post("/courses/{course_id}/releases", response_model=None)
async def create_release(
    course_id: str,
    body: ReleaseCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "course_designer"})
    await service.get_course_or_404(db, course_id)
    domain_release_id, domain_pack = await _resolve_domain_release_for_draft(
        db,
        course_id=course_id,
        domain_release_id=body.domain_release_id,
        domain_pack=body.domain_pack,
    )
    for pack_type, pack in (
        ("domain_pack", domain_pack),
        ("pedagogy_pack", body.pedagogy_pack),
        ("assessment_pack", body.assessment_pack),
    ):
        service.validate_course_release_pack(pack_type, pack)
    material_ids = list(body.material_ids)
    if len(set(material_ids)) != len(material_ids):
        raise ApiError(
            status_code=422,
            code="RELEASE_MATERIAL_DUPLICATE",
            message="课程版本不能重复选择同一资料",
        )
    if material_ids:
        result = await db.execute(
            select(Material.id).where(
                Material.course_id == course_id,
                Material.id.in_(material_ids),
                Material.status == "active",
            )
        )
        found = set(result.scalars())
        if found != set(material_ids):
            raise ApiError(
                status_code=409,
                code="RELEASE_CROSS_COURSE_ASSET",
                message="发布组合包含不属于当前课程的资料",
            )
    latest = await db.scalar(
        select(CourseRelease.version_no)
        .where(CourseRelease.course_id == course_id)
        .order_by(CourseRelease.version_no.desc())
        .limit(1)
    )
    material_version_ids, publication_snapshots = await _pin_current_publication_snapshots(
        db, course_id=course_id, material_ids=material_ids
    )
    release = CourseRelease(
        course_id=course_id,
        version_no=(latest or 0) + 1,
        name=body.name,
        manifest={
            "materials": material_ids,
            "material_version_ids": material_version_ids,
            "publication_snapshots": publication_snapshots,
            "domain_pack": domain_pack,
            "pedagogy_pack": body.pedagogy_pack,
            "assessment_pack": body.assessment_pack,
            "schema_version": "course-release.v1",
        },
        domain_release_id=domain_release_id,
        created_by=user.id,
    )
    db.add(release)
    await db.flush()
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.release_created",
        resource_type="course_release",
        resource_id=release.id,
        course_id=course_id,
        detail={
            "version_no": release.version_no,
            "material_count": len(material_ids),
            "domain_release_id": domain_release_id,
        },
    )
    await db.commit()
    await db.refresh(release)
    return ok(
        request,
        ReleaseOut.model_validate(release, from_attributes=True).model_dump(mode="json"),
        status_code=201,
    )


@router.patch("/courses/{course_id}/releases/{release_id}", response_model=None)
async def update_release(
    course_id: str,
    release_id: str,
    body: ReleaseUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(course_id, user, db, roles={"teacher", "course_designer"})
    release = await db.scalar(
        select(CourseRelease)
        .where(CourseRelease.id == release_id, CourseRelease.course_id == course_id)
        .with_for_update()
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    if release.version != body.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="课程版本已变化，请刷新后再编辑",
            details={"actual_version": release.version},
        )
    if release.status != "draft":
        raise ApiError(
            status_code=409,
            code="RELEASE_NOT_EDITABLE",
            message="已发布课程版本不可修改",
        )
    material_ids = (
        list(body.material_ids)
        if body.material_ids is not None
        else list(release.manifest.get("materials", []))
    )
    if body.material_ids is not None and len(set(material_ids)) != len(material_ids):
        raise ApiError(
            status_code=422,
            code="RELEASE_MATERIAL_DUPLICATE",
            message="课程版本不能重复选择同一资料",
        )
    if body.material_ids is not None and material_ids:
        result = await db.execute(
            select(Material.id).where(
                Material.course_id == course_id,
                Material.id.in_(material_ids),
                Material.status == "active",
            )
        )
        if set(result.scalars()) != set(material_ids):
            raise ApiError(
                status_code=409,
                code="RELEASE_CROSS_COURSE_ASSET",
                message="发布组合包含不属于当前课程的资料",
            )
    domain_release_id = release.domain_release_id
    domain_pack = (
        body.domain_pack
        if body.domain_pack is not None
        else release.manifest.get("domain_pack", {})
    )
    if "domain_release_id" in body.model_fields_set:
        domain_release_id = body.domain_release_id
        if (
            body.domain_release_id
            and body.domain_release_id != release.domain_release_id
            and body.domain_pack is None
        ):
            domain_pack = {}
    domain_release_id, domain_pack = await _resolve_domain_release_for_draft(
        db,
        course_id=course_id,
        domain_release_id=domain_release_id,
        domain_pack=domain_pack,
    )
    manifest = dict(release.manifest)
    if body.material_ids is not None:
        material_version_ids, publication_snapshots = (
            await _pin_current_publication_snapshots(
                db, course_id=course_id, material_ids=material_ids
            )
        )
        manifest["materials"] = material_ids
        manifest["material_version_ids"] = material_version_ids
        manifest["publication_snapshots"] = publication_snapshots
    for key, value in (
        ("domain_pack", domain_pack),
        ("pedagogy_pack", body.pedagogy_pack),
        ("assessment_pack", body.assessment_pack),
    ):
        if value is not None:
            service.validate_course_release_pack(key, value)
            manifest[key] = value
    release.manifest = manifest
    release.domain_release_id = domain_release_id
    if body.name is not None:
        release.name = body.name
    release.version += 1
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.release_updated",
        resource_type="course_release",
        resource_id=release.id,
        course_id=course_id,
        detail={"version_no": release.version_no, "resource_version": release.version},
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.release_updated",
        payload={"course_id": course_id, "release_id": release.id},
        producer="courses.router",
        trace_id=release.id,
    )
    await db.commit()
    await db.refresh(release)
    return ok(
        request,
        ReleaseOut.model_validate(release, from_attributes=True).model_dump(mode="json"),
    )


@router.get("/courses/{course_id}/releases", response_model=None)
async def list_releases(
    course_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "assistant", "student", "course_designer", "course_publisher"},
    )
    result = await db.execute(
        select(CourseRelease)
        .where(CourseRelease.course_id == course_id)
        .order_by(CourseRelease.version_no.desc())
    )
    items = [
        ReleaseOut.model_validate(item, from_attributes=True).model_dump(mode="json")
        for item in result.scalars()
    ]
    return ok(request, items, has_more=False)


@router.get("/courses/{course_id}/releases/{release_id}/preview", response_model=None)
async def preview_release(
    course_id: str,
    release_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "course_designer", "course_publisher"},
    )
    release = await db.scalar(
        select(CourseRelease).where(
            CourseRelease.id == release_id,
            CourseRelease.course_id == course_id,
        )
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    data = ReleasePreviewOut(
        release=ReleaseOut.model_validate(release, from_attributes=True),
        manifest_sha256=_course_release_manifest_sha256(release),
    ).model_dump(mode="json")
    return ok(request, data)


@router.get("/courses/{course_id}/releases/{release_id}/diff", response_model=None)
async def diff_releases(
    course_id: str,
    release_id: str,
    request: Request,
    against_release_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "course_designer", "course_publisher"},
    )
    if release_id == against_release_id:
        raise ApiError(
            status_code=422, code="RELEASE_DIFF_SAME_VERSION", message="版本差异需要两个不同快照"
        )
    rows = await db.execute(
        select(CourseRelease).where(
            CourseRelease.course_id == course_id,
            CourseRelease.id.in_({release_id, against_release_id}),
        )
    )
    releases = {item.id: item for item in rows.scalars()}
    left = releases.get(release_id)
    right = releases.get(against_release_id)
    if left is None or right is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    if left.status not in {"published", "deprecated"} or right.status not in {
        "published",
        "deprecated",
    }:
        raise ApiError(
            status_code=409,
            code="RELEASE_DIFF_REQUIRES_IMMUTABLE_SNAPSHOTS",
            message="差异只支持两个不可变的已发布课程版本",
        )
    before = _flatten_release_value({"name": left.name, "manifest": left.manifest})
    after = _flatten_release_value({"name": right.name, "manifest": right.manifest})
    changes = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            changes.append({"path": path, "kind": "added", "after": after[path]})
        elif path not in after:
            changes.append({"path": path, "kind": "removed", "before": before[path]})
        elif before[path] != after[path]:
            changes.append(
                {
                    "path": path,
                    "kind": "changed",
                    "before": before[path],
                    "after": after[path],
                }
            )
    return ok(
        request,
        {
            "base": {
                "id": left.id,
                "version_no": left.version_no,
                "manifest_sha256": _course_release_manifest_sha256(left),
            },
            "target": {
                "id": right.id,
                "version_no": right.version_no,
                "manifest_sha256": _course_release_manifest_sha256(right),
            },
            "changes": changes,
        },
        has_more=False,
    )


@router.get("/courses/{course_id}/releases/{release_id}/gate", response_model=None)
async def get_release_gate(
    course_id: str,
    release_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "course_designer", "course_publisher"},
    )
    release = await db.scalar(
        select(CourseRelease).where(
            CourseRelease.id == release_id,
            CourseRelease.course_id == course_id,
        )
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    return ok(request, await _release_gate_report(db, course_id, release))


@router.post("/courses/{course_id}/releases/{release_id}/reviews", response_model=None)
async def review_release(
    course_id: str,
    release_id: str,
    body: ReleaseReviewCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    reviewer_role = await require_course_role(
        course_id,
        user,
        db,
        roles={"course_publisher", "teacher"},
    )
    release = await db.scalar(
        select(CourseRelease)
        .where(
            CourseRelease.id == release_id,
            CourseRelease.course_id == course_id,
        )
        .with_for_update()
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )

    endpoint = "POST:/api/v1/courses/{course_id}/releases/{release_id}/reviews"
    request_hash = service.canonical_request_hash(body.model_dump(mode="json"))
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    if release.status != "draft":
        raise ApiError(status_code=409, code="RELEASE_NOT_REVIEWABLE", message="仅草稿版本可审核")
    if release.created_by == user.id:
        raise ApiError(
            status_code=403, code="RELEASE_SELF_REVIEW", message="课程版本作者不能审核自己的版本"
        )
    current_hash = _course_release_manifest_sha256(release)
    if body.expected_version != release.version or body.manifest_sha256 != current_hash:
        raise ApiError(
            status_code=409,
            code="RELEASE_REVIEW_STALE",
            message="课程版本在审核前已变化，请刷新后重新审核",
            details={"actual_version": release.version, "actual_manifest_sha256": current_hash},
        )
    detail = {
        "expected_version": body.expected_version,
        "manifest_sha256": body.manifest_sha256,
        "decision": body.decision,
        "reason": body.reason.strip(),
        "reviewer_role": reviewer_role,
    }
    if not detail["reason"]:
        raise ApiError(
            status_code=422, code="RELEASE_REVIEW_REASON_REQUIRED", message="审核理由不能为空"
        )
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.release_reviewed",
        resource_type="course_release",
        resource_id=release.id,
        course_id=course_id,
        detail=detail,
    )
    data = {
        "release_id": release.id,
        "reviewer_id": user.id,
        **detail,
        "current": True,
    }
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=201,
        data=data,
        conflict_code="RELEASE_REVIEW_CONFLICT",
    )
    return conflict or ok(request, data, status_code=201)


@router.get("/courses/{course_id}/releases/{release_id}/impact", response_model=None)
async def get_release_impact(
    course_id: str,
    release_id: str,
    request: Request,
    class_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "assistant", "course_publisher"},
    )
    release = await db.scalar(
        select(CourseRelease).where(
            CourseRelease.id == release_id,
            CourseRelease.course_id == course_id,
        )
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    course_class = await db.scalar(
        select(CourseClass).where(
            CourseClass.id == class_id,
            CourseClass.course_id == course_id,
        )
    )
    if course_class is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    assignment = await db.scalar(
        select(CourseReleaseAssignment.id)
        .where(
            CourseReleaseAssignment.course_id == course_id,
            CourseReleaseAssignment.class_id == class_id,
            CourseReleaseAssignment.course_release_id == release_id,
        )
        .limit(1)
    )
    if assignment is None:
        raise ApiError(
            status_code=404,
            code="RELEASE_ASSIGNMENT_NOT_FOUND",
            message="该课程版本未曾指派给当前班级",
        )
    sample_size = await db.scalar(
        select(func.count(ClassMember.id)).where(
            ClassMember.class_id == class_id,
            ClassMember.status == "active",
        )
    )
    privacy_group_size = int(sample_size or 0) if int(sample_size or 0) >= 5 else None
    return ok(
        request,
        {
            "course_id": course_id,
            "class_id": class_id,
            "release_id": release_id,
            "measurement_status": "not_measured",
            "reason_code": "RELEASE_NOT_BOUND_TO_QUALIFIED_LEARNING_EVIDENCE",
            "privacy_group_size": privacy_group_size,
            "suppressed_small_sample": privacy_group_size is None,
            "effects": [],
        },
    )


def _release_assignment_data(assignment: CourseReleaseAssignment | None) -> dict[str, Any] | None:
    if assignment is None:
        return None
    return ReleaseAssignmentOut.model_validate(assignment, from_attributes=True).model_dump(
        mode="json"
    )


@router.get("/courses/{course_id}/classes/{class_id}/release-assignment", response_model=None)
async def get_class_release_assignment(
    course_id: str,
    class_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "course_publisher", "course_designer"},
    )
    course_class = await db.scalar(
        select(CourseClass).where(
            CourseClass.id == class_id,
            CourseClass.course_id == course_id,
            CourseClass.status == "active",
        )
    )
    if course_class is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    assignment = await db.scalar(
        select(CourseReleaseAssignment).where(
            CourseReleaseAssignment.course_id == course_id,
            CourseReleaseAssignment.class_id == class_id,
            CourseReleaseAssignment.status == "active",
        )
    )
    return ok(request, _release_assignment_data(assignment))


@router.put("/courses/{course_id}/classes/{class_id}/release-assignment", response_model=None)
async def set_class_release_assignment(
    course_id: str,
    class_id: str,
    body: ReleaseAssignmentSet,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    await require_course_role(
        course_id,
        user,
        db,
        roles={"teacher", "course_publisher"},
    )
    course_class = await db.scalar(
        select(CourseClass)
        .where(
            CourseClass.id == class_id,
            CourseClass.course_id == course_id,
            CourseClass.status == "active",
        )
        .with_for_update()
    )
    if course_class is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="班级不存在或无权访问")
    endpoint = "PUT:/api/v1/courses/{course_id}/classes/{class_id}/release-assignment"
    request_hash = service.canonical_request_hash(body.model_dump(mode="json"))
    replay = await _admin_idempotency_replay(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    current = await db.scalar(
        select(CourseReleaseAssignment)
        .where(
            CourseReleaseAssignment.course_id == course_id,
            CourseReleaseAssignment.class_id == class_id,
            CourseReleaseAssignment.status == "active",
        )
        .with_for_update()
    )
    actual_version = current.version if current is not None else 0
    if body.expected_version != actual_version:
        raise ApiError(
            status_code=409,
            code="RELEASE_ASSIGNMENT_VERSION_CONFLICT",
            message="班级课程版本指派已变化，请刷新后重试",
            details={"actual_version": actual_version},
        )
    release = await db.scalar(
        select(CourseRelease).where(
            CourseRelease.id == body.course_release_id,
            CourseRelease.course_id == course_id,
        )
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    if release.status != "published":
        raise ApiError(
            status_code=409,
            code="RELEASE_ASSIGNMENT_REQUIRES_PUBLISHED_RELEASE",
            message="班级只能指派当前已发布的课程版本",
        )
    if current is not None and current.course_release_id == release.id:
        data = _release_assignment_data(current)
    else:
        now = datetime.now(UTC)
        supersedes_id = current.id if current is not None else None
        if current is not None:
            current.status = "closed"
            current.closed_by = user.id
            current.closed_at = now
            current.close_reason = (body.close_reason or "课程版本换版").strip()[:500]
            current.version += 1
        assignment = CourseReleaseAssignment(
            course_id=course_id,
            class_id=class_id,
            course_release_id=release.id,
            status="active",
            assigned_by=user.id,
            assigned_at=now,
            supersedes_id=supersedes_id,
        )
        db.add(assignment)
        await db.flush()
        await service.write_audit(
            db,
            actor_id=user.id,
            action="course.release_assigned",
            resource_type="course_release_assignment",
            resource_id=assignment.id,
            course_id=course_id,
            detail={
                "class_id": class_id,
                "course_release_id": release.id,
                "supersedes_id": supersedes_id,
                "close_reason": current.close_reason if current is not None else None,
            },
        )
        from app.core.outbox import append_event

        await append_event(
            db,
            event_type="course.release_assigned",
            payload={
                "course_id": course_id,
                "class_id": class_id,
                "assignment_id": assignment.id,
                "course_release_id": release.id,
            },
            producer="courses.router",
            trace_id=assignment.id,
        )
        data = _release_assignment_data(assignment)
    conflict = await _commit_admin_idempotent_write(
        request,
        db,
        user_id=user.id,
        endpoint=endpoint,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=200,
        data=data,
        conflict_code="RELEASE_ASSIGNMENT_CONFLICT",
    )
    return conflict or ok(request, data)


@router.post(
    "/courses/{course_id}/releases/{release_id}/publish",
    response_model=None,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ReleasePublishRequest"}
                }
            },
        }
    },
)
async def publish_release(
    course_id: str,
    release_id: str,
    request: Request,
    body: ReleasePublishRequest | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    allowed_roles = {"course_publisher"} if body is not None else {"teacher", "course_publisher"}
    await require_course_role(course_id, user, db, roles=allowed_roles)
    if body is None:
        raise ApiError(
            status_code=422,
            code="RELEASE_PUBLISH_REQUEST_REQUIRED",
            message="课程发布必须提供版本号和幂等键；请使用受控发布请求",
        )
    endpoint = "POST:/api/v1/courses/{course_id}/releases/{release_id}/publish"
    request_hash = service.canonical_request_hash(body.model_dump(mode="json"))
    if not idempotency_key:
        raise ApiError(
            status_code=422,
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="正式发布请求必须提供 Idempotency-Key",
        )
    replay = await _admin_idempotency_replay(
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
        select(CourseRelease)
        .where(CourseRelease.id == release_id, CourseRelease.course_id == course_id)
        .with_for_update()
    )
    if release is None:
        raise ApiError(
            status_code=404, code="RELEASE_NOT_FOUND", message="课程版本不存在或无权访问"
        )
    if release.status == "published":
        data = ReleaseOut.model_validate(release, from_attributes=True).model_dump(mode="json")
        raise ApiError(
            status_code=409,
            code="RELEASE_ALREADY_PUBLISHED",
            message="该课程版本已发布；请使用原幂等键重放发布回执",
        )
    if release.status != "draft":
        raise ApiError(status_code=409, code="RELEASE_NOT_EDITABLE", message="该版本已不能发布")
    warning_reason: str | None = None
    if body.expected_version != release.version:
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="课程版本已变化，请刷新后重试发布",
            details={"actual_version": release.version},
        )
    gate = await _release_gate_report(db, course_id, release)
    if not gate["can_publish"]:
        raise ApiError(
            status_code=409,
            code="RELEASE_GATE_BLOCKED",
            message="课程版本尚未通过发布门禁",
            details={"errors": gate["errors"], "warnings": gate["warnings"]},
        )
    warning_reason = body.warning_reason.strip() if body.warning_reason else None
    if gate["warnings"] and not warning_reason:
        raise ApiError(
            status_code=409,
            code="RELEASE_WARNING_REASON_REQUIRED",
            message="继续发布前必须为门禁警告填写审计理由",
            details={"warnings": gate["warnings"]},
        )
    material_ids = release.manifest.get("materials", [])
    pinned_material_ids = release.manifest.get("material_version_ids", [])
    material_versions = (
        dict(zip(material_ids, pinned_material_ids, strict=True))
        if isinstance(material_ids, list)
        and isinstance(pinned_material_ids, list)
        and len(material_ids) == len(pinned_material_ids)
        else {}
    )
    domain_pack = release.manifest.get("domain_pack", {})
    evidence_bindings = (
        domain_pack.get("evidence_bindings", []) if isinstance(domain_pack, dict) else []
    )
    source_object_ids = (
        {
            binding.get("source_object_id")
            for binding in evidence_bindings
            if isinstance(binding, dict)
            and isinstance(binding.get("source_object_id"), str)
            and binding["source_object_id"]
        }
        if isinstance(evidence_bindings, list)
        else set()
    )
    evidence_sources: dict[str, str] = {}
    if source_object_ids:
        source_rows = await db.execute(
            select(KnowledgeObject.id, KnowledgeObject.material_version_id).where(
                KnowledgeObject.id.in_(source_object_ids)
            )
        )
        evidence_sources = dict(source_rows.all())
    # Revalidate the immutable-at-publish snapshot as legacy drafts may predate
    # Domain Pack graph validation or have been written by older clients.
    service.validate_course_release_pack(
        "domain_pack",
        domain_pack,
        for_publish=True,
        material_ids=set(material_ids),
        material_versions=material_versions,
        evidence_sources=evidence_sources,
    )
    now = datetime.now(UTC)
    await db.execute(
        update(CourseRelease)
        .where(
            CourseRelease.course_id == course_id,
            CourseRelease.status == "published",
            CourseRelease.id != release.id,
        )
        .values(status="deprecated", deprecated_at=now)
    )
    release.status = "published"
    release.published_by = user.id
    release.published_at = now
    await service.write_audit(
        db,
        actor_id=user.id,
        action="course.release_published",
        resource_type="course_release",
        resource_id=release.id,
        course_id=course_id,
        detail={
            "version_no": release.version_no,
            "expected_version": body.expected_version,
            "manifest_sha256": _course_release_manifest_sha256(release),
            "domain_release_id": release.domain_release_id,
            "warning_reason": warning_reason,
            "legacy_publish_request": False,
        },
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.release_published",
        payload={
            "course_id": course_id,
            "release_id": release.id,
            "version_no": release.version_no,
            "domain_release_id": release.domain_release_id,
        },
        producer="courses.router",
        trace_id=release.id,
    )
    await db.flush()
    await db.refresh(release)
    data = ReleaseOut.model_validate(release, from_attributes=True).model_dump(mode="json")
    if body is not None and idempotency_key and request_hash:
        conflict = await _commit_admin_idempotent_write(
            request,
            db,
            user_id=user.id,
            endpoint=endpoint,
            key=idempotency_key,
            request_hash=request_hash,
            status_code=200,
            data=data,
            conflict_code="RELEASE_PUBLISH_CONFLICT",
        )
        return conflict or ok(request, data)
    await db.commit()
    await db.refresh(release)
    data = ReleaseOut.model_validate(release, from_attributes=True).model_dump(mode="json")
    return ok(request, data)


@router.get("/admin/class-assignment-options", response_model=None)
async def get_admin_class_assignment_options(
    request: Request,
    course_id: str = Query(min_length=26, max_length=26),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """返回指定同机构课程的班级、可任课成员和分配元数据。"""
    _require_platform_admin(user)
    course = await db.scalar(
        select(Course).where(
            Course.id == course_id,
            Course.organization_id == user.organization_id,
            Course.status == "active",
        )
    )
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="同机构有效课程不存在")
    classes = (
        await db.execute(
            select(CourseClass)
            .where(CourseClass.course_id == course_id, CourseClass.status == "active")
            .order_by(CourseClass.code.asc(), CourseClass.id.asc())
        )
    ).scalars()
    teachers = (
        await db.execute(
            select(User.id, User.display_name, CourseMember.role)
            .join(CourseMember, CourseMember.user_id == User.id)
            .where(
                CourseMember.course_id == course_id,
                CourseMember.role.in_({"teacher", "assistant"}),
                CourseMember.status == "active",
                User.organization_id == user.organization_id,
                User.status == "active",
            )
            .order_by(User.display_name.asc(), User.id.asc())
        )
    ).all()
    assignments = (
        await db.execute(
            select(TeacherAssignment, CourseClass.code, CourseClass.name, User.display_name)
            .join(CourseClass, CourseClass.id == TeacherAssignment.class_id)
            .join(User, User.id == TeacherAssignment.teacher_id)
            .where(CourseClass.course_id == course_id)
            .order_by(CourseClass.code.asc(), TeacherAssignment.created_at.asc())
            .limit(500)
        )
    ).all()
    return ok(
        request,
        {
            "course_id": course_id,
            "classes": [{"id": item.id, "code": item.code, "name": item.name} for item in classes],
            "teachers": [
                {"id": teacher_id, "display_name": name, "course_role": role}
                for teacher_id, name, role in teachers
            ],
            "assignments": [
                {
                    "id": assignment.id,
                    "class_id": assignment.class_id,
                    "class_code": class_code,
                    "class_name": class_name,
                    "teacher_id": assignment.teacher_id,
                    "teacher_name": teacher_name,
                    "assignment_role": assignment.assignment_role,
                    "status": assignment.status,
                    "version": assignment.version,
                    "assigned_by": assignment.assigned_by,
                    "created_at": assignment.created_at.isoformat(),
                }
                for assignment, class_code, class_name, teacher_name in assignments
            ],
        },
        has_more=False,
    )


@router.post("/admin/class-teacher-assignments", response_model=None)
async def admin_assign_class_teacher(
    body: AdminClassTeacherAssignmentCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    endpoint = ADMIN_CLASS_ASSIGN_ENDPOINT
    request_data = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(request_data)
    previous = await service.find_idempotent_response(
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

    row = await db.execute(
        select(CourseClass, Course)
        .join(Course, Course.id == CourseClass.course_id)
        .where(
            CourseClass.id == body.class_id,
            CourseClass.status == "active",
            Course.status == "active",
            Course.organization_id == user.organization_id,
        )
        .with_for_update(of=CourseClass)
    )
    course_class, course = row.one_or_none() or (None, None)
    if course_class is None or course is None:
        raise ApiError(status_code=404, code="CLASS_NOT_FOUND", message="同机构有效班级不存在")
    if body.teacher_id == user.id:
        raise ApiError(
            status_code=409,
            code="ROLE_SELF_ASSIGNMENT_FORBIDDEN",
            message="管理员不能为自己新增班级任课授权",
        )
    member_row = await db.execute(
        select(User, CourseMember)
        .join(CourseMember, CourseMember.user_id == User.id)
        .where(
            User.id == body.teacher_id,
            User.organization_id == user.organization_id,
            User.status == "active",
            CourseMember.course_id == course.id,
            CourseMember.role.in_({"teacher", "assistant"}),
            CourseMember.status == "active",
        )
        .with_for_update(of=CourseMember)
    )
    target, _membership = member_row.one_or_none() or (None, None)
    if target is None:
        raise ApiError(
            status_code=409,
            code="TEACHER_NOT_COURSE_MEMBER",
            message="任课对象必须是同机构且已加入该课程的教师或助教",
        )
    assignment = await db.scalar(
        select(TeacherAssignment)
        .where(
            TeacherAssignment.class_id == course_class.id,
            TeacherAssignment.teacher_id == target.id,
        )
        .with_for_update()
    )
    if assignment is not None and assignment.status == "active":
        raise ApiError(
            status_code=409,
            code="TEACHER_ALREADY_ASSIGNED",
            message="该教师已分配到此班级",
        )
    if assignment is None:
        assignment = TeacherAssignment(
            class_id=course_class.id,
            teacher_id=target.id,
            assignment_role=body.assignment_role,
            assigned_by=user.id,
        )
        db.add(assignment)
    else:
        assignment.assignment_role = body.assignment_role
        assignment.status = "active"
        assignment.assigned_by = user.id
        assignment.version += 1
    await db.flush()
    data = TeacherAssignmentOut(
        id=assignment.id,
        class_id=assignment.class_id,
        teacher_id=assignment.teacher_id,
        teacher_name=target.display_name,
        assignment_role=assignment.assignment_role,
        status=assignment.status,
        version=assignment.version,
        assigned_by=assignment.assigned_by,
        created_at=assignment.created_at,
    ).model_dump(mode="json")
    await service.write_audit(
        db,
        actor_id=user.id,
        action="admin.class.teacher_assigned",
        resource_type="teacher_assignment",
        resource_id=assignment.id,
        course_id=course.id,
        detail={
            "class_id": course_class.id,
            "teacher_id": target.id,
            "assignment_role": assignment.assignment_role,
            "version": assignment.version,
            "reason": body.reason,
        },
    )
    from app.core.outbox import append_event

    await append_event(
        db,
        event_type="course.teacher_assigned",
        payload={
            "class_id": course_class.id,
            "teacher_id": target.id,
            "assigned_by": user.id,
        },
        producer="courses.admin_router",
        trace_id=assignment.id,
    )
    await service.save_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=endpoint,
        request_hash=request_hash,
        status=201,
        body={"data": data},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        previous = await service.find_idempotent_response(
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
        raise ApiError(
            status_code=409,
            code="TEACHER_ASSIGNMENT_CONFLICT",
            message="任课关系已被其他管理员更新，请刷新后重试",
        ) from exc
    return ok(request, data, status_code=201)


@router.post("/admin/class-teacher-assignments/{assignment_id}/end", response_model=None)
async def admin_end_class_teacher_assignment(
    assignment_id: str,
    body: AdminClassTeacherAssignmentEnd,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    _require_platform_admin(user)
    endpoint = ADMIN_CLASS_END_ENDPOINT.format(id=assignment_id)
    request_data = body.model_dump(mode="json")
    request_hash = service.canonical_request_hash(request_data)
    previous = await service.find_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=endpoint,
        request_hash=request_hash,
    )
    if previous is not None:
        return ok(request, previous["body"]["data"], idempotent_replay=True)
    row = await db.execute(
        select(TeacherAssignment, CourseClass, Course, User)
        .join(CourseClass, CourseClass.id == TeacherAssignment.class_id)
        .join(Course, Course.id == CourseClass.course_id)
        .join(User, User.id == TeacherAssignment.teacher_id)
        .where(
            TeacherAssignment.id == assignment_id,
            Course.organization_id == user.organization_id,
        )
        .with_for_update(of=TeacherAssignment)
    )
    assignment, course_class, course, target = row.one_or_none() or (None, None, None, None)
    if assignment is None:
        raise ApiError(
            status_code=404,
            code="TEACHER_ASSIGNMENT_NOT_FOUND",
            message="同机构任课关系不存在",
        )
    if assignment.version != body.version:
        previous = await service.find_idempotent_response(
            db,
            key=idempotency_key,
            user_id=user.id,
            endpoint=endpoint,
            request_hash=request_hash,
        )
        if previous is not None:
            return ok(request, previous["body"]["data"], idempotent_replay=True)
        raise ApiError(
            status_code=409,
            code="RESOURCE_VERSION_CONFLICT",
            message="任课关系已更新，请刷新后重试",
            details={"expected_version": body.version, "actual_version": assignment.version},
        )
    if assignment.status == "active":
        assignment.status = "ended"
        assignment.version += 1
        await service.write_audit(
            db,
            actor_id=user.id,
            action="admin.class.teacher_assignment_ended",
            resource_type="teacher_assignment",
            resource_id=assignment.id,
            course_id=course.id,
            detail={
                "class_id": course_class.id,
                "teacher_id": target.id,
                "assignment_role": assignment.assignment_role,
                "version": assignment.version,
                "reason": body.reason,
            },
        )
        from app.core.outbox import append_event

        await append_event(
            db,
            event_type="course.teacher_assignment_ended",
            payload={
                "class_id": course_class.id,
                "teacher_id": target.id,
                "ended_by": user.id,
            },
            producer="courses.admin_router",
            trace_id=assignment.id,
        )
    data = TeacherAssignmentOut(
        id=assignment.id,
        class_id=assignment.class_id,
        teacher_id=assignment.teacher_id,
        teacher_name=target.display_name,
        assignment_role=assignment.assignment_role,
        status=assignment.status,
        version=assignment.version,
        assigned_by=assignment.assigned_by,
        created_at=assignment.created_at,
    ).model_dump(mode="json")
    await service.save_idempotent_response(
        db,
        key=idempotency_key,
        user_id=user.id,
        endpoint=endpoint,
        request_hash=request_hash,
        status=200,
        body={"data": data},
    )
    await db.commit()
    return ok(request, data)
