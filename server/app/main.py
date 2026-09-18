from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.middleware import RequestContextMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 后续在这里初始化共享连接池、对象存储桶和后台任务资源。
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
install_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}

