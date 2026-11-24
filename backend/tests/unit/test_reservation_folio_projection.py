"""Guest-card selectors must use ledger balances, with no cache repair writes."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from test_folio_allocation import Cursor, matches

from routers.reservation_detail import _project_reservation_folio_balances


class ReadOnlyCollection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))

    def find(self, query, projection=None, **kwargs):
        return Cursor([row for row in self.rows if matches(row, query)])


@pytest.fixture
def ledger():
    base = {'tenant_id': 'hotel', 'booking_id': 'booking', 'currency': 'TRY', 'status': 'open'}
    folios = [{**base, 'id': 'source', 'balance': 65, 'folio_number': 'F413'},
              {**base, 'id': 'target', 'balance': 999, 'company_id': 'company'}]
    return SimpleNamespace(folios=ReadOnlyCollection(folios),
        bookings=ReadOnlyCollection([{'id': 'booking', 'tenant_id': 'hotel', 'currency': 'TRY'}]),
        folio_charges=ReadOnlyCollection([
            {**base, 'id': 'active', 'folio_id': 'source', 'total': 25},
            {**base, 'id': 'void', 'folio_id': 'source', 'total': 40, 'voided': True},
            {**base, 'id': 'other', 'tenant_id': 'other', 'folio_id': 'source', 'total': 500},
            {**base, 'id': 'target-charge', 'folio_id': 'target', 'total': 50}]),
        payments=ReadOnlyCollection(), extra_charges=ReadOnlyCollection())


async def project(db):
    return await _project_reservation_folio_balances(db, 'hotel', {'currency': 'TRY'}, db.folios.rows)


@pytest.mark.asyncio
async def test_voided_extra_and_other_tenant_do_not_inflate_selector_balance(ledger):
    original = deepcopy(vars(ledger))
    result = await project(ledger)
    assert [row['balance'] for row in result] == [25, 50]
    assert result[0]['folio_number'] == 'F413'
    assert result[1]['company_id'] == 'company'
    for name, collection in original.items():
        assert getattr(ledger, name).rows == collection.rows


@pytest.mark.asyncio
async def test_payment_and_opening_balance_change_payment_and_merge_defaults(ledger):
    ledger.folios.rows[0]['opening_balance'] = 10
    ledger.payments.rows.append({'id': 'paid', 'tenant_id': 'hotel', 'folio_id': 'source',
                                'currency': 'TRY', 'amount': 20, 'method': 'cash'})
    assert (await project(ledger))[0]['balance'] == 15


@pytest.mark.asyncio
async def test_mirrored_extra_is_not_added_twice(ledger):
    ledger.folio_charges.rows[0]['source_extra_charge_id'] = 'extra'
    ledger.extra_charges.rows.append({'id': 'extra', 'tenant_id': 'hotel', 'booking_id': 'booking',
                                     'folio_id': 'source', 'currency': 'TRY', 'total': 25})
    assert (await project(ledger))[0]['balance'] == 25


@pytest.mark.asyncio
async def test_ambiguous_unbound_extra_is_not_assigned_to_first_window(ledger):
    ledger.extra_charges.rows.append({'id': 'legacy', 'tenant_id': 'hotel', 'booking_id': 'booking',
                                     'currency': 'TRY', 'total': 40})
    assert [row['balance'] for row in await project(ledger)] == [25, 50]
    ledger.folios.rows.pop()
    assert (await project(ledger))[0]['balance'] == 65


@pytest.mark.asyncio
async def test_foreign_currency_debt_rejects_unsafe_single_currency_defaults(ledger):
    ledger.folio_charges.rows.append({'tenant_id': 'hotel', 'folio_id': 'source', 'currency': 'USD', 'total': 5})
    with pytest.raises(HTTPException) as exc:
        await project(ledger)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_empty_folios_need_no_database():
    assert await _project_reservation_folio_balances(None, 'hotel', {}, []) == []
