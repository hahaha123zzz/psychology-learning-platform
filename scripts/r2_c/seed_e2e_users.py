"""在专属 E2E 库中创建可丢弃的演示教师/学生，不输出密码。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import validate_e2e_environment  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import session_factory  # noqa: E402

TEACHER_EMAIL = os.environ.get(
    "R2_C_ASSESSMENT_TEACHER_EMAIL", "r2-c-teacher@example.com"
)
STUDENT_EMAIL = os.environ.get(
    "R2_C_ASSESSMENT_STUDENT_EMAIL", "r2-c-student@example.com"
)


async def main() -> None:
    validate_e2e_environment()
    password = os.environ.get("R2_C_E2E_PASSWORD", "r2-c-local-only-password")
    settings = get_settings()
    async with session_factory() as db:
        ids: dict[str, str] = {}
        for email, display_name, is_teacher in (
            (TEACHER_EMAIL, "R2-C 演示教师", True),
            (STUDENT_EMAIL, "R2-C 演示学生", False),
        ):
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    organization_id=settings.default_organization_id,
                    email=email,
                    password_hash=hash_password(password),
                    display_name=display_name,
                    status="active",
                    is_teacher=is_teacher,
                )
                db.add(user)
                await db.flush()
            elif user.organization_id != settings.default_organization_id:
                raise RuntimeError(f"E2E 用户机构不符：{email}")
            ids[email] = user.id
        await db.commit()
    print(f"R2-C E2E accounts ready: teacher={ids[TEACHER_EMAIL]} student={ids[STUDENT_EMAIL]}")


if __name__ == "__main__":
    asyncio.run(main())
