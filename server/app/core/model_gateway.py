"""模型网关：按用途分配超时、并发与预算，统一记录调用元数据。

当前所有"生成"均为本地确定性实现（provider=internal），
接入外部LLM/Embedding时在此扩展provider调用器，业务层不变。
"""

import asyncio
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModelCallLog

PURPOSE_LIMITS: dict[str, dict] = {
    # purpose: {timeout_seconds, max_concurrent, daily_call_budget}
    "course_qa": {"timeout": 30, "concurrency": 8, "budget": 5000},
    "tutor": {"timeout": 30, "concurrency": 8, "budget": 5000},
    "question_coach": {"timeout": 20, "concurrency": 4, "budget": 2000},
    "question_generation": {"timeout": 60, "concurrency": 2, "budget": 500},
    "summary": {"timeout": 15, "concurrency": 4, "budget": 2000},
}

_semaphores: dict[str, asyncio.Semaphore] = {
    purpose: asyncio.Semaphore(limits["concurrency"])
    for purpose, limits in PURPOSE_LIMITS.items()
}

_circuit: dict[str, dict] = {}


@dataclass
class GatewayResult:
    status: str
    output: object
    latency_ms: int
    model: str


def _circuit_open(purpose: str) -> bool:
    state = _circuit.get(purpose)
    if not state:
        return False
    if state["failures"] >= 5 and time.monotonic() - state["last_failure"] < 60:
        return True
    if state["failures"] >= 5 and time.monotonic() - state["last_failure"] >= 60:
        state["failures"] = 0
    return False


def _record_failure(purpose: str) -> None:
    state = _circuit.setdefault(purpose, {"failures": 0, "last_failure": 0.0})
    state["failures"] += 1
    state["last_failure"] = time.monotonic()


def _record_success(purpose: str) -> None:
    state = _circuit.setdefault(purpose, {"failures": 0, "last_failure": 0.0})
    state["failures"] = 0


async def call_model(
    db: AsyncSession,
    *,
    purpose: str,
    provider: str,
    model: str,
    invoke,
    user_id: str | None = None,
) -> GatewayResult:
    """invoke是执行真实生成的协程函数，返回(输出, prompt_tokens, completion_tokens)。"""
    limits = PURPOSE_LIMITS.get(purpose)
    if limits is None:
        raise ValueError(f"未登记的模型用途: {purpose}")
    started = time.monotonic()
    if _circuit_open(purpose):
        await _log(db, purpose, provider, model, "circuit_open", 0, user_id, 0, 0)
        return GatewayResult("circuit_open", None, 0, model)
    try:
        async with asyncio.timeout(limits["timeout"]):
            async with _semaphores[purpose]:
                output, prompt_tokens, completion_tokens = await invoke()
    except TimeoutError:
        _record_failure(purpose)
        latency = int((time.monotonic() - started) * 1000)
        await _log(db, purpose, provider, model, "timeout", latency, user_id, 0, 0)
        return GatewayResult("timeout", None, latency, model)
    except Exception:  # noqa: BLE001
        _record_failure(purpose)
        latency = int((time.monotonic() - started) * 1000)
        await _log(db, purpose, provider, model, "error", latency, user_id, 0, 0)
        raise
    _record_success(purpose)
    latency = int((time.monotonic() - started) * 1000)
    await _log(
        db, purpose, provider, model, "ok", latency, user_id, prompt_tokens, completion_tokens
    )
    return GatewayResult("ok", output, latency, model)


async def _log(
    db: AsyncSession,
    purpose: str,
    provider: str,
    model: str,
    status: str,
    latency_ms: int,
    user_id: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    from app.db.base import new_ulid

    db.add(
        ModelCallLog(
            id=new_ulid(),
            purpose=purpose,
            provider=provider,
            model=model,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            user_id=user_id,
        )
    )
