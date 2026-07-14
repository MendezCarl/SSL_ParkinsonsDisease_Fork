from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth import get_current_user, get_current_user_from_header_or_query
from main import app


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_from_header_or_query, None)


def test_protected_route_without_token_returns_401():
    _clear_auth_override()
    client = TestClient(app)
    response = client.get("/patients/")
    assert response.status_code == 401


def test_protected_route_with_garbage_token_returns_401():
    _clear_auth_override()
    client = TestClient(app)
    response = client.get("/patients/", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_login_then_authenticated_request_succeeds():
    _clear_auth_override()
    client = TestClient(app)

    token_response = client.post(
        "/token",
        data={"username": "doctor@hospital.com", "password": "Demo123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_response.status_code == 200
    access_token = token_response.json()["access_token"]

    response = client.get("/patients/", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200


def test_dtw_and_classifier_routers_require_auth():
    _clear_auth_override()
    client = TestClient(app)

    assert client.get("/dtw/tests").status_code == 401
    assert client.post("/ml/updrs/predict", json={"sequence": [], "return_attention": False}).status_code == 401


def test_websocket_rejects_connection_without_token():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/camera"):
            pass
