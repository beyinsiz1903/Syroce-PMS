import pytest
import jwt
import time
from datetime import datetime, UTC
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from core.security import get_current_user, create_token, JWT_SECRET, JWT_ALGORITHM

@pytest.mark.asyncio
async def test_auth_watermark_lifecycle():
    user_id = "user123"
    tenant_id = "tenantABC"
    
    # Mock system db
    mock_db = AsyncMock()
    
    # a) token valid before logout
    user_doc = {
        "id": user_id,
        "tenant_id": tenant_id,
        "role": "admin",
        "email": "test@syroce.com",
        "name": "Test User",
        "is_active": True,
        "tokens_invalid_before": None
    }
    mock_db.users.find_one = AsyncMock(return_value=user_doc)
    
    token = create_token(user_id, tenant_id)
    credentials = AsyncMock()
    credentials.credentials = token
    
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db):
        user = await get_current_user(credentials=credentials)
        assert user.id == user_id

    # b) same token invalid immediately after logout
    now = int(time.time())
    
    # Token generated 2 seconds before logout (iat = now - 2)
    payload_before = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": now - 2,
        "jti": "jti_before",
        "exp": now + 3600,
        "type": "access",
    }
    token_before = jwt.encode(payload_before, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Logout occurs at `now`, setting watermark to `now + 1`
    user_doc["tokens_invalid_before"] = now + 1
    mock_db.users.find_one = AsyncMock(return_value=user_doc)
    
    credentials.credentials = token_before
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        # Under 2-second leeway: iat (now - 2) < invalid_before - 2 (now - 1) is True -> rejected!
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)
        assert exc.value.status_code == 401

    # c) newly issued token after logout is valid
    # New token generated at `now` (iat = now)
    payload_new = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": now,
        "jti": "jti_new",
        "exp": now + 3600,
        "type": "access",
    }
    token_new = jwt.encode(payload_new, JWT_SECRET, algorithm=JWT_ALGORITHM)
    credentials.credentials = token_new
    
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        # Under 2-second leeway: iat (now) < invalid_before - 2 (now - 1) is False -> accepted!
        user = await get_current_user(credentials=credentials)
        assert user.id == user_id

    # d) password reset invalidates prior token immediately
    # Password reset occurs at `now + 10`, setting watermark to `now + 11`
    user_doc["tokens_invalid_before"] = now + 11
    mock_db.users.find_one = AsyncMock(return_value=user_doc)
    
    # Prior token (iat = now) should be immediately invalid
    credentials.credentials = token_new
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)
        assert exc.value.status_code == 401

    # e) force logout invalidates prior token immediately
    # Handled by the same watermark check logic as password reset above

    # f) clock skew scenario
    # If the validating server's clock is 1 second ahead, the watermark is set to `now + 2`
    user_doc["tokens_invalid_before"] = now + 2
    mock_db.users.find_one = AsyncMock(return_value=user_doc)
    
    # Token generated on an in-sync server at `now` (iat = now)
    # Under 2-second leeway: iat (now) < invalid_before - 2 (now) is False -> accepted!
    credentials.credentials = token_new
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        user = await get_current_user(credentials=credentials)
        assert user.id == user_id
