from fastapi.testclient import TestClient

from ima.api.app import create_app
from ima.config import Settings


def test_openapi_has_only_foundation_operations() -> None:
    app = create_app(
        Settings(environment="test", database_url="postgresql+asyncpg://x:x@localhost/app")
    )
    schema = app.openapi()
    assert "/api/v1/system/info" in schema["paths"]
    assert "/api/v1/chat/completions" not in schema["paths"]
    assert schema["paths"]["/api/v1/system/info"]["get"]["operationId"] == "getSystemInfo"


def test_liveness_has_correlation_header() -> None:
    app = create_app(Settings(environment="test"))
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-correlation-id"]


def test_custom_settings_are_used_by_route_dependencies() -> None:
    app = create_app(
        Settings(
            environment="test",
            build_version="contract-test",
            database_url="postgresql+asyncpg://x:x@localhost/app",
        )
    )
    response = TestClient(app).get("/api/v1/system/info")
    assert response.status_code == 200
    assert response.json()["version"] == "contract-test"
