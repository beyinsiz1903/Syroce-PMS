from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.pos_fnb import report_adapters


@pytest.mark.asyncio
async def test_fnb_dashboard_uses_canonical_current_and_previous_business_day(monkeypatch):
    calls = []
    async def snapshot(database, tenant_id, first, last, *args):
        calls.append((tenant_id, first, last))
        return {'period': {'start_date': first, 'end_date': last}, 'currency': 'TRY',
            'totals_by_currency': {}, 'financial_by_currency': {}, 'report_warnings': [], 'basis': 'posted business day',
            'revenue_rows': [], 'financial_total': 0, 'sale_count': 0, 'refund_count': 0, 'sales': []}
    monkeypatch.setattr(report_adapters, 'snapshot', snapshot)

    result = await report_adapters.report(SimpleNamespace(), 'tenant-1', 'dashboard', '2026-10-02', '2026-10-02')

    assert calls == [('tenant-1', '2026-10-02', '2026-10-02'), ('tenant-1', '2026-10-01', '2026-10-01')]
    assert result['date'] == '2026-10-02' and result['summary']['total_revenue'] == 0
