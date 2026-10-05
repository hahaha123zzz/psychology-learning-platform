"""真实 R2-C Redis TCP 中断期间验证删除请求安全拒绝及恢复。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import (  # noqa: E402
    validate_api_target,
    validate_e2e_environment,
    validate_marker_path,
)

from app.db.models import PrivacyDeletionRequest, User  # noqa: E402
from app.db.session import session_factory  # noqa: E402

API_BASE = validate_api_target(
    os.environ.get("R2_C_API_BASE_URL", "http://127.0.0.1:8203")
)
PASSWORD = os.environ.get("R2_C_E2E_PASSWORD", "r2-c-local-only-password")
EMAIL = "r2-c-teacher@example.com"
REQUEST_ID = os.environ.get("R2_C_DELETION_REQUEST_ID", "")
STATUS_CREDENTIAL = os.environ.get("R2_C_DELETION_CREDENTIAL", "")
MARKER = validate_marker_path(os.environ.get("R2_C_FAULT_MARKER", ""))
READY = MARKER.with_name(f"{MARKER.stem}-ready")
GO = MARKER.with_name(f"{MARKER.stem}-go")
ATTEMPTED = MARKER.with_name(f"{MARKER.stem}-attempted")
RESTORED = MARKER.with_name(f"{MARKER.stem}-restored")


def mark(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ready", encoding="utf-8")


def wait_for(path: Path, timeout_seconds: int = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.05)
    raise TimeoutError("等待 Redis 故障协调标记超时")


async def verify_database(user_id: str) -> tuple[bool, bool]:
    async with session_factory() as db:
        user = await db.get(User, user_id)
        deletion = await db.get(PrivacyDeletionRequest, REQUEST_ID)
        return user is not None and user.status == "active", deletion is None


def main() -> None:
    validate_e2e_environment()
    if len(REQUEST_ID) != 26 or len(STATUS_CREDENTIAL) != 43:
        raise RuntimeError("需要隔离删除工作单标识和临时凭证")
    for marker in (READY, GO, ATTEMPTED, RESTORED):
        if marker.exists():
            raise RuntimeError("本次 Redis 故障标记已存在；请为新演练使用唯一名称")

    with httpx.Client(base_url=API_BASE, timeout=10.0) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        if login.status_code != 200:
            raise RuntimeError(f"Redis 中断前登录失败：HTTP {login.status_code}")
        me = client.get("/api/v1/me")
        if me.status_code != 200:
            raise RuntimeError("Redis 中断前未能读取合成教师身份")
        user_id = me.json()["data"]["id"]
        mark(READY)
        wait_for(GO)

        response = client.post(
            "/api/v1/me/privacy/delete-request",
            json={"request_id": REQUEST_ID, "status_credential": STATUS_CREDENTIAL},
        )
        body = response.json()
        error_code = body.get("error", {}).get("code")
        if response.status_code != 503 or error_code != "PRIVACY_DELETE_RETRYABLE":
            raise RuntimeError(
                f"Redis 不可达时删除受理结果不符合预期：HTTP {response.status_code}"
            )
        mark(ATTEMPTED)
        wait_for(RESTORED)

        recovered_login = client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        user_active, deletion_absent = asyncio.run(verify_database(user_id))
        result = {
            "login_before_outage": True,
            "privacy_delete_status_during_redis_outage": response.status_code,
            "error_code": error_code,
            "login_after_redis_restore": recovered_login.status_code == 200,
            "user_active_after_outage": user_active,
            "deletion_request_absent": deletion_absent,
            "credential_logged": False,
        }
        if not result["login_after_redis_restore"] or not user_active or not deletion_absent:
            raise RuntimeError("Redis 恢复后的状态或无副作用断言失败")
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
