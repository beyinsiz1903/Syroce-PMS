import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from domains.pms import frontdesk_router


class _Request:
    headers = {"Idempotency-Key": "frontdesk-payment-1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("code,received,received_amount,rate,try_rate,expected_try", [
    ("TRY", "TRY", 125, 1, None, 125),
    ("TRY", "USD", 2.5, .02, None, 125),
    ("EUR", "EUR", 125, 1, 55, 6875),
    ("USD", "TRY", 6250, 50, None, 6250),
])
async def test_quick_payment_replay_does_not_post_twice(monkeypatch, code, received, received_amount, rate, try_rate, expected_try):
    """A browser retry must replay the first folio payment, not collect it twice."""
    payments = SimpleNamespace(insert_one=AsyncMock())
    folios = SimpleNamespace(update_one=AsyncMock(), find_one=AsyncMock(return_value={"id": "folio-1", "status": "open"}))
    bookings = SimpleNamespace(update_one=AsyncMock())
    tenant_settings = SimpleNamespace(
        find_one=AsyncMock(return_value={"tenant_id": "tenant-1", "business_date": "2026-09-22"})
    )
    fake_db = SimpleNamespace(
        payments=payments,
        folios=folios,
        bookings=bookings,
        tenant_settings=tenant_settings,
    )
    monkeypatch.setattr(frontdesk_router, "db", fake_db)

    monkeypatch.setattr(
        frontdesk_router,
        "_ensure_booking",
        AsyncMock(return_value={"id": "booking-1", "guest_id": "guest-1", "room_number": "105", "currency": code}),
    )
    monkeypatch.setattr(
        frontdesk_router,
        "_ensure_open_folio",
        AsyncMock(return_value={"id": "folio-1"}),
    )

    cached_response = {}

    async def _claim(*_args, **_kwargs):
        if cached_response:
            return {"status": "replay", "response": cached_response["body"]}
        return {"status": "acquired", "lock_id": "lock-1"}

    async def _complete(*_args, response_body, **_kwargs):
        cached_response["body"] = response_body

    monkeypatch.setattr(frontdesk_router, "claim_idempotency", _claim)
    monkeypatch.setattr(frontdesk_router, "complete_idempotency", _complete)
    monkeypatch.setattr(frontdesk_router, "release_idempotency", AsyncMock())

    from domains.pms import cashier_service

    monkeypatch.setattr(cashier_service, "ensure_active_shift", AsyncMock())
    record_cash = AsyncMock()
    monkeypatch.setattr(cashier_service, "record_cash_transaction", record_cash)

    payload = frontdesk_router.FolioPaymentRequest(
        amount=125,
        folio_id="folio-1",
        method="card",
        payment_type="final",
        notes="Ön büro hızlı tahsilat",
        currency=code, received_currency=received, received_amount=received_amount,
        exchange_rate=rate, received_to_try_rate=try_rate,
    )
    user = SimpleNamespace(
        tenant_id="tenant-1",
        name="Resepsiyon",
        email="reception@example.com",
    )

    first = await frontdesk_router.add_folio_payment(
        "booking-1", payload, _Request(), user, None,
    )
    replay = await frontdesk_router.add_folio_payment(
        "booking-1", payload, _Request(), user, None,
    )

    assert replay == first
    assert first["amount"] == 125
    assert first["payment_type"] == "final"
    assert first["reporting_amount"] == expected_try
    assert record_cash.await_args.kwargs["amount"] == expected_try
    assert record_cash.await_args.kwargs["currency"] == received
    assert record_cash.await_args.kwargs["original_amount"] == received_amount
    assert record_cash.await_count == 1
    payments.insert_one.assert_awaited_once()
    folios.update_one.assert_awaited_once()
    bookings.update_one.assert_awaited_once()
