"""建立真实服务端测评双标签/截止浏览器场景的合成数据。"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from runtime_guard import validate_api_target, validate_e2e_environment

validate_e2e_environment()
API_BASE = validate_api_target(os.environ.get("R2_C_API_BASE_URL", "http://127.0.0.1:8203"))
PASSWORD = os.environ.get("R2_C_E2E_PASSWORD", "r2-c-local-only-password")
TEACHER_EMAIL = os.environ.get(
    "R2_C_ASSESSMENT_TEACHER_EMAIL", "r2-c-teacher@example.com"
)
STUDENT_EMAIL = os.environ.get(
    "R2_C_ASSESSMENT_STUDENT_EMAIL", "r2-c-student@example.com"
)


def require(response: httpx.Response, expected: int, operation: str) -> dict:
    if response.status_code != expected:
        raise RuntimeError(f"{operation} 失败：HTTP {response.status_code}")
    return response.json().get("data", {})


def login(client: httpx.Client, email: str) -> None:
    require(
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        ),
        200,
        "登录",
    )


def main() -> None:
    with httpx.Client(base_url=API_BASE, timeout=15.0) as teacher:
        login(teacher, TEACHER_EMAIL)
        course = require(
            teacher.post(
                "/api/v1/courses",
                json={
                    "title": f"R2-C 双标签截止 {uuid.uuid4().hex[:8]}",
                    "term": "2026秋",
                },
            ),
            201,
            "建课",
        )
        with httpx.Client(base_url=API_BASE, timeout=15.0) as student:
            login(student, STUDENT_EMAIL)
            me = require(student.get("/api/v1/me"), 200, "学生身份读取")
            membership = teacher.post(
                f"/api/v1/courses/{course['id']}/members",
                json={"user_id": me["id"], "role": "student"},
            )
            if membership.status_code not in {200, 201}:
                raise RuntimeError(f"学生入课失败：HTTP {membership.status_code}")

            question = require(
                teacher.post(
                    f"/api/v1/courses/{course['id']}/questions",
                    json={
                        "type": "single",
                        "stem": "研究者操纵的变量是什么？",
                        "options": [
                            {"key": "A", "text": "自变量", "is_correct": True},
                            {"key": "B", "text": "因变量", "is_correct": False},
                        ],
                        "difficulty": 2,
                        "explanation": "操纵的变量是自变量。",
                        "evidence_ids": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
                    },
                ),
                201,
                "创建题目",
            )
            require(
                teacher.post(
                    f"/api/v1/questions/{question['id']}/review",
                    json={"action": "approve", "version": 1, "comment": "R2-C 验收题目"},
                ),
                200,
                "审核题目",
            )
            require(
                teacher.post(f"/api/v1/questions/{question['id']}/publish"),
                200,
                "发布题目",
            )

            closes_in_seconds = int(
                os.environ.get("R2_C_ASSESSMENT_CLOSES_IN_SECONDS", "90")
            )
            if not 60 <= closes_in_seconds <= 300:
                raise RuntimeError(
                    "R2_C_ASSESSMENT_CLOSES_IN_SECONDS 必须在 60—300 秒之间"
                )
            closes_at = datetime.now(UTC) + timedelta(seconds=closes_in_seconds)
            assessment = require(
                teacher.post(
                    f"/api/v1/courses/{course['id']}/assessments",
                    json={
                        "title": "双标签与服务端截止验收",
                        "question_ids": [question["id"]],
                        "closes_at": closes_at.isoformat(),
                        "ai_policy": "disabled",
                    },
                ),
                201,
                "创建测验",
            )
            require(
                teacher.post(f"/api/v1/assessments/{assessment['id']}/publish"),
                200,
                "发布测验",
            )
            attempt = require(
                student.post(f"/api/v1/assessments/{assessment['id']}/attempts"),
                201,
                "开始测验",
            )
            print(
                json.dumps(
                    {
                        "course_id": course["id"],
                        "assessment_id": assessment["id"],
                        "attempt_id": attempt["attempt_id"],
                        "question_version_id": question["current_version"]["id"],
                        "closes_at": closes_at.isoformat(),
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
