import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from domains.pms import folio_window_router as windows
from routers import reservation_detail as detail


def test_cari_settlement_is_not_a_cash_collection_or_discount():
    summary = detail._build_financial_summary(
        {"total_amount": 10000}, [{"total": 10000, "charge_type": "room_charge"}],
        [{"amount": 6000, "method": "city_ledger", "status": "paid"}, {"amount": 4000, "method": "card", "status": "paid"}], [], [])
    assert summary["cash_collection_total"] == 4000
    assert summary["city_ledger_transfer_total"] == 6000
    assert summary["total_payments"] == 10000
    assert summary["total_discounts"] == 0
    assert summary["balance"] == 0


def test_same_reference_on_another_window_is_not_a_replay():
    data = detail.PaymentRecord(amount=4000, method='card', folio_id='guest', payment_type='final')
    existing = {'amount': 4000, 'method': 'card', 'folio_id': 'company', 'payment_type': 'final'}
    assert not detail._same_payment_record(existing, data)
    assert detail._same_payment_record({**existing, 'folio_id': 'guest'}, data)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['company', 'agency'])
async def test_corporate_window_requires_a_real_account(kind):
    with pytest.raises(HTTPException) as exc:
        await windows._validate_payor(windows.WindowCreate(booking_id='b', payor_type=kind), 'tenant')
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_account_validation_uses_canonical_tenant_scoped_cari_resolver(monkeypatch):
    resolve = AsyncMock(return_value=({'id': 'canonical', 'name': 'Synthetic company'}, False, {}))
    monkeypatch.setattr(detail, '_find_cari_account', resolve)
    result = await windows._validate_payor(windows.PayorPatch(payor_type='company', cari_account_id='legacy'), 'tenant-a')
    resolve.assert_awaited_once_with('tenant-a', 'legacy')
    assert result == {'cari_account_id': 'canonical', 'cari_account_name': 'Synthetic company'}
    resolve.return_value = (None, False, {})
    with pytest.raises(HTTPException) as exc:
        await windows._validate_payor(windows.PayorPatch(payor_type='company', cari_account_id='foreign'), 'tenant-a')
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_payor_change_cannot_reference_a_foreign_guest(monkeypatch):
    find = AsyncMock(return_value=None)
    monkeypatch.setattr(windows, 'db', SimpleNamespace(guests=SimpleNamespace(find_one=find), companies=SimpleNamespace()))
    with pytest.raises(HTTPException):
        await windows._validate_payor(windows.PayorPatch(payor_type='guest', payor_id='foreign'), 'tenant-a')
    find.assert_awaited_once_with({'id': 'foreign', 'tenant_id': 'tenant-a'}, {'_id': 0, 'id': 1})


@pytest.mark.asyncio
async def test_cari_and_guest_profiles_cannot_be_mixed():
    with pytest.raises(HTTPException):
        await windows._validate_payor(windows.PayorPatch(payor_type='company', payor_id='foreign', cari_account_id='ar'), 'tenant-a')
