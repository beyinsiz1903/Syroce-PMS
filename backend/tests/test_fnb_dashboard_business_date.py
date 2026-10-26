from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.pos_fnb import report_adapters
from domains.pms.pos_fnb_router import fnb_reports


@pytest.mark.asyncio
async def test_fnb_dashboard_defaults_to_open_business_day(monkeypatch):
    database = SimpleNamespace()
    monkeypatch.setattr(fnb_reports, 'db', database)
    monkeypatch.setattr(fnb_reports, 'get_current_user', AsyncMock(return_value=SimpleNamespace(tenant_id='tenant-1')))
    day = AsyncMock(return_value={'business_date': '2026-10-02'})
    monkeypatch.setattr(fnb_reports, 'ensure_business_date_initialized', day)
    build = AsyncMock(return_value={'date': '2026-10-02'})
    monkeypatch.setattr(report_adapters, 'report', build)

    result = await fnb_reports.get_fnb_dashboard(credentials=None)

    assert result['date'] == '2026-10-02'
    day.assert_awaited_once_with(database, 'tenant-1')
    build.assert_awaited_once_with(database, 'tenant-1', 'dashboard', '2026-10-02', '2026-10-02', days=1)
