from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.pos_extensions import pos_shift_close as shifts


@pytest.mark.asyncio
async def test_open_shift_preserves_verified_business_day_separate_from_event_time(monkeypatch):
    database = SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={'business_date': '2026-11-13'})),
        hotel_settings=SimpleNamespace(find_one=AsyncMock(return_value={'currency': 'TRY'})),
        pos_shifts=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(shifts, 'db', database)
    monkeypatch.setattr(shifts, '_ensure_shift_indexes', AsyncMock())
    monkeypatch.setattr(shifts, '_now', lambda: '2026-11-27T00:00:00Z')
    result = await shifts.open_shift(shifts.ShiftOpen(outlet_id='outlet', opening_cash=0), SimpleNamespace(id='operator', tenant_id='tenant'))
    assert result['shift']['business_date'] == '2026-11-13'
    assert result['shift']['opened_at'] == '2026-11-27T00:00:00Z'
    assert database.tenant_settings.find_one.await_args.args[0] == {'tenant_id': 'tenant'}


@pytest.mark.asyncio
@pytest.mark.parametrize('settings', [None, {}, {'business_date': 'invalid'}])
async def test_open_shift_without_verified_business_day_never_inserts(monkeypatch, settings):
    database = SimpleNamespace(
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value=settings)),
        hotel_settings=SimpleNamespace(find_one=AsyncMock(return_value={'currency': 'TRY'})),
        pos_shifts=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(shifts, 'db', database)
    monkeypatch.setattr(shifts, '_ensure_shift_indexes', AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await shifts.open_shift(shifts.ShiftOpen(outlet_id='outlet'), SimpleNamespace(id='operator', tenant_id='tenant'))
    assert exc.value.status_code == 409
    database.pos_shifts.insert_one.assert_not_awaited()
