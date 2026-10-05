from app.core.config import get_settings
from app.core.errors import ApiError


def ensure_legacy_material_authoring_api_enabled() -> None:
    """关闭旧教师教材写入入口，同时保留隔离工程环境的显式开关。"""
    if get_settings().material_legacy_authoring_api_enabled:
        return
    raise ApiError(
        status_code=410,
        code="LEGACY_MATERIAL_AUTHORING_DISABLED",
        message="当前不开放教师直接上传、解析、索引或发布教材；如需新增或调整教材，请联系课程内容管理员。",
        details={"replacement": "course_content_admin"},
    )
