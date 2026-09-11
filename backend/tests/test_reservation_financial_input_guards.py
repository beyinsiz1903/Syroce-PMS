import os
import uuid
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


class AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeSession(AsyncContext):
    def start_transaction(self):
        return AsyncContext()


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
    assert reservation_detail._cari_transfer_lookup_id(account) == str(legacy_id)


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
    assert reservation_detail._cari_transfer_lookup_id(numeric_account) == "12"


@pytest.mark.asyncio
async def test_uuid_backed_cari_id_round_trips_from_list_response(monkeypatch):
    persisted_id = uuid.uuid4()
    uuid_account = {
        "_id": persisted_id,
        "tenant_id": "tenant-a",
        "account_name": "Etstur",
    }

    async def find_uuid_account(query, *_args, **_kwargs):
        if query.get("_id") == persisted_id:
            return uuid_account
        return None

    database = SimpleNamespace(
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            find=lambda *_args, **_kwargs: AsyncRows([]),
        ),
        city_ledger_accounts=SimpleNamespace(
            find_one=AsyncMock(side_effect=find_uuid_account),
            find=lambda *_args, **_kwargs: AsyncRows([uuid_account]),
        ),
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    account, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        str(persisted_id),
    )

    assert account is uuid_account
    assert is_city_ledger is True
    assert update_filter == {"tenant_id": "tenant-a", "_id": persisted_id}


@pytest.mark.asyncio
async def test_serialized_identity_fallback_reuses_exact_persisted_id(monkeypatch):
    class OpaquePersistedId:
        def __str__(self):
            return "090a62e9-ee24-5083-a918-748d71cbd416"

        def __repr__(self):
            return "OpaquePersistedId(090a62e9)"

    persisted_id = OpaquePersistedId()
    account = {
        "_id": persisted_id,
        "tenant_id": "tenant-a",
        "account_name": "Etstur",
    }
    city_ledger = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        find=lambda *_args, **_kwargs: AsyncRows([account]),
    )
    database = SimpleNamespace(
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            find=lambda *_args, **_kwargs: AsyncRows([]),
        ),
        city_ledger_accounts=city_ledger,
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    found, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        str(persisted_id),
    )

    assert found is account
    assert is_city_ledger is True
    assert update_filter == {"tenant_id": "tenant-a", "_id": persisted_id}


@pytest.mark.asyncio
async def test_cari_account_exact_name_fallback_resolves_unique_legacy_row(monkeypatch):
    legacy_account = {
        "_id": "persisted-etstur",
        "id": "public-etstur",
        "tenant_id": "tenant-a",
        "account_name": "Etstur",
    }

    async def find_city_ledger(query, *_args, **_kwargs):
        if "$or" in query:
            return legacy_account
        return None

    database = SimpleNamespace(
        cari_accounts=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        city_ledger_accounts=SimpleNamespace(find_one=AsyncMock(side_effect=find_city_ledger)),
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    account, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        "stale-browser-id",
        account_name="Etstur",
    )

    assert account is legacy_account
    assert is_city_ledger is True
    assert update_filter == {"tenant_id": "tenant-a", "_id": "persisted-etstur"}


@pytest.mark.asyncio
async def test_cari_account_name_fallback_refuses_ambiguous_rows(monkeypatch):
    legacy = {"_id": "legacy-etstur", "tenant_id": "tenant-a", "name": "Etstur"}
    city_ledger = {"_id": "ledger-etstur", "tenant_id": "tenant-a", "account_name": "Etstur"}

    async def find_legacy(query, *_args, **_kwargs):
        return legacy if "$or" in query else None

    async def find_city_ledger(query, *_args, **_kwargs):
        return city_ledger if "$or" in query else None

    database = SimpleNamespace(
        cari_accounts=SimpleNamespace(find_one=AsyncMock(side_effect=find_legacy)),
        city_ledger_accounts=SimpleNamespace(find_one=AsyncMock(side_effect=find_city_ledger)),
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    account, is_city_ledger, update_filter = await reservation_detail._find_cari_account(
        "tenant-a",
        "stale-browser-id",
        account_name="Etstur",
    )

    assert account is None
    assert is_city_ledger is False
    assert update_filter is None


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            pms_reservations.ExtraChargeCreate,
            {"charge_name": "Zero charge", "charge_amount": 0},
        ),
    ],
)
def test_zero_financial_values_are_rejected_by_contract(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


def test_daily_rate_contract_allows_zero_for_complimentary_stays():
    # Whether it is authorised is checked after the booking has been loaded.
    # This allows a complete zero-valued comp stay to reach that business rule.
    assert reservation_detail.DailyRateEntry(date="2026-08-17", rate=0).rate == 0


@pytest.mark.asyncio
async def test_daily_rate_zero_is_rejected_for_a_non_complimentary_booking(monkeypatch):
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": "confirmed",
                    "is_complimentary": False,
                }
            )
        )
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())

    with pytest.raises(HTTPException, match="yalnızca comp") as exc:
        await reservation_detail.update_daily_rates(
            "booking-a",
            reservation_detail.DailyRateUpdate(
                rates=[reservation_detail.DailyRateEntry(date="2026-08-17", rate=0)]
            ),
            current_user=SimpleNamespace(id="user-a", tenant_id="tenant-a", role="manager", name="Test Operator"),
            _perm=None,
        )

    assert exc.value.status_code == 422


def test_zero_reservation_detail_extra_charge_is_a_valid_comp_item():
    payload = reservation_detail.ExtraChargeAdd(description="Kola ikram", amount=0, quantity=1)
    assert payload.amount == 0


def test_negative_reservation_detail_extra_charge_is_rejected():
    with pytest.raises(ValidationError):
        reservation_detail.ExtraChargeAdd(description="Negative charge", amount=-1, quantity=1)


@pytest.mark.asyncio
async def test_full_comp_extra_charge_keeps_list_value_without_affecting_balance(monkeypatch):
    extra_charges = SimpleNamespace(insert_one=AsyncMock())
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "is_complimentary": True,
                    "complimentary_scope": "full",
                }
            )
        ),
        extra_charges=extra_charges,
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
    from routers import webhook_retry_service
    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", lambda *_args, **_kwargs: None)

    result = await reservation_detail.add_extra_charge_detail(
        "booking-a",
        reservation_detail.ExtraChargeAdd(description="Akşam yemeği", amount=750, quantity=2),
        current_user=SimpleNamespace(
            id="user-a", tenant_id="tenant-a", role="manager", name="Test Operator"
        ),
        _perm=None,
    )

    charge = result["charge"]
    assert charge["total"] == 0
    assert charge["amount"] == 0
    assert charge["is_complimentary"] is True
    assert charge["complimentary_original_amount"] == 1500
    assert charge["complimentary_scope"] == "full"


@pytest.mark.asyncio
async def test_mark_full_comp_zeroes_open_extras_and_preserves_original_values(monkeypatch):
    daily_rates = SimpleNamespace(
        find=lambda *_args, **_kwargs: AsyncRows(
            [{"id": "rate-a", "date": "2099-01-01", "rate": 1200}]
        ),
        update_one=AsyncMock(),
    )
    extra_charges = SimpleNamespace(
        find=lambda *_args, **_kwargs: AsyncRows(
            [{"id": "extra-a", "amount": 250, "quantity": 1, "total": 250}]
        ),
        update_one=AsyncMock(),
    )
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "check_in": "2099-01-01",
                    "check_out": "2099-01-02",
                    "total_amount": 1200,
                }
            ),
            update_one=AsyncMock(),
        ),
        folio_charges=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        folios=SimpleNamespace(find=lambda *_args, **_kwargs: AsyncRows([])),
        payments=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        invoices=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        daily_rates=daily_rates,
        extra_charges=extra_charges,
        client=SimpleNamespace(start_session=AsyncMock(return_value=FakeSession())),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2099-01-01"}),
    )
    activity = AsyncMock()
    monkeypatch.setattr(reservation_detail, "_log_activity", activity)

    result = await reservation_detail.mark_reservation_complimentary(
        "booking-a",
        reservation_detail.ComplimentaryReservationRequest(
            reason="VIP ağırlama", scope="full"
        ),
        current_user=SimpleNamespace(
            id="user-a", tenant_id="tenant-a", role="manager", name="Test Operator"
        ),
        _perm=None,
    )

    assert result["scope"] == "full"
    assert result["affected_extra_charges"] == 1
    extra_update = extra_charges.update_one.await_args.args[1]["$set"]
    assert extra_update["total"] == 0
    assert extra_update["complimentary_original_amount"] == 250
    booking_update = database.bookings.update_one.await_args.args[1]["$set"]
    assert booking_update["total_amount"] == 0
    assert booking_update["complimentary_scope"] == "full"


@pytest.mark.asyncio
async def test_comp_blocks_a_charge_linked_only_to_its_folio(monkeypatch):
    """Legacy folio-only revenue must not be bypassed by the comp guard."""
    charge_lookup = AsyncMock(return_value={"id": "charge-a"})
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "check_in": "2099-01-01",
                    "check_out": "2099-01-02",
                }
            )
        ),
        folios=SimpleNamespace(find=lambda *_args, **_kwargs: AsyncRows([{"id": "folio-a"}])),
        folio_charges=SimpleNamespace(find_one=charge_lookup),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2099-01-01"}),
    )

    with pytest.raises(HTTPException, match="Tahakkuk edilmiş ücret"):
        await reservation_detail.mark_reservation_complimentary(
            "booking-a",
            reservation_detail.ComplimentaryReservationRequest(
                reason="Yönetim ağırlaması", scope="full"
            ),
            current_user=SimpleNamespace(
                id="user-a", tenant_id="tenant-a", role="manager", name="Test Operator"
            ),
            _perm=None,
        )

    query = charge_lookup.await_args.args[0]
    assert query["$or"] == [
        {"booking_id": "booking-a"},
        {"folio_id": {"$in": ["folio-a"]}},
    ]


def test_booking_or_folio_scope_includes_legacy_folio_rows():
    query = reservation_detail._booking_or_folio_scope_query(
        "tenant-a", "booking-a", ["folio-a", None, ""]
    )
    assert query == {
        "tenant_id": "tenant-a",
        "$or": [
            {"booking_id": "booking-a"},
            {"folio_id": {"$in": ["folio-a"]}},
        ],
    }


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
                    "check_in": "2026-08-17",
                    "check_out": "2026-08-18",
                    "total_amount": 400.0,
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


@pytest.mark.asyncio
async def test_daily_rate_update_requires_each_stay_night_exactly_once(monkeypatch):
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": "confirmed",
                    "check_in": "2026-08-18",
                    "check_out": "2026-08-20",
                    "total_amount": 400.0,
                }
            )
        ),
        daily_rates=SimpleNamespace(find=lambda *_args, **_kwargs: AsyncRows([])),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-08-18"}),
    )

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.update_daily_rates(
            "booking-a",
            reservation_detail.DailyRateUpdate(
                rates=[reservation_detail.DailyRateEntry(date="2026-08-18", rate=200.0)]
            ),
            current_user=SimpleNamespace(id="user-a", tenant_id="tenant-a", role="manager", name="Test Operator"),
            _perm=None,
        )

    assert exc.value.status_code == 422
    assert "Eksik: 2026-08-19" in exc.value.detail


@pytest.mark.asyncio
async def test_daily_rate_update_blocks_pricing_change_after_payment_before_any_write(monkeypatch):
    daily_rates = SimpleNamespace(
        find=lambda *_args, **_kwargs: AsyncRows(
            [{"booking_id": "booking-a", "tenant_id": "tenant-a", "date": "2026-08-18", "rate": 400.0}]
        ),
        update_one=AsyncMock(),
    )
    bookings = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "booking-a",
                "tenant_id": "tenant-a",
                "status": "checked_in",
                "check_in": "2026-08-18",
                "check_out": "2026-08-19",
                "total_amount": 400.0,
            }
        ),
        update_one=AsyncMock(),
    )
    database = SimpleNamespace(
        bookings=bookings,
        daily_rates=daily_rates,
        folios=SimpleNamespace(find_one=AsyncMock(return_value={"id": "folio-a"})),
        payments=SimpleNamespace(find_one=AsyncMock(return_value={"id": "payment-a"})),
        invoices=SimpleNamespace(find_one=AsyncMock(return_value=None)),
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
    monkeypatch.setattr(
        reservation_detail,
        "_posted_room_charge_rate_mismatches",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.update_daily_rates(
            "booking-a",
            reservation_detail.DailyRateUpdate(
                rates=[reservation_detail.DailyRateEntry(date="2026-08-18", rate=450.0)]
            ),
            current_user=SimpleNamespace(id="user-a", tenant_id="tenant-a", role="manager", name="Test Operator"),
            _perm=None,
        )

    assert exc.value.status_code == 409
    assert "Ödeme" in exc.value.detail
    daily_rates.update_one.assert_not_awaited()
    bookings.update_one.assert_not_awaited()
