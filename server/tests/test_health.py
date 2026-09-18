from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_live_health_has_request_id() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


def test_root_is_available() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"

