import unittest.mock as mock

from fastapi.testclient import TestClient

# Mock the database before importing app
with mock.patch("core.database.AsyncIOMotorClient"):
    from models.schemas import User
    from server import app

    def mock_get_current_user():
        return User(
            id="test_user_id",
            name="Admin",
            tenant_id="syrocedemo",
            email="admin@syrocedemo.com",
            role="admin",
            permissions=["all"]
        )

    app.dependency_overrides = {}
    from core.security import get_current_user
    app.dependency_overrides[get_current_user] = mock_get_current_user

    # Bypass migrations
    from server import _db_migrations_startup
    app.router.on_startup.remove(_db_migrations_startup) if _db_migrations_startup in app.router.on_startup else None

    with TestClient(app) as client:
        response = client.get("/api/mice/diary?date_from=2026-07-01&date_to=2026-07-31")
        print("Status:", response.status_code)
        print("Body:", response.json() if response.status_code == 200 else response.text)
