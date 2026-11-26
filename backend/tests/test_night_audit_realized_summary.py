"""Actual history query, fake collection: no live database operations."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.context import OperationContext
from domains.pms.night_audit.service import NightAuditCoreService


@pytest.mark.asyncio
@pytest.mark.parametrize('completed_only', [False, True])
async def test_history_summary_filter_scopes_rows_and_count_to_same_tenant(completed_only):
    class Cursor:
        def sort(self, *args):
            return self
        def skip(self, count):
            assert count == 0
            return self
        def limit(self, count):
            assert count == 1
            return self
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise StopAsyncIteration

    collection = SimpleNamespace(find=MagicMock(return_value=Cursor()), count_documents=AsyncMock(return_value=0))
    service = NightAuditCoreService.__new__(NightAuditCoreService)
    service._db = SimpleNamespace(night_audit_runs=collection)
    result = await service.get_audit_history(OperationContext(tenant_id='synthetic-hotel', actor_id='local'), 1, 0, completed_only=completed_only)
    expected = {'tenant_id': 'synthetic-hotel'}
    if completed_only:
        expected.update({'status': {'$in': ['completed', 'completed_with_exceptions']},
                         'dry_run': {'$ne': True}, 'is_dry_run': {'$ne': True}})
    collection.find.assert_called_once_with(expected, {'_id': 0})
    collection.count_documents.assert_awaited_once_with(expected)
    assert result.data == {'runs': [], 'total': 0, 'limit': 1, 'skip': 0}


@pytest.mark.asyncio
async def test_history_http_passes_completed_filter_without_changing_access_scope(monkeypatch):
    import httpx
    from fastapi import FastAPI

    from common.result import ServiceResult
    from core.security import get_current_user
    from domains.pms.night_audit.router import router
    from domains.pms.night_audit.service import night_audit_core_service

    query = AsyncMock(return_value=ServiceResult.success({'runs': [], 'total': 0}))
    monkeypatch.setattr(night_audit_core_service, 'get_audit_history', query)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id='local-user', tenant_id='synthetic-hotel', role='admin', email='local@example.invalid',
        is_super_admin=False, granted_permissions=[],
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-test') as client:
        response = await client.get('/api/night-audit/history', params={'limit': 1, 'completed_only': True, 'nocache': 1})
    assert response.status_code == 200
    args, kwargs = query.await_args
    assert args[0].tenant_id == 'synthetic-hotel'
    assert args[1:] == (1, 0)
    assert kwargs == {'completed_only': True}
