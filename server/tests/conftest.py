import os
import pathlib
import sys

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://psychology:change-me@127.0.0.1:5432/psychology_learning_test"
)
os.environ["JWT_SECRET"] = "test-secret-key-for-hmac-sha256-32bytes!"
os.environ["APP_ENV"] = "test"

import asyncio  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import engine, session_factory  # noqa: E402

TEST_DB = "psychology_learning_test"

TABLES_TO_TRUNCATE = (
    "idempotency_records",
    "audit_logs",
    "course_members",
    "courses",
    "auth_sessions",
    "users",
)


def _ensure_test_database() -> None:
    asyncio.run(_ensure_test_database_async())


async def _ensure_test_database_async() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    admin_url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB}
        )
        if exists.scalar() is None:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    await admin_engine.dispose()


def _run_migrations() -> None:
    alembic_cfg = Config(str(SERVER_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> None:
    _ensure_test_database()
    _run_migrations()
    yield


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
    _cleanup_data()


def _cleanup_data() -> None:
    async def _clean() -> None:
        async with engine.begin() as conn:
            for table in TABLES_TO_TRUNCATE:
                await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

    asyncio.run(_clean())

    import redis as redis_lib

    r = redis_lib.from_url("redis://127.0.0.1:6379/0")
    for key in r.scan_iter("login_fail:*"):
        r.delete(key)
    r.close()


def create_user_sync(
    *,
    email: str,
    password: str = "correct-password",
    display_name: str = "测试用户",
    is_teacher: bool = False,
    is_platform_admin: bool = False,
    status: str = "active",
) -> str:
    async def _create() -> str:
        async with session_factory() as session:
            from app.core.config import get_settings

            user = User(
                organization_id=get_settings().default_organization_id,
                email=email.lower(),
                password_hash=hash_password(password),
                display_name=display_name,
                status=status,
                is_teacher=is_teacher,
                is_platform_admin=is_platform_admin,
            )
            session.add(user)
            await session.commit()
            return user.id

    return asyncio.run(_create())
