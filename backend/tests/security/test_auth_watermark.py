import time
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException

from core.security import JWT_ALGORITHM, JWT_SECRET, create_token, get_current_user


@pytest.mark.asyncio
async def test_auth_watermark_lifecycle():
    user_id = "user123"
    tenant_id = "tenantABC"

    # Mock system db
    mock_db = AsyncMock()

    # 1. Old token valid before logout
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

    # 2. Same token rejected on the first request after logout (no global grace window!)
    now = time.time() - 100

    # Token generated before logout (iat = now - 0.05)
    payload_before = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": now - 0.05,
        "jti": "jti_before",
        "exp": now + 3600,
        "type": "access",
    }
    token_before = jwt.encode(payload_before, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Logout occurs at `now`, setting watermark to exactly `now` (no extra padding or leeway!)
    user_doc["tokens_invalid_before"] = now
    mock_db.users.find_one = AsyncMock(return_value=user_doc)

    credentials.credentials = token_before
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        # With zero leeway, old token (now - 0.05) < invalid_before (now) evaluates to True -> strictly rejected!
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)
        assert exc.value.status_code == 401

    # 3. Newly issued token in the same second accepted
    # New token generated at `now + 0.05`
    payload_new = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": now + 0.05,
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
        # New token (now + 0.05) < invalid_before (now) evaluates to False -> accepted!
        user = await get_current_user(credentials=credentials)
        assert user.id == user_id

    # 4. Password reset rejects all earlier tokens immediately
    # Password reset occurs at `now + 10`
    user_doc["tokens_invalid_before"] = now + 10
    mock_db.users.find_one = AsyncMock(return_value=user_doc)

    # Token issued before password reset (now + 0.05) must be rejected immediately on first request
    credentials.credentials = token_new
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)
        assert exc.value.status_code == 401

    # 5. Force logout rejects all earlier tokens immediately
    # Force logout occurs at `now + 20`
    user_doc["tokens_invalid_before"] = now + 20
    mock_db.users.find_one = AsyncMock(return_value=user_doc)

    credentials.credentials = token_new
    with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
         patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
         patch("core.tenant_db.get_system_db", return_value=mock_db), \
         patch("core.security._user_doc_cache_get", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)
        assert exc.value.status_code == 401

    # 6. Malformed iat tests (missing, null, bad string, NaN, Infinity)
    bad_payloads = [
        {"user_id": user_id, "tenant_id": tenant_id, "jti": "jti1", "exp": now + 3600},  # missing iat
        {"user_id": user_id, "tenant_id": tenant_id, "iat": None, "jti": "jti2", "exp": now + 3600},  # None iat
        {"user_id": user_id, "tenant_id": tenant_id, "iat": "invalid_str", "jti": "jti3", "exp": now + 3600},  # bad string
        {"user_id": user_id, "tenant_id": tenant_id, "iat": float("nan"), "jti": "jti4", "exp": now + 3600},  # NaN iat
        {"user_id": user_id, "tenant_id": tenant_id, "iat": float("inf"), "jti": "jti5", "exp": now + 3600},  # Inf iat
    ]

    for bp in bad_payloads:
        bad_token = jwt.encode(bp, JWT_SECRET, algorithm=JWT_ALGORITHM)
        credentials.credentials = bad_token
        with patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)), \
             patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda x: x), \
             patch("core.tenant_db.get_system_db", return_value=mock_db), \
             patch("core.security._user_doc_cache_get", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await get_current_user(credentials=credentials)
            assert exc.value.status_code == 401
