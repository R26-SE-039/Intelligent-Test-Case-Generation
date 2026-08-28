"""Integration tests: exercise the FastAPI app end-to-end via TestClient.

These boot the whole app (all routers import cleanly) and hit the routes that
need no database — proving the service starts and its contract/OpenAPI docs are
intact. If the app or any router fails to import, these tests fail, which is
exactly what should block a deploy.
"""
import pytest

pytestmark = pytest.mark.integration


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "0.2.0"
    assert "running" in body["message"].lower()


def test_openapi_schema_is_served(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"].startswith("NextGen QA Component 2")
    assert schema["info"]["version"] == "0.2.0"
    # Core routes must be documented in the spec.
    assert "/health" in schema["paths"]
    assert "/" in schema["paths"]


def test_swagger_ui_is_served(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger-ui" in resp.text.lower()


def test_redoc_is_served(client):
    resp = client.get("/redoc")
    assert resp.status_code == 200
    assert "redoc" in resp.text.lower()
