"""在专属 R2-A E2E 数据库中创建固定 PDF Reader 的真实课程数据。"""

from __future__ import annotations

import asyncio
import io
import json
import time
import uuid

import pymupdf
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import User
from app.db.session import session_factory
from app.main import app


def _reader_pdf() -> bytes:
    document = pymupdf.open()
    first = document.new_page(width=612, height=792)
    first.insert_text((72, 72), "Chapter 1 Foundations", fontsize=14)
    first.insert_text(
        (72, 108),
        "Independent variable control improves internal validity in experiments.",
        fontsize=12,
    )
    second = document.new_page(width=612, height=792)
    second.insert_text(
        (72, 72),
        "Between subjects design assigns different participants to conditions.",
        fontsize=12,
    )
    content = document.tobytes()
    document.close()
    return content


def _ensure_users(teacher_email: str, student_email: str) -> None:
    async def create() -> None:
        async with session_factory() as db:
            for email, is_teacher in ((teacher_email, True), (student_email, False)):
                db.add(
                    User(
                        organization_id=get_settings().default_organization_id,
                        email=email,
                        password_hash=hash_password("correct-password"),
                        display_name="R2-A Reader 验收账号",
                        status="active",
                        is_teacher=is_teacher,
                        is_platform_admin=False,
                    )
                )
            await db.commit()
        # 这个脚本会切换到 TestClient 的事件循环；不要把连接池连接跨 loop 复用。
        from app.db.session import engine

        await engine.dispose()

    asyncio.run(create())


def _require_status(response, expected: int) -> dict:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: "
            f"expected {expected}, got {response.status_code}: {response.text}"
        )
    return response.json()["data"]


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = _require_status(client.get(f"/api/v1/jobs/{job_id}"), 200)
        if job["status"] in {"succeeded", "failed"}:
            if job["status"] != "succeeded":
                raise AssertionError(f"Reader fixture job failed: {job['status']}")
            return job
        time.sleep(0.2)
    raise TimeoutError("Reader fixture ingestion job timed out")


def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    teacher_email = f"r2a-reader-teacher-{suffix}@example.com"
    student_email = f"r2a-reader-student-{suffix}@example.com"
    _ensure_users(teacher_email, student_email)

    with TestClient(app) as client:
        _require_status(
            client.post(
                "/api/v1/auth/login",
                json={"email": teacher_email, "password": "correct-password"},
            ),
            200,
        )
        course = _require_status(
            client.post(
                "/api/v1/courses",
                json={"title": "R2-A Reader 固定页图验收", "term": "2026 秋"},
            ),
            201,
        )
        course_id = course["id"]

        _require_status(
            client.post(
                "/api/v1/auth/login",
                json={"email": student_email, "password": "correct-password"},
            ),
            200,
        )
        student_id = _require_status(client.get("/api/v1/me"), 200)["id"]

        _require_status(
            client.post(
                "/api/v1/auth/login",
                json={"email": teacher_email, "password": "correct-password"},
            ),
            200,
        )
        _require_status(
            client.post(
                f"/api/v1/courses/{course_id}/members",
                json={"user_id": student_id, "role": "student"},
            ),
            201,
        )
        upload = _require_status(
            client.post(
                f"/api/v1/courses/{course_id}/materials",
                data={"title": "Reader 固定页图验收 PDF", "material_type": "textbook"},
                files={
                    "file": (
                        "r2-a-reader-fixture.pdf",
                        io.BytesIO(_reader_pdf()),
                        "application/pdf",
                    )
                },
            ),
            201,
        )
        version_id = upload["version_id"]
        parse_job = _require_status(
            client.post(f"/api/v1/material-versions/{version_id}/parse"),
            202,
        )["job_id"]
        _wait_for_job(client, parse_job)
        embed_job = _require_status(
            client.post(f"/api/v1/material-versions/{version_id}/embed"),
            202,
        )["job_id"]
        _wait_for_job(client, embed_job)
        _require_status(
            client.post(f"/api/v1/material-versions/{version_id}/publish"),
            200,
        )

        _require_status(
            client.post(
                "/api/v1/auth/login",
                json={"email": student_email, "password": "correct-password"},
            ),
            200,
        )
        search = _require_status(
            client.post(
                "/api/v1/knowledge/search",
                json={
                    "course_id": course_id,
                    "query": "independent variable validity",
                    "top_k": 8,
                    "purpose": "course_qa",
                },
            ),
            200,
        )
        pointer = next(
            item
            for item in search["items"]
            if item.get("evidence_pointer_id") and item.get("bbox")
        )

        _require_status(
            client.post(
                "/api/v1/auth/login",
                json={"email": teacher_email, "password": "correct-password"},
            ),
            200,
        )
        members = _require_status(client.get(f"/api/v1/courses/{course_id}/members"), 200)
        membership_id = next(item["id"] for item in members if item["user_id"] == student_id)

    print(
        json.dumps(
            {
                "course_id": course_id,
                "student_id": student_id,
                "material_version_id": version_id,
                "evidence_pointer_id": pointer["evidence_pointer_id"],
                "physical_page": pointer["physical_page"],
                "bbox": pointer["bbox"],
                "excerpt": pointer["text"],
                "membership_id": membership_id,
                "student_email": student_email,
                "teacher_email": teacher_email,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
