from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import night_audit_hardened as engine
from modules.pms_core import operational_snapshot_service


@pytest.mark.asyncio
@pytest.mark.parametrize('instant,expected,drift', [
    ('2026-10-31T20:59:59+00:00', '2026-10-31', 0),
    ('2026-10-31T21:00:00+00:00', '2026-11-01', 1),
])
async def test_preview_calendar_matches_turkiye_run_guard_without_shifting_business_day(monkeypatch, instant, expected, drift):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.count_documents = AsyncMock(return_value=0)
    settings = SimpleNamespace(find_one=AsyncMock(return_value={'business_date': '2026-10-31'}))
    database = SimpleNamespace(tenant_settings=settings, night_audit_runs=col, bookings=col, housekeeping_tasks=col, pos_orders=col)
    monkeypatch.setattr(engine, 'db', database)
    monkeypatch.setattr(engine, '_now', lambda: datetime.fromisoformat(instant).astimezone(UTC))
    monkeypatch.setattr(engine, '_load_bookings_for_date_check', AsyncMock(return_value=[]))
    monkeypatch.setattr(engine, 'load_mapping_issues', AsyncMock(return_value=[]))
    monkeypatch.setattr(operational_snapshot_service, 'build_operational_snapshot', AsyncMock(return_value={
        'room_status': {}, 'total_rooms': 1, 'occupied_rooms': 0, 'in_house_stays': 0, 'today_checkins': 0, 'today_checkouts': 0}))
    result = await engine.build_audit_preview.__wrapped__('qa-clock')
    assert result['business_date'] == '2026-10-31'
    assert result['calendar_date'] == expected
    assert result['date_drift_days'] == drift
