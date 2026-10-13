from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import marketplace_b2b as marketplace


@pytest.mark.asyncio
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('plan,expected', [('RO', 1000), ('BB', 1500), (None, None), ('other', None)])
async def test_price_never_depends_on_row_order(monkeypatch, reverse, plan, expected):
    rows = [{'date': '2027-01-01', 'rate_plan_code': 'RO', 'rate': 1000},
            {'date': '2027-01-01', 'rate_plan_code': 'BB', 'rate': 1500}]
    if reverse:
        rows.reverse()
    collection = lambda items: SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=items)))
    monkeypatch.setattr(marketplace, 'db', SimpleNamespace(agency_rate_calendar=collection(rows), hr_rate_calendar=collection([]), rate_calendar=collection([])))
    quote = await marketplace._marketplace_stay_price(tenant_id='t', agency_id='a', room_type='s', check_in='2027-01-01', check_out='2027-01-02', fallback_rate=5, rate_plan_code=plan)
    assert quote['sellable'] is (expected is not None)
    if expected:
        assert quote['total_price'] == expected and quote['rate_plan_code'] == plan


def test_product_snapshot_keeps_meal_and_cancellation_terms():
    contract = {'cancellation_policy': {'free_until_days_before': 7}}
    snapshot = marketplace._rate_product_snapshot('BB', {}, contract)
    assert snapshot == {'rate_plan_code': 'BB', 'meal_plan': 'BB', 'cancellation_policy': contract['cancellation_policy']}
