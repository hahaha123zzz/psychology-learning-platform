"""G0 冒烟验收：新环境按顺序执行迁移检查、契约检查、种子数据与核心业务流。

用法：python scripts/g0_smoke.py
前置：docker compose up -d postgres redis minio
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
PY = sys.executable
PORT = 8901
BASE = f"http://127.0.0.1:{PORT}"

results: list[tuple[str, bool, str]] = []


def step(name: str, func) -> None:
    try:
        detail = func()
        results.append((name, True, detail or ""))
        print(f"PASS  {name}  {detail or ''}")
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, str(exc)))
        print(f"FAIL  {name}  {exc}")


def run_migrations() -> str:
    proc = subprocess.run(
        [PY, "-m", "alembic", "upgrade", "head"],
        cwd=SERVER, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-400:])
    return "schema at head"


def check_migrations_match_models() -> str:
    proc = subprocess.run(
        [PY, "-m", "alembic", "check"],
        cwd=SERVER, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stdout + proc.stderr)[-400:])
    return "models match migrations"


def check_openapi_drift() -> str:
    sys.path.insert(0, str(SERVER))
    from app.main import app

    expected = json.dumps(app.openapi(), ensure_ascii=False, indent=2)
    committed = (ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")
    if expected != committed:
        (ROOT / "contracts" / "openapi.json").write_text(expected, encoding="utf-8")
        raise RuntimeError("openapi.json 已过期，已重新导出，请提交")
    return "openapi.json up to date"


def seed_demo() -> str:
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "seed_demo.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-400:])
    return "demo data ready"


def start_api_and_run_flow() -> str:
    server = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=SERVER,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                r = httpx.get(f"{BASE}/api/v1/health/ready", timeout=2)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("API 未在20秒内就绪")

        client = httpx.Client(base_url=BASE, timeout=10)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "teacher@demo.edu", "password": "demo-password-123"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"登录失败: {login.status_code} {login.text[:200]}")
        roles = login.json()["data"]["platform_roles"]
        if "teacher" not in roles:
            raise RuntimeError(f"角色异常: {roles}")

        body = {"title": "G0冒烟课程", "term": "2026春"}
        first = client.post(
            "/api/v1/courses", json=body, headers={"Idempotency-Key": "g0-course-1"}
        )
        replay = client.post(
            "/api/v1/courses", json=body, headers={"Idempotency-Key": "g0-course-1"}
        )
        if first.status_code != 201 or replay.status_code != 201:
            raise RuntimeError(f"创建课程异常: {first.status_code}/{replay.status_code}")
        if first.json()["data"]["id"] != replay.json()["data"]["id"]:
            raise RuntimeError("幂等重放返回了不同课程")

        course_id = first.json()["data"]["id"]
        conflict = client.patch(
            f"/api/v1/courses/{course_id}",
            json={"version": 99, "title": "不应成功"},
        )
        if conflict.status_code != 409:
            raise RuntimeError(f"版本冲突应返回409，实际 {conflict.status_code}")

        me = client.get("/api/v1/me")
        if me.status_code != 200 or not me.json()["data"]["course_memberships"]:
            raise RuntimeError("/me 未返回课程成员身份")

        client.post("/api/v1/auth/logout")
        return "login→create(idempotent)→conflict→me→logout 全部通过"
    finally:
        server.terminate()
        server.wait(timeout=10)


def main() -> int:
    step("迁移: alembic upgrade head", run_migrations)
    step("迁移: alembic check 模型一致", check_migrations_match_models)
    step("契约: OpenAPI 无漂移", check_openapi_drift)
    step("数据: 演示数据种子", seed_demo)
    step("冒烟: API核心业务流", start_api_and_run_flow)

    failed = [r for r in results if not r[1]]
    print(f"\nG0 结果: {len(results) - len(failed)}/{len(results)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
