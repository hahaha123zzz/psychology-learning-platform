import json
import re
from typing import Any

from app.core.errors import ApiError

ALLOWED_ACTIONS = {
    "SHOW",
    "HIGHLIGHT",
    "REVEAL",
    "FOCUS",
    "COMPARE",
    "PLAY",
    "PAUSE",
    "RESET",
}
FORBIDDEN_KEYS = {"html", "script", "onclick", "onload", "javascript", "component"}
CONTENT_FIELDS = {"title", "text", "items"}
UNSAFE_TEXT = re.compile(
    r"(?:javascript\s*:|vbscript\s*:|data\s*:\s*text/html|"
    r"<\s*/?[a-z][a-z0-9:-]*(?:\s+[^<>]*)?\s*/?>|<!--|<!doctype\b)",
    re.I,
)


def _walk_forbidden(value: Any, *, path: str = "content") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return f"{path}.{key}"
            found = _walk_forbidden(child, path=f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _walk_forbidden(child, path=f"{path}[{index}]")
            if found:
                return found
    return None


def validate_asset_payload(
    *,
    content: dict[str, Any],
    template: str,
    fallback_text: str,
    evidence_refs: list[str],
    allowed_actions: list[str],
) -> None:
    if len(json.dumps(content, ensure_ascii=False)) > 100_000:
        raise ApiError(status_code=422, code="TEACHING_ASSET_TOO_LARGE", message="教学资产内容过大")
    forbidden = _walk_forbidden(content)
    if forbidden:
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_UNSAFE_CONTENT",
            message="教学资产包含不允许的可执行内容",
            details={"path": forbidden},
        )
    extra_fields = sorted(set(content) - CONTENT_FIELDS)
    if extra_fields:
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_CONTENT_NOT_ALLOWED",
            message="教学资产包含当前白名单模板不支持的字段",
            details={"fields": extra_fields},
        )
    title = content.get("title")
    text = content.get("text")
    items = content.get("items", [])
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_CONTENT_INVALID",
            message="教学资产标题必须是 1 至 160 字的文本",
        )
    if text is not None and (
        not isinstance(text, str) or len(text) > 5000 or (not text.strip() and not items)
    ):
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_CONTENT_INVALID",
            message="教学资产正文必须是纯文本且不超过 5000 字",
        )
    if not isinstance(items, list) or len(items) > 50 or any(
        not isinstance(item, str) or not item.strip() or len(item) > 600 for item in items
    ):
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_CONTENT_INVALID",
            message="教学资产条目必须是最多 50 项的非空短文本列表",
        )
    if (text is None or not text.strip()) and not items:
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_CONTENT_INVALID",
            message="教学资产必须包含正文或条目",
        )
    if template not in {"explanation", "comparison", "variable_map", "table", "focus"}:
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_TEMPLATE_NOT_ALLOWED",
            message="教学资产模板不在白名单中",
        )
    text_values = [title, text or "", fallback_text, *items]
    if any(UNSAFE_TEXT.search(value) for value in text_values):
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_UNSAFE_CONTENT",
            message="教学资产文本包含不允许的脚本或可执行 URL",
        )
    if not fallback_text.strip():
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_FALLBACK_REQUIRED",
            message="教学资产必须提供文本降级内容",
        )
    if len(evidence_refs) > 20 or any(not ref.strip() or len(ref) > 200 for ref in evidence_refs):
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_EVIDENCE_INVALID",
            message="教学资产依据引用数量或长度超限",
        )
    if len(allowed_actions) > len(ALLOWED_ACTIONS) or not set(allowed_actions).issubset(
        ALLOWED_ACTIONS
    ):
        raise ApiError(
            status_code=422,
            code="TEACHING_ASSET_ACTION_NOT_ALLOWED",
            message="教学资产包含未注册动作",
        )


def validate_evidence_refs_for_release(
    *, evidence_refs: list[str], release_manifest: dict[str, Any]
) -> None:
    """新发布资产的 refs 必须精确引用目标 Release 的 DomainPack binding key。"""
    if not evidence_refs:
        raise ApiError(
            status_code=409,
            code="TEACHING_ASSET_EVIDENCE_REQUIRED",
            message="发布教学资产前必须绑定目标课程版本的教材 Evidence",
        )

    domain_pack = release_manifest.get("domain_pack")
    bindings = domain_pack.get("evidence_bindings", []) if isinstance(domain_pack, dict) else []
    binding_keys = {
        binding["key"]
        for binding in bindings
        if isinstance(binding, dict)
        and isinstance(binding.get("key"), str)
        and binding["key"].strip()
        and binding["key"] == binding["key"].strip()
    } if isinstance(bindings, list) else set()
    unknown_refs = sorted(set(evidence_refs) - binding_keys)
    if unknown_refs:
        raise ApiError(
            status_code=409,
            code="TEACHING_ASSET_EVIDENCE_UNBOUND",
            message="教学资产依据必须引用目标课程版本中已固定的 EvidenceBinding key",
            details={"unbound_refs": unknown_refs},
        )
