from datetime import UTC, datetime
from typing import Any

from fastapi import Request, Response


def _meta(request: Request, **extra: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "request_id": getattr(request.state, "request_id", None),
        "server_time": datetime.now(UTC).isoformat(),
    }
    meta.update(extra)
    return meta


def ok(
    request: Request,
    data: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    next_cursor: str | None = None,
    has_more: bool | None = None,
) -> Response:
    from fastapi.responses import JSONResponse

    extra: dict[str, Any] = {}
    if next_cursor is not None:
        extra["next_cursor"] = next_cursor
    if has_more is not None:
        extra["has_more"] = has_more
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "meta": _meta(request, **extra)},
        headers=headers,
    )
