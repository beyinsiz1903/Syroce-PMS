from fastapi.testclient import TestClient
from backend.app import app
from backend.models.schemas import User

def mock_get_current_user():
    return User(
        tenant_id="syrocedemo",
        email="admin@syrocedemo.com",
        role="admin",
        permissions=["all"]
    )

app.dependency_overrides = {}
from backend.core.security import get_current_user
app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app)
response = client.get("/api/mice/diary?date_from=2026-07-01&date_to=2026-07-31")
print("Status:", response.status_code)
print("Body:", response.json() if response.status_code == 200 else response.text)
