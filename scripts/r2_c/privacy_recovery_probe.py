"""R2-C 隐私删除真实 Worker/Redis 演练；输出只含状态与计数，不含凭证或正文。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import validate_api_target, validate_e2e_environment  # noqa: E402

from app.db.base import new_ulid  # noqa: E402
from app.db.models import (  # noqa: E402
    ChatSession,
    ChatTurn,
    CourseMember,
    MemoryItem,
    PrivacyDeletionRequest,
    User,
)
from app.db.session import session_factory  # noqa: E402

API_BASE = validate_api_target(
    os.environ.get("R2_C_API_BASE_URL", "http://127.0.0.1:8203")
)
EMAIL = "r2-c-student@example.com"


def deletion_identity() -> tuple[str, str]:
    request_id = os.environ.get("R2_C_DELETION_REQUEST_ID", "")
    credential = os.environ.get("R2_C_DELETION_CREDENTIAL", "")
    if not request_id or len(credential) != 43:
        raise RuntimeError("必须提供 R2-C 删除状态标识和 43 位临时凭证")
    return request_id, credential


async def counts(user_id: str) -> dict[str, int]:
    async with session_factory() as db:
        session_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
        return {
            "chat_sessions": int(
                await db.scalar(
                    select(func.count()).select_from(ChatSession).where(
                        ChatSession.user_id == user_id
                    )
                )
                or 0
            ),
            "chat_turns": int(
                await db.scalar(
                    select(func.count()).select_from(ChatTurn).where(
                        ChatTurn.session_id.in_(session_ids)
                    )
                )
                or 0
            ),
            "memory_items": int(
                await db.scalar(
                    select(func.count()).select_from(MemoryItem).where(
                        MemoryItem.user_id == user_id
                    )
                )
                or 0
            ),
            "course_memberships": int(
                await db.scalar(
                    select(func.count()).select_from(CourseMember).where(
                        CourseMember.user_id == user_id
                    )
                )
                or 0
            ),
        }


async def main() -> None:
    validate_e2e_environment()
    mode = os.environ.get("R2_C_PRIVACY_MODE", "snapshot")
    if mode == "snapshot":
        async with session_factory() as db:
            user = await db.scalar(select(User).where(User.email == EMAIL))
            if user is None:
                raise RuntimeError("R2-C 合成学生不存在")
            output = {"user_id": user.id, "status": user.status, "counts": await counts(user.id)}
    elif mode == "request":
        request_id, credential = deletion_identity()
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": EMAIL,
                    "password": os.environ.get(
                        "R2_C_E2E_PASSWORD", "r2-c-local-only-password"
                    ),
                },
            )
            if login.status_code != 200:
                raise RuntimeError(f"R2-C 合成学生登录失败：HTTP {login.status_code}")
            response = await client.post(
                "/api/v1/me/privacy/delete-request",
                json={"request_id": request_id, "status_credential": credential},
            )
            if response.status_code != 202:
                raise RuntimeError(f"删除请求受理失败：HTTP {response.status_code}")
            receipt = response.json()["data"]
            output = {
                "request_id": receipt["request_id"],
                "status": receipt["status"],
                "attempt_count": receipt["attempt_count"],
                "credential_logged": False,
            }
    elif mode == "status":
        request_id, credential = deletion_identity()
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            response = await client.post(
                "/api/v1/privacy/deletion-status",
                json={"request_id": request_id, "status_credential": credential},
            )
            if response.status_code != 200:
                raise RuntimeError(f"删除状态查询失败：HTTP {response.status_code}")
            receipt = response.json()["data"]
            output = {
                "status": receipt["status"],
                "attempt_count": receipt["attempt_count"],
                "retryable": receipt["retryable"],
                "processed_counts": receipt["processed_counts"],
                "credential_logged": False,
            }
    elif mode == "retry":
        request_id, credential = deletion_identity()
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            response = await client.post(
                "/api/v1/privacy/deletion-status/retry",
                json={"request_id": request_id, "status_credential": credential},
            )
            if response.status_code not in {200, 202}:
                raise RuntimeError(f"删除任务恢复派发失败：HTTP {response.status_code}")
            receipt = response.json()["data"]
            output = {
                "status": receipt["status"],
                "attempt_count": receipt["attempt_count"],
                "retryable": receipt["retryable"],
                "credential_logged": False,
            }
    elif mode == "wait":
        request_id, credential = deletion_identity()
        timeout_seconds = int(os.environ.get("R2_C_PRIVACY_WAIT_SECONDS", "45"))
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            receipt = None
            while asyncio.get_running_loop().time() < deadline:
                response = await client.post(
                    "/api/v1/privacy/deletion-status",
                    json={"request_id": request_id, "status_credential": credential},
                )
                if response.status_code != 200:
                    raise RuntimeError(f"删除状态查询失败：HTTP {response.status_code}")
                receipt = response.json()["data"]
                if receipt["status"] == "completed_with_retention":
                    break
                await asyncio.sleep(0.5)
            assert receipt is not None
            output = {
                "status": receipt["status"],
                "attempt_count": receipt["attempt_count"],
                "retryable": receipt["retryable"],
                "processed_counts": receipt["processed_counts"],
                "credential_logged": False,
            }
    elif mode == "verify":
        request_id = os.environ.get("R2_C_DELETION_REQUEST_ID", "")
        subject_user_id = os.environ.get("R2_C_SUBJECT_USER_ID", "")
        if not request_id or len(subject_user_id) != 26:
            raise RuntimeError("verify 需要 request_id 和合成 subject_user_id")
        async with session_factory() as db:
            deletion = await db.get(PrivacyDeletionRequest, request_id)
            user = await db.get(User, subject_user_id)
            if deletion is None or user is None:
                raise RuntimeError("R2-C 删除请求或合成学生不存在")
            output = {
                "status": deletion.status,
                "attempt_count": deletion.attempt_count,
                "retryable": deletion.retryable,
                "user_disabled": user.status == "disabled",
                "remaining_personal_rows": await counts(subject_user_id),
                "processed_counts": deletion.processed_counts,
                "credential_logged": False,
            }
    elif mode == "db-wait":
        request_id = os.environ.get("R2_C_DELETION_REQUEST_ID", "")
        subject_user_id = os.environ.get("R2_C_SUBJECT_USER_ID", "")
        timeout_seconds = int(os.environ.get("R2_C_PRIVACY_WAIT_SECONDS", "45"))
        if not request_id or len(subject_user_id) != 26:
            raise RuntimeError("db-wait 需要 request_id 和合成 subject_user_id")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        deletion = None
        user = None
        while asyncio.get_running_loop().time() < deadline:
            async with session_factory() as db:
                deletion = await db.get(PrivacyDeletionRequest, request_id)
                user = await db.get(User, subject_user_id)
            if deletion is None or user is None:
                raise RuntimeError("R2-C 删除请求或合成学生不存在")
            if deletion.status == "completed_with_retention":
                break
            await asyncio.sleep(0.5)
        output = {
            "status": deletion.status,
            "attempt_count": deletion.attempt_count,
            "retryable": deletion.retryable,
            "user_disabled": user.status == "disabled",
            "remaining_personal_rows": await counts(subject_user_id),
            "processed_counts": deletion.processed_counts,
            "credential_logged": False,
        }
    elif mode == "receipt":
        request_id = new_ulid()
        credential = secrets.token_urlsafe(32)
        if len(credential) != 43:
            raise RuntimeError("状态凭证长度不符合 256-bit 格式")
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": "r2-c-teacher@example.com", "password": os.environ.get(
                    "R2_C_E2E_PASSWORD", "r2-c-local-only-password"
                )},
            )
            if login.status_code != 200:
                raise RuntimeError(f"R2-C 合成教师登录失败：HTTP {login.status_code}")
            me = await client.get("/api/v1/me")
            if me.status_code != 200:
                raise RuntimeError("R2-C 合成教师身份读取失败")
            user_id = me.json()["data"]["id"]
            accepted = await client.post(
                "/api/v1/me/privacy/delete-request",
                json={"request_id": request_id, "status_credential": credential},
            )
            if accepted.status_code not in {200, 202}:
                raise RuntimeError(f"隐私删除受理失败：HTTP {accepted.status_code}")

            async def poll_status(timeout: int = 30) -> dict:
                deadline = time.monotonic() + timeout
                receipt = accepted.json()["data"]
                while time.monotonic() < deadline:
                    response = await client.post(
                        "/api/v1/privacy/deletion-status",
                        json={"request_id": request_id, "status_credential": credential},
                    )
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"删除状态凭证查询失败：HTTP {response.status_code}"
                        )
                    receipt = response.json()["data"]
                    if receipt["status"] == "completed_with_retention":
                        return receipt
                    await asyncio.sleep(0.5)
                return receipt

            receipt = await poll_status()
            if receipt["status"] != "completed_with_retention" and receipt["retryable"]:
                retry = await client.post(
                    "/api/v1/privacy/deletion-status/retry",
                    json={"request_id": request_id, "status_credential": credential},
                )
                if retry.status_code not in {200, 202}:
                    raise RuntimeError(f"删除请求凭证恢复派发失败：HTTP {retry.status_code}")
                receipt = await poll_status()
            if receipt["status"] != "completed_with_retention":
                raise RuntimeError("真实 Worker 未在期限内完成删除工作单")

            replay = await client.post(
                "/api/v1/privacy/deletion-status/retry",
                json={"request_id": request_id, "status_credential": credential},
            )
            if replay.status_code != 200 or replay.json()["data"]["status"] != receipt["status"]:
                raise RuntimeError("完成后的状态重试不满足幂等约束")

        async with session_factory() as db:
            deletion = await db.get(PrivacyDeletionRequest, request_id)
            user = await db.get(User, user_id)
            if deletion is None or user is None:
                raise RuntimeError("R2-C 删除工作单或合成教师缺失")
            output = {
                "status": deletion.status,
                "attempt_count": deletion.attempt_count,
                "retryable": deletion.retryable,
                "user_disabled": user.status == "disabled",
                "credential_hash_only": deletion.status_credential_hash
                == hashlib.sha256(credential.encode("ascii")).hexdigest(),
                "remaining_personal_rows": await counts(user_id),
                "processed_counts": deletion.processed_counts,
                "completed_retry_idempotent": replay.status_code == 200,
                "credential_logged": False,
            }
    else:
        raise RuntimeError(
            "R2_C_PRIVACY_MODE 必须为 snapshot/request/status/retry/wait/verify/db-wait/receipt"
        )
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
