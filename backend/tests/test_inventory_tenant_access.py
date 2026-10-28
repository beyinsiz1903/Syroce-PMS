"""HTTP-only inventory access tests; fake data/services, no provider or DB IO."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from core import room_type_inventory_service as service
from core.security import get_current_user
from routers import inventory

READ_PATHS = ['/api/inventory/room-types', '/api/inventory/room-types/summary',
    '/api/inventory/room-types/health']
ALL_PATHS = [*READ_PATHS, '/api/inventory/room-types/reconcile']


@pytest.fixture
def access(monkeypatch):
    state = SimpleNamespace(tenant='tenant-a', role='admin', grants=[])
    get_rows = AsyncMock(side_effect=lambda tenant, day, room_type: [{
        'tenant_id': tenant, 'date': day, 'room_type': room_type or 'Standard',
        'physical_total': 8, 'sellable': 7, 'locked_booking': 1}])
    get_summary = AsyncMock(side_effect=lambda tenant, start, end: {
        'tenant_id': tenant, 'start_date': start, 'end_date': end, 'room_types': []})
    reconcile = AsyncMock(return_value={
        'dates_processed': 2, 'types_processed': 1, 'drift_detected': False, 'drifts': []})
    count = AsyncMock(return_value=1)
    latest = AsyncMock(return_value={'last_computed_at': datetime.now(UTC).isoformat()})
    fallback = AsyncMock(return_value={'id': 'unrelated-first-tenant', 'tenant_id': 'unrelated-first-tenant'})
    monkeypatch.setattr(service, 'get_room_type_inventory', get_rows)
    monkeypatch.setattr(service, 'get_inventory_summary', get_summary)
    monkeypatch.setattr(service, 'reconcile_date_range', reconcile)
    monkeypatch.setattr(inventory, 'db', SimpleNamespace(
        room_type_inventory=SimpleNamespace(count_documents=count, find_one=latest),
        organizations=SimpleNamespace(find_one=fallback), rooms=SimpleNamespace(find_one=fallback)))

    async def identity(authorization: str | None = Header(default=None)):
        if authorization != 'Bearer inventory-unit-fixture':
            raise HTTPException(401, 'Authentication required')
        return SimpleNamespace(id='unit-user', tenant_id=state.tenant, role=state.role,
            roles=[], granted_permissions=state.grants)

    app = FastAPI()
    app.include_router(inventory.router)
    app.dependency_overrides[get_current_user] = identity
    mocks = (get_rows, get_summary, reconcile, count, latest, fallback)
    with TestClient(app, headers={'Authorization': 'Bearer inventory-unit-fixture'}) as client:
        yield SimpleNamespace(client=client, app=app, state=state, mocks=mocks,
            get_rows=get_rows, get_summary=get_summary, reconcile=reconcile,
            count=count, latest=latest, fallback=fallback)


def request(access, path, params=None, **kwargs):
    method = access.client.post if path.endswith('/reconcile') else access.client.get
    return method(path, params=params or {}, **kwargs)


def no_data_access(access):
    for mock in access.mocks:
        mock.assert_not_called()


@pytest.mark.parametrize('path', ALL_PATHS)
def test_anonymous_inventory_requests_never_reach_data(access, path):
    response = request(access, path, {'tenant_id': 'tenant-a'}, headers={'Authorization': ''})
    assert response.status_code == 401
    no_data_access(access)


@pytest.mark.parametrize('path', ALL_PATHS)
@pytest.mark.parametrize('role', ['admin', 'super_admin'])
def test_reject_cross_tenant_even_for_privileged_roles(access, path, role):
    access.state.role = role
    response = request(access, path, {'tenant_id': 'tenant-b'})
    assert response.status_code == 403
    no_data_access(access)


@pytest.mark.parametrize('path', ALL_PATHS)
@pytest.mark.parametrize('tenant', ['', '   ', 'x' * 129])
def test_invalid_explicit_tenant_never_falls_back(access, path, tenant):
    assert request(access, path, {'tenant_id': tenant}).status_code == 422
    no_data_access(access)


@pytest.mark.parametrize('path', ALL_PATHS)
@pytest.mark.parametrize('tenant', ['', None, '   '])
def test_identity_without_tenant_fails_closed(access, path, tenant):
    access.state.tenant = tenant
    assert request(access, path).status_code == 403
    no_data_access(access)


@pytest.mark.parametrize('path', ALL_PATHS)
@pytest.mark.parametrize('explicit_tenant', [False, True])
def test_own_tenant_is_default_and_optional_legacy_parameter(access, path, explicit_tenant):
    params = {'tenant_id': 'tenant-a'} if explicit_tenant else {}
    params.update({'date': '2026-11-10', 'start_date': '2026-11-10', 'end_date': '2026-11-11'})
    response = request(access, path, params)
    assert response.status_code == 200
    data = response.json()
    assert data['tenant_id'] == 'tenant-a'
    access.fallback.assert_not_called()
    if path.endswith('/summary'):
        access.get_summary.assert_awaited_once_with('tenant-a', '2026-11-10', '2026-11-11')
    elif path.endswith('/reconcile'):
        access.reconcile.assert_awaited_once_with('tenant-a', '2026-11-10', '2026-11-11')
    elif path.endswith('/health'):
        assert access.count.call_args.args[0]['tenant_id'] == 'tenant-a'
        assert access.latest.call_args.args[0] == {'tenant_id': 'tenant-a'}
    else:
        access.get_rows.assert_awaited_once_with('tenant-a', '2026-11-10', None)
        assert data['totals']['physical'] == 8 and data['totals']['sellable'] == 7


@pytest.mark.parametrize('path', READ_PATHS)
@pytest.mark.parametrize('role', ['front_desk', 'housekeeping', 'sales', 'finance', 'staff', 'call_center_agent'])
def test_booking_read_roles_retain_own_inventory_access(access, path, role):
    access.state.role = role
    assert request(access, path).status_code == 200


@pytest.mark.parametrize('path', READ_PATHS)
@pytest.mark.parametrize('role', ['guest', 'agency_agent', 'procurement'])
def test_non_booking_roles_cannot_read_internal_inventory(access, path, role):
    access.state.role = role
    assert request(access, path).status_code == 403
    no_data_access(access)


def test_explicit_booking_read_grant_does_not_grant_reconciliation(access):
    access.state.role = 'procurement'
    access.state.grants = ['view_bookings']
    assert request(access, READ_PATHS[0]).status_code == 200
    access.get_rows.reset_mock()
    assert request(access, ALL_PATHS[-1]).status_code == 403
    no_data_access(access)


@pytest.mark.parametrize('role', ['front_desk', 'housekeeping', 'sales', 'finance', 'staff'])
def test_existing_reconciliation_admin_guard_is_preserved(access, role):
    access.state.role = role
    assert request(access, ALL_PATHS[-1]).status_code == 403
    no_data_access(access)


def test_real_auth_dependency_rejects_missing_credentials_before_inventory(access):
    access.app.dependency_overrides.clear()
    response = request(access, READ_PATHS[0], {'tenant_id': 'tenant-a'}, headers={'Authorization': ''})
    assert response.status_code == 401
    no_data_access(access)


@pytest.mark.parametrize('path', READ_PATHS)
def test_read_does_not_trigger_reconciliation(access, path):
    assert request(access, path, {'tenant_id': 'tenant-a'}).status_code == 200
    access.reconcile.assert_not_awaited()
