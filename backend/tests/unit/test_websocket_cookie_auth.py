from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest

import core.database
import websocket_server
from core.security import JWT_ALGORITHM, JWT_SECRET


@pytest.mark.asyncio
async def test_socket_identity_accepts_http_only_access_cookie(monkeypatch):
    token = jwt.encode(
        {
            "user_id": "user-1",
            "tenant_id": "tenant-a",
            "type": "access",
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    users = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "user-1",
                "tenant_id": "tenant-a",
                "role": "front_desk",
            }
        )
    )
    monkeypatch.setattr(core.database, "db", SimpleNamespace(users=users))

    identity = await websocket_server._resolve_user_identity(
        {},
        {"HTTP_COOKIE": f"theme=light; access_token={token}; locale=tr"},
    )

    assert identity == {
        "user_id": "user-1",
        "tenant_id": "tenant-a",
        "role": "front_desk",
        "department": "Reception",
    }
    users.find_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_socket_identity_rejects_missing_token():
    assert await websocket_server._resolve_user_identity({}, {"HTTP_COOKIE": "theme=light"}) is None
