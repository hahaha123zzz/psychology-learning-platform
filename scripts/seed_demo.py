"""创建演示数据：一名教师、一名学生和一门课程。可重复执行（按邮箱和课程名幂等）。"""

import asyncio
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models import Course, CourseMember, User  # noqa: E402
from app.db.session import engine, session_factory  # noqa: E402

DEMO_TEACHER_EMAIL = "teacher@demo.edu"
DEMO_STUDENT_EMAIL = "student@demo.edu"
DEMO_PASSWORD = "demo-password-123"
COURSE_TITLE = "实验心理学（演示）"
COURSE_TERM = "2026春"


async def upsert_user(
    session, *, email: str, display_name: str, is_teacher: bool
) -> User:
    existing = await session.execute(
        select(User).where(User.email == email).limit(1)
    )
    user = existing.scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        organization_id=get_settings().default_organization_id,
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        display_name=display_name,
        status="active",
        is_teacher=is_teacher,
    )
    session.add(user)
    await session.flush()
    return user


async def ensure_course(session, teacher: User, student: User) -> Course:
    existing = await session.execute(
        select(Course)
        .where(Course.title == COURSE_TITLE, Course.term == COURSE_TERM)
        .limit(1)
    )
    course = existing.scalar_one_or_none()
    if course is None:
        course = Course(
            organization_id=get_settings().default_organization_id,
            title=COURSE_TITLE,
            term=COURSE_TERM,
            description="用于G0冒烟与开发的演示课程",
            created_by=teacher.id,
        )
        session.add(course)
        await session.flush()
        session.add(
            CourseMember(
                course_id=course.id,
                user_id=teacher.id,
                role="teacher",
                status="active",
            )
        )
    membership = await session.execute(
        select(CourseMember).where(
            CourseMember.course_id == course.id,
            CourseMember.user_id == student.id,
        )
    )
    member = membership.scalar_one_or_none()
    if member is None:
        session.add(
            CourseMember(
                course_id=course.id,
                user_id=student.id,
                role="student",
                status="active",
            )
        )
    return course


async def main() -> None:
    async with session_factory() as session:
        teacher = await upsert_user(
            session,
            email=DEMO_TEACHER_EMAIL,
            display_name="演示教师",
            is_teacher=True,
        )
        student = await upsert_user(
            session,
            email=DEMO_STUDENT_EMAIL,
            display_name="演示学生",
            is_teacher=False,
        )
        course = await ensure_course(session, teacher, student)
        await session.commit()
        print(f"teacher: {teacher.email}")
        print(f"student: {student.email}")
        print(f"course:  {course.title} ({course.id})")
        print(f"password: {DEMO_PASSWORD}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
