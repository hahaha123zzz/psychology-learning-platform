"""R2-C 独立 Celery Worker 入口，可在真实任务临界点暂停后由测试终止。"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import validate_e2e_environment, validate_marker_path  # noqa: E402

validate_e2e_environment()

fault_mode = os.environ.get("R2_C_WORKER_FAULT_MODE", "none")
if fault_mode not in {"none", "hold_parse", "hold_privacy_after_delete"}:
    raise RuntimeError("R2_C_WORKER_FAULT_MODE 不在允许值内")
marker_value = os.environ.get("R2_C_FAULT_MARKER", "")
marker_path = validate_marker_path(marker_value) if marker_value else None
if fault_mode != "none" and marker_path is None:
    raise RuntimeError("故障模式必须指定唯一临时 R2_C_FAULT_MARKER")


def _mark_fault_reached() -> None:
    assert marker_path is not None
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("fault-window-reached", encoding="utf-8")


from app.core.celery_app import celery_app  # noqa: E402

# 专属 Redis DB1 仅用于本次故障注入；缩短 visibility timeout，便于在真实
# Worker 被终止后观察 late-ack 消息是否重新入队，不影响共享 Redis。
celery_app.conf.broker_transport_options = {"visibility_timeout": 8}

if fault_mode == "hold_parse":
    from app.modules.materials.parsers import base as parser_base

    original_get_parser = parser_base.get_parser

    class HeldParser:
        def __init__(self, delegate):
            self._delegate = delegate

        def __getattr__(self, name):
            return getattr(self._delegate, name)

        def parse(self, *args, **kwargs):
            _mark_fault_reached()
            threading.Event().wait()
            return self._delegate.parse(*args, **kwargs)

    def held_get_parser(content_type: str):
        return HeldParser(original_get_parser(content_type))

    parser_base.get_parser = held_get_parser

if fault_mode == "hold_privacy_after_delete":
    from app.modules.memory import tasks as privacy_tasks

    original_delete = privacy_tasks.delete_personal_learning_data

    async def held_delete(db, *, user_id: str):
        result = await original_delete(db, user_id=user_id)
        _mark_fault_reached()
        await asyncio.Future()
        return result

    privacy_tasks.delete_personal_learning_data = held_delete


if __name__ == "__main__":
    print(f"R2-C Celery worker starting; fault_mode={fault_mode}; pool=solo")
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=INFO",
            "--pool=solo",
            "--concurrency=1",
            "--hostname=r2-c-worker@%h",
        ]
    )
