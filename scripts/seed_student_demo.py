"""为 V0.9 Demo 创建可重复的隔离合成课程、教材和练习数据。

仅允许使用专属本地数据库 psychology_learning_student_demo_20261005、
Redis DB12 与 student-demo-20261005 MinIO bucket。脚本会拒绝旧库、共享预览
Redis 和外部模型配置。运行前需设置 APP_ENV=test、TASK_BACKEND=in_process、
MATERIAL_LEGACY_AUTHORING_API_ENABLED=true 及本文档头部指定的资源环境变量。
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

EXPECTED_DB = "psychology_learning_student_demo_20261005"
EXPECTED_REDIS = "redis://127.0.0.1:6379/12"
EXPECTED_BUCKET = "student-demo-20261005"
TEACHER_EMAIL = "teacher@student-demo.edu"
STUDENT_EMAIL = "student@student-demo.edu"
ROUND_STUDENT_EMAILS = (
    "student-round-2@student-demo.edu",
    "student-round-3@student-demo.edu",
)
STUDENT_EMAILS = (STUDENT_EMAIL, *ROUND_STUDENT_EMAILS)
DEMO_PASSWORD = "student-demo-local-only-20261005"
COURSE_TITLE = "实验心理学｜学生端合成演示"
COURSE_TERM = "V0.9 Demo"
MATERIAL_TITLE = "合成教材：实验设计与图表（原生定位版）"
QUESTION_STEM = "【本地合成演示】研究者操纵的变量是什么？"
ASSESSMENT_TITLE = "合成练习：实验变量辨析（五题版）"
COURSE_RELEASE_NAME = "V1.2 学生闭环合成课程版本（五题 Practice）"
PINNED_COURSE_RELEASE_NAME = f"{COURSE_RELEASE_NAME}（固定 DomainRelease）"
DOMAIN_PACK = {"chapters": ["synthetic-experimental-variables"]}
PRACTICE_QUESTION_SPECS = (
    {
        "type": "single",
        "stem": QUESTION_STEM,
        "options": [
            {"key": "A", "text": "自变量", "is_correct": True},
            {"key": "B", "text": "因变量", "is_correct": False},
        ],
        "difficulty": 1,
        "explanation": "自变量是研究者主动操纵的变量；此题为合成演示题。",
    },
    {
        "type": "multiple",
        "stem": "【本地合成演示】哪些做法有助于控制无关变量？",
        "options": [
            {"key": "A", "text": "统一指导语", "is_correct": True},
            {"key": "B", "text": "随机分派被试", "is_correct": True},
            {"key": "C", "text": "只记录显著结果", "is_correct": False},
        ],
        "difficulty": 2,
        "explanation": "统一程序与随机分派有助于减少混淆；筛选显著结果会引入偏差。",
    },
    {
        "type": "true_false",
        "stem": "【本地合成演示】因变量是研究者测量的结果。",
        "answer": {"correct": True},
        "difficulty": 1,
        "explanation": "因变量是实验中被测量的结果变量。",
    },
    {
        "type": "short_answer",
        "stem": "【本地合成演示】用一句话说明控制组的作用。",
        "rubric": "指出控制组提供比较基准，帮助解释干预或条件变化。",
        "difficulty": 2,
        "explanation": "控制组提供对照，帮助判断结果是否与实验条件有关。",
    },
    {
        "type": "essay",
        "stem": "【本地合成演示】简述研究者如何用实验比较学习时间对回忆的影响。",
        "rubric": "说明操纵学习时间、测量回忆结果，并控制或随机分派其他因素。",
        "difficulty": 2,
        "explanation": "回答需区分操纵的学习时间与测量的回忆表现。",
    },
)
TABLE_TEXT = "Measure | Score\nRecall | 42"


def validate_environment() -> None:
    database = urlparse(os.environ.get("DATABASE_URL", ""))
    redis_url = os.environ.get("REDIS_URL", "")
    settings_expected = {
        "APP_ENV": "test",
        "TASK_BACKEND": "in_process",
        "MATERIAL_LEGACY_AUTHORING_API_ENABLED": "true",
        "LLM_PROVIDER": "internal",
        "MINIO_BUCKET": EXPECTED_BUCKET,
    }
    if (
        database.scheme != "postgresql+asyncpg"
        or database.hostname not in {"127.0.0.1", "localhost"}
        or database.port != 5432
        or database.path.strip("/") != EXPECTED_DB
    ):
        raise RuntimeError(f"DATABASE_URL 必须指向本机专属库 {EXPECTED_DB}")
    if redis_url != EXPECTED_REDIS:
        raise RuntimeError(f"REDIS_URL 必须精确为 {EXPECTED_REDIS}")
    for name, expected in settings_expected.items():
        if os.environ.get(name) != expected:
            raise RuntimeError(f"{name} 必须显式设为 {expected}")
    from app.core.config import get_settings

    settings = get_settings()
    if settings.llm_provider != "internal" or settings.llm_api_key or settings.llm_base_url:
        raise RuntimeError("本地 Demo 禁止配置外部 LLM 地址或密钥")
    if settings.embedding_api_key or settings.embedding_base_url:
        raise RuntimeError("本地 Demo 禁止配置外部 Embedding 地址或密钥")
    if settings.minio_endpoint not in {"127.0.0.1:9000", "localhost:9000"} or settings.minio_secure:
        raise RuntimeError("本地 Demo 只允许使用 localhost MinIO")


def synthetic_pdf() -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    lines = [
        (72, 72, "Synthetic Demo Chapter 1: Experimental Variables", 15),
        (
            72,
            118,
            "An independent variable is manipulated by the researcher.",
            11,
        ),
        (72, 145, "A dependent variable is measured as an outcome.", 11),
        (
            72,
            184,
            "For example, changing study time and measuring recall compares conditions.",
            11,
        ),
        (
            72,
            480,
            "A control group gives researchers a comparison for an intervention.",
            11,
        ),
        (
            72,
            520,
            "These sentences are synthetic course material for local software testing.",
            10,
        ),
    ]
    for x, y, text, size in lines:
        page.insert_text((x, y), text, fontsize=size)
    page.insert_text((72, 560), "The surrounding paragraph explains the measured result.")
    for x in (72, 172, 272):
        page.draw_line((x, 335), (x, 435))
    for y in (335, 385, 435):
        page.draw_line((72, y), (272, y))
    for point, text in (
        ((82, 365), "Measure"),
        ((182, 365), "Score"),
        ((82, 415), "Recall"),
        ((182, 415), "42"),
    ):
        page.insert_text(point, text)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pixmap.clear_with(255)
    page.insert_image(pymupdf.Rect(72, 220, 172, 320), stream=pixmap.tobytes("png"))
    data = document.tobytes()
    document.close()
    return data


def expect(response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: "
            f"{response.text[:1200]}"
        )
    return response.json()["data"]


def login(client, email: str) -> dict:
    client.cookies.clear()
    return expect(
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": DEMO_PASSWORD},
        ),
        200,
        "login",
    )


def wait_for_job(client, job_id: str, timeout: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = expect(client.get(f"/api/v1/jobs/{job_id}"), 200, "get ingestion job")
        if job["status"] in {"succeeded", "failed"}:
            if job["status"] != "succeeded":
                raise RuntimeError(f"Synthetic ingestion failed: {job['status']}")
            return job
        time.sleep(0.2)
    raise TimeoutError("Synthetic material ingestion timed out")


async def ensure_demo_release_reviewer(course_id: str, release_id: str) -> tuple[str, str]:
    """为合成课程发布准备稳定的课程级审核者账号与权限。"""
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.db.models import CourseRelease, RoleAssignment, User
    from app.db.session import session_factory

    email = f"release-reviewer-{release_id.lower()}@student-demo.edu"
    async with session_factory() as db:
        release = await db.get(CourseRelease, release_id)
        if release is None or release.course_id != course_id:
            raise RuntimeError("合成课程 Release 不存在或课程不匹配")
        author_id = release.created_by
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                organization_id=get_settings().default_organization_id,
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="V1.2 合成课程审核者",
                status="active",
                is_teacher=False,
            )
            db.add(user)
            await db.flush()
        assignment = await db.scalar(
            select(RoleAssignment).where(
                RoleAssignment.user_id == user.id,
                RoleAssignment.role == "course_publisher",
                RoleAssignment.scope_type == "course",
                RoleAssignment.scope_id == course_id,
            )
        )
        if assignment is None:
            db.add(
                RoleAssignment(
                    user_id=user.id,
                    role="course_publisher",
                    scope_type="course",
                    scope_id=course_id,
                    status="active",
                    granted_by=author_id,
                )
            )
        else:
            assignment.status = "active"
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.status = "active"
        await db.commit()
    return email, DEMO_PASSWORD


def publish_demo_release(client, course_id: str, release: dict) -> dict:
    """通过独立课程审核者发布带固定教材快照的本地合成 Release。"""
    from app.db.session import engine

    preview = expect(
        client.get(f"/api/v1/courses/{course_id}/releases/{release['id']}/preview"),
        200,
        "preview synthetic course release",
    )
    reviewer_email, reviewer_password = asyncio.run(
        ensure_demo_release_reviewer(course_id, release["id"])
    )
    # Direct async DB setup used asyncio.run; discard that loop's pool connections
    # before TestClient resumes on its managed event loop.
    asyncio.run(engine.dispose())
    client.cookies.clear()
    expect(
        client.post(
            "/api/v1/auth/login",
            json={"email": reviewer_email, "password": reviewer_password},
        ),
        200,
        "login synthetic release reviewer",
    )
    review_response = client.post(
        f"/api/v1/courses/{course_id}/releases/{release['id']}/reviews",
        headers={"Idempotency-Key": f"student-demo-review:{release['id']}"},
        json={
            "expected_version": release["version"],
            "manifest_sha256": preview["manifest_sha256"],
            "decision": "approved",
            "reason": "本地 V1.2 学生端合成演示课程审核",
        },
    )
    if review_response.status_code not in {200, 201}:
        raise RuntimeError(
            f"review synthetic release: {review_response.status_code}: "
            f"{review_response.text[:1200]}"
        )
    published_response = client.post(
        f"/api/v1/courses/{course_id}/releases/{release['id']}/publish",
        headers={"Idempotency-Key": f"student-demo-publish:{release['id']}"},
        json={"expected_version": release["version"]},
    )
    if published_response.status_code != 200:
        raise RuntimeError(
            f"publish synthetic release: {published_response.status_code}: "
            f"{published_response.text[:1200]}"
        )
    client.cookies.clear()
    result = client.post(
        "/api/v1/auth/login",
        json={"email": TEACHER_EMAIL, "password": DEMO_PASSWORD},
    )
    expect(result, 200, "restore synthetic teacher session")
    return published_response.json()["data"]


def ensure_demo_domain_release(client, course_id: str) -> str:
    """创建或复用本地合成 DomainRelease，供索引与课程版本精确固定。"""
    releases = expect(
        client.get(f"/api/v1/courses/{course_id}/domain-releases"),
        200,
        "list synthetic domain releases",
    )
    release = next(
        (
            item
            for item in releases
            if item.get("manifest", {}).get("domain_pack", item.get("manifest"))
            == DOMAIN_PACK
            and item.get("status") in {"draft", "published"}
        ),
        None,
    )
    if release is None:
        release = expect(
            client.post(
                f"/api/v1/courses/{course_id}/domain-releases",
                headers={"Idempotency-Key": "student-demo-domain-release-v12"},
                json={"manifest": {"domain_pack": DOMAIN_PACK}},
            ),
            201,
            "create synthetic domain release",
        )
    if release["status"] == "draft":
        release = expect(
            client.post(
                f"/api/v1/courses/{course_id}/domain-releases/{release['id']}/publish",
                headers={
                    "Idempotency-Key": f"student-demo-domain-publish:{release['id']}"
                },
            ),
            200,
            "publish synthetic domain release",
        )
    if release["status"] != "published":
        raise RuntimeError("合成 DomainRelease 必须处于 published 状态")
    return release["id"]


async def ensure_database() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    database_url = os.environ["DATABASE_URL"]
    admin_url = database_url.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        exists = await connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": EXPECTED_DB},
        )
        if exists.scalar() is None:
            await connection.execute(text(f'CREATE DATABASE "{EXPECTED_DB}"'))
    await engine.dispose()


async def ensure_users() -> None:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.db.models import User
    from app.db.session import engine, session_factory

    settings = get_settings()
    async with session_factory() as db:
        demo_users = [
            (TEACHER_EMAIL, "V0.9 合成演示教师", True),
            (STUDENT_EMAIL, "V0.9 合成演示学生", False),
            (ROUND_STUDENT_EMAILS[0], "V1.2 合成演示学生 2", False),
            (ROUND_STUDENT_EMAILS[1], "V1.2 合成演示学生 3", False),
        ]
        for email, name, is_teacher in demo_users:
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    organization_id=settings.default_organization_id,
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=name,
                    status="active",
                    is_teacher=is_teacher,
                )
                db.add(user)
            else:
                if user.organization_id != settings.default_organization_id:
                    raise RuntimeError("合成演示账号机构不一致，拒绝修改")
                user.password_hash = hash_password(DEMO_PASSWORD)
                user.display_name = name
                user.status = "active"
                user.is_teacher = is_teacher
        await db.commit()
    # TestClient uses its own event loop; do not reuse asyncpg connections across loops.
    await engine.dispose()
    await engine.dispose()


async def make_synthetic_reviews_due(course_id: str) -> None:
    """让专属合成课程中的待复习错题能在同一轮演示里复习。"""
    from sqlalchemy import update

    from app.db.models import ReviewTask
    from app.db.session import session_factory

    async with session_factory() as db:
        await db.execute(
            update(ReviewTask)
            .where(
                ReviewTask.course_id == course_id,
                ReviewTask.reason == "wrong_answer",
                ReviewTask.status == "pending",
            )
            .values(due_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()


async def learning_session_release_binding(task_id: str) -> tuple[str | None, str | None]:
    from app.db.models import LearningSession
    from app.db.session import session_factory

    async with session_factory() as db:
        row = await db.get(LearningSession, task_id)
        return (
            (row.course_release_assignment_id, row.course_release_id)
            if row is not None
            else (None, None)
        )


async def chat_session_release_binding(session_id: str) -> tuple[str | None, str | None]:
    from app.db.models import ChatSession
    from app.db.session import session_factory

    async with session_factory() as db:
        row = await db.get(ChatSession, session_id)
        return (
            (row.course_release_assignment_id, row.course_release_id)
            if row is not None
            else (None, None)
        )


def seed_api_data() -> dict[str, str]:
    from fastapi.testclient import TestClient

    from app.db.session import engine
    from app.main import app

    with TestClient(app) as client:
        login(client, TEACHER_EMAIL)
        courses = expect(client.get("/api/v1/courses"), 200, "list courses")
        course = next(
            (
                item
                for item in courses
                if item["title"] == COURSE_TITLE and item["term"] == COURSE_TERM
            ),
            None,
        )
        if course is None:
            course = expect(
                client.post(
                    "/api/v1/courses",
                    json={"title": COURSE_TITLE, "term": COURSE_TERM},
                ),
                201,
                "create synthetic course",
            )
        course_id = course["id"]
        domain_release_id = ensure_demo_domain_release(client, course_id)

        student_ids = []
        for student_email in STUDENT_EMAILS:
            login(client, student_email)
            student = expect(
                client.get("/api/v1/me"), 200, f"get synthetic student {student_email}"
            )
            student_ids.append(student["id"])
        login(client, TEACHER_EMAIL)
        members = expect(
            client.get(f"/api/v1/courses/{course_id}/members"), 200, "list members"
        )
        member_ids = {member["user_id"] for member in members}
        for student_id in student_ids:
            if student_id not in member_ids:
                expect(
                    client.post(
                        f"/api/v1/courses/{course_id}/members",
                        json={"user_id": student_id, "role": "student"},
                    ),
                    201,
                    "add synthetic student",
                )

        materials = expect(
            client.get(f"/api/v1/courses/{course_id}/materials"),
            200,
            "list synthetic materials",
        )
        material = next(
            (
                item
                for item in materials
                if item["title"] == MATERIAL_TITLE and item["status"] == "active"
            ),
            None,
        )
        if material is None:
            uploaded = expect(
                client.post(
                    f"/api/v1/courses/{course_id}/materials",
                    data={"title": MATERIAL_TITLE, "material_type": "textbook"},
                    files={
                        "file": (
                            "synthetic-experimental-variables.pdf",
                            io.BytesIO(synthetic_pdf()),
                            "application/pdf",
                        )
                    },
                ),
                201,
                "upload synthetic PDF",
            )
            version_id = uploaded["version_id"]
            parse = expect(
                client.post(f"/api/v1/material-versions/{version_id}/parse"),
                202,
                "parse synthetic PDF",
            )
            wait_for_job(client, parse["job_id"])
            embed = expect(
                client.post(
                    f"/api/v1/material-versions/{version_id}/embed",
                    params={"domain_release_id": domain_release_id},
                    headers={
                        "Idempotency-Key": (
                            f"student-demo-index:{version_id}:{domain_release_id}"
                        )
                    },
                ),
                202,
                "embed synthetic PDF",
            )
            wait_for_job(client, embed["job_id"])
            expect(
                client.post(
                    f"/api/v1/material-versions/{version_id}/publish",
                    params={"domain_release_id": domain_release_id},
                ),
                200,
                "publish synthetic PDF",
            )
        else:
            current = material.get("current_version") or {}
            version_id = current.get("id", "")
            if not version_id or current.get("status") != "parsed":
                raise RuntimeError(
                    "同名演示教材尚未解析成功；请使用专属 Demo 库排障后再重跑"
                )
            # 该端点会复用同一教材版本、Embedding 与 DomainRelease 的现有快照；
            # 若旧快照缺少 DomainRelease，则会先以精确领域版本重建索引并替换快照。
            embed = expect(
                client.post(
                    f"/api/v1/material-versions/{version_id}/embed",
                    params={"domain_release_id": domain_release_id},
                    headers={
                        "Idempotency-Key": (
                            f"student-demo-index:{version_id}:{domain_release_id}"
                        )
                    },
                ),
                202,
                "ensure pinned synthetic index",
            )
            wait_for_job(client, embed["job_id"])
            expect(
                client.post(
                    f"/api/v1/material-versions/{version_id}/publish",
                    params={"domain_release_id": domain_release_id},
                ),
                200,
                "ensure pinned synthetic publication",
            )

        # 种子阶段尚未切换班级 Release；教师身份只用于生成带确切领域快照的
        # 合成题目 EvidencePointer。学生侧资格路径由后续联调单独验证。
        login(client, TEACHER_EMAIL)
        search = expect(
            client.post(
                "/api/v1/knowledge/search",
                json={
                    "course_id": course_id,
                    "material_version_ids": [version_id],
                    "domain_release_id": domain_release_id,
                    "query": "independent variable manipulated researcher",
                    "top_k": 8,
                    "purpose": "course_qa",
                },
            ),
            200,
            "retrieve synthetic evidence pointer",
        )
        evidence = next(
            (
                item
                for item in search["items"]
                if item.get("evidence_pointer_id")
                and "independent variable" in (item.get("text") or "").lower()
            ),
            None,
        )
        if evidence is None:
            raise RuntimeError("未能从合成教材检索到带固定来源的自变量证据")
        evidence_pointer_id = evidence["evidence_pointer_id"]
        pointer = expect(
            client.get(f"/api/v1/evidence-pointers/{evidence_pointer_id}"),
            200,
            "validate synthetic evidence pointer",
        )
        if pointer["material_version_id"] != version_id:
            raise RuntimeError("题目候选证据指针未绑定本次合成教材版本")

        table_search = expect(
            client.post(
                "/api/v1/knowledge/search",
                json={
                    "course_id": course_id,
                    "material_version_ids": [version_id],
                    "domain_release_id": domain_release_id,
                    "query": "measure score recall",
                    "object_types": ["table"],
                    "top_k": 8,
                    "purpose": "course_qa",
                },
            ),
            200,
            "retrieve synthetic native table",
        )
        table_item = next(
            (
                item
                for item in table_search["items"]
                if item.get("object_type") == "table"
                and item.get("evidence_pointer_id")
                and TABLE_TEXT in (item.get("text") or "")
            ),
            None,
        )
        if table_item is None:
            raise RuntimeError("合成 PDF 的原生表格未按稀疏词项检索到")
        figure_item = next(
            (
                item
                for item in table_item.get("closure", [])
                if item.get("object_type") == "figure"
                and item.get("evidence_pointer_id")
            ),
            None,
        )
        if figure_item is None:
            raise RuntimeError("原生表格的已审核阅读顺序闭包未生成图像 EvidencePointer")
        table_pointer = expect(
            client.get(f"/api/v1/evidence-pointers/{table_item['evidence_pointer_id']}"),
            200,
            "validate synthetic table EvidencePointer",
        )
        figure_pointer = expect(
            client.get(f"/api/v1/evidence-pointers/{figure_item['evidence_pointer_id']}"),
            200,
            "validate synthetic figure EvidencePointer",
        )
        if (
            table_pointer["material_version_id"] != version_id
            or table_pointer["object_type"] != "table"
        ):
            raise RuntimeError("表格指针没有固定到预期教材版本和对象类型")
        if (
            figure_pointer["material_version_id"] != version_id
            or figure_pointer["object_type"] != "figure"
        ):
            raise RuntimeError("图像指针没有固定到预期教材版本和对象类型")
        page_image = client.get(
            f"/api/v1/evidence-pointers/{figure_item['evidence_pointer_id']}/page-image",
            params={"physical_page": figure_item["physical_page"]},
        )
        if page_image.status_code != 200 or not page_image.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("合成图像指针无法读取固定版本的 Reader 页图")

        login(client, TEACHER_EMAIL)
        questions = expect(
            client.get(f"/api/v1/courses/{course_id}/questions?status=published"),
            200,
            "list synthetic questions",
        )
        question_ids = []
        for spec in PRACTICE_QUESTION_SPECS:
            question = next(
                (
                    item
                    for item in questions
                    if item.get("current_version", {}).get("stem") == spec["stem"]
                ),
                None,
            )
            if question is None:
                question = expect(
                    client.post(
                        f"/api/v1/courses/{course_id}/questions",
                        json={**spec, "evidence_ids": [evidence_pointer_id]},
                    ),
                    201,
                    f"create synthetic {spec['type']} practice question",
                )
                expect(
                    client.post(
                        f"/api/v1/questions/{question['id']}/review",
                        json={
                            "action": "approve",
                            "version": question["version"],
                            "comment": "本地合成 Demo 自动验收",
                        },
                    ),
                    200,
                    f"approve synthetic {spec['type']} practice question",
                )
                expect(
                    client.post(f"/api/v1/questions/{question['id']}/publish"),
                    200,
                    f"publish synthetic {spec['type']} practice question",
                )
            question_ids.append(question["id"])

        assessments = expect(
            client.get(f"/api/v1/courses/{course_id}/assessments"),
            200,
            "list synthetic assessments",
        )
        assessment = next(
            (
                item
                for item in assessments
                if item["title"] == ASSESSMENT_TITLE and item["purpose"] == "practice"
            ),
            None,
        )
        if assessment is None:
            created = expect(
                client.post(
                    f"/api/v1/courses/{course_id}/assessments",
                    json={
                        "title": ASSESSMENT_TITLE,
                        "question_ids": question_ids,
                        "purpose": "practice",
                        "ai_policy": "disabled",
                        "points_per_question": 1,
                    },
                ),
                201,
                "create synthetic practice assessment",
            )
            assessment_id = created["id"]
            expect(
                client.post(f"/api/v1/assessments/{assessment_id}/publish"),
                200,
                "publish synthetic practice assessment",
            )
        else:
            assessment_id = assessment["id"]

        published_questions = expect(
            client.get(f"/api/v1/courses/{course_id}/questions?status=published"),
            200,
            "reload published synthetic question",
        )
        published_question = next(
            (
                item
                for item in published_questions
                if item.get("current_version", {}).get("stem") == QUESTION_STEM
            ),
            None,
        )
        question_version_id = (published_question or {}).get("current_version", {}).get("id")
        if not question_version_id:
            raise RuntimeError("无法取得已发布合成题的固定版本 ID")

        classes = expect(
            client.get(f"/api/v1/courses/{course_id}/classes"),
            200,
            "list synthetic classes",
        )
        course_class = next((item for item in classes if item["code"] == "DEMO-V12"), None)
        if course_class is None:
            course_class = expect(
                client.post(
                    f"/api/v1/courses/{course_id}/classes",
                    json={"code": "DEMO-V12", "name": "V1.2 学生闭环合成班"},
                ),
                201,
                "create synthetic class",
            )
        class_members = expect(
            client.get(
                f"/api/v1/courses/{course_id}/classes/{course_class['id']}/members"
            ),
            200,
            "list synthetic class members",
        )
        class_member_ids = {item["user_id"] for item in class_members}
        for student_id in student_ids:
            if student_id not in class_member_ids:
                expect(
                    client.post(
                        f"/api/v1/courses/{course_id}/classes/{course_class['id']}/members",
                        json={"user_id": student_id},
                    ),
                    201,
                    "add synthetic student to class",
                )

        releases = expect(
            client.get(f"/api/v1/courses/{course_id}/releases"),
            200,
            "list synthetic course releases",
        )
        release_name = PINNED_COURSE_RELEASE_NAME
        release = next(
            (
                item
                for item in releases
                if item["name"] == release_name
                and item.get("domain_release_id") == domain_release_id
            ),
            None,
        )
        if release is None:
            release = expect(
                client.post(
                    f"/api/v1/courses/{course_id}/releases",
                    json={
                        "name": release_name,
                        "material_ids": [material["id"]],
                        "domain_release_id": domain_release_id,
                        "domain_pack": DOMAIN_PACK,
                        "pedagogy_pack": {"tasks": ["retrieve", "explain", "practice", "review"]},
                        "assessment_pack": {"release_ids": [assessment_id]},
                    },
                ),
                201,
                "create synthetic course release",
            )
        if release["status"] == "draft":
            release = publish_demo_release(client, course_id, release)
        elif release["status"] != "published":
            raise RuntimeError("合成 V1.2 课程 Release 必须处于 draft 或 published")

        assignment = expect(
            client.get(
                f"/api/v1/courses/{course_id}/classes/{course_class['id']}/release-assignment"
            ),
            200,
            "get synthetic class release assignment",
        )
        if assignment is None or assignment["course_release_id"] != release["id"]:
            expect(
                client.put(
                    f"/api/v1/courses/{course_id}/classes/{course_class['id']}/release-assignment",
                    headers={"Idempotency-Key": f"student-demo-assignment:{release['id']}"},
                    json={
                        "course_release_id": release["id"],
                        "expected_version": assignment["version"] if assignment else 0,
                        "close_reason": "V1.2 合成课程版本替换",
                    },
                ),
                200,
                "assign synthetic course release to class",
            )

        home_tasks = {}
        course_qa_sessions = {}
        for student_email in STUDENT_EMAILS:
            login(client, student_email)
            session_title = f"V1.2 Demo course_qa {release['id']} {student_email}"
            sessions = expect(
                client.get("/api/v1/chat/sessions"),
                200,
                f"list synthetic course_qa sessions for {student_email}",
            )
            course_qa = next(
                (
                    item
                    for item in sessions
                    if item.get("course_id") == course_id
                    and item.get("mode") == "course_qa"
                    and item.get("title") == session_title
                ),
                None,
            )
            if course_qa is not None:
                chat_binding = asyncio.run(chat_session_release_binding(course_qa["id"]))
                asyncio.run(engine.dispose())
            else:
                chat_binding = (None, None)
            if course_qa is None or chat_binding[0] is None or chat_binding[1] != release["id"]:
                course_qa = expect(
                    client.post(
                        "/api/v1/chat/sessions",
                        json={
                            "course_id": course_id,
                            "mode": "course_qa",
                            "title": session_title,
                        },
                    ),
                    201,
                    f"create pinned synthetic course_qa session for {student_email}",
                )
                chat_binding = asyncio.run(chat_session_release_binding(course_qa["id"]))
                asyncio.run(engine.dispose())
            if chat_binding[0] is None or chat_binding[1] != release["id"]:
                raise RuntimeError("合成 course_qa 会话必须固定到班级指派的 CourseRelease")
            course_qa_sessions[student_email] = course_qa["id"]

            home = expect(
                client.get("/api/v1/student/home"),
                200,
                f"get synthetic student home for {student_email}",
            )
            current_task = home.get("current_task")
            current_binding = (
                asyncio.run(learning_session_release_binding(current_task["id"]))
                if current_task is not None
                else (None, None)
            )
            if current_task is not None:
                asyncio.run(engine.dispose())
            if (
                current_task is None
                or current_task.get("course_id") != course_id
                or current_task.get("material_version_id") != version_id
                or current_binding[0] is None
                or current_binding[1] != release["id"]
            ):
                current_task = expect(
                    client.post(
                        "/api/v1/learning-sessions",
                        json={
                            "course_id": course_id,
                            "material_version_id": version_id,
                        },
                    ),
                    201,
                    "create synthetic resumable learning task",
                )
            if (
                current_task.get("course_id") != course_id
                or current_task.get("material_version_id") != version_id
            ):
                raise RuntimeError("Home 当前合成任务必须绑定本次课程与教材版本")
            assignment_id, pinned_release_id = asyncio.run(
                learning_session_release_binding(current_task["id"])
            )
            asyncio.run(engine.dispose())
            if not assignment_id or pinned_release_id != release["id"]:
                raise RuntimeError("Home 当前合成任务必须固定到班级指派的 CourseRelease")
            home = expect(
                client.get("/api/v1/student/home"),
                200,
                f"verify synthetic student home task for {student_email}",
            )
            home_task = home.get("current_task")
            if not home_task or home_task.get("id") != current_task.get("id"):
                raise RuntimeError("Home 未返回刚创建或复用的可恢复合成任务")
            home_tasks[student_email] = home_task["id"]

    home_task = home_tasks[STUDENT_EMAIL]
    return {
        "course_id": course_id,
        "material_version_id": version_id,
        "assessment_id": assessment_id,
        "question_version_id": question_version_id,
        "course_release_id": release["id"],
        "class_id": course_class["id"],
        "learning_task_id": home_task,
        "learning_task_ids_by_student": home_tasks,
        "course_qa_session_ids_by_student": course_qa_sessions,
        "table_pointer_id": table_item["evidence_pointer_id"],
        "figure_pointer_id": figure_item["evidence_pointer_id"],
    }


def main() -> None:
    validate_environment()
    from alembic.config import Config

    from alembic import command
    from app.db.session import engine

    asyncio.run(ensure_database())
    alembic = Config(str(SERVER / "alembic.ini"))
    alembic.set_main_option("script_location", str(SERVER / "alembic"))
    command.upgrade(alembic, "head")
    asyncio.run(ensure_users())
    seeded = seed_api_data()
    asyncio.run(make_synthetic_reviews_due(seeded["course_id"]))
    print(
        json.dumps(
            {
                "database": EXPECTED_DB,
                "redis_db": 12,
                "minio_bucket": EXPECTED_BUCKET,
                "synthetic_only": True,
                "external_models": False,
                "synthetic_reviews_due_immediately": True,
                "teacher_email": TEACHER_EMAIL,
                "student_email": STUDENT_EMAIL,
                "additional_student_emails": list(ROUND_STUDENT_EMAILS),
                **seeded,
            },
            ensure_ascii=False,
        )
    )
    asyncio.run(engine.dispose())


if __name__ == "__main__":
    validate_environment()
    main()
