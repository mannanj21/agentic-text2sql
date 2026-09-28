from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data


def test_request_id_middleware() -> None:
    # No request ID provided, middleware should generate one
    response = client.get("/health")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0

    # Request ID provided, middleware should preserve it
    response2 = client.get("/health", headers={"X-Request-ID": "custom-id-123"})
    assert response2.headers["X-Request-ID"] == "custom-id-123"
