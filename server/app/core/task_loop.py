"""Celery 任务专用持久事件循环。

每次 ``asyncio.run()`` 执行完毕都会关闭事件循环，而全局 async engine 的连接池
会把连接绑定到创建时的循环；Worker 中第二个任务复用已关闭循环上的连接会触发
"Event loop is closed"。因此 Worker 进程改用单一持久循环执行任务，使连接池
跨任务始终绑定同一循环。
"""

import asyncio

_loop: asyncio.AbstractEventLoop | None = None


def run_task(coro):  # noqa: ANN001, ANN201
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)
