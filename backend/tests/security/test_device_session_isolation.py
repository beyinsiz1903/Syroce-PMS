from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request, Response

from core.security import JWT_ALGORITHM, JWT_SECRET, create_refresh_token, create_token, get_current_user
from models.schemas import User
from routers.auth import _build_token_response, logout


def _user(user_id="user-1", tenant_id="hotel-a"):
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email=f"{user_id}@example.com",
        name=user_id,
        role="admin",
        is_active=True,
    )


def _claims(token):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def test_each_login_gets_an_independent_device_session_family():
    first = _build_token_response(_user(), None)
    second = _build_token_response(_user(), None)

    first_access = _claims(first.access_token)
    first_refresh = _claims(first.refresh_token)
    second_access = _claims(second.access_token)
    second_refresh = _claims(second.refresh_token)

    assert first_access["sid"] == first_refresh["sid"]
    assert second_access["sid"] == second_refresh["sid"]
    assert first_access["sid"] != second_access["sid"]


def test_different_hotel_logins_cannot_share_identity_or_tenant_session():
    hotel_a = _build_token_response(_user("user-a", "hotel-a"), None)
    hotel_b = _build_token_response(_user("user-b", "hotel-b"), None)

    claims_a = _claims(hotel_a.access_token)
    claims_b = _claims(hotel_b.access_token)

    assert (claims_a["user_id"], claims_a["tenant_id"]) == ("user-a", "hotel-a")
    assert (claims_b["user_id"], claims_b["tenant_id"]) == ("user-b", "hotel-b")
    assert claims_a["sid"] != claims_b["sid"]


@pytest.mark.asyncio
async def test_logout_revokes_only_current_device_not_all_user_tokens():
    user = _user()
    current_sid = "device-session-a"
    request = Request({"type": "http", "headers": []})
    response = MagicMock(spec=Response)
    mock_db = AsyncMock()
    mock_db.audit_logs.insert_one = AsyncMock()

    with (
        patch("routers.auth.db", mock_db),
        patch("routers.auth.revoke_jti", new=AsyncMock(return_value=True)),
        patch("routers.auth.revoke_session", new=AsyncMock(return_value=True)) as revoke_family,
        patch(
            "routers.auth._decode_bearer_payload",
            return_value={"jti": "access-a", "sid": current_sid, "exp": 9_999_999_999},
        ),
    ):
        await logout(request=request, response=response, body={}, current_user=user)

    revoke_family.assert_awaited_once()
    assert revoke_family.await_args.args[0] == current_sid
    # Ordinary logout must never bump the user-wide watermark. That operation
    # would terminate every other workstation belonging to the employee.
    mock_db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoked_device_is_rejected_while_parallel_device_stays_valid():
    user_id = "user-1"
    tenant_id = "hotel-a"
    token_a = create_token(user_id, tenant_id, session_id="device-a")
    token_b = create_token(user_id, tenant_id, session_id="device-b")
    user_doc = {
        "id": user_id,
        "tenant_id": tenant_id,
        "role": "admin",
        "email": "user-1@example.com",
        "name": "User One",
        "is_active": True,
    }
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(return_value=user_doc)

    async def token_or_session_revoked(_jti, *, session_id=None):
        return session_id == "device-a"

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(side_effect=token_or_session_revoked)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
        patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda value: value),
    ):
        credentials_a = MagicMock(credentials=token_a)
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials_a)
        assert exc.value.status_code == 401

        credentials_b = MagicMock(credentials=token_b)
        authenticated = await get_current_user(credentials=credentials_b)
        assert authenticated.id == user_id
        assert authenticated.tenant_id == tenant_id


def test_refresh_rotation_can_keep_the_same_device_family():
    session_id = "device-family"
    access = create_token("user-1", "hotel-a", session_id=session_id)
    refresh, _ = create_refresh_token("user-1", "hotel-a", session_id=session_id)

    assert _claims(access)["sid"] == session_id
    assert _claims(refresh)["sid"] == session_id


@pytest.mark.asyncio
async def test_fresh_bearer_identity_wins_over_stale_cookie_during_account_switch():
    stale_cookie = create_token("old-user", "old-hotel", session_id="old-device")
    fresh_bearer = create_token("new-user", "new-hotel", session_id="new-device")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/me",
            "headers": [(b"cookie", f"access_token={stale_cookie}".encode())],
        }
    )
    credentials = MagicMock(credentials=fresh_bearer)
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(
        return_value={
            "id": "new-user",
            "tenant_id": "new-hotel",
            "role": "admin",
            "email": "new-user@example.com",
            "name": "New User",
            "is_active": True,
        }
    )

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security.is_session_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
        patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda value: value),
    ):
        authenticated = await get_current_user(request=request, credentials=credentials)

    assert authenticated.id == "new-user"
    assert authenticated.tenant_id == "new-hotel"
    queried_identity = sys_db.users.find_one.await_args.args[0]
    assert queried_identity["$or"] == [{"id": "new-user"}, {"user_id": "new-user"}]
