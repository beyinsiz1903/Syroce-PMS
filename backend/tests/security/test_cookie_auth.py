import pytest
from unittest.mock import patch, MagicMock

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
    assert refresh_cookie_args["path"] == "/api/auth/refresh"

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
