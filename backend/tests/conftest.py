"""Shared pytest fixtures for the C2 backend test suite."""
import pytest


@pytest.fixture(scope="session")
def client():
    """A FastAPI TestClient for integration tests.

    IMPORTANT: we deliberately do NOT use `with TestClient(app) as client:`.
    The context-manager form runs the app's lifespan, whose startup calls
    init_db() → a real Neon/Postgres connection. These tests only exercise
    routes that need no DB state (root, health, OpenAPI), so we skip the
    lifespan entirely and keep the suite hermetic (no network, no database).
    """
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)
