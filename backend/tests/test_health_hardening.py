from fastapi import status
from fastapi.testclient import TestClient

from core.secrets.config import reset_config_cache
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import User
from server import app

# Instantiate client globally to match test_uploads_auth.py and prevent loop mismatch errors
client = TestClient(app)


def test_health_check_dynamic_commit_sha(monkeypatch):
    monkeypatch.setenv("COMMIT_SHA", "dynamic_sha_12345")
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["commit"] == "dynamic_sha_12345"


def test_health_check_commit_sha_unknown(monkeypatch):
    monkeypatch.delenv("COMMIT_SHA", raising=False)
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["commit"] == "unknown"


def test_debug_config_inaccessible_anonymously():
    app.dependency_overrides.clear()
    response = client.get("/api/voice/debug-config")
    # should return 401 unauthorized
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_debug_config_returns_404_in_production(monkeypatch):
    # Emulate production env
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRETS_PROVIDER", "env")
    reset_config_cache()

    async def mock_super_admin():
        return User(
            id="admin_id",
            tenant_id="tenant_id",
            email="admin@test.com",
            name="Super Admin",
            role=UserRole.SUPER_ADMIN,
        )

    app.dependency_overrides[get_current_user] = mock_super_admin

    try:
        response = client.get("/api/voice/debug-config")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        reset_config_cache()


def test_debug_config_returns_403_for_non_super_admin(monkeypatch):
    # Emulate development env
    monkeypatch.setenv("APP_ENV", "development")
    reset_config_cache()

    async def mock_regular_user():
        return User(
            id="user_id",
            tenant_id="tenant_id",
            email="user@test.com",
            name="Regular User",
            role=UserRole.ADMIN,
        )

    app.dependency_overrides[get_current_user] = mock_regular_user

    try:
        response = client.get("/api/voice/debug-config")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        reset_config_cache()


def test_debug_config_returns_config_for_super_admin_in_dev(monkeypatch):
    # Emulate development env
    monkeypatch.setenv("APP_ENV", "development")
    reset_config_cache()

    async def mock_super_admin():
        return User(
            id="admin_id",
            tenant_id="tenant_id",
            email="admin@test.com",
            name="Super Admin",
            role=UserRole.SUPER_ADMIN,
        )

    app.dependency_overrides[get_current_user] = mock_super_admin

    try:
        response = client.get("/api/voice/debug-config")
        assert response.status_code == 200
        data = response.json()
        assert "has_account_sid" in data
        assert "has_auth_token" in data
    finally:
        app.dependency_overrides.clear()
        reset_config_cache()
