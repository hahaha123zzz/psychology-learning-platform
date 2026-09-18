import asyncio
from datetime import UTC, datetime
from typing import Literal

import redis.asyncio as redis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(prefix="/health")
settings = get_settings()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    time: datetime
    checks: dict[str, str] | None = None


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok", service="api", time=datetime.now(UTC))


async def check_database() -> str:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return "ok"


async def check_redis() -> str:
    client = redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        await client.ping()
        return "ok"
    finally:
        await client.aclose()


@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    checks: dict[str, str] = {}
    results = await asyncio.gather(check_database(), check_redis(), return_exceptions=True)
    for name, result in zip(("database", "redis"), results, strict=True):
        checks[name] = "ok" if result == "ok" else "unavailable"
    if any(value != "ok" for value in checks.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degraded", service="api", time=datetime.now(UTC), checks=checks
        )
    return HealthResponse(status="ok", service="api", time=datetime.now(UTC), checks=checks)

