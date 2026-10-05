"""为 R3-F 真实只读 Release 页面准备隔离合成数据。"""

import json
import os
import time

if os.environ.get("PSYCHOLOGY_TEST_DB") != "psychology_learning_v1_r3_f_20261004":
    raise RuntimeError("Set PSYCHOLOGY_TEST_DB to the dedicated R3-F database before seeding")
if os.environ.get("PSYCHOLOGY_TEST_REDIS_URL") != "redis://127.0.0.1:6379/8":
    raise RuntimeError(
        "Set PSYCHOLOGY_TEST_REDIS_URL to the dedicated R3-F Redis DB before seeding"
    )
if os.environ.get("MINIO_BUCKET") != "v1-r3-f":
    raise RuntimeError("Set MINIO_BUCKET to the dedicated R3-F bucket before seeding")

from tests.conftest import create_user_sync, publish_course_release_for_test  # noqa: I001
from fastapi.testclient import TestClient

from app.main import app


stamp = str(time.time_ns())
teacher_email = f"r3-f-release-{stamp}@example.org"
admin_email = f"r3-f-admin-{stamp}@example.org"
password = "r3-f-browser-test-password"
teacher_id = create_user_sync(email=teacher_email, password=password, is_teacher=True)
create_user_sync(email=admin_email, password=password, is_platform_admin=True)

with TestClient(app) as client:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": teacher_email, "password": password},
    )
    assert login.status_code == 200, login.text
    course_response = client.post(
        "/api/v1/courses",
        json={"title": "R3-F 工程验收课程", "term": "synthetic", "timezone": "UTC"},
    )
    assert course_response.status_code == 201, course_response.text
    course = course_response.json()["data"]

    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": password},
    )
    assert admin_login.status_code == 200, admin_login.text
    role_grant = client.post(
        "/api/v1/admin/role-assignments",
        headers={"Idempotency-Key": f"r3-f-course-designer:{stamp}"},
        json={
            "user_id": teacher_id,
            "role": "course_designer",
            "scope_type": "platform",
            "scope_id": None,
            "reason": "隔离浏览器验收合成账号授权",
        },
    )
    assert role_grant.status_code == 201, role_grant.text
    teacher_login = client.post(
        "/api/v1/auth/login",
        json={"email": teacher_email, "password": password},
    )
    assert teacher_login.status_code == 200, teacher_login.text
    first_release_response = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "R3-F 合成只读版本 v1",
            "material_ids": [],
            "domain_pack": {"chapters": ["synthetic-intro"]},
            "pedagogy_pack": {"tasks": ["synthetic-review"]},
            "assessment_pack": {"release_ids": []},
        },
    )
    assert first_release_response.status_code == 201, first_release_response.text
    first_release = first_release_response.json()["data"]
    publish_course_release_for_test(client, course["id"], first_release["id"])
    author_login = client.post(
        "/api/v1/auth/login",
        json={"email": teacher_email, "password": password},
    )
    assert author_login.status_code == 200, author_login.text
    second_release_response = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={
            "name": "R3-F 合成只读版本 v2",
            "material_ids": [],
            "domain_pack": {"chapters": ["synthetic-intro", "synthetic-method"]},
            "pedagogy_pack": {"tasks": ["synthetic-review", "synthetic-compare"]},
            "assessment_pack": {"release_ids": []},
        },
    )
    assert second_release_response.status_code == 201, second_release_response.text
    second_release = second_release_response.json()["data"]
    publish_course_release_for_test(client, course["id"], second_release["id"])
    listed = client.get(f"/api/v1/courses/{course['id']}/releases")
    assert listed.status_code == 200, listed.text
    assert {item["id"] for item in listed.json()["data"]} >= {
        first_release["id"],
        second_release["id"],
    }

print(
    json.dumps(
        {
            "teacher_email": teacher_email,
            "password": password,
            "admin_email": admin_email,
            "course_id": course["id"],
            "release_ids": [first_release["id"], second_release["id"]],
            "material_ids": [],
            "role": "course_designer",
            "fixture_kind": "synthetic_engineering_only",
        },
        ensure_ascii=False,
    )
)
