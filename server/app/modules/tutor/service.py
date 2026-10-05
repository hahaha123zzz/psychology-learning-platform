"""教学运行时：证据包构建、主张—证据校验、SSE教学回合与学习状态机。

当前答案生成采用"教材证据抽取式"实现（确定性、可校验、无外部模型依赖）；
接入真实LLM时仅替换 generate_answer，检索、校验、引用与状态机合同不变。
"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.model_gateway import call_model
from app.core.providers.llm import OpenAICompatibleLLM
from app.db.base import new_ulid
from app.db.models import (
    ChatTurn,
    ClassMember,
    CourseClass,
    CourseRelease,
    CourseReleaseAssignment,
    DomainRelease,
    Job,
    LearningSession,
    Material,
    MaterialVersion,
    PublicationSnapshot,
    RetrievalUnit,
)
from app.modules.knowledge import service as knowledge_service
from app.modules.knowledge.context import GenerationUnit, assemble_generation_units
from app.modules.knowledge.domain import classify_claim, verify_claim_with_bounded_retrieval
from app.modules.knowledge.query import analyze_query

SENTENCE_RE = re.compile(r"[^。！？.!?]+[。！？]?")
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")

MAX_HINT_LEVEL = 3
TOP_EVIDENCE = 3
LEARNING_BLOCK_SCHEMA_VERSION = "learning-block.v1"
TUTOR_CLAIM_VERIFICATION_SCHEMA_VERSION = "tutor-claim-verification.v1"
CLAIM_SCOPE_REQUIRED_FIELDS = frozenset(
    {
        "user_id",
        "organization_id",
        "course_id",
        "class_id",
        "course_release_assignment_id",
        "course_release_id",
        "domain_release_id",
        "publication_snapshot_id",
        "material_version_ids",
        "index_job_id",
        "embedding_version",
        "publication_snapshots",
    }
)
CLAIM_STATES = frozenset(
    {"supported", "partially-supported", "contradicted", "unknown"}
)

BACKGROUND_TASKS: set[asyncio.Task] = set()


def _citation_label(index: int, title: str, physical_page: int | None) -> str:
    """仅在解析器提供可信物理页码时展示页码，不推测 DOCX 页码。"""
    page_label = f" 第{physical_page}页" if physical_page is not None else ""
    return f"[{index}] {title}{page_label}"


def build_learning_blocks(
    *, session_id: str, state: str, state_version: int, message: str,
    action: str, hint_level: int,
) -> list[dict]:
    """把旧学习状态映射为受白名单约束的结构化 Blocks。

    Block 只描述可渲染内容和允许动作，不直接改变 Mastery、Memory 或成绩。
    结构参考 OpenTutor 的 block workspace，但字段和动作由本项目定义。
    """
    blocks: list[dict] = [
        {
            "id": f"{session_id}:{state_version}:explanation",
            "schema_version": LEARNING_BLOCK_SCHEMA_VERSION,
            "type": "TutorExplanation",
            "text": message,
            "evidence_refs": [],
            "allowed_actions": ["OPEN_EVIDENCE"],
            "state": state,
            "hint_level": hint_level,
        }
    ]
    if action == "complete" or state == "completed":
        blocks.append(
            {
                "id": f"{session_id}:{state_version}:completion",
                "schema_version": LEARNING_BLOCK_SCHEMA_VERSION,
                "type": "TaskCompletion",
                "completion": "activity_completed",
                "allowed_actions": ["REVIEW"],
            }
        )
    else:
        blocks.append(
            {
                "id": f"{session_id}:{state_version}:transition",
                "schema_version": LEARNING_BLOCK_SCHEMA_VERSION,
                "type": "Transition",
                "next_action": action,
                "allowed_actions": ["CONTINUE"],
            }
        )
    return blocks


# ---- 数据结构 ----

@dataclass
class EvidencePackage:
    package_id: str
    course_id: str
    query: str
    retrieval_version: str
    items: list[dict] = field(default_factory=list)
    generation_units: list[GenerationUnit] = field(default_factory=list)
    context_budget_chars: int = 12000
    created_at: str = ""

    def evidence_text(self) -> str:
        return "\n".join(unit.text for unit in self.generation_units)


@dataclass
class DomainClaimContext:
    """由 Tutor 路由从同一不可变发布快照构造的 Domain Claim 运行上下文。"""

    retrieval_scope: dict[str, Any]
    required_scope: dict[str, Any]
    evaluate: Callable[[str, list[Any]], dict[str, Any]]
    retrieve_once: Callable[[dict[str, Any]], Awaitable[list[Any]]]
    refusal_reason: str | None = None


@dataclass(frozen=True)
class ChatSessionReleaseScope:
    assignment_id: str
    release_id: str
    class_id: str
    domain_release_id: str | None
    manifest: dict[str, Any]


@dataclass(frozen=True)
class BoundChatRetrieval:
    items: list[dict[str, Any]]
    warnings: list[str]
    claim_context: DomainClaimContext


def _valid_claim_scope(
    scope: Mapping[str, Any], *, enforce_snapshot_consistency: bool = True
) -> bool:
    if not CLAIM_SCOPE_REQUIRED_FIELDS.issubset(scope):
        return False
    list_or_id_fields = {"publication_snapshot_id", "index_job_id", "embedding_version"}
    for field_name in CLAIM_SCOPE_REQUIRED_FIELDS - {
        "material_version_ids",
        "publication_snapshots",
        *list_or_id_fields,
    }:
        if not isinstance(scope[field_name], str) or not scope[field_name].strip():
            return False
    versions = scope["material_version_ids"]
    if (
        not isinstance(versions, list)
        or any(not isinstance(value, str) or not value.strip() for value in versions)
        or len(set(versions)) != len(versions)
    ):
        return False
    for field_name in list_or_id_fields:
        value = scope[field_name]
        values = [value] if isinstance(value, str) else value
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item.strip() for item in values)
        ):
            return False
    snapshots = scope["publication_snapshots"]
    if not isinstance(snapshots, list) or not snapshots:
        return False
    snapshot_fields = {
        "material_id",
        "material_version_id",
        "publication_snapshot_id",
        "index_job_id",
        "embedding_version",
        "domain_release_id",
    }
    if any(
        not isinstance(item, Mapping)
        or set(item) != snapshot_fields
        or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in snapshot_fields
        )
        for item in snapshots
    ):
        return False
    if enforce_snapshot_consistency and [
        item["material_version_id"] for item in snapshots
    ] != versions:
        return False
    if enforce_snapshot_consistency:
        for scope_key, snapshot_key in (
            ("publication_snapshot_id", "publication_snapshot_id"),
            ("index_job_id", "index_job_id"),
        ):
            expected = [item[snapshot_key] for item in snapshots]
            actual = scope[scope_key]
            actual_values = [actual] if isinstance(actual, str) else actual
            if actual_values != expected:
                return False
        snapshot_embeddings = sorted({item["embedding_version"] for item in snapshots})
        actual_embeddings = scope["embedding_version"]
        actual_embedding_values = (
            [actual_embeddings]
            if isinstance(actual_embeddings, str)
            else actual_embeddings
        )
        if actual_embedding_values != snapshot_embeddings:
            return False
        if any(item["domain_release_id"] != scope["domain_release_id"] for item in snapshots):
            return False
    try:
        json.dumps(dict(scope), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return False
    return True


def _evidence_reference_ids(evidence: list[Any]) -> list[str]:
    references: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        if isinstance(item, str):
            reference = item
        elif isinstance(item, Mapping):
            reference = item.get("evidence_id") or item.get("id")
        else:
            reference = getattr(item, "evidence_id", None) or getattr(item, "id", None)
        if not isinstance(reference, str) or not reference.strip():
            continue
        reference = reference.strip()
        if reference not in seen:
            seen.add(reference)
            references.append(reference)
    return references


def _claim_verification_record(
    *,
    result: dict[str, Any],
    required_scope: dict[str, Any],
    retrieval_scope: dict[str, Any],
    initial_evidence: list[Any],
    attempts: int,
) -> dict[str, Any]:
    status = result.get("status")
    if status not in CLAIM_STATES:
        status = "unknown"
    supplemental_evidence = result.get("supplemental_evidence", [])
    if not isinstance(supplemental_evidence, list):
        supplemental_evidence = []
    supported = result.get("supported_subclaims", [])
    unsupported = result.get("unsupported_subclaims", [])
    contradicted = result.get("contradicted_subclaims", [])
    refusal_reason = result.get("refusal_reason")
    if not refusal_reason and status == "partially-supported":
        refusal_reason = "claim_partially_supported"
    elif not refusal_reason and status == "contradicted":
        refusal_reason = "claim_contradicted"
    elif not refusal_reason and status == "unknown":
        refusal_reason = "insufficient_evidence"
    return {
        "schema_version": TUTOR_CLAIM_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "supported_subclaims": [value for value in supported if isinstance(value, str)],
        "unsupported_subclaims": [
            value for value in unsupported if isinstance(value, str)
        ],
        "contradicted_subclaims": [
            value for value in contradicted if isinstance(value, str)
        ],
        "scope": deepcopy(required_scope),
        "retrieval_scope": deepcopy(retrieval_scope),
        "initial_evidence_refs": _evidence_reference_ids(initial_evidence),
        "supplemental_evidence_refs": _evidence_reference_ids(supplemental_evidence),
        "supplemental_retrieval_attempts": min(max(attempts, 0), 1),
        "refusal_reason": refusal_reason,
    }


async def verify_domain_claim_for_tutor(
    *,
    claim: str,
    initial_evidence: list[Any],
    context: DomainClaimContext,
) -> dict[str, Any]:
    """消费 A 的有界 Claim helper，并生成可安全写入 TutorTurn.verification 的记录。"""
    required_scope = deepcopy(context.required_scope)
    retrieval_scope = deepcopy(context.retrieval_scope)
    if context.refusal_reason is not None:
        return _claim_verification_record(
            result={"status": "unknown", "refusal_reason": context.refusal_reason},
            required_scope=required_scope,
            retrieval_scope=retrieval_scope,
            initial_evidence=initial_evidence,
            attempts=0,
        )
    if not _valid_claim_scope(required_scope) or not _valid_claim_scope(
        retrieval_scope, enforce_snapshot_consistency=False
    ):
        raise ValueError("Domain Claim scope 缺少完整的不可变发布快照字段")
    if not isinstance(claim, str) or not claim.strip():
        raise ValueError("Domain Claim 内容不能为空")
    if not isinstance(initial_evidence, list):
        raise ValueError("Domain Claim 初始证据必须是数组")

    retrieval_attempts = 0

    async def retrieve_once(scope: dict[str, Any]) -> list[Any]:
        nonlocal retrieval_attempts
        retrieval_attempts += 1
        return await context.retrieve_once(scope)

    try:
        result = await verify_claim_with_bounded_retrieval(
            claim=claim,
            initial_evidence=deepcopy(initial_evidence),
            evaluate=context.evaluate,
            retrieve_once=retrieve_once,
            retrieval_scope=retrieval_scope,
            required_scope=required_scope,
        )
    except TimeoutError:
        result = {"status": "unknown", "refusal_reason": "claim_verification_timeout"}
    except Exception:  # noqa: BLE001 verification failure must fail closed without leaking exception text
        result = {"status": "unknown", "refusal_reason": "claim_verification_failed"}

    return _claim_verification_record(
        result=result,
        required_scope=required_scope,
        retrieval_scope=retrieval_scope,
        initial_evidence=initial_evidence,
        attempts=retrieval_attempts,
    )


# ---- 证据包 ----

def build_evidence_package(
    *, user_id: str, course_id: str, query: str, items: list[dict]
) -> EvidencePackage:
    package = EvidencePackage(
        package_id=new_ulid(),
        course_id=course_id,
        query=query,
        retrieval_version=knowledge_service.RETRIEVAL_VERSION,
        created_at=datetime.now(UTC).isoformat(),
    )
    package.generation_units = assemble_generation_units(
        items, context_budget_chars=package.context_budget_chars, max_units=TOP_EVIDENCE
    )
    selected_evidence_ids = {unit.evidence_id for unit in package.generation_units}
    package.items = [item for item in items if item["evidence_id"] in selected_evidence_ids]
    return package


async def resolve_learning_release_binding(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    material_id: str,
) -> tuple[str | None, str | None]:
    """为新学习会话解析唯一活动班级 assignment；无 assignment 保留 legacy 空值。"""
    rows = (
        await db.execute(
            select(CourseReleaseAssignment.id, CourseReleaseAssignment.course_release_id)
            .join(ClassMember, ClassMember.class_id == CourseReleaseAssignment.class_id)
            .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
            .where(
                CourseReleaseAssignment.course_id == course_id,
                CourseReleaseAssignment.status == "active",
                ClassMember.user_id == user_id,
                ClassMember.status == "active",
                CourseClass.course_id == course_id,
                CourseClass.status == "active",
            )
            .order_by(CourseReleaseAssignment.id.asc())
        )
    ).all()
    if not rows:
        return None, None
    if len(rows) != 1:
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS",
            message="当前学生属于多个已发布课程版本班级，请联系教师确认班级归属。",
        )

    assignment_id, release_id = rows[0]
    release = await db.scalar(
        select(CourseRelease).where(
            CourseRelease.id == release_id,
            CourseRelease.course_id == course_id,
            CourseRelease.status.in_(("published", "deprecated")),
        )
    )
    if release is None:
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_ASSIGNMENT_INVALID",
            message="当前班级课程版本不可用，请联系教师检查课程指派。",
        )
    materials = (release.manifest or {}).get("materials")
    if (
        not isinstance(materials, list)
        or any(not isinstance(value, str) for value in materials)
        or material_id not in materials
    ):
        raise ApiError(
            status_code=404,
            code="MATERIAL_VERSION_NOT_IN_ASSIGNED_RELEASE",
            message="资料不存在或不属于当前班级课程版本。",
        )
    return assignment_id, release.id


async def resolve_chat_session_release_binding(
    db: AsyncSession, *, user_id: str, course_id: str
) -> tuple[str | None, str | None]:
    """为学生新 Tutor 会话解析唯一的活动班级与已发布课程版本。"""
    rows = (
        await db.execute(
            select(CourseReleaseAssignment.id, CourseReleaseAssignment.course_release_id)
            .join(ClassMember, ClassMember.class_id == CourseReleaseAssignment.class_id)
            .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
            .join(CourseRelease, CourseRelease.id == CourseReleaseAssignment.course_release_id)
            .where(
                CourseReleaseAssignment.course_id == course_id,
                CourseReleaseAssignment.status == "active",
                ClassMember.user_id == user_id,
                ClassMember.status == "active",
                CourseClass.course_id == course_id,
                CourseClass.status == "active",
                CourseRelease.course_id == course_id,
                CourseRelease.status == "published",
            )
            .order_by(CourseReleaseAssignment.id.asc())
        )
    ).all()
    if not rows:
        return None, None
    if len(rows) != 1:
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS",
            message="当前学生属于多个已发布课程版本班级，请联系教师确认班级归属。",
        )
    return rows[0][0], rows[0][1]


async def authorize_chat_session_release_scope(
    db: AsyncSession, *, session_row: Any, user_id: str
) -> ChatSessionReleaseScope | None:
    """重新核验绑定会话的课程/班级权限；closed assignment 可继续读旧版本。"""
    assignment_id = session_row.course_release_assignment_id
    release_id = session_row.course_release_id
    if assignment_id is None and release_id is None:
        return None
    if (assignment_id is None) != (release_id is None):
        raise ApiError(404, "CHAT_SESSION_NOT_FOUND", "会话不存在或无权访问")

    row = (
        await db.execute(
            select(CourseReleaseAssignment, CourseClass, CourseRelease)
            .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
            .join(CourseRelease, CourseRelease.id == CourseReleaseAssignment.course_release_id)
            .join(ClassMember, ClassMember.class_id == CourseClass.id)
            .where(
                CourseReleaseAssignment.id == assignment_id,
                CourseReleaseAssignment.course_id == session_row.course_id,
                CourseReleaseAssignment.course_release_id == release_id,
                CourseReleaseAssignment.status.in_(("active", "closed")),
                CourseClass.course_id == session_row.course_id,
                CourseClass.status == "active",
                ClassMember.user_id == user_id,
                ClassMember.status == "active",
                CourseRelease.course_id == session_row.course_id,
                CourseRelease.status.in_(("published", "deprecated")),
            )
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        raise ApiError(404, "CHAT_SESSION_NOT_FOUND", "会话不存在或无权访问")
    assignment, course_class, release = row
    manifest = release.manifest if isinstance(release.manifest, dict) else {}
    return ChatSessionReleaseScope(
        assignment_id=assignment.id,
        release_id=release.id,
        class_id=course_class.id,
        domain_release_id=release.domain_release_id,
        manifest=deepcopy(manifest),
    )


async def prepare_bound_chat_retrieval(
    db: AsyncSession,
    *,
    session_row: Any,
    organization_id: str,
    query: str,
) -> BoundChatRetrieval:
    """按不可变 ChatSession Release 构造 Domain 快照检索和 Claim Scope。"""
    binding = await authorize_chat_session_release_scope(
        db, session_row=session_row, user_id=session_row.user_id
    )
    if binding is None:
        raise ValueError("未绑定课程版本的会话不应构造固定 Release 检索")

    material_version_ids = binding.manifest.get("material_version_ids")
    material_ids = binding.manifest.get("materials")
    if (
        not isinstance(material_ids, list)
        or not material_ids
        or any(not isinstance(value, str) or not value.strip() for value in material_ids)
        or len(set(material_ids)) != len(material_ids)
        or
        not isinstance(material_version_ids, list)
        or not material_version_ids
        or any(not isinstance(value, str) or not value.strip() for value in material_version_ids)
        or len(set(material_version_ids)) != len(material_version_ids)
        or len(material_version_ids) != len(material_ids)
    ):
        return _blocked_bound_chat_retrieval(
            session_row=session_row,
            organization_id=organization_id,
            binding=binding,
            material_version_ids=[],
            refusal_reason="release_material_versions_unpinned",
        )
    if binding.domain_release_id is None:
        return _blocked_bound_chat_retrieval(
            session_row=session_row,
            organization_id=organization_id,
            binding=binding,
            material_version_ids=material_version_ids,
            refusal_reason="release_domain_snapshot_missing",
        )

    domain_release = await db.scalar(
        select(DomainRelease).where(
            DomainRelease.id == binding.domain_release_id,
            DomainRelease.course_id == session_row.course_id,
            DomainRelease.status.in_(("published", "deprecated")),
        )
    )
    if domain_release is None:
        return _blocked_bound_chat_retrieval(
            session_row=session_row,
            organization_id=organization_id,
            binding=binding,
            material_version_ids=material_version_ids,
            refusal_reason="domain_release_unavailable",
        )

    manifest_snapshots = binding.manifest.get("publication_snapshots")
    snapshot_fields = {
        "material_id",
        "material_version_id",
        "publication_snapshot_id",
        "index_job_id",
        "embedding_version",
        "domain_release_id",
    }
    valid_snapshot_pins = isinstance(manifest_snapshots, list) and len(
        manifest_snapshots
    ) == len(material_ids)
    if valid_snapshot_pins:
        valid_snapshot_pins = all(
            isinstance(item, dict)
            and set(item) == snapshot_fields
            and all(
                isinstance(item.get(key), str) and item[key].strip()
                for key in snapshot_fields
            )
            for item in manifest_snapshots
        )
    if valid_snapshot_pins:
        snapshot_ids = [item["publication_snapshot_id"] for item in manifest_snapshots]
        valid_snapshot_pins = len(set(snapshot_ids)) == len(snapshot_ids)
    if not valid_snapshot_pins:
        return _blocked_bound_chat_retrieval(
            session_row=session_row,
            organization_id=organization_id,
            binding=binding,
            material_version_ids=material_version_ids,
            refusal_reason="release_material_snapshots_unpinned",
        )

    ordered_snapshots = list(
        zip(material_ids, material_version_ids, manifest_snapshots, strict=True)
    )
    if any(
        item["material_id"] != material_id
        or item["material_version_id"] != version_id
        or item["domain_release_id"] != binding.domain_release_id
        for material_id, version_id, item in ordered_snapshots
    ):
        return _blocked_bound_chat_retrieval(
            session_row=session_row,
            organization_id=organization_id,
            binding=binding,
            material_version_ids=material_version_ids,
            refusal_reason="release_material_snapshots_mismatch",
        )

    snapshots: list[PublicationSnapshot] = []
    for material_id, version_id, pin in ordered_snapshots:
        snapshot = await db.get(PublicationSnapshot, pin["publication_snapshot_id"])
        material = await db.get(Material, material_id)
        version = await db.get(MaterialVersion, version_id)
        if (
            snapshot is None
            or snapshot.material_id != material_id
            or snapshot.material_version_id != version_id
            or snapshot.index_job_id != pin["index_job_id"]
            or snapshot.embedding_version != pin["embedding_version"]
            or snapshot.domain_release_id != binding.domain_release_id
            or material is None
            or material.course_id != session_row.course_id
            or material.status != "active"
            or material.visibility != "published"
            or version is None
            or version.material_id != material_id
            or version.status != "parsed"
        ):
            return _blocked_bound_chat_retrieval(
                session_row=session_row,
                organization_id=organization_id,
                binding=binding,
                material_version_ids=material_version_ids,
                refusal_reason="publication_snapshot_unavailable",
            )

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
            or payload.get("material_version_id") != version_id
            or payload.get("domain_release_id") != binding.domain_release_id
        ):
            return _blocked_bound_chat_retrieval(
                session_row=session_row,
                organization_id=organization_id,
                binding=binding,
                material_version_ids=material_version_ids,
                refusal_reason="publication_index_job_mismatch",
            )

        ready_units = await db.scalar(
            select(func.count(RetrievalUnit.id)).where(
                RetrievalUnit.material_version_id == version_id,
                RetrievalUnit.domain_release_id == binding.domain_release_id,
                RetrievalUnit.build_version == f"v1-{index_job.id}",
                RetrievalUnit.status == "ready",
            )
        )
        if not ready_units:
            return _blocked_bound_chat_retrieval(
                session_row=session_row,
                organization_id=organization_id,
                binding=binding,
                material_version_ids=material_version_ids,
                refusal_reason="publication_retrieval_snapshot_missing",
            )
        snapshots.append(snapshot)

    publication_snapshots = [
        {
            "material_id": snapshot.material_id,
            "material_version_id": snapshot.material_version_id,
            "publication_snapshot_id": snapshot.id,
            "index_job_id": snapshot.index_job_id,
            "embedding_version": snapshot.embedding_version,
            "domain_release_id": snapshot.domain_release_id,
        }
        for snapshot in snapshots
    ]
    required_scope = _chat_claim_scope(
        session_row=session_row,
        organization_id=organization_id,
        binding=binding,
        material_version_ids=material_version_ids,
        publication_snapshots=publication_snapshots,
    )
    index_job_ids = {
        item["material_version_id"]: item["index_job_id"]
        for item in publication_snapshots
    }
    query_plan = analyze_query(query)

    async def retrieve(scoped_scope: dict[str, Any]) -> list[dict[str, Any]]:
        if scoped_scope != required_scope:
            return []
        items, _warnings = await knowledge_service.hybrid_search(
            db,
            user_id=session_row.user_id,
            course_id=session_row.course_id,
            version_ids=list(material_version_ids),
            query=query,
            top_k=min(8, query_plan.retrieval_budget),
            staff=False,
            channel_priors=query_plan.channel_priors,
            domain_release_id=binding.domain_release_id,
            domain_index_job_ids=index_job_ids,
        )
        return items

    initial_items = await retrieve(required_scope)
    await db.flush()

    def evaluate_claim(claim: str, evidence: list[Any]) -> dict[str, Any]:
        evidence_items = [item for item in evidence if isinstance(item, dict)]
        package = build_evidence_package(
            user_id=session_row.user_id,
            course_id=session_row.course_id,
            query=claim,
            items=evidence_items,
        )
        result = verify_claims(claim, package)
        supported = [
            item["claim"] for item in result["claims"] if item.get("support") == "supported"
        ]
        unsupported = [
            item["claim"] for item in result["claims"] if item.get("support") != "supported"
        ]
        classified = classify_claim(
            supported_subclaims=supported,
            unsupported_subclaims=unsupported,
        )
        classified["evidence_ids"] = [
            item["evidence_id"] for item in evidence_items if item.get("evidence_id")
        ]
        return classified

    claim_context = DomainClaimContext(
        retrieval_scope=deepcopy(required_scope),
        required_scope=deepcopy(required_scope),
        evaluate=evaluate_claim,
        retrieve_once=retrieve,
    )
    warnings = ["检索范围固定为会话绑定的 CourseRelease PublicationSnapshot"]
    return BoundChatRetrieval(items=initial_items, warnings=warnings, claim_context=claim_context)


def _chat_claim_scope(
    *,
    session_row: Any,
    organization_id: str,
    binding: ChatSessionReleaseScope,
    material_version_ids: list[str],
    publication_snapshots: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "user_id": session_row.user_id,
        "organization_id": organization_id,
        "course_id": session_row.course_id,
        "class_id": binding.class_id,
        "course_release_assignment_id": binding.assignment_id,
        "course_release_id": binding.release_id,
        "domain_release_id": binding.domain_release_id or "unavailable",
        "publication_snapshot_id": [
            item["publication_snapshot_id"] for item in publication_snapshots
        ],
        "material_version_ids": list(material_version_ids),
        "index_job_id": [item["index_job_id"] for item in publication_snapshots],
        "embedding_version": sorted({item["embedding_version"] for item in publication_snapshots}),
        "publication_snapshots": deepcopy(publication_snapshots),
    }


def _blocked_bound_chat_retrieval(
    *,
    session_row: Any,
    organization_id: str,
    binding: ChatSessionReleaseScope,
    material_version_ids: list[str],
    refusal_reason: str,
) -> BoundChatRetrieval:
    scope = _chat_claim_scope(
        session_row=session_row,
        organization_id=organization_id,
        binding=binding,
        material_version_ids=material_version_ids,
        publication_snapshots=[],
    )
    context = DomainClaimContext(
        retrieval_scope=scope,
        required_scope=deepcopy(scope),
        evaluate=lambda _claim, _evidence: {"status": "unknown"},
        retrieve_once=lambda _scope: _empty_evidence(),
        refusal_reason=refusal_reason,
    )
    return BoundChatRetrieval(
        items=[],
        warnings=["当前课程版本没有可安全使用的固定教材快照"],
        claim_context=context,
    )


async def _empty_evidence() -> list[dict[str, Any]]:
    return []


# ---- 抽取式回答生成（可替换为LLM） ----

def generate_answer(
    query: str,
    package: EvidencePackage,
    *,
    response_length: str = "BALANCED",
    example_order: str = "CONCEPT_FIRST",
) -> str:
    """从证据中抽取相关句子，并按学生偏好控制长度与讲解顺序。"""
    if not package.items:
        return "当前教材中未找到足够依据回答这个问题，建议补充资料或向教师求助。"
    query_tokens = set(TOKEN_RE.findall(query.lower()))
    best_sentences: list[tuple[float, str]] = []
    for item in package.items:
        for sentence in SENTENCE_RE.findall(item["text"]):
            sentence = sentence.strip()
            if len(sentence) < 8:
                continue
            tokens = set(TOKEN_RE.findall(sentence.lower()))
            overlap = len(tokens & query_tokens) / max(len(tokens), 1)
            best_sentences.append((overlap, sentence))
    best_sentences.sort(key=lambda pair: pair[0], reverse=True)
    picked = [s for score, s in best_sentences if score > 0]
    if not picked:
        picked = [best_sentences[0][1]] if best_sentences else []
    adaptive_example_first = example_order == "ADAPTIVE" and any(
        marker in query for marker in ("例子", "举例", "例如", "比如", "案例")
    )
    if example_order == "EXAMPLE_FIRST" or adaptive_example_first:
        example_markers = ("例如", "比如", "举例", "案例")
        picked.sort(key=lambda sentence: not any(marker in sentence for marker in example_markers))
    if response_length == "CONCISE":
        picked = picked[:1]
    elif response_length == "BALANCED":
        picked = picked[:3]
    else:
        picked = picked[:5]
    return "根据教材：" + " ".join(picked)


def apply_presentation_preferences(
    answer: str, *, response_length: str, example_order: str, query: str = ""
) -> str:
    """只重排或截短已生成内容，不增加教材外事实。"""
    prefix = "根据教材："
    content = answer.removeprefix(prefix)
    sentences = [sentence.strip() for sentence in SENTENCE_RE.findall(content) if sentence.strip()]
    adaptive_example_first = example_order == "ADAPTIVE" and any(
        marker in query for marker in ("例子", "举例", "例如", "比如", "案例")
    )
    if example_order == "EXAMPLE_FIRST" or adaptive_example_first:
        markers = ("例如", "比如", "举例", "案例")
        sentences.sort(key=lambda sentence: not any(marker in sentence for marker in markers))
    if response_length == "CONCISE":
        sentences = sentences[:1]
    elif response_length == "BALANCED":
        sentences = sentences[:3]
    else:
        sentences = sentences[:5]
    return prefix + " ".join(sentences) if sentences else answer


async def generate_grounded_answer(
    db: AsyncSession,
    *,
    query: str,
    package: EvidencePackage,
    user_id: str,
    purpose: str,
) -> tuple[str, str]:
    """按部署配置调用单一供应商；失败时退回教材抽取式答案。"""
    settings = get_settings()
    if settings.llm_provider == "internal" or not package.items:
        return generate_answer(query, package), "internal"
    try:
        provider = OpenAICompatibleLLM(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    except ValueError:
        return generate_answer(query, package), "internal_configuration_fallback"

    async def invoke():
        generated = await provider.generate_grounded_answer(
            query=query, evidence=package.items
        )
        return generated, generated.prompt_tokens, generated.completion_tokens

    try:
        result = await call_model(
            db,
            purpose=purpose,
            provider=settings.llm_provider,
            model=settings.llm_model,
            invoke=invoke,
            user_id=user_id,
        )
    except Exception:  # noqa: BLE001 外部失败不得破坏教材约束回答
        return generate_answer(query, package), "internal_fallback"
    if result.status != "ok" or result.output is None:
        return generate_answer(query, package), "internal_fallback"
    return result.output.answer, settings.llm_provider


# ---- 主张—证据校验 ----

def verify_claims(answer: str, package: EvidencePackage) -> dict:
    """逐句核对是否被证据支持。无支持内容标记为not_found（应删除或标注）。"""
    evidence_text = package.evidence_text().lower()
    evidence_tokens = set(TOKEN_RE.findall(evidence_text))
    claims = []
    for sentence in SENTENCE_RE.findall(answer):
        sentence = sentence.strip()
        if len(sentence) < 4:
            continue
        normalized = sentence.lower().removeprefix("根据教材：")
        tokens = set(TOKEN_RE.findall(normalized))
        if not tokens:
            continue
        overlap = len(tokens & evidence_tokens) / len(tokens)
        level = "supported" if overlap >= 0.9 else "partial" if overlap >= 0.6 else "not_found"
        claims.append({"claim": sentence, "support": level, "overlap": round(overlap, 3)})
    unsupported = sum(1 for c in claims if c["support"] == "not_found")
    return {"claims": claims, "unsupported_count": unsupported}


# ---- SSE 回合 ----

def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": data}


async def run_turn_stream(
    db: AsyncSession,
    *,
    session_row,  # ChatSession
    student_turn_id: str,
    client_turn_id: str,
    content: str,
    purpose: str,
    effective_policy: dict | None = None,
    domain_claim_context: DomainClaimContext | None = None,
    organization_id: str | None = None,
    response_length: str = "BALANCED",
    example_order: str = "CONCEPT_FIRST",
):
    """生成SSE事件流。仅当全部成功时才提交（半截结论不落库）。"""
    yield _sse("state", {"stage": "retrieving"})

    from app.modules.memory.service import is_crisis_content, safety_response

    if is_crisis_content(content):
        answer = safety_response()
        yield _sse("state", {"stage": "safety"})
        for chunk_start in range(0, len(answer), 24):
            yield _sse(
                "delta",
                {"sequence": chunk_start // 24, "text": answer[chunk_start : chunk_start + 24]},
            )
        db.add(
            ChatTurn(
                session_id=session_row.id,
                client_turn_id=client_turn_id,
                role="student",
                content=content,
            )
        )
        tutor_turn = ChatTurn(
            session_id=session_row.id,
            client_turn_id=f"{client_turn_id}:tutor",
            role="tutor",
            content=answer,
            citations=[],
            refusal=True,
            finish_reason="safety",
            verification={"effective_policy": effective_policy} if effective_policy else None,
        )
        db.add(tutor_turn)
        await db.flush()
        await db.refresh(tutor_turn, attribute_names=["id"])
        await db.commit()
        yield _sse(
            "done",
            {
                "turn_id": tutor_turn.id,
                "finish_reason": "safety",
                "saved": True,
                "refusal": True,
            },
        )
        return

    try:
        plan = analyze_query(content)
        if session_row.course_release_assignment_id is not None:
            if not organization_id:
                raise ValueError("固定 Release 检索缺少组织 Scope")
            bound_retrieval = await prepare_bound_chat_retrieval(
                db,
                session_row=session_row,
                organization_id=organization_id,
                query=content,
            )
            items = bound_retrieval.items
            warnings = bound_retrieval.warnings
            domain_claim_context = bound_retrieval.claim_context
        else:
            items, warnings = await knowledge_service.hybrid_search(
                db,
                user_id=session_row.user_id,
                course_id=session_row.course_id,
                version_ids=await knowledge_service.resolve_searchable_versions(
                    db,
                    course_id=session_row.course_id,
                    requested_version_ids=[],
                    staff=False,
                ),
                query=content,
                top_k=min(8, plan.retrieval_budget),
                staff=False,
                channel_priors=plan.channel_priors,
            )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        yield _sse(
            "error",
            {"code": "RETRIEVAL_FAILED", "retryable": True, "message": str(exc)[:200]},
        )
        return

    package = build_evidence_package(
        user_id=session_row.user_id,
        course_id=session_row.course_id,
        query=content,
        items=items,
    )
    yield _sse(
        "state",
        {"stage": "generating", "evidence_count": len(package.items), "warnings": warnings},
    )

    refusal = not package.items
    answer, generation_provider = await generate_grounded_answer(
        db,
        query=content,
        package=package,
        user_id=session_row.user_id,
        purpose=purpose,
    )
    answer = apply_presentation_preferences(
        answer,
        response_length=response_length,
        example_order=example_order,
        query=content,
    )
    verification = verify_claims(answer, package)
    if verification["unsupported_count"]:
        answer = generate_answer(
            content, package, response_length=response_length, example_order=example_order
        )
        generation_provider = "internal_verification_fallback"
        verification = verify_claims(answer, package)
    verification["generation_provider"] = generation_provider
    if effective_policy:
        verification["effective_policy"] = effective_policy
    if domain_claim_context is not None:
        domain_claim = await verify_domain_claim_for_tutor(
            claim=answer,
            initial_evidence=package.items,
            context=domain_claim_context,
        )
        verification["domain_claim"] = domain_claim
        if domain_claim["status"] != "supported":
            refusal = True
            answer = "当前课程发布版本中的证据不足以核验这条回答，暂不提供结论。"
    answer = answer.removeprefix("根据教材：")
    answer = "根据教材：" + answer if not refusal else answer

    for index, item in enumerate(package.items, start=1):
        yield _sse(
            "citation",
            {
                "evidence_id": item["evidence_id"],
                "evidence_pointer_id": item.get("evidence_pointer_id"),
                "label": _citation_label(index, item["title"], item["physical_page"]),
            },
        )

    yield _sse("state", {"stage": "verifying"})
    for chunk_start in range(0, len(answer), 24):
        yield _sse(
            "delta",
            {"sequence": chunk_start // 24, "text": answer[chunk_start : chunk_start + 24]},
        )
        await asyncio.sleep(0.02)

    db.add(
        ChatTurn(
            session_id=session_row.id,
            client_turn_id=client_turn_id,
            role="student",
            content=content,
        )
    )
    tutor_turn = ChatTurn(
        session_id=session_row.id,
        client_turn_id=f"{client_turn_id}:tutor",
        role="tutor",
        content=answer,
        citations=[
            {
                "evidence_id": item["evidence_id"],
                "evidence_pointer_id": item.get("evidence_pointer_id"),
                "material_id": item["material_id"],
                "material_version_id": item["material_version_id"],
                "physical_page": item["physical_page"],
                "label": _citation_label(index, item["title"], item["physical_page"]),
            }
            for index, item in enumerate(package.items, start=1)
        ],
        verification=verification,
        refusal=refusal,
        finish_reason="stop",
    )
    db.add(tutor_turn)
    await db.flush()
    await db.refresh(tutor_turn, attribute_names=["id"])
    await db.commit()
    yield _sse(
        "done",
        {
            "turn_id": tutor_turn.id,
            "finish_reason": "stop",
            "saved": True,
            "refusal": refusal,
            "unsupported_count": verification["unsupported_count"],
        },
    )


# ---- 学习状态机 ----

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "对", "被", "把",
    "个", "这", "那", "the", "a", "an", "of", "to", "is", "are",
}
CORRECT_THRESHOLD = 0.2


def _texts_from_objects(objects: list) -> list[str]:
    return [
        (o.normalized_content or o.raw_content)
        for o in objects
        if o.type in ("paragraph",) and (o.normalized_content or o.raw_content).strip()
    ]


def top_keywords(texts: list[str], n: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        for token in TOKEN_RE.findall(text.lower()):
            if token in STOPWORDS or len(token) == 1:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [token for token, _ in ranked[:n]]


def _evaluate(content: str, keywords: list[str]) -> tuple[bool, float]:
    tokens = set(TOKEN_RE.findall(content.lower()))
    if not tokens or not keywords:
        return False, 0.0
    hits = sum(1 for k in keywords if any(k in t or t in k for t in tokens))
    ratio = hits / len(keywords)
    return ratio >= CORRECT_THRESHOLD, ratio


async def load_chapter_texts(
    db: AsyncSession, *, material_version_id: str, chapter_object_id: str | None
) -> list[str]:
    from app.db.models import KnowledgeObject

    query = select(KnowledgeObject).where(
        KnowledgeObject.material_version_id == material_version_id
    )
    if chapter_object_id:
        chapter = await db.get(KnowledgeObject, chapter_object_id)
        if chapter is not None:
            query = query.where(
                (KnowledgeObject.id == chapter_object_id)
                | (KnowledgeObject.chapter_path == chapter.chapter_path)
            )
    result = await db.execute(query.order_by(KnowledgeObject.reading_order.asc()))
    return _texts_from_objects(list(result.scalars()))


def opening_message(texts: list[str]) -> str:
    summary = texts[0][:120] if texts else "本章暂无可用教材内容。"
    return (
        "在开始讲解之前，想先了解你目前的理解："
        "请用自己的话说说你对这部分内容的认识，或者直接选择“从零开始”。\n"
        f"教材要点提示：{summary}"
    )


def teach_message(texts: list[str]) -> str:
    body = " ".join(texts)[:600] if texts else "教材中暂无本节内容。"
    return (
        f"{body}\n\n"
        "请确认理解情况：回复“继续”进入检查，或回复“没懂”换个方式再讲。"
    )


def check_question(keywords: list[str]) -> str:
    focus = "、".join(keywords[:3]) if keywords else "核心概念"
    return f"检查一下理解：请用自己的话解释“{focus}”之间的关系或区别。"


HINT_LADDER = [
    "先想想这一节主要讨论的是哪两个概念的对比。",
    "提示：关注“控制”与“有效性”之间的因果关系。",
    "示例：研究者控制参与者的分组方式，观察结果差异，由此推断因果。",
]


def hint_message(level: int) -> str:
    if level <= len(HINT_LADDER):
        return f"提示{level}：{HINT_LADDER[level - 1]}"
    return "提示已用完，下面给出完整讲解，请认真学习后进入练习。"


def full_explanation(texts: list[str]) -> str:
    return "完整讲解：" + (" ".join(texts)[:500] if texts else "教材中暂无本节内容。")


def practice_question(keywords: list[str]) -> str:
    focus = keywords[0] if keywords else "本章概念"
    return f"迁移练习：请举一个体现“{focus}”的新例子，并说明理由。"


def summary_message(texts: list[str], keywords: list[str]) -> str:
    focus = "、".join(keywords[:3]) if keywords else "本章内容"
    return f"小结：本节围绕{focus}展开。已完成学习，稍后会安排间隔复习。"


async def start_learning_session(
    db: AsyncSession, *, material_version_id: str, chapter_object_id: str | None
) -> str:
    texts = await load_chapter_texts(
        db, material_version_id=material_version_id, chapter_object_id=chapter_object_id
    )
    return opening_message(texts)


async def respond_learning_session(
    db: AsyncSession,
    session_row: LearningSession,
    content: str,
    effective_policy: dict | None = None,
) -> dict:
    """推进状态机。调用方需先校验state_version。"""
    texts = await load_chapter_texts(
        db,
        material_version_id=session_row.material_version_id,
        chapter_object_id=session_row.chapter_object_id,
    )
    keywords = top_keywords(texts)
    correct, _ = _evaluate(content, keywords)
    original_hint_level = session_row.hint_level
    state = session_row.state
    action = "wait_for_student"

    if content.strip() in ("从零开始", "没懂", "不会"):
        if effective_policy and "teach" not in effective_policy["allowed_actions"]:
            raise ApiError(
                status_code=403,
                code="TEACHING_ACTION_NOT_ALLOWED",
                message="当前教学策略不允许讲解动作。",
                details={"policy_version": effective_policy["version"], "action": "teach"},
            )
        state, session_row.hint_level = "teach", 0
        session_row.state = state
        session_row.version += 1
        session_row.tutor_message = teach_message(texts)
        return {
            "state": state,
            "message": session_row.tutor_message,
            "action": action,
            "hint_level": 0,
            "correct": None,
            "teaching_action": "teach",
            "support_gradient": 0,
            "policy": effective_policy,
        }

    if state == "diagnose":
        state = "teach"
        session_row.tutor_message = teach_message(texts)
    elif state == "teach":
        if correct:
            state = "check"
            session_row.tutor_message = check_question(keywords)
        else:
            state = "teach"
            session_row.hint_level = min(session_row.hint_level + 1, MAX_HINT_LEVEL)
            session_row.tutor_message = (
                hint_message(session_row.hint_level) + "\n" + teach_message(texts)
            )
    elif state == "check":
        if correct:
            state = "practice"
            session_row.tutor_message = practice_question(keywords)
        else:
            session_row.hint_level += 1
            if session_row.hint_level >= MAX_HINT_LEVEL:
                state = "practice"
                action = "show_example"
                full_note = full_explanation(texts)
                session_row.tutor_message = full_note + "\n" + practice_question(keywords)
                session_row.hint_level = MAX_HINT_LEVEL
            else:
                state = "hint"
                session_row.tutor_message = hint_message(
                    session_row.hint_level
                ) + "\n" + check_question(keywords)
    elif state == "hint":
        if correct:
            state = "practice"
            session_row.tutor_message = practice_question(keywords)
        else:
            session_row.hint_level += 1
            if session_row.hint_level >= MAX_HINT_LEVEL:
                state = "practice"
                action = "show_example"
                session_row.tutor_message = full_explanation(texts) + "\n" + practice_question(
                    keywords
                )
            else:
                session_row.tutor_message = hint_message(
                    session_row.hint_level
                ) + "\n" + check_question(keywords)
    elif state == "practice":
        state = "summary"
        verdict = "回答正确" if correct else "回答有偏差，已记录为待巩固"
        session_row.tutor_message = f"{verdict}。\n" + summary_message(texts, keywords)
    elif state == "summary":
        state = "completed"
        action = "complete"
        session_row.tutor_message = "本节学习已完成，可随时回来复习。"
        session_row.status = "closed"
    else:  # completed
        session_row.tutor_message = "学习已结束。"

    session_row.state = state
    session_row.version += 1
    teaching_action = (
        "hint"
        if session_row.hint_level > original_hint_level
        else {
            "diagnose": "diagnose",
            "teach": "teach",
            "check": "check",
            "hint": "hint",
            "practice": "practice",
            "summary": "summarize",
            "completed": "summarize",
        }.get(state, "handoff")
    )
    if effective_policy:
        if teaching_action not in effective_policy["allowed_actions"]:
            raise ApiError(
                status_code=403,
                code="TEACHING_ACTION_NOT_ALLOWED",
                message="当前教学策略不允许该教学动作。",
                details={"policy_version": effective_policy["version"], "action": teaching_action},
            )
        if teaching_action == "hint" and session_row.hint_level > effective_policy["max_hints"]:
            raise ApiError(
                status_code=403,
                code="TEACHING_HINT_BUDGET_EXHAUSTED",
                message="当前教学策略的提示预算已用完。",
                details={"policy_version": effective_policy["version"]},
            )
    return {
        "state": session_row.state,
        "message": session_row.tutor_message,
        "action": action,
        "hint_level": session_row.hint_level,
        "correct": correct,
        "teaching_action": teaching_action,
        "support_gradient": min(session_row.hint_level, effective_policy["max_support_gradient"])
        if effective_policy
        else min(session_row.hint_level, 3),
        "policy": effective_policy,
    }
