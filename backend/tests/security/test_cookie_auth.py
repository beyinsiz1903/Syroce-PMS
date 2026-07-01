import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from models.schemas import User

def test_login_cookie_attributes():
    from routers.auth import _build_token_response
    from fastapi import Response
    
    user = User(id="user123", tenant_id="tenantA", email="a@b.com", name="Test", role="admin", is_active=True)
    
    mock_response = MagicMock(spec=Response)
    
    result = _build_token_response(user, None, mock_response)
    
    assert mock_response.set_cookie.call_count == 2
    
    call_args_list = mock_response.set_cookie.call_args_list
    access_cookie_args = [args[1] for args in call_args_list if args[1].get("key") == "access_token"][0]
    refresh_cookie_args = [args[1] for args in call_args_list if args[1].get("key") == "refresh_token"][0]
    
    assert access_cookie_args["httponly"] is True
    assert access_cookie_args["samesite"] == "lax"
    assert access_cookie_args["path"] == "/"
    
    assert refresh_cookie_args["httponly"] is True
    assert refresh_cookie_args["samesite"] == "lax"
    assert refresh_cookie_args["path"] == "/api/auth/refresh-token"

@pytest.mark.asyncio
async def test_logout_clears_cookies():
    from routers.auth import logout
    from fastapi import Request, Response
    from models.schemas import User
    from unittest.mock import AsyncMock
    
    request = Request({"type": "http", "headers": []})
    mock_response = MagicMock(spec=Response)
    user = User(id="user123", tenant_id="tenantA", email="a@b.com", name="Test", role="admin", is_active=True)
    
    mock_db = AsyncMock()
    
    with patch("routers.auth.revoke_jti", new_callable=AsyncMock), \
         patch("routers.auth.db", mock_db), \
         patch("routers.auth._decode_bearer_payload", return_value={"jti": "foo", "exp": 9999999999}):
         
        try:
            await logout(request=request, response=mock_response, body={}, current_user=user)
        except Exception:
            pass # We don't care if it errors after setting cookies. We just want to check cookies.
            
    # delete_cookie is called twice (access_token, refresh_token)
    assert mock_response.delete_cookie.call_count == 2
    
    call_args_list = mock_response.delete_cookie.call_args_list
    
    # check access_token
    access_cookie = [args[0][0] for args in call_args_list if args[0][0] == "access_token"]
    assert len(access_cookie) == 1
    
    # check refresh_token
    refresh_cookie = [args[0][0] for args in call_args_list if args[0][0] == "refresh_token"]
    assert len(refresh_cookie) == 1


@pytest.mark.asyncio
async def test_refresh_token_sets_tenant_context():
    from routers.auth import refresh_token
    from fastapi import Request, Response
    import jwt
    from core.security import JWT_SECRET, JWT_ALGORITHM
    from core.tenant_db import get_current_tenant_id
    
    # Create a mock refresh token payload
    payload = {
        "type": "refresh",
        "user_id": "user123",
        "tenant_id": "tenantABC",
        "jti": "jti123",
        "exp": 9999999999
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Mock request cookies
    mock_request = MagicMock(spec=Request)
    mock_request.cookies = {"refresh_token": token}
    mock_response = MagicMock(spec=Response)
    
    mock_db = AsyncMock()
    
    async def mock_find_one(*args, **kwargs):
        # Assert tenant context is set during the database lookup
        assert get_current_tenant_id() == "tenantABC"
        return {"id": "user123", "tenant_id": "tenantABC", "is_active": True}
        
    mock_db.users.find_one = AsyncMock(side_effect=mock_find_one)
    mock_db.audit_logs.insert_one = AsyncMock()
    
    with patch("routers.auth.db", mock_db), \
         patch("routers.auth.revoke_jti", return_value=True), \
         patch("routers.auth.create_token", return_value="access_token_val"), \
         patch("routers.auth.create_refresh_token", return_value=("refresh_token_val", None)):
         
        resp = await refresh_token(request=mock_request, response=mock_response, body={})
        
        # Verify that db.users.find_one was called
        assert mock_db.users.find_one.call_count == 1
        # Check that response was successfully generated
        assert resp["access_token"] == "access_token_val"
        assert resp["refresh_token"] == "refresh_token_val"
        
        # Assert tenant context is cleared after the request finishes
        assert get_current_tenant_id() is None

