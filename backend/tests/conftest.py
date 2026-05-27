"""Test fixtures for prd-agent-rag."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create a test client with fresh DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def guest_token(client):
    """Get a guest auth token."""
    resp = client.post("/api/v1/auth/guest-login", data={"username": "guest", "password": "x"})
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(guest_token):
    """Auth headers with guest token."""
    return {"Authorization": f"Bearer {guest_token}"}
