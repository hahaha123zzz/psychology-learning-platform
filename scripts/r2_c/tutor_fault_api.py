"""带单次故障栅栏的真实 Uvicorn API 入口，仅供隔离 R2-C 验收。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import validate_e2e_environment, validate_marker_path  # noqa: E402

validate_e2e_environment()

fault_mode = os.environ.get("R2_C_TUTOR_FAULT_MODE", "none")
if fault_mode not in {"none", "after_first_delta", "after_commit_before_done"}:
    raise RuntimeError("R2_C_TUTOR_FAULT_MODE 不在允许值内")

marker_value = os.environ.get("R2_C_FAULT_MARKER", "")
marker_path = validate_marker_path(marker_value) if marker_value else None
if fault_mode != "none" and marker_path is None:
    raise RuntimeError("故障模式必须指定唯一临时 R2_C_FAULT_MARKER")

from app.modules.tutor import service as tutor_service  # noqa: E402

original_stream = tutor_service.run_turn_stream
fault_triggered = False


def _mark_fault_reached() -> None:
    assert marker_path is not None
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("fault-window-reached", encoding="utf-8")


async def gated_turn_stream(*args, **kwargs):
    global fault_triggered
    source = original_stream(*args, **kwargs)
    try:
        async for event in source:
            is_target = (
                not fault_triggered
                and (
                    (fault_mode == "after_first_delta" and event["event"] == "delta")
                    or (
                        fault_mode == "after_commit_before_done"
                        and event["event"] == "done"
                    )
                )
            )
            if is_target:
                fault_triggered = True
                _mark_fault_reached()
                if fault_mode == "after_first_delta":
                    yield event
                await asyncio.Future()
            else:
                yield event
    finally:
        await source.aclose()


if fault_mode != "none":
    tutor_service.run_turn_stream = gated_turn_stream

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

if __name__ == "__main__":
    print(f"R2-C fault API starting on 127.0.0.1:8203; mode={fault_mode}")
    uvicorn.run(app, host="127.0.0.1", port=8203, access_log=False, log_level="warning")
