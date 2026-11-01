"""Read-only run-history query and actual FastAPI contract. No live services."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from core import night_audit_hardened as engine
from core.security import get_current_user
from domains.pms.night_audit.router import router


@pytest.mark.asyncio
@pytest.mark.parametrize('start,end,status,expected', [
    ('2026-10-25', '2026-10-26', 'completed', {'status': 'completed', 'business_date': {'$gte': '2026-10-25', '$lte': '2026-10-26'}}),
    ('2026-10-25', None, None, {'business_date': {'$gte': '2026-10-25'}}),
    (None, '2026-10-26', 'rerun_superseded', {'status': 'rerun_superseded', 'business_date': {'$lte': '2026-10-26'}}),
    (None, None, None, {}),
])
async def test_run_query_uses_same_tenant_day_status_for_rows_and_total(monkeypatch, start, end, status, expected):
    rows = [{'id': 'test-run', 'business_date': '2026-10-25'}]
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=rows)
    collection = SimpleNamespace(find=MagicMock(return_value=cursor), count_documents=AsyncMock(return_value=21))
    monkeypatch.setattr(engine, 'db', SimpleNamespace(night_audit_runs=collection))
    value = await engine.get_runs('test-tenant', 20, 20, status, start, end)
    query = {'tenant_id': 'test-tenant', **expected}
    collection.find.assert_called_once_with(query, {'_id': 0, 'lock_token': 0})
    collection.count_documents.assert_awaited_once_with(query)
    cursor.sort.assert_called_once_with([('started_at', -1), ('id', -1)])
    cursor.skip.assert_called_once_with(20)
    cursor.limit.assert_called_once_with(20)
    assert value == {'runs': rows, 'total': 21, 'limit': 20, 'skip': 20}


def make_app(role='admin'):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id='test-user', tenant_id='test-tenant', role=role, email='test@example.invalid',
        is_super_admin=False, granted_permissions=[],
    )
    return app


@pytest.mark.asyncio
async def test_actual_http_run_contract_forwards_validated_filters(monkeypatch):
    query = AsyncMock(return_value={'runs': [], 'total': 0, 'limit': 20, 'skip': 20})
    monkeypatch.setattr(engine, 'get_runs', query)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app()), base_url='http://local-test') as client:
        response = await client.get('/api/night-audit/runs', params={'limit': 20, 'skip': 20, 'status': 'rerun_superseded', 'start_date': '2026-10-25', 'end_date': '2026-10-26'})
    assert response.status_code == 200
    assert response.json()['runs'] == []
    query.assert_awaited_once_with('test-tenant', 20, 20, 'rerun_superseded', '2026-10-25', '2026-10-26')


@pytest.mark.asyncio
@pytest.mark.parametrize('params,code', [
    ({'start_date': '2026-11-02', 'end_date': '2026-11-01'}, 400),
    ({'start_date': '2026-02-30'}, 422),
    ({'end_date': 'not-a-date'}, 422),
    ({'limit': 101}, 422),
    ({'skip': -1}, 422),
])
async def test_invalid_history_query_is_not_disguised_as_empty(monkeypatch, params, code):
    query = AsyncMock()
    monkeypatch.setattr(engine, 'get_runs', query)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app()), base_url='http://local-test') as client:
        response = await client.get('/api/night-audit/runs', params=params)
    assert response.status_code == code
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_finance_permission_is_not_weakened(monkeypatch):
    query = AsyncMock()
    monkeypatch.setattr(engine, 'get_runs', query)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app('housekeeping')), base_url='http://local-test') as client:
        response = await client.get('/api/night-audit/runs')
    assert response.status_code == 403
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_requires_authentication(monkeypatch):
    query = AsyncMock()
    monkeypatch.setattr(engine, 'get_runs', query)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-test') as client:
        response = await client.get('/api/night-audit/runs')
    assert response.status_code in {401, 403}
    query.assert_not_awaited()
