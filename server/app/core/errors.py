from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_body(
    request: Request,
    *,
    code: str,
    message: str,
    details: Any = None,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "retryable": retryable,
        },
        "request_id": getattr(request.state, "request_id", None),
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                request,
                code="VALIDATION_ERROR",
                message="请求参数不符合要求",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, _: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_body(
                request,
                code="INTERNAL_ERROR",
                message="服务器暂时无法处理该请求",
                retryable=True,
            ),
        )

