from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.channel_manager.unified_rate_manager_router import _validate_agency_restrictions
from routers import marketplace_b2b as marketplace


@pytest.mark.asyncio
@pytest.mark.parametrize('nights,minimum,sellable', [(1, 3, False), (3, 3, True), (4, 3, True)])
async def test_shared_minimum_stay(monkeypatch, nights, minimum, sellable):
    rows = [{'date': f'2027-01-0{i}', 'rate': 100, 'min_stay': minimum} for i in range(1, nights + 1)]
    collection = lambda rows: SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    monkeypatch.setattr(marketplace, 'db', SimpleNamespace(agency_rate_calendar=collection(rows), hr_rate_calendar=collection([]), rate_calendar=collection([])))
    result = await marketplace._marketplace_stay_price(tenant_id='t', agency_id='a', room_type='standard', check_in='2027-01-01', check_out=f'2027-01-0{nights+1}', fallback_rate=100)
    assert result['sellable'] is sellable


def _calendar(monkeypatch, rows):
    collection = lambda rows: SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    monkeypatch.setattr(marketplace, 'db', SimpleNamespace(agency_rate_calendar=collection(rows), hr_rate_calendar=collection([]), rate_calendar=collection([])))


async def _price(check_out):
    return await marketplace._marketplace_stay_price(tenant_id='t', agency_id='a', room_type='standard', check_in='2027-01-01', check_out=check_out, fallback_rate=100)


@pytest.mark.asyncio
async def test_closed_to_arrival_blocks_only_the_arrival_night(monkeypatch):
    _calendar(monkeypatch, [{'date': '2027-01-01', 'rate': 100, 'cta': True}, {'date': '2027-01-02', 'rate': 100}])
    assert (await _price('2027-01-03'))['reason'] == 'closed_to_arrival'
    _calendar(monkeypatch, [{'date': '2027-01-01', 'rate': 100}, {'date': '2027-01-02', 'rate': 100, 'cta': True}])
    assert (await _price('2027-01-03'))['sellable'] is True


@pytest.mark.asyncio
async def test_closed_to_departure_reads_the_checkout_date(monkeypatch):
    nights = [{'date': '2027-01-01', 'rate': 100}, {'date': '2027-01-02', 'rate': 100}]
    _calendar(monkeypatch, nights + [{'date': '2027-01-03', 'rate': 100, 'ctd': True}])
    assert (await _price('2027-01-03'))['reason'] == 'closed_to_departure'
    _calendar(monkeypatch, [{**nights[0], 'ctd': True}, nights[1]])
    assert (await _price('2027-01-03'))['sellable'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('nights,maximum,sellable', [(2, 2, True), (3, 2, False)])
async def test_shared_maximum_stay(monkeypatch, nights, maximum, sellable):
    _calendar(monkeypatch, [{'date': f'2027-01-0{i}', 'rate': 100, 'max_stay': maximum} for i in range(1, nights + 1)])
    assert (await _price(f'2027-01-0{nights + 1}'))['sellable'] is sellable


@pytest.mark.asyncio
async def test_minimum_stay_on_arrival(monkeypatch):
    _calendar(monkeypatch, [{'date': '2027-01-01', 'rate': 100, 'min_los_arrival': 3}, {'date': '2027-01-02', 'rate': 100}])
    assert (await _price('2027-01-03'))['reason'] == 'min_stay_arrival'


@pytest.mark.parametrize('field', ['cta', 'ctd', 'max_stay', 'min_los_arrival'])
def test_enforced_restrictions_can_target_agencies(field):
    _validate_agency_restrictions(['a'], {'rate', field})
    _validate_agency_restrictions(['a'], {'rate', 'min_stay', 'availability', 'stop_sell'})


def test_unknown_agency_fields_still_fail_closed():
    with pytest.raises(HTTPException) as exc:
        _validate_agency_restrictions(['a'], {'rate', 'extra_adult_rate'})
    assert exc.value.status_code == 422
    _validate_agency_restrictions([], {'extra_adult_rate'})
