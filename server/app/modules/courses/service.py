import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.outbox import append_event
from app.db.models import (
    AuditLog,
    ClassMember,
    Course,
    CourseClass,
    CourseMember,
    CourseRelease,
    CourseReleaseAssignment,
    IdempotencyRecord,
    User,
)
from app.modules.courses.schemas import CourseOut

_PACK_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "domain_pack": (
        "chapters",
        "knowledge_points",
        "relations",
        "experiments",
        "misconceptions",
        "evidence_bindings",
    ),
    "pedagogy_pack": ("tasks", "flows", "hints", "remediations", "success_criteria"),
    "assessment_pack": ("release_ids", "questions", "rubrics", "coverage"),
}
_PACK_ITEM_FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("domain_pack", "knowledge_points"): ("key", "title"),
    ("domain_pack", "relations"): ("source_key", "target_key", "relation_type"),
    ("domain_pack", "experiments"): ("key", "title"),
    ("domain_pack", "misconceptions"): ("key", "title"),
    ("domain_pack", "evidence_bindings"): (
        "key",
        "object_key",
        "material_id",
        "material_version_id",
        "source_object_id",
    ),
    ("pedagogy_pack", "flows"): ("key", "title", "steps"),
    ("assessment_pack", "questions"): ("key", "prompt", "type"),
    ("assessment_pack", "rubrics"): ("key", "title", "criteria"),
}
_PACK_ITEM_OPTIONAL_FIELDS: dict[tuple[str, str], frozenset[str]] = {
    ("domain_pack", "knowledge_points"): frozenset({"evidence_binding_keys"}),
    ("domain_pack", "relations"): frozenset({"key", "evidence_binding_keys"}),
    ("domain_pack", "experiments"): frozenset(
        {
            "research_question",
            "hypothesis",
            "iv",
            "dv",
            "operationalization",
            "controls",
            "confounds",
            "design",
            "procedure",
            "prediction",
            "result_pattern",
            "interpretation",
            "limitations",
            "textbook_evidence",
            "knowledge_point_keys",
            "evidence_binding_keys",
        }
    ),
    ("domain_pack", "misconceptions"): frozenset({"knowledge_point_keys", "evidence_binding_keys"}),
}
_DOMAIN_RELATION_ENDPOINT_TYPES: dict[str, tuple[str, str]] = {
    # 课程设计目前只定义了知识点先修关系；其他关系类型需先进入契约。
    "prerequisite": ("knowledge_points", "knowledge_points"),
}


async def resolve_active_student_course_release(
    db: AsyncSession, *, user_id: str, course_id: str
) -> tuple[CourseReleaseAssignment, CourseRelease] | None:
    """解析学生在课程中的唯一活动 Release assignment。"""
    rows = (
        await db.execute(
            select(CourseReleaseAssignment, CourseRelease)
            .join(CourseClass, CourseClass.id == CourseReleaseAssignment.class_id)
            .join(ClassMember, ClassMember.class_id == CourseClass.id)
            .outerjoin(
                CourseRelease, CourseRelease.id == CourseReleaseAssignment.course_release_id
            )
            .where(
                CourseReleaseAssignment.course_id == course_id,
                CourseReleaseAssignment.status == "active",
                CourseClass.course_id == course_id,
                CourseClass.status == "active",
                ClassMember.user_id == user_id,
                ClassMember.status == "active",
            )
            .order_by(CourseReleaseAssignment.id.asc())
        )
    ).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS",
            message="当前学生属于多个已发布课程版本班级，请联系教师确认班级归属。",
        )
    assignment, release = rows[0]
    if (
        release is None
        or release.course_id != course_id
        or release.status not in {"published", "deprecated"}
    ):
        raise ApiError(
            status_code=409,
            code="COURSE_RELEASE_ASSIGNMENT_INVALID",
            message="当前班级课程版本不可用，请联系教师检查课程指派。",
        )
    return assignment, release


def _domain_graph_issues(
    value: dict[str, Any],
    *,
    for_publish: bool,
    material_ids: set[str] | None,
    material_versions: dict[str, str] | None,
    evidence_sources: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """Validate the portion of the Domain Pack graph with a documented shape.

    Domain object types are fixed by their collection. Stable keys share one
    namespace across chapters, KnowledgePoints, experiments, misconceptions, and relations.
    The only currently supported Relation is a directed KnowledgePoint
    ``prerequisite`` edge. Experiments and misconceptions may reference declared
    KnowledgePoints; EvidenceBindings must reference a declared object and a
    selected textbook material and stable source object before publication.
    """
    issues: list[dict[str, Any]] = []
    chapters = value.get("chapters", [])
    knowledge_points = value.get("knowledge_points", [])
    experiments = value.get("experiments", [])
    misconceptions = value.get("misconceptions", [])
    relations = value.get("relations", [])
    evidence_bindings = value.get("evidence_bindings", [])

    # Structural validation emits the primary 422 before this helper is called.
    if not isinstance(knowledge_points, list):
        return issues
    if not isinstance(chapters, list):
        chapters = []
    if not isinstance(experiments, list):
        experiments = []
    if not isinstance(misconceptions, list):
        misconceptions = []
    if not isinstance(relations, list):
        return issues
    if not isinstance(evidence_bindings, list):
        evidence_bindings = []

    object_keys: dict[str, str] = {}
    knowledge_point_keys: set[str] = set()
    domain_facts: list[tuple[str, str, list[str]]] = []
    for index, key in enumerate(chapters):
        if not isinstance(key, str) or not key.strip():
            continue
        if key != key.strip():
            issues.append(
                {
                    "code": "DOMAIN_OBJECT_KEY_NOT_CANONICAL",
                    "path": f"chapters[{index}]",
                    "message": "章节稳定 ID 不得包含首尾空白",
                    "key": key,
                }
            )
        if key in object_keys:
            issues.append(
                {
                    "code": "DOMAIN_OBJECT_KEY_DUPLICATE",
                    "path": f"chapters[{index}]",
                    "message": "Domain Pack 中对象 key 必须唯一",
                    "key": key,
                    "first_type": object_keys[key],
                    "duplicate_type": "chapters",
                }
            )
        else:
            object_keys[key] = "chapters"
    for field, items in (
        ("knowledge_points", knowledge_points),
        ("experiments", experiments),
        ("misconceptions", misconceptions),
    ):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if field == "experiments":
                for field_name in (
                    "research_question",
                    "hypothesis",
                    "iv",
                    "dv",
                    "operationalization",
                    "design",
                    "procedure",
                    "prediction",
                    "result_pattern",
                    "interpretation",
                    "limitations",
                ):
                    field_value = item.get(field_name)
                    if field_value is not None and (
                        not isinstance(field_value, str) or len(field_value) > 4000
                    ):
                        issues.append(
                            {
                                "code": "DOMAIN_EXPERIMENT_FIELD_INVALID",
                                "path": f"experiments[{index}].{field_name}",
                                "message": "实验结构字段必须是至多 4000 字符的文本，或留空",
                            }
                        )
                for field_name in ("controls", "confounds"):
                    field_value = item.get(field_name)
                    if field_value is None:
                        continue
                    if (
                        not isinstance(field_value, list)
                        or len(field_value) > 50
                        or any(
                            not isinstance(entry, str)
                            or not entry.strip()
                            or len(entry) > 1000
                            for entry in field_value
                        )
                    ):
                        issues.append(
                            {
                                "code": "DOMAIN_EXPERIMENT_FIELD_INVALID",
                                "path": f"experiments[{index}].{field_name}",
                                "message": "该字段必须是至多 50 项的非空文本数组，或留空",
                            }
                        )
            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                continue
            if key != key.strip():
                issues.append(
                    {
                        "code": "DOMAIN_OBJECT_KEY_NOT_CANONICAL",
                        "path": f"{field}[{index}].key",
                        "message": "稳定对象 key 不得包含首尾空白",
                        "key": key,
                    }
                )
            previous_type = object_keys.get(key)
            if previous_type is not None:
                issues.append(
                    {
                        "code": "DOMAIN_OBJECT_KEY_DUPLICATE",
                        "path": f"{field}[{index}].key",
                        "message": "Domain Pack 中对象 key 必须唯一",
                        "key": key,
                        "first_type": previous_type,
                        "duplicate_type": field,
                    }
                )
            else:
                object_keys[key] = field
            if field == "knowledge_points":
                knowledge_point_keys.add(key)
            binding_keys = item.get("evidence_binding_keys", [])
            if not isinstance(binding_keys, list) or not all(
                isinstance(binding_key, str) and binding_key.strip() for binding_key in binding_keys
            ):
                issues.append(
                    {
                        "code": "DOMAIN_EVIDENCE_BINDING_KEYS_INVALID",
                        "path": f"{field}[{index}].evidence_binding_keys",
                        "message": "evidence_binding_keys 必须是非空字符串数组",
                    }
                )
                binding_keys = []
            if field == "experiments" and item.get("textbook_evidence") is not None:
                textbook_evidence = item["textbook_evidence"]
                if (
                    "evidence_binding_keys" in item
                    and item["evidence_binding_keys"] != textbook_evidence
                ):
                    issues.append(
                        {
                            "code": "DOMAIN_EXPERIMENT_EVIDENCE_FIELDS_CONFLICT",
                            "path": f"experiments[{index}].textbook_evidence",
                            "message": (
                                "textbook_evidence 与 evidence_binding_keys "
                                "同时填写时必须完全一致"
                            ),
                        }
                    )
                binding_keys = textbook_evidence
                if not isinstance(binding_keys, list) or not all(
                    isinstance(binding_key, str) and binding_key.strip()
                    for binding_key in binding_keys
                ):
                    issues.append(
                        {
                            "code": "DOMAIN_EVIDENCE_BINDING_KEYS_INVALID",
                            "path": f"experiments[{index}].textbook_evidence",
                            "message": "textbook_evidence 必须是非空字符串 key 数组",
                        }
                    )
                    binding_keys = []
            domain_facts.append((field, key, binding_keys))

            refs = item.get("knowledge_point_keys", [])
            if field != "knowledge_points" and not isinstance(refs, list):
                issues.append(
                    {
                        "code": "DOMAIN_KNOWLEDGE_POINT_REFS_INVALID",
                        "path": f"{field}[{index}].knowledge_point_keys",
                        "message": "knowledge_point_keys 必须是数组",
                    }
                )

    seen_edges: set[tuple[str, str, str]] = set()
    relation_fact_bindings: list[tuple[str, list[str]]] = []
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue
        source_key = relation.get("source_key")
        target_key = relation.get("target_key")
        relation_type = relation.get("relation_type")
        # The structural validator already reports absent/ill-typed fields.
        relation_fields = (source_key, target_key, relation_type)
        if not all(isinstance(item, str) and item.strip() for item in relation_fields):
            continue
        path = f"relations[{index}]"
        relation_key = relation.get("key")
        if relation_key is None:
            # 没有显式 ID 时，以有序端点和类型生成稳定关系 ID。
            relation_key = "relation:" + json.dumps(
                [source_key, relation_type, target_key],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif not isinstance(relation_key, str) or not relation_key.strip():
            issues.append(
                {
                    "code": "DOMAIN_RELATION_KEY_INVALID",
                    "path": f"{path}.key",
                    "message": "显式 Relation key 必须是非空字符串",
                }
            )
            relation_key = "relation:" + json.dumps(
                [source_key, relation_type, target_key],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif relation_key != relation_key.strip():
            issues.append(
                {
                    "code": "DOMAIN_OBJECT_KEY_NOT_CANONICAL",
                    "path": f"{path}.key",
                    "message": "稳定对象 key 不得包含首尾空白",
                    "key": relation_key,
                }
            )
        previous_type = object_keys.get(relation_key)
        if previous_type is not None:
            issues.append(
                {
                    "code": "DOMAIN_OBJECT_KEY_DUPLICATE",
                    "path": f"{path}.key",
                    "message": "Domain Pack 中对象 key 必须唯一",
                    "key": relation_key,
                    "first_type": previous_type,
                    "duplicate_type": "relations",
                }
            )
        else:
            object_keys[relation_key] = "relations"
        binding_keys = relation.get("evidence_binding_keys", [])
        if not isinstance(binding_keys, list) or not all(
            isinstance(binding_key, str) and binding_key.strip() for binding_key in binding_keys
        ):
            issues.append(
                {
                    "code": "DOMAIN_EVIDENCE_BINDING_KEYS_INVALID",
                    "path": f"{path}.evidence_binding_keys",
                    "message": "evidence_binding_keys 必须是非空字符串数组",
                }
            )
            binding_keys = []
        relation_fact_bindings.append((relation_key, binding_keys))
        if source_key not in knowledge_point_keys:
            issues.append(
                {
                    "code": "DOMAIN_RELATION_SOURCE_NOT_FOUND",
                    "path": f"{path}.source_key",
                    "message": "关系 source_key 必须引用已声明的 KnowledgePoint key",
                    "key": source_key,
                }
            )
        if target_key not in knowledge_point_keys:
            issues.append(
                {
                    "code": "DOMAIN_RELATION_TARGET_NOT_FOUND",
                    "path": f"{path}.target_key",
                    "message": "关系 target_key 必须引用已声明的 KnowledgePoint key",
                    "key": target_key,
                }
            )
        expected_endpoints = _DOMAIN_RELATION_ENDPOINT_TYPES.get(relation_type)
        if expected_endpoints is None:
            issues.append(
                {
                    "code": "DOMAIN_RELATION_TYPE_UNSUPPORTED",
                    "path": f"{path}.relation_type",
                    "message": "关系类型尚未纳入 Domain Pack 契约",
                    "relation_type": relation_type,
                }
            )
        elif (object_keys.get(source_key), object_keys.get(target_key)) != expected_endpoints:
            issues.append(
                {
                    "code": "DOMAIN_RELATION_ENDPOINT_TYPE_INVALID",
                    "path": path,
                    "message": "关系两端对象类型不符合该关系类型的方向约束",
                    "relation_type": relation_type,
                    "expected_endpoint_types": list(expected_endpoints),
                    "actual_endpoint_types": [
                        object_keys.get(source_key),
                        object_keys.get(target_key),
                    ],
                }
            )
        if source_key == target_key:
            issues.append(
                {
                    "code": "DOMAIN_RELATION_SELF_REFERENCE",
                    "path": path,
                    "message": "Domain Relation 不允许自引用",
                    "key": source_key,
                }
            )
        edge = (source_key, target_key, relation_type)
        if edge in seen_edges:
            issues.append(
                {
                    "code": "DOMAIN_RELATION_DUPLICATE",
                    "path": path,
                    "message": "相同方向与类型的关系边不得重复",
                    "source_key": source_key,
                    "target_key": target_key,
                    "relation_type": relation_type,
                }
            )
        else:
            seen_edges.add(edge)

    # prerequisite 是有向无环关系。检测只使用两端都已声明的合法边，
    # 这样悬空引用仍由上面的字段级错误报告，不会产生误导性的环错误。
    prerequisite_edges: dict[str, set[str]] = {}
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        source_key = relation.get("source_key")
        target_key = relation.get("target_key")
        if (
            relation.get("relation_type") == "prerequisite"
            and source_key in knowledge_point_keys
            and target_key in knowledge_point_keys
            and source_key != target_key
        ):
            prerequisite_edges.setdefault(source_key, set()).add(target_key)
    visited: set[str] = set()
    active: set[str] = set()
    reported_cycles: set[tuple[str, ...]] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in active:
            cycle_start = trail.index(node)
            cycle = tuple(sorted(trail[cycle_start:]))
            if cycle not in reported_cycles:
                reported_cycles.add(cycle)
                issues.append(
                    {
                        "code": "DOMAIN_RELATION_CYCLE",
                        "path": "relations",
                        "message": "prerequisite 关系必须构成有向无环图",
                        "keys": list(cycle),
                    }
                )
            return
        if node in visited:
            return
        active.add(node)
        trail.append(node)
        for target in sorted(prerequisite_edges.get(node, set())):
            visit(target, trail)
        trail.pop()
        active.remove(node)
        visited.add(node)

    for key in sorted(knowledge_point_keys):
        visit(key, [])

    # Resolve experiment/misconception references after collecting all node keys.
    for field, items in (("experiments", experiments), ("misconceptions", misconceptions)):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            refs = item.get("knowledge_point_keys", [])
            if isinstance(refs, list):
                for ref_index, ref_key in enumerate(refs):
                    if not isinstance(ref_key, str) or ref_key not in knowledge_point_keys:
                        issues.append(
                            {
                                "code": "DOMAIN_KNOWLEDGE_POINT_NOT_FOUND",
                                "path": f"{field}[{index}].knowledge_point_keys[{ref_index}]",
                                "message": "引用必须指向已声明的 KnowledgePoint key",
                                "key": ref_key,
                            }
                        )

    evidence_by_key: dict[str, dict[str, Any]] = {}
    for index, binding in enumerate(evidence_bindings):
        if not isinstance(binding, dict):
            continue
        binding_key = binding.get("key")
        if not isinstance(binding_key, str) or not binding_key.strip():
            continue
        canonical_binding_key = binding_key.strip()
        if binding_key != canonical_binding_key:
            issues.append(
                {
                    "code": "DOMAIN_EVIDENCE_BINDING_KEY_NOT_CANONICAL",
                    "path": f"evidence_bindings[{index}].key",
                    "message": "稳定 EvidenceBinding key 不得包含首尾空白",
                    "key": binding_key,
                }
            )
        if canonical_binding_key in evidence_by_key:
            issues.append(
                {
                    "code": "DOMAIN_EVIDENCE_BINDING_KEY_DUPLICATE",
                    "path": f"evidence_bindings[{index}].key",
                    "message": "EvidenceBinding key 必须唯一",
                    "key": binding_key,
                }
            )
            continue
        evidence_by_key[canonical_binding_key] = binding
        object_key = binding.get("object_key")
        if object_key not in object_keys:
            issues.append(
                {
                    "code": "DOMAIN_EVIDENCE_OBJECT_NOT_FOUND",
                    "path": f"evidence_bindings[{index}].object_key",
                    "message": "EvidenceBinding 必须引用已声明的 Domain Object key",
                    "key": object_key,
                }
            )
        if (
            for_publish
            and material_ids is not None
            and binding.get("material_id") not in material_ids
        ):
            issues.append(
                {
                    "code": "DOMAIN_EVIDENCE_MATERIAL_NOT_SELECTED",
                    "path": f"evidence_bindings[{index}].material_id",
                    "message": "EvidenceBinding 教材必须包含在当前 Release 的教材清单中",
                    "material_id": binding.get("material_id"),
                }
            )
        if (
            for_publish
            and material_versions is not None
            and binding.get("material_id") in material_versions
            and binding.get("material_version_id") != material_versions[binding.get("material_id")]
        ):
            issues.append(
                {
                    "code": "DOMAIN_EVIDENCE_VERSION_MISMATCH",
                    "path": f"evidence_bindings[{index}].material_version_id",
                    "message": "EvidenceBinding 版本必须与当前发布的教材版本一致",
                    "material_id": binding.get("material_id"),
                    "expected_material_version_id": material_versions[binding.get("material_id")],
                }
            )
        source_object_id = binding.get("source_object_id")
        if for_publish and evidence_sources is not None:
            source_version_id = evidence_sources.get(source_object_id)
            if source_version_id is None:
                issues.append(
                    {
                        "code": "DOMAIN_EVIDENCE_SOURCE_NOT_FOUND",
                        "path": f"evidence_bindings[{index}].source_object_id",
                        "message": "EvidenceBinding 来源必须是已解析的教材对象",
                        "source_object_id": source_object_id,
                    }
                )
            elif source_version_id != binding.get("material_version_id"):
                issues.append(
                    {
                        "code": "DOMAIN_EVIDENCE_SOURCE_VERSION_MISMATCH",
                        "path": f"evidence_bindings[{index}].source_object_id",
                        "message": "EvidenceBinding 来源对象必须属于声明的教材版本",
                        "source_object_id": source_object_id,
                        "material_version_id": binding.get("material_version_id"),
                        "source_material_version_id": source_version_id,
                    }
                )

    facts_with_bindings = domain_facts + [
        ("relations", object_key, binding_keys)
        for object_key, binding_keys in relation_fact_bindings
    ]
    valid_fact_bindings: set[tuple[str, str]] = set()
    for field, object_key, binding_keys in facts_with_bindings:
        for index, binding_key in enumerate(binding_keys):
            binding = evidence_by_key.get(binding_key)
            if binding is None:
                issues.append(
                    {
                        "code": "DOMAIN_EVIDENCE_BINDING_NOT_FOUND",
                        "path": f"{field}[{object_key}].evidence_binding_keys[{index}]",
                        "message": "引用必须指向已声明的 EvidenceBinding key",
                        "key": binding_key,
                    }
                )
            elif binding.get("object_key") != object_key:
                issues.append(
                    {
                        "code": "DOMAIN_EVIDENCE_BINDING_OBJECT_MISMATCH",
                        "path": f"{field}[{object_key}].evidence_binding_keys[{index}]",
                        "message": "EvidenceBinding 必须绑定到当前事实对象",
                        "key": binding_key,
                    }
                )
            elif (
                material_ids is None
                or not for_publish
                or binding.get("material_id") in material_ids
            ):
                version_matches = (
                    material_versions is None
                    or binding.get("material_id") not in material_versions
                    or binding.get("material_version_id")
                    == material_versions[binding.get("material_id")]
                )
                source_matches = (
                    evidence_sources is None
                    or binding.get("source_object_id") in evidence_sources
                    and evidence_sources[binding.get("source_object_id")]
                    == binding.get("material_version_id")
                )
                if version_matches and source_matches:
                    valid_fact_bindings.add((field, object_key))

    if for_publish:
        for field, object_key, _binding_keys in facts_with_bindings:
            if (field, object_key) not in valid_fact_bindings:
                issues.append(
                    {
                        "code": "DOMAIN_FACT_EVIDENCE_REQUIRED",
                        "path": f"{field}[{object_key}].evidence_binding_keys",
                        "message": "可发布事实必须绑定至少一条教材 Evidence",
                        "key": object_key,
                    }
                )
    return issues


def validate_domain_pack_graph(
    value: Any,
    *,
    for_publish: bool = False,
    material_ids: set[str] | None = None,
    material_versions: dict[str, str] | None = None,
    evidence_sources: dict[str, str] | None = None,
) -> None:
    """校验 Domain Pack 当前契约；发布时额外要求每条事实绑定教材证据。"""
    if not isinstance(value, dict):
        return
    issues = _domain_graph_issues(
        value,
        for_publish=for_publish,
        material_ids=material_ids,
        material_versions=material_versions,
        evidence_sources=evidence_sources,
    )
    if issues:
        raise ApiError(
            status_code=422,
            code="RELEASE_DOMAIN_GRAPH_INVALID",
            message="Domain Pack 图结构存在无效对象或关系引用",
            details={"issues": issues},
        )


def validate_course_release_pack(
    pack_type: str,
    value: Any,
    *,
    for_publish: bool = False,
    material_ids: set[str] | None = None,
    material_versions: dict[str, str] | None = None,
    evidence_sources: dict[str, str] | None = None,
) -> None:
    """校验可持久化的 Pack 结构，禁止把任意可执行内容伪装成课程资产。"""
    if pack_type not in _PACK_LIST_FIELDS or not isinstance(value, dict):
        raise ApiError(
            status_code=422,
            code="RELEASE_PACK_INVALID",
            message="课程设计资产包必须是 JSON 对象",
            details={"pack_type": pack_type},
        )
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ApiError(
            status_code=422,
            code="RELEASE_PACK_INVALID",
            message="课程设计资产包不是可持久化的 JSON",
            details={"pack_type": pack_type},
        ) from exc
    if len(encoded) > 256_000:
        raise ApiError(
            status_code=422,
            code="RELEASE_PACK_TOO_LARGE",
            message="课程设计资产包超过 256KB 限制",
            details={"pack_type": pack_type},
        )
    forbidden_keys = {"__proto__", "constructor", "prototype", "script", "javascript"}
    allowed_pack_fields = set(_PACK_LIST_FIELDS[pack_type])
    for key in value:
        if not isinstance(key, str) or key.lower() in forbidden_keys:
            raise ApiError(
                status_code=422,
                code="RELEASE_PACK_INVALID",
                message="课程设计资产包包含不允许的字段",
                details={"pack_type": pack_type, "field": str(key)},
            )
        if key not in allowed_pack_fields:
            raise ApiError(
                status_code=422,
                code="RELEASE_PACK_UNKNOWN_FIELD",
                message="课程设计资产包包含未定义字段；请先更新契约后再使用",
                details={"pack_type": pack_type, "field": key},
            )
    for field in _PACK_LIST_FIELDS[pack_type]:
        items = value.get(field)
        if items is None:
            continue
        if not isinstance(items, list):
            raise ApiError(
                status_code=422,
                code="RELEASE_PACK_INVALID",
                message=f"{field} 必须是数组",
                details={"pack_type": pack_type, "field": field},
            )
        if field == "chapters" and pack_type == "domain_pack":
            invalid = [
                index
                for index, item in enumerate(items)
                if not isinstance(item, str) or not item.strip()
            ]
            if invalid:
                raise ApiError(
                    status_code=422,
                    code="RELEASE_PACK_INVALID",
                    message="chapters 目前只接受非空稳定 ID 字符串",
                    details={"pack_type": pack_type, "field": field, "indices": invalid},
                )
        required = _PACK_ITEM_FIELDS.get((pack_type, field), ())
        allowed_item_fields = set(required) | set(
            _PACK_ITEM_OPTIONAL_FIELDS.get((pack_type, field), frozenset())
        )
        for index, item in enumerate(items):
            if required and not isinstance(item, dict):
                raise ApiError(
                    status_code=422,
                    code="RELEASE_PACK_INVALID",
                    message=f"{field}[{index}] 必须是对象",
                    details={"pack_type": pack_type, "field": field, "index": index},
                )
            if isinstance(item, dict):
                unknown = (
                    sorted(set(item) - allowed_item_fields) if pack_type == "domain_pack" else []
                )
                if unknown:
                    raise ApiError(
                        status_code=422,
                        code="RELEASE_PACK_UNKNOWN_FIELD",
                        message=f"{field}[{index}] 包含未定义字段；请先更新契约后再使用",
                        details={
                            "pack_type": pack_type,
                            "field": field,
                            "index": index,
                            "unknown_fields": unknown,
                        },
                    )
                missing = [
                    name
                    for name in required
                    if not isinstance(item.get(name), str) or not item[name].strip()
                ]
                if missing:
                    raise ApiError(
                        status_code=422,
                        code="RELEASE_PACK_INVALID",
                        message=f"{field}[{index}] 缺少结构化字段",
                        details={
                            "pack_type": pack_type,
                            "field": field,
                            "index": index,
                            "missing": missing,
                        },
                    )
                reference_fields = (
                    (
                        ("knowledge_point_keys", "evidence_binding_keys", "textbook_evidence")
                        if field == "experiments"
                        else ("knowledge_point_keys", "evidence_binding_keys")
                    )
                    if pack_type == "domain_pack"
                    else ()
                )
                for ref_field in reference_fields:
                    refs = item.get(ref_field)
                    if refs is not None and (
                        not isinstance(refs, list)
                        or not all(isinstance(ref, str) and ref.strip() for ref in refs)
                        or len(refs) != len(set(refs))
                    ):
                        raise ApiError(
                            status_code=422,
                            code="RELEASE_PACK_INVALID",
                            message=f"{field}[{index}].{ref_field} 必须是无重复的非空字符串数组",
                            details={
                                "pack_type": pack_type,
                                "field": field,
                                "index": index,
                                "reference_field": ref_field,
                            },
                        )
                if (
                    pack_type == "pedagogy_pack"
                    and field == "flows"
                    and not isinstance(item.get("steps"), list)
                ):
                    raise ApiError(
                        status_code=422,
                        code="RELEASE_PACK_INVALID",
                        message=f"flows[{index}].steps 必须是数组",
                        details={"pack_type": pack_type, "field": field, "index": index},
                    )
    if pack_type == "domain_pack":
        validate_domain_pack_graph(
            value,
            for_publish=for_publish,
            material_ids=material_ids,
            material_versions=material_versions,
            evidence_sources=evidence_sources,
        )


def canonical_request_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def course_out(course: Course) -> dict[str, Any]:
    return CourseOut(
        id=course.id,
        title=course.title,
        term=course.term,
        description=course.description,
        timezone=course.timezone,
        status=course.status,
        version=course.version,
        created_by=course.created_by,
        created_at=course.created_at,
        updated_at=course.updated_at,
    ).model_dump(mode="json")


async def find_idempotent_response(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.endpoint == endpoint,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="该幂等键已用于不同内容的请求",
        )
    return {"status": record.response_status, "body": record.response_body}


async def save_idempotent_response(
    db: AsyncSession,
    *,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
    status: int,
    body: dict[str, Any],
) -> None:
    db.add(
        IdempotencyRecord(
            idempotency_key=key,
            user_id=user_id,
            endpoint=endpoint,
            request_hash=request_hash,
            response_status=status,
            response_body=body,
        )
    )


async def write_audit(
    db: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    course_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            course_id=course_id,
            detail=detail,
        )
    )


async def get_course_or_404(db: AsyncSession, course_id: str) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id).limit(1))
    course = result.scalar_one_or_none()
    if course is None:
        raise ApiError(status_code=404, code="COURSE_NOT_FOUND", message="课程不存在或无权访问")
    return course


async def create_course_with_membership(
    db: AsyncSession,
    *,
    creator: User,
    title: str,
    term: str,
    description: str | None,
    timezone: str,
) -> Course:
    course = Course(
        organization_id=get_settings().default_organization_id,
        title=title,
        term=term,
        description=description,
        timezone=timezone,
        created_by=creator.id,
    )
    db.add(course)
    await db.flush()
    db.add(
        CourseMember(
            course_id=course.id,
            user_id=creator.id,
            role="teacher",
            status="active",
        )
    )
    await write_audit(
        db,
        actor_id=creator.id,
        action="course.created",
        resource_type="course",
        resource_id=course.id,
        course_id=course.id,
        detail={"title": title, "term": term},
    )
    await append_event(
        db,
        event_type="course.created",
        payload={"course_id": course.id, "created_by": creator.id},
        producer="courses.service",
        trace_id=course.id,
    )
    return course


async def get_active_membership(
    db: AsyncSession, *, course_id: str, user_id: str
) -> CourseMember | None:
    result = await db.execute(
        select(CourseMember).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == user_id,
            CourseMember.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def get_member_or_404(db: AsyncSession, *, course_id: str, member_id: str) -> CourseMember:
    result = await db.execute(
        select(CourseMember).where(
            CourseMember.id == member_id, CourseMember.course_id == course_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise ApiError(status_code=404, code="MEMBER_NOT_FOUND", message="成员不存在")
    return member
