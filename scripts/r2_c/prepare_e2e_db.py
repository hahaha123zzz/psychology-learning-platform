"""只创建/迁移专属 R2-C E2E 数据库；绝不删除已有数据库。"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

import asyncpg
from runtime_guard import EXPECTED_DATABASE


async def main() -> None:
    admin_url = os.environ.get(
        "R2_C_ADMIN_DATABASE_URL",
        "postgresql://psychology:change-me@127.0.0.1:5432/postgres",
    )
    parsed = urlparse(admin_url)
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port != 5432
        or parsed.path.strip("/") != "postgres"
    ):
        raise RuntimeError("管理员连接必须限定为本机 PostgreSQL maintenance database")
    connection = await asyncpg.connect(admin_url)
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", EXPECTED_DATABASE
        )
        if exists:
            print(f"R2-C E2E database already exists; preserved: {EXPECTED_DATABASE}")
            return
        await connection.execute(f'CREATE DATABASE "{EXPECTED_DATABASE}"')
        print(f"Created dedicated R2-C E2E database: {EXPECTED_DATABASE}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
