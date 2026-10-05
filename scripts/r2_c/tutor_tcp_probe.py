"""真实 HTTP/TCP Tutor SSE 中断验收；输出仅含状态与计数，不含答案正文。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import (  # noqa: E402
    validate_api_target,
    validate_e2e_environment,
    validate_marker_path,
)

from app.db.models import ChatTurn  # noqa: E402
from app.db.session import session_factory  # noqa: E402

validate_e2e_environment()
API_BASE = validate_api_target(os.environ.get("R2_C_API_BASE_URL", "http://127.0.0.1:8203"))
FAULT_MODE = os.environ.get("R2_C_TUTOR_FAULT_MODE", "")
MARKER_VALUE = os.environ.get("R2_C_FAULT_MARKER", "")
MARKER_PATH = validate_marker_path(MARKER_VALUE) if MARKER_VALUE else None
PASSWORD = os.environ.get("R2_C_E2E_PASSWORD", "r2-c-local-only-password")
TEACHER_EMAIL = "r2-c-teacher@example.com"
STUDENT_EMAIL = "r2-c-student@example.com"
QUESTION = "请解释实验心理学中自变量与因变量的区别。"


async def sse_events(response: httpx.Response):
    event_name = "message"
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line.startswith("event:"):
            event_name = line.partition(":")[2].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line.partition(":")[2].lstrip())
        elif not line and data_lines:
            yield event_name, json.loads("\n".join(data_lines))
            event_name = "message"
            data_lines.clear()


async def session_turns(session_id: str) -> list[dict[str, str]]:
    async with session_factory() as db:
        rows = (
            await db.scalars(
                select(ChatTurn)
                .where(ChatTurn.session_id == session_id)
                .order_by(ChatTurn.created_at, ChatTurn.id)
            )
        ).all()
        return [
            {"role": row.role, "client_turn_id": row.client_turn_id, "content": row.content}
            for row in rows
        ]


async def wait_for_marker(timeout: float = 20.0) -> None:
    assert MARKER_PATH is not None
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if MARKER_PATH.is_file():
            return
        await asyncio.sleep(0.025)
    raise TimeoutError("Tutor fault API 未进入预期故障窗口")


async def login(client: httpx.AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    if response.status_code != 200:
        raise RuntimeError(f"R2-C E2E 登录失败：HTTP {response.status_code}")


async def create_chat_session(client: httpx.AsyncClient, course_id: str) -> str:
    response = await client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    )
    if response.status_code != 201:
        raise RuntimeError(f"R2-C E2E 会话创建失败：HTTP {response.status_code}")
    return response.json()["data"]["id"]


async def setup_course(student: httpx.AsyncClient) -> str:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as teacher:
        await login(teacher, TEACHER_EMAIL)
        course_response = await teacher.post(
            "/api/v1/courses",
            json={"title": f"R2-C TCP 测试课 {uuid.uuid4().hex[:8]}", "term": "2026秋"},
        )
        if course_response.status_code != 201:
            raise RuntimeError(f"R2-C E2E 课程创建失败：HTTP {course_response.status_code}")
        course_id = course_response.json()["data"]["id"]
        me = await student.get("/api/v1/me")
        if me.status_code != 200:
            raise RuntimeError("R2-C E2E 学生身份读取失败")
        membership = await teacher.post(
            f"/api/v1/courses/{course_id}/members",
            json={"user_id": me.json()["data"]["id"], "role": "student"},
        )
        if membership.status_code not in {200, 201}:
            raise RuntimeError(f"R2-C E2E 学生入课失败：HTTP {membership.status_code}")
        return course_id


async def read_complete_stream(
    client: httpx.AsyncClient, session_id: str, turn_id: str
) -> list[tuple[str, dict]]:
    async with client.stream(
        "POST",
        f"/api/v1/chat/sessions/{session_id}/turns",
        json={"content": QUESTION, "client_turn_id": turn_id},
    ) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Tutor 重试失败：HTTP {response.status_code}")
        return [event async for event in sse_events(response)]


async def run_probe() -> dict[str, object]:
    if FAULT_MODE not in {"after_first_delta", "after_commit_before_done"}:
        raise RuntimeError("R2_C_TUTOR_FAULT_MODE 必须显式指定真实 TCP 场景")
    if not MARKER_VALUE:
        raise RuntimeError("必须指定本次唯一的 R2_C_FAULT_MARKER")

    async with httpx.AsyncClient(base_url=API_BASE, timeout=20.0) as student:
        await login(student, STUDENT_EMAIL)
        course_id = await setup_course(student)
        session_id = await create_chat_session(student, course_id)
        turn_id = f"r2-c-tcp-{uuid.uuid4().hex}"
        request_events: list[tuple[str, dict]] = []
        done_seen = False

        async with student.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/turns",
            json={"content": QUESTION, "client_turn_id": turn_id},
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Tutor SSE 首次响应失败：HTTP {response.status_code}")
            if FAULT_MODE == "after_first_delta":
                async for event in sse_events(response):
                    request_events.append(event)
                    if event[0] == "delta":
                        break
            else:
                reader = asyncio.create_task(
                    _collect_until_stream_end(response, request_events)
                )
                await wait_for_marker()
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reader
                done_seen = any(name == "done" for name, _ in request_events)

        if FAULT_MODE == "after_first_delta":
            await wait_for_marker()
            if not any(name == "delta" for name, _ in request_events):
                raise AssertionError("TCP 断开前没有收到 delta")
        elif done_seen:
            raise AssertionError("故障窗口中 done 不应到达客户端")

        before_retry = await session_turns(session_id)
        if FAULT_MODE == "after_first_delta" and before_retry:
            raise AssertionError("delta 中断后出现了未确认的半回合持久化")
        if FAULT_MODE == "after_commit_before_done" and [
            row["role"] for row in before_retry
        ] != ["student", "tutor"]:
            raise AssertionError("done 丢失窗口未观察到已提交的完整回合")

        replay = await read_complete_stream(student, session_id, turn_id)
        done = next((data for name, data in replay if name == "done"), None)
        if not done or done.get("saved") is not True:
            raise AssertionError("同 key 重试没有确认服务端已保存回合")
        replay_answer = "".join(
            data["text"] for name, data in replay if name == "delta"
        )
        after_retry = await session_turns(session_id)
        if len(after_retry) != 2 or after_retry[1]["content"] != replay_answer:
            raise AssertionError("同 key 回放后持久记录重复或回答不一致")
        if FAULT_MODE == "after_commit_before_done" and done.get("replayed") is not True:
            raise AssertionError("已提交但 done 丢失的回合没有标记为 replayed")

        return {
            "mode": FAULT_MODE,
            "tcp_disconnect_observed": True,
            "delta_received_before_disconnect": any(
                name == "delta" for name, _ in request_events
            ),
            "done_lost": FAULT_MODE == "after_commit_before_done" and not done_seen,
            "turn_rows_before_retry": len(before_retry),
            "turn_rows_after_retry": len(after_retry),
            "retry_saved": done.get("saved") is True,
            "retry_replayed": done.get("replayed") is True,
        }


async def _collect_until_stream_end(
    response: httpx.Response, events: list[tuple[str, dict]]
) -> None:
    async for event in sse_events(response):
        events.append(event)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_probe()), ensure_ascii=False))
