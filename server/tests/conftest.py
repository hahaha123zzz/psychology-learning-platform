import os
import pathlib
import re
import sys
from urllib.parse import urlparse

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

TEST_DB = os.environ.get("PSYCHOLOGY_TEST_DB", "psychology_learning_test")
if not re.fullmatch(r"[a-zA-Z0-9_]+", TEST_DB):
    raise ValueError("PSYCHOLOGY_TEST_DB must contain only letters, digits, and underscores")
os.environ["DATABASE_URL"] = (
    f"postgresql+asyncpg://psychology:change-me@127.0.0.1:5432/{TEST_DB}"
)
TEST_REDIS_URL = os.environ.get(
    "PSYCHOLOGY_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"
)
if urlparse(TEST_REDIS_URL).path.strip("/") in {"0", "1"}:
    raise ValueError("PSYCHOLOGY_TEST_REDIS_URL must not use preview Redis DB0 or Celery DB1")
os.environ["REDIS_URL"] = TEST_REDIS_URL
os.environ["JWT_SECRET"] = "test-secret-key-for-hmac-sha256-32bytes!"
os.environ["APP_ENV"] = "test"
os.environ["MATERIAL_LEGACY_AUTHORING_API_ENABLED"] = "true"
os.environ["TASK_BACKEND"] = "in_process"

import asyncio  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import engine, session_factory  # noqa: E402

TABLES_TO_TRUNCATE = (
    "interventions",
    "learning_qualifications",
    "learning_events",
    "outbox_consumer_receipts",
    "outbox_events",
    "idempotency_records",
    "privacy_deletion_requests",
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


@pytest.fixture(scope="session")
def _prepare_database() -> None:
    _ensure_test_database()
    _run_migrations()
    yield


@pytest.fixture()
def client(_prepare_database):
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

    from app.core.config import get_settings

    # 清理当前测试所配置的 Redis 实例/数据库，不触碰共享预览环境的登录限流状态。
    r = redis_lib.from_url(get_settings().redis_url)
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


def publish_course_release_for_test(client, course_id: str, release_id: str) -> dict:
    """通过独立审核者和受控请求发布测试用课程版本。"""
    from app.db.models import CourseRelease, RoleAssignment

    async def _release_context() -> tuple[str, int]:
        async with session_factory() as session:
            release = await session.get(CourseRelease, release_id)
            assert release is not None
            author = await session.get(User, release.created_by)
            return author.email, release.version

    author_email, version = asyncio.run(_release_context())
    preview_response = client.get(
        f"/api/v1/courses/{course_id}/releases/{release_id}/preview"
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()["data"]
    reviewer_email = f"release-reviewer-{release_id}@example.com"
    reviewer_id = create_user_sync(email=reviewer_email)

    async def _grant_reviewer() -> None:
        async with session_factory() as session:
            session.add(
                RoleAssignment(
                    user_id=reviewer_id,
                    role="course_publisher",
                    scope_type="course",
                    scope_id=course_id,
                    status="active",
                    granted_by=preview["release"]["created_by"],
                )
            )
            await session.commit()

    asyncio.run(_grant_reviewer())
    login = client.post(
        "/api/v1/auth/login",
        json={"email": reviewer_email, "password": "correct-password"},
    )
    assert login.status_code == 200, login.text
    review = client.post(
        f"/api/v1/courses/{course_id}/releases/{release_id}/reviews",
        headers={"Idempotency-Key": f"test-review:{release_id}"},
        json={
            "expected_version": version,
            "manifest_sha256": preview["manifest_sha256"],
            "decision": "approved",
            "reason": "自动化测试的独立审核",
        },
    )
    assert review.status_code == 201, review.text
    published = client.post(
        f"/api/v1/courses/{course_id}/releases/{release_id}/publish",
        headers={"Idempotency-Key": f"test-publish:{release_id}"},
        json={"expected_version": version},
    )
    client.post(
        "/api/v1/auth/login",
        json={"email": author_email, "password": "correct-password"},
    )
    assert published.status_code == 200, published.text
    return published.json()["data"]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """生成带文本层的合法PDF（含xref），每页多行文本。"""
    objects: dict[int, bytes] = {}
    n_pages = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for i, lines in enumerate(pages):
        page_no = 4 + 2 * i
        content_no = page_no + 1
        objects[page_no] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_no} 0 R >>"
        ).encode()
        text_ops = ["BT /F1 14 Tf 72 720 Td 16 TL"]
        for line in lines:
            text_ops.append(f"({_pdf_escape(line)}) Tj T*")
        text_ops.append("ET")
        stream = "\n".join(text_ops).encode("latin-1", errors="replace")
        objects[content_no] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream"
        )
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_pos = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in sorted(objects):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)
