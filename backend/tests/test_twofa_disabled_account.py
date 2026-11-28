"""Reject disabled accounts before redeeming an in-flight 2FA challenge."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from core.security import JWT_ALGORITHM, JWT_SECRET
from routers import auth


@pytest.mark.asyncio
async def test_account_disabled_after_password_step_cannot_redeem_challenge(monkeypatch):
    now = datetime.now(UTC)
    token = jwt.encode({'purpose': '2fa_challenge', 'user_id': 'fixture-user', 'jti': 'fixture-challenge',
                        'iat': now, 'exp': now + timedelta(minutes=5)}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    consumed = SimpleNamespace(insert_one=AsyncMock())
    users = SimpleNamespace(find_one=AsyncMock(return_value={'id': 'fixture-user', 'tenant_id': 'fixture-tenant',
                                                           'two_factor_enabled': True, 'is_active': False}))
    audit = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(auth, 'db', SimpleNamespace(consumed_jtis=consumed, users=users, audit_logs=audit))
    monkeypatch.setattr(auth, '_ensure_consumed_jti_index', AsyncMock())
    decrypt = Mock(side_effect=AssertionError('Disabled account reached secret verification'))
    monkeypatch.setattr(auth, 'decrypt_user_doc', decrypt)
    request = Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 12345)})
    with pytest.raises(HTTPException) as error:
        await auth.verify_2fa_login(auth.TwoFAVerifyIn(challenge_token=token, code='123456'), request, Response())
    assert error.value.status_code == 401
    decrypt.assert_not_called()
    consumed.insert_one.assert_awaited_once()
    audit.insert_one.assert_awaited_once()
    assert audit.insert_one.call_args.args[0]['details'] == 'account_disabled'


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['expired', 'wrong-purpose', 'missing-jti', 'invalid-signature'])
async def test_invalid_challenge_rejected_before_database_or_secret_access(monkeypatch, case):
    now = datetime.now(UTC)
    claims = {'purpose': '2fa_challenge', 'user_id': 'fixture-user', 'jti': 'fixture-challenge',
              'iat': now, 'exp': now + timedelta(minutes=5)}
    if case == 'expired':
        claims['exp'] = now - timedelta(minutes=1)
    elif case == 'wrong-purpose':
        claims['purpose'] = 'access'
    elif case == 'missing-jti':
        del claims['jti']
    key = 'untrusted-local-fixture-signing-key' if case == 'invalid-signature' else JWT_SECRET
    token = jwt.encode(claims, key, algorithm=JWT_ALGORITHM)
    index = AsyncMock(side_effect=AssertionError('Invalid challenge reached database'))
    monkeypatch.setattr(auth, '_ensure_consumed_jti_index', index)
    request = Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 12345)})
    with pytest.raises(HTTPException) as error:
        await auth.verify_2fa_login(auth.TwoFAVerifyIn(challenge_token=token, code='123456'), request, Response())
    assert error.value.status_code == 401
    index.assert_not_awaited()
