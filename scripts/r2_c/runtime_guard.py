"""R2-C 独立进程的 fail-closed 环境校验。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_DATABASE = "psychology_learning_v1_r2_c_e2e"
EXPECTED_REDIS_HOST = "127.0.0.1"
EXPECTED_REDIS_PORT = 6381


def _require_url(name: str, *, database: str, scheme: str) -> None:
    raw = os.environ.get(name, "")
    parsed = urlparse(raw)
    actual_database = parsed.path.strip("/")
    if (
        parsed.scheme not in scheme.split("|")
        or parsed.hostname not in {EXPECTED_REDIS_HOST, "localhost"}
        or parsed.port != EXPECTED_REDIS_PORT
        or actual_database != database
    ):
        raise RuntimeError(
            f"{name} 必须指向 R2-C localhost:{EXPECTED_REDIS_PORT}/{database}"
        )


def validate_e2e_environment(*, require_celery: bool = True) -> None:
    database_url = urlparse(os.environ.get("DATABASE_URL", ""))
    if (
        database_url.scheme not in {"postgresql+asyncpg", "postgresql"}
        or database_url.hostname not in {"127.0.0.1", "localhost"}
        or database_url.port != 5432
        or database_url.path.strip("/") != EXPECTED_DATABASE
    ):
        raise RuntimeError(
            "DATABASE_URL 必须指向 localhost:5432/psychology_learning_v1_r2_c_e2e"
        )
    _require_url("REDIS_URL", database="14", scheme="redis|rediss")
    _require_url("CELERY_BROKER_URL", database="1", scheme="redis|rediss")
    _require_url("CELERY_RESULT_BACKEND", database="2", scheme="redis|rediss")
    if os.environ.get("MINIO_BUCKET") != "v1-r2-c":
        raise RuntimeError("MINIO_BUCKET 必须固定为专属桶 v1-r2-c")
    if require_celery and os.environ.get("TASK_BACKEND") != "celery":
        raise RuntimeError("真实进程验收要求 TASK_BACKEND=celery")


def validate_api_target(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port != 8203
    ):
        raise RuntimeError("R2-C API_BASE_URL 只能指向 http://127.0.0.1:8203")
    return value.rstrip("/")


def validate_marker_path(value: str) -> Path:
    marker = Path(value).resolve()
    temp_root = (Path(os.environ.get("TEMP", tempfile.gettempdir())) / "psychology-r2-c").resolve()
    if marker.parent != temp_root or not marker.name.startswith("r2-c-"):
        raise RuntimeError("故障标记文件必须位于专属临时目录 psychology-r2-c")
    return marker
