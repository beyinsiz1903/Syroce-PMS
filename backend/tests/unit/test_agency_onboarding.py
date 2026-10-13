import asyncio
import importlib
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import agency_onboarding as onboarding


def matches(row, query):
    for key, value in query.items():
        if key == '$or':
            if not any(matches(row, part) for part in value):
                return False
        elif isinstance(value, dict):
            for op, expected in value.items():
                actual = row.get(key)
                if op == '$exists' and (key in row) != expected:
                    return False
                if op == '$gt' and (actual is None or actual <= expected):
                    return False
                if op == '$gte' and (actual is None or actual < expected):
                    return False
                if op == '$lte' and (actual is None or actual > expected):
                    return False
        elif row.get(key) != value:
            return False
    return True


class Collection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))

    async def find_one(self, query, *args):
        return deepcopy(next((row for row in self.rows if matches(row, query)), None))

    def find(self, query, *args):
        return SimpleNamespace(to_list=AsyncMock(return_value=deepcopy([row for row in self.rows if matches(row, query)])))

    async def count_documents(self, query):
        return len([row for row in self.rows if matches(row, query)])

    async def insert_one(self, doc):
        self.rows.append(deepcopy(doc))

    async def update_one(self, query, update):
        for row in self.rows:
            if matches(row, query):
                row.update(update.get('$set', {}))
                for key in update.get('$unset', {}):
                    row.pop(key, None)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


@pytest.fixture
def setup(monkeypatch):
    import core.email
    security = importlib.import_module('core.security')
    database = SimpleNamespace(users=Collection(), marketplace_agencies=Collection([{'id': 'a', 'name': 'Agency', 'status': 'active'}]),
                               marketplace_audit_logs=Collection(), agency_contracts=Collection())
    monkeypatch.setattr(onboarding, 'get_system_db', lambda: database)
    monkeypatch.setattr(onboarding, 'encrypt_user_doc', lambda doc: doc)
    monkeypatch.setattr(onboarding, 'decrypt_user_doc', lambda doc: doc)
    monkeypatch.setattr(onboarding, 'build_user_email_query', lambda email: {'email': email})
    monkeypatch.setattr(security, '_is_super_admin', lambda user: user.role == 'super_admin')
    mail = AsyncMock(return_value={'sent': True})
    monkeypatch.setattr(core.email, 'send_email', mail)
    monkeypatch.setattr(core.email, '_frontend_base_url', lambda: 'https://example.com')
    return database, mail, SimpleNamespace(id='admin', role='super_admin', is_impersonating=False)


async def issue(setup):
    database, mail, admin = setup
    result = await onboarding.invite('a', onboarding.InviteRequest(name='Agent Name', email='agent@example.com'), admin)
    token = re.search(r'#token=([^"<]+)', mail.call_args.args[2]).group(1)
    return result, token


@pytest.mark.asyncio
async def test_invite_activation_replay_and_scope(setup):
    from core.security import verify_password
    database, mail, admin = setup
    result, token = await issue(setup)
    user = database.users.rows[0]
    assert result['email_sent'] and token not in str(result)
    assert token not in str(user) and user['agency_invite_hash'] == onboarding.digest(token)
    assert not user['is_active'] and user['tenant_id'] is None and user['role'] == 'marketplace_agent'
    data = onboarding.AcceptRequest(token=token, password='SecureAgency2026!')
    assert (await onboarding.accept(data))['ok']
    assert user['is_active'] and user['email_verified']
    assert verify_password(data.password, user['hashed_password'])
    assert 'agency_invite_hash' not in user
    with pytest.raises(HTTPException) as error:
        await onboarding.accept(data)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_accept_only_one_wins(setup):
    _, token = await issue(setup)
    data = onboarding.AcceptRequest(token=token, password='SecureAgency2026!')
    results = await asyncio.gather(onboarding.accept(data), onboarding.accept(data), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1


@pytest.mark.asyncio
async def test_resend_invalidates_old_token_and_throttles(setup):
    database, _, admin = setup
    _, old = await issue(setup)
    with pytest.raises(HTTPException) as error:
        await issue(setup)
    assert error.value.status_code == 409
    database.users.rows[0]['agency_invite_sent_at'] -= timedelta(minutes=2)
    _, new = await issue(setup)
    assert new != old and len(database.users.rows) == 1
    with pytest.raises(HTTPException):
        await onboarding.accept(onboarding.AcceptRequest(token=old, password='SecureAgency2026!'))


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['expired', 'agency_disabled', 'weak_password'])
async def test_invalid_activation_does_not_change_account(setup, change):
    database, _, _ = setup
    _, token = await issue(setup)
    if change == 'expired':
        database.users.rows[0]['agency_invite_expires'] = datetime.now(UTC) - timedelta(seconds=1)
    if change == 'agency_disabled':
        database.marketplace_agencies.rows[0]['status'] = 'inactive'
    with pytest.raises(HTTPException):
        await onboarding.accept(onboarding.AcceptRequest(token=token, password='alllowercasepassword' if change == 'weak_password' else 'SecureAgency2026!'))
    assert database.users.rows[0]['is_active'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('existing', [
    {'role': 'hotel_admin', 'agency_id': 'a'},
    {'role': 'marketplace_agent', 'agency_id': 'other', 'onboarding_status': 'invited'},
    {'role': 'marketplace_agent', 'agency_id': 'a', 'onboarding_status': 'active'},
])
async def test_never_repurpose_existing_account(setup, existing):
    database, mail, _ = setup
    database.users.rows.append({'email': 'agent@example.com', **existing})
    before = deepcopy(database.users.rows)
    with pytest.raises(HTTPException) as error:
        await issue(setup)
    assert error.value.status_code == 409 and database.users.rows == before
    mail.assert_not_called()


@pytest.mark.asyncio
async def test_delivery_failure_and_authorization(setup):
    database, mail, admin = setup
    mail.return_value = {'sent': False}
    result, _ = await issue(setup)
    assert not result['email_sent'] and database.users.rows[0]['agency_invite_delivery'] == 'failed'
    for user in [SimpleNamespace(role='hotel_admin'), SimpleNamespace(role='super_admin', is_impersonating=True)]:
        with pytest.raises(HTTPException) as error:
            await onboarding.invite('a', onboarding.InviteRequest(name='Agent', email='other@example.com'), user)
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_readiness_all_steps_and_fail_closed(setup, monkeypatch):
    from routers import marketplace_b2b
    database, _, admin = setup
    ci = datetime.now(UTC).date() + timedelta(days=1)
    co = ci + timedelta(days=2)
    database.users.rows.append({'id': 'u', 'agency_id': 'a', 'role': 'marketplace_agent', 'is_active': True})
    database.agency_contracts.rows.append({'agency_id': 'a', 'status': 'approved', 'valid_from': ci.isoformat(), 'valid_to': co.isoformat()})
    search = AsyncMock(return_value={'results': [{'tenant_id': 't', 'hotel_name': 'Hotel', 'available_room_types': [
        {'room_type': 'standard', 'total_price': 100, 'available_rooms': 1, 'currency': 'TRY'}]}]})
    monkeypatch.setattr(marketplace_b2b, 'agency_search', search)
    verify = AsyncMock(return_value=True)
    monkeypatch.setattr(onboarding, 'verified_offer', verify)
    assert (await onboarding.readiness('a', ci, co, admin))['ready']
    verify.return_value = False
    assert not (await onboarding.readiness('a', ci, co, admin))['ready']
    verify.return_value = True
    database.users.rows[0]['is_active'] = False
    assert not (await onboarding.readiness('a', ci, co, admin))['ready']
    database.users.rows[0]['is_active'] = True
    search.side_effect = RuntimeError('provider unavailable')
    result = await onboarding.readiness('a', ci, co, admin)
    assert not result['ready'] and result['check_error']
    database.agency_contracts.rows[0]['status'] = 'pending'
    assert not (await onboarding.readiness('a', ci, co, admin))['checks']['contract_approved']


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['valid', 'missing_night', 'duplicate_plan', 'zero_rate', 'zero_stock', 'min_stay', 'stop_sell', 'wrong_room', 'inactive_hotel'])
async def test_readiness_requires_explicit_unambiguous_shared_inventory(monkeypatch, case):
    from routers import agency_contracts, marketplace_b2b
    ci = datetime.now(UTC).date() + timedelta(days=1)
    co = ci + timedelta(days=2)
    rows = [{'date': (ci + timedelta(days=i)).isoformat(), 'rate': 100, 'availability': 2,
             'tenant_id': 't', 'agency_id': 'a', 'room_type_code': 'standard'} for i in range(2)]
    contract = {'allowed_room_types': ['other'] if case == 'wrong_room' else ['standard']}
    if case == 'missing_night':
        rows.pop()
    if case == 'duplicate_plan':
        rows.append(deepcopy(rows[0]))
    for label, field, value in [('zero_rate', 'rate', 0), ('zero_stock', 'availability', 0),
                                ('min_stay', 'min_stay', 3), ('stop_sell', 'stop_sell', True)]:
        if case == label:
            rows[0][field] = value
    monkeypatch.setattr(marketplace_b2b, 'db', SimpleNamespace(agency_rate_calendar=Collection(rows)))
    listing = AsyncMock(return_value={})
    if case == 'inactive_hotel':
        listing.side_effect = HTTPException(404, 'closed')
    monkeypatch.setattr(marketplace_b2b, '_get_listing_or_404', listing)
    monkeypatch.setattr(agency_contracts, 'has_active_contract', AsyncMock(return_value=contract))
    assert await onboarding.verified_offer('a', 't', 'standard', ci, co) is (case == 'valid')


@pytest.mark.asyncio
async def test_sensitive_email_does_not_log_invitation(monkeypatch, caplog):
    from core.email import send_email
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.setenv('MAIL_PROVIDER', 'resend')
    result = await send_email('agent@example.com', 'Activation', '<a>secret-activation-token</a>', sensitive=True)
    assert not result['sent']
    assert 'secret-activation-token' not in caplog.text


@pytest.mark.asyncio
async def test_marketplace_login_uses_encrypted_email_lookup(monkeypatch):
    from starlette.requests import Request

    from core.security import hash_password
    from routers import marketplace_b2b
    from security import encrypted_lookup
    user = {'id': 'u', 'agency_id': 'a', 'email': 'encrypted', 'role': 'marketplace_agent',
            'is_active': True, 'hashed_password': hash_password('SecureAgency2026!')}
    users = SimpleNamespace(find_one=AsyncMock(return_value=user))
    monkeypatch.setattr(marketplace_b2b, 'get_system_db', lambda: SimpleNamespace(
        users=users, marketplace_agencies=Collection([{'id': 'a', 'status': 'active'}]),
        marketplace_login_attempts=SimpleNamespace(count_documents=AsyncMock(return_value=0), delete_many=AsyncMock())))
    monkeypatch.setattr(encrypted_lookup, 'build_user_email_query', lambda email: {'_hash_email': 'blind-index'})
    monkeypatch.setattr(encrypted_lookup, 'decrypt_user_doc', lambda doc: {**doc, 'email': 'agent@example.com'})
    result = await marketplace_b2b.marketplace_extranet_login(
        marketplace_b2b.MarketplaceLoginRequest(email='Agent@example.com', password='SecureAgency2026!'),
        Request({'type': 'http', 'client': ('127.0.0.1', 1)}))
    users.find_one.assert_awaited_once_with({'_hash_email': 'blind-index'})
    assert result['token'] and result['user']['email'] == 'agent@example.com'


@pytest.mark.asyncio
async def test_public_accept_route_and_admin_auth_contract(setup):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from core.security import get_current_user
    _, token = await issue(setup)
    app = FastAPI()
    app.include_router(onboarding.router)

    async def denied():
        raise HTTPException(401, 'login required')
    app.dependency_overrides[get_current_user] = denied
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post('/api/marketplace/v1/admin/agencies/a/invitations', json={'name': 'Agent', 'email': 'agent@example.com'})).status_code == 401
        response = await client.post('/api/marketplace/v1/extranet/invitations/accept', json={'token': token, 'password': 'SecureAgency2026!'})
        assert response.status_code == 200 and response.json()['ok']
