"""Celery 持久任务循环：连续任务共享同一循环且关闭后可恢复。"""

import asyncio

from app.core import task_loop


def test_run_task_reuses_loop_across_calls() -> None:
    task_loop._loop = None

    async def current_loop() -> int:
        return id(asyncio.get_running_loop())

    first = task_loop.run_task(current_loop())
    second = task_loop.run_task(current_loop())
    assert first == second


def test_run_task_recovers_after_loop_close() -> None:
    task_loop._loop = None

    async def ok() -> str:
        return "done"

    assert task_loop.run_task(ok()) == "done"
    assert task_loop._loop is not None
    task_loop._loop.close()
    assert task_loop.run_task(ok()) == "done"
