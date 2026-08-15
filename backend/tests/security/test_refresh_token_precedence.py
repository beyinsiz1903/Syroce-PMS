from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import Request, Response


@pytest.mark.asyncio
async def test_refresh_token_body_takes_precedence_over_stale_cookie():
    from core.security import JWT_ALGORITHM, JWT_SECRET
    from routers.auth import refresh_token

    cookie_token = jwt.encode(
        {
            "type": "refresh",
            "user_id": "stale-user",
            "tenant_id": "stale-tenant",
            "jti": "stale-jti",
            "exp": 9999999999,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    body_token = jwt.encode(
        {
            "type": "refresh",
            "user_id": "current-user",
            "tenant_id": "current-tenant",
            "jti": "current-jti",
            "exp": 9999999999,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    mock_request = MagicMock(spec=Request)
    mock_request.cookies = {"refresh_token": cookie_token}
    mock_response = MagicMock(spec=Response)
    mock_db = AsyncMock()
    mock_db.users.find_one = AsyncMock(
        return_value={
            "id": "current-user",
            "tenant_id": "current-tenant",
            "is_active": True,
        }
    )
    mock_db.audit_logs.insert_one = AsyncMock()

    with (
        patch("routers.auth.db", mock_db),
        patch("routers.auth.revoke_jti", return_value=True) as mock_revoke,
        patch("routers.auth.create_token", return_value="access-token"),
        patch(
            "routers.auth.create_refresh_token",
            return_value=("rotated-refresh", None),
        ),
    ):
        response = await refresh_token(
            request=mock_request,
            response=mock_response,
            body={"refresh_token": body_token},
        )

    mock_db.users.find_one.assert_awaited_once_with(
        {"id": "current-user"},
        {"_id": 0},
    )
    mock_revoke.assert_awaited_once()
    assert mock_revoke.await_args.args[0] == "current-jti"
    assert response["refresh_token"] == "rotated-refresh"
