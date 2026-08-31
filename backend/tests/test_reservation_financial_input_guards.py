import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import pms_reservations, reservation_detail


class AsyncRows:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row

        return iterate()


@pytest.mark.asyncio
async def test_legacy_cari_object_id_is_found_and_normalized(monkeypatch):
    legacy_id = ObjectId()
    legacy_account = {
        "_id": legacy_id,
        "tenant_id": "tenant-a",
        "account_name": "Etstur",
        "current_balance": 0,
    }

    async def find_legacy_account(query, *_args, **_kwargs):
        if query.get("_id") == legacy_id:
            return legacy_account
        return None

    database = SimpleNamespace(
        cari_accounts=SimpleNamespace(find_one=AsyncMock(side_effect=find_legacy_account)),
        city_ledger_accounts=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    account, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        str(legacy_id),
    )

    assert account is legacy_account
    assert is_city_ledger is False
    assert update_filter == {"tenant_id": "tenant-a", "_id": legacy_id}
    assert reservation_detail._canonical_cari_account_id(account) == str(legacy_id)
    assert reservation_detail._canonical_cari_account_name(account) == "Etstur"


@pytest.mark.asyncio
async def test_legacy_city_ledger_account_id_is_found(monkeypatch):
    legacy_account = {
        "tenant_id": "tenant-a",
        "account_id": "agency-etstur",
        "account_name": "Etstur",
        "current_balance": 0,
    }

    async def find_city_ledger(query, *_args, **_kwargs):
        if query.get("account_id") == "agency-etstur":
            return legacy_account
        return None

    database = SimpleNamespace(
        cari_accounts=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        city_ledger_accounts=SimpleNamespace(find_one=AsyncMock(side_effect=find_city_ledger)),
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    account, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        "agency-etstur",
    )

    assert account is legacy_account
    assert is_city_ledger is True
    assert update_filter == {"tenant_id": "tenant-a", "account_id": "agency-etstur"}


@pytest.mark.asyncio
async def test_legacy_numeric_cari_account_id_round_trips_from_list_response(monkeypatch):
    numeric_account = {"id": 12, "tenant_id": "tenant-a", "name": "Etstur"}

    async def find_numeric_account(query, *_args, **_kwargs):
        if query.get("id") == 12:
            return numeric_account
        return None

    cari_accounts = SimpleNamespace(find_one=AsyncMock(side_effect=find_numeric_account))
    database = SimpleNamespace(
        cari_accounts=cari_accounts,
        city_ledger_accounts=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    # The list response serializes the BSON numeric identifier for the browser.
    account, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        reservation_detail._canonical_cari_account_id(numeric_account),
    )

    assert account == numeric_account
    assert is_city_ledger is False
    assert update_filter == {"tenant_id": "tenant-a", "id": 12}


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            reservation_detail.ExtraChargeAdd,
            {"description": "Zero charge", "amount": 0, "quantity": 1},
        ),
        (
            pms_reservations.ExtraChargeCreate,
            {"charge_name": "Zero charge", "charge_amount": 0},
        ),
        (
            reservation_detail.DailyRateEntry,
            {"date": "2026-08-17", "rate": 0},
        ),
    ],
)
def test_zero_financial_values_are_rejected_by_contract(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_out", "cancelled", "no_show"])
async def test_terminal_booking_cannot_receive_deposit(monkeypatch, status):
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": status,
                }
            ),
            update_one=AsyncMock(),
        ),
        deposits=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.record_deposit(
            "booking-a",
            reservation_detail.DepositRecord(amount=1, method="cash"),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert exc.value.status_code == 409
    database.deposits.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_deposit_is_linked_to_reservation_folio_and_refreshes_balance(monkeypatch):
    folio = {
        "id": "folio-a",
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "status": "open",
    }
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "guest_id": "guest-a",
                    "status": "confirmed",
                    "paid_amount": 250,
                }
            ),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value=folio),
            insert_one=AsyncMock(),
        ),
        deposits=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
    refresh_balance = AsyncMock(return_value=750)
    monkeypatch.setattr(reservation_detail, "_refresh_cached_folio_balance", refresh_balance)

    from routers import webhook_retry_service

    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", lambda *_args, **_kwargs: None)

    result = await reservation_detail.record_deposit(
        "booking-a",
        reservation_detail.DepositRecord(amount=500, method="cash"),
        current_user=SimpleNamespace(
            id="user-a",
            tenant_id="tenant-a",
            role="manager",
            name="Test Operator",
        ),
        _perm=None,
    )

    assert result["deposit"]["folio_id"] == "folio-a"
    inserted_deposit = database.deposits.insert_one.await_args.args[0]
    inserted_payment = database.payments.insert_one.await_args.args[0]
    assert inserted_deposit["folio_id"] == "folio-a"
    assert inserted_payment["folio_id"] == "folio-a"
    assert inserted_payment["payment_type"] == "deposit"
    database.bookings.update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$set": {"paid_amount": 750.0}},
    )
    refresh_balance.assert_awaited_once_with("tenant-a", "folio-a")


@pytest.mark.asyncio
async def test_deposit_refund_prefers_original_folio(monkeypatch):
    database = SimpleNamespace(
        folios=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "folio-closed",
                    "tenant_id": "tenant-a",
                    "booking_id": "booking-a",
                    "status": "closed",
                }
            ),
            insert_one=AsyncMock(),
        )
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    folio = await reservation_detail._ensure_reservation_folio(
        "tenant-a",
        {"id": "booking-a", "guest_id": "guest-a"},
        preferred_folio_id="folio-closed",
    )

    assert folio["id"] == "folio-closed"
    database.folios.find_one.assert_awaited_once_with(
        {"tenant_id": "tenant-a", "id": "folio-closed"},
        {"_id": 0},
    )
    database.folios.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_night_audit_closed_daily_rate_cannot_be_changed(monkeypatch):
    daily_rates = SimpleNamespace(
        find=lambda *_args, **_kwargs: AsyncRows(
            [
                {
                    "id": "rate-a",
                    "booking_id": "booking-a",
                    "tenant_id": "tenant-a",
                    "date": "2026-08-17",
                    "rate": 400.0,
                }
            ]
        ),
        update_one=AsyncMock(),
    )
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": "checked_in",
                }
            ),
            update_one=AsyncMock(),
        ),
        daily_rates=daily_rates,
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-08-18"}),
    )
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.update_daily_rates(
            "booking-a",
            reservation_detail.DailyRateUpdate(
                rates=[reservation_detail.DailyRateEntry(date="2026-08-17", rate=450.0)]
            ),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert exc.value.status_code == 409
    assert "Night Audit ile kapatıldığı" in exc.value.detail
    daily_rates.update_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()
