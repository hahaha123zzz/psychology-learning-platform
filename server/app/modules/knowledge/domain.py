"""Domain Pack 生命周期与 Claim 证据判定合同。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from app.core.errors import ApiError

CLAIM_STATES = frozenset({"supported", "partially-supported", "contradicted", "unknown"})
MAX_SUPPLEMENTAL_RETRIEVALS = 1


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def misconception_digest(item: dict[str, Any]) -> str:
    return canonical_json_hash(
        {key: value for key, value in item.items() if key not in {"lifecycle_state"}}
    )


def validate_domain_pack_shape(pack: Any) -> None:
    if not isinstance(pack, dict):
        raise ApiError(422, "DOMAIN_PACK_INVALID", "Domain Pack 必须是 JSON 对象")
    misconceptions = pack.get("misconceptions", [])
    bindings = pack.get("evidence_bindings", [])
    points = pack.get("knowledge_points", [])
    if not all(isinstance(value, list) for value in (misconceptions, bindings, points)):
        raise ApiError(
            422,
            "DOMAIN_PACK_INVALID",
            "misconceptions、evidence_bindings 和 knowledge_points 必须是数组",
        )
    point_keys = {
        item.get("key")
        for item in points
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    binding_keys = {
        item.get("key")
        for item in bindings
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    seen: set[str] = set()
    allowed_misconception_fields = {
        "key",
        "title",
        "definition",
        "conditions",
        "knowledge_point_keys",
        "evidence_binding_keys",
    }
    for index, item in enumerate(misconceptions):
        path = f"misconceptions[{index}]"
        if not isinstance(item, dict):
            raise ApiError(422, "MISCONCEPTION_DEFINITION_INVALID", f"{path} 必须是对象")
        if item.get("canonical") is True:
            raise ApiError(
                422,
                "MISCONCEPTION_CANONICAL_FORBIDDEN",
                "canonical 由人工审核并发布后派生，不能由候选内容指定",
                details={"key": item.get("key")},
            )
        unknown = sorted(set(item) - allowed_misconception_fields)
        if unknown:
            raise ApiError(
                422,
                "MISCONCEPTION_FIELD_UNKNOWN",
                f"{path} 包含未定义字段",
                details={"path": path, "unknown_fields": unknown},
            )
        key = item.get("key")
        required = ("key", "title", "definition", "conditions")
        if any(
            not isinstance(item.get(field), str) or not item[field].strip() for field in required
        ):
            raise ApiError(
                422,
                "MISCONCEPTION_DEFINITION_INVALID",
                f"{path} 必须包含非空 key、title、definition 和 conditions",
                details={"path": path, "required": list(required)},
            )
        if any(len(item[field]) > 4000 for field in ("title", "definition", "conditions")):
            raise ApiError(
                422,
                "MISCONCEPTION_DEFINITION_INVALID",
                f"{path} 文本字段最多 4000 字符",
                details={"path": path},
            )
        if key in seen:
            raise ApiError(
                422, "MISCONCEPTION_KEY_DUPLICATE", "误区 key 必须唯一", details={"key": key}
            )
        seen.add(key)
        refs = item.get("knowledge_point_keys", [])
        evidence = item.get("evidence_binding_keys", [])
        if (
            not isinstance(refs, list)
            or not refs
            or not all(isinstance(ref, str) and ref for ref in refs)
            or len(refs) != len(set(refs))
            or any(ref not in point_keys for ref in refs)
        ):
            raise ApiError(
                422,
                "MISCONCEPTION_KNOWLEDGE_POINT_INVALID",
                "误区必须引用已声明的知识点",
                details={"key": key},
            )
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(ref, str) and ref for ref in evidence)
            or len(evidence) != len(set(evidence))
            or any(ref not in binding_keys for ref in evidence)
        ):
            raise ApiError(
                422,
                "MISCONCEPTION_EVIDENCE_REQUIRED",
                "误区必须引用已声明的 EvidenceBinding",
                details={"key": key},
            )


def classify_claim(
    *,
    supported_subclaims: list[str] | None = None,
    unsupported_subclaims: list[str] | None = None,
    contradicted_subclaims: list[str] | None = None,
    counterevidence_scope_matches: bool = False,
) -> dict[str, Any]:
    """确定 Claim 四态；矛盾态要求调用者确认同对象/范围/极性的直接反证。"""
    supported = [item for item in (supported_subclaims or []) if item]
    unsupported = [item for item in (unsupported_subclaims or []) if item]
    contradicted = [item for item in (contradicted_subclaims or []) if item]
    if contradicted and counterevidence_scope_matches:
        status = "contradicted"
    elif supported and unsupported:
        status = "partially-supported"
    elif supported and not unsupported:
        status = "supported"
    else:
        status = "unknown"
    return {
        "status": status,
        "supported_subclaims": supported,
        "unsupported_subclaims": unsupported,
        "contradicted_subclaims": contradicted if status == "contradicted" else [],
        "evidence_ids": [],
        "supplemental_retrieval_attempts": 0,
    }


async def verify_claim_with_bounded_retrieval(
    *,
    claim: str,
    initial_evidence: list[Any],
    evaluate: Callable[[str, list[Any]], dict[str, Any]],
    retrieve_once: Callable[[dict[str, Any]], Awaitable[list[Any]]],
    retrieval_scope: dict[str, Any],
    required_scope: dict[str, Any],
) -> dict[str, Any]:
    """最多补检索一次；retrieval_scope 必须与 required_scope 完整相等。

    两个 scope 应含用户/组织/课程、DomainRelease、PublicationSnapshot、教材版本、索引任务和
    Embedding 版本。补检索收到隔离副本，返回值保留未被回调改写的原始 scope。
    """
    result = evaluate(claim, initial_evidence)
    if result.get("status") not in CLAIM_STATES:
        raise ValueError("evaluate must return one of the four Claim states")
    if result["status"] == "contradicted" and not (
        result.get("counterevidence_scope_matches") is True and result.get("contradicted_subclaims")
    ):
        result = {**result, "status": "unknown", "contradicted_subclaims": []}
    if result["status"] == "partially-supported" and not (
        result.get("supported_subclaims") and result.get("unsupported_subclaims")
    ):
        result = {**result, "status": "unknown"}
    if result["status"] == "supported" and not result.get("supported_subclaims"):
        result = {**result, "status": "unknown"}
    attempts = 0
    supplemental: list[Any] = []
    scope_snapshot = deepcopy(retrieval_scope)
    if result["status"] == "unknown":
        if scope_snapshot != required_scope:
            result = {**result, "status": "unknown", "refusal_reason": "retrieval_scope_changed"}
        else:
            supplemental = await retrieve_once(deepcopy(scope_snapshot))
            attempts = 1
            combined = [*initial_evidence, *supplemental]
            result = evaluate(claim, combined)
            if result.get("status") not in CLAIM_STATES:
                raise ValueError("evaluate must return one of the four Claim states")
            if result["status"] == "contradicted" and not (
                result.get("counterevidence_scope_matches") is True
                and result.get("contradicted_subclaims")
            ):
                result = {**result, "status": "unknown", "contradicted_subclaims": []}
            if result["status"] == "partially-supported" and not (
                result.get("supported_subclaims") and result.get("unsupported_subclaims")
            ):
                result = {**result, "status": "unknown"}
            if result["status"] == "supported" and not result.get("supported_subclaims"):
                result = {**result, "status": "unknown"}
            if result["status"] == "unknown":
                result = {**result, "refusal_reason": "insufficient_evidence"}
    return {
        **result,
        "status": result.get("status", "unknown"),
        "initial_evidence": initial_evidence,
        "supplemental_evidence": supplemental,
        "supplemental_retrieval_attempts": attempts,
        "scope": scope_snapshot,
    }
