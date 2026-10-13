from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import marketplace_b2b as marketplace
from domains.channel_manager.unified_rate_manager_router import _validate_agency_restrictions


@pytest.mark.asyncio
@pytest.mark.parametrize('nights,minimum,sellable', [(1, 3, False), (3, 3, True), (4, 3, True)])
async def test_shared_minimum_stay(monkeypatch, nights, minimum, sellable):
    rows = [{'date': f'2027-01-0{i}', 'rate': 100, 'min_stay': minimum} for i in range(1, nights + 1)]
    collection = lambda rows: SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    monkeypatch.setattr(marketplace, 'db', SimpleNamespace(agency_rate_calendar=collection(rows), hr_rate_calendar=collection([]), rate_calendar=collection([])))
    result = await marketplace._marketplace_stay_price(tenant_id='t', agency_id='a', room_type='standard', check_in='2027-01-01', check_out=f'2027-01-0{nights+1}', fallback_rate=100)
    assert result['sellable'] is sellable


@pytest.mark.parametrize('field', ['cta', 'ctd', 'max_stay'])
def test_unsupported_agency_fields_fail_closed(field):
    with pytest.raises(HTTPException) as exc:
        _validate_agency_restrictions(['a'], {'rate', field})
    assert exc.value.status_code == 422
    _validate_agency_restrictions([], {field})
    _validate_agency_restrictions(['a'], {'rate', 'min_stay', 'availability', 'stop_sell'})
