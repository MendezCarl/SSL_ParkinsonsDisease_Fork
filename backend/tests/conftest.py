from __future__ import annotations

from pathlib import Path
import sys

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

from auth import get_current_user, get_current_user_from_header_or_query
from main import app
import routes.websockets as ws_routes


class _FakeUser:
    id = 0
    username = "test-doctor@hospital.com"
    full_name = "Test Doctor"
    email = "test-doctor@hospital.com"
    location = "Test Clinic"
    title = "Neurologist"
    speciality = "Movement Disorders"


def _fake_current_user():
    return _FakeUser()


@pytest.fixture(autouse=True)
def override_auth(monkeypatch):
    """Most tests exercise business logic, not auth, so authenticate every
    request as a fake doctor by default. test_auth.py removes these
    overrides to test the real auth behavior."""
    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[get_current_user_from_header_or_query] = _fake_current_user
    monkeypatch.setattr(ws_routes, "get_user_by_token", lambda token: _fake_current_user())
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_from_header_or_query, None)
