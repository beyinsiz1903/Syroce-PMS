import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

import routers.finance.folio as finance_folio
import routers.reservation_detail as reservation_detail


def test_summary_does_not_double_count_posted_room_charge():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 3500.0, "paid_amount": 3955.0},
        [
            {"charge_type": "room_charge", "total": 3920.0, "voided": False},
            {"charge_type": "tax", "total": 35.0, "voided": False},
        ],
        [{"amount": 3955.0, "voided": False}],
        [],
        [],
    )

    assert summary["total_charges"] == 3955.0
    assert summary["total_payments"] == 3955.0
    assert summary["balance"] == 0.0


def test_summary_keeps_unposted_room_total_before_night_audit():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 3500.0, "paid_amount": 500.0},
        [{"charge_type": "minibar", "total": 100.0, "voided": False}],
        [{"amount": 500.0, "voided": False}],
        [],
        [],
    )

    assert summary["balance"] == 3100.0


def test_summary_keeps_full_stay_visible_when_only_some_room_nights_are_posted():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 7500.0, "paid_amount": 0.0},
        [{"charge_type": "room_charge", "total": 5833.34, "voided": False}],
        [],
        [],
        [],
    )

    # Operational checkout still uses the amount already present on the
    # folio, while the reservation view must show the entire agreed stay.
    assert summary["balance"] == 5833.34
    assert summary["folio_balance"] == 5833.34
    assert summary["unposted_room_amount"] == 1666.66
    assert summary["reservation_total_due"] == 7500.0


def test_summary_marks_room_charge_overage_as_reconciliation_not_guest_debt():
    """A stale posted room charge must not be labelled as collectable money."""
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 7500.0, "paid_amount": 7500.0},
        [{"charge_type": "room_charge", "total": 7515.03, "voided": False}],
        [{"amount": 7500.0, "voided": False}],
        [],
        [],
    )

    assert summary["reservation_total_due"] == 15.03
    assert summary["pricing_reconciliation_required"] is True
    assert summary["pricing_reconciliation_difference"] == 15.03


def test_summary_marks_automatic_accommodation_tax_overage_as_reconciliation():
    """A system tax row may not turn a fully paid booking into new debt."""
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 7500.0, "paid_amount": 7500.0},
        [
            {"charge_type": "room_charge", "total": 7500.0, "voided": False},
            {"charge_type": "tax", "charge_category": "tax", "total": 15.03, "voided": False},
        ],
        [{"amount": 7500.0, "voided": False}],
        [],
        [],
    )

    assert summary["reservation_total_due"] == 15.03
    assert summary["pricing_reconciliation_required"] is True
    assert summary["pricing_reconciliation_difference"] == 15.03
    assert summary["accommodation_tax_total"] == 15.03


def test_room_charge_rate_mismatch_detects_the_exact_cent_difference():
    mismatches = reservation_detail._room_charge_rate_mismatches(
        [
            {
                "id": "charge-a",
                "charge_type": "room_charge",
                "date": "2026-09-03T00:00:00+00:00",
                "total": 2515.03,
                "voided": False,
            }
        ],
        {"2026-09-03": 2500.0},
    )

    assert mismatches == [
        {
            "date": "2026-09-03",
            "charge_id": "charge-a",
            "expected_total": 2500.0,
            "posted_total": 2515.03,
        }
    ]


@pytest.mark.asyncio
async def test_payment_is_blocked_when_posted_room_rate_and_daily_rate_disagree(monkeypatch):
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(
                find_one=AsyncMock(
                    return_value={"id": "booking-a", "tenant_id": "tenant-a", "total_amount": 7500.0}
                )
            )
        ),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_: None)
    mismatch_probe = AsyncMock(
        return_value=[
            {"date": "2026-09-03", "charge_id": "charge-a", "expected_total": 2500.0, "posted_total": 2515.03}
        ]
    )
    monkeypatch.setattr(reservation_detail, "_posted_room_charge_rate_mismatches", mismatch_probe)

    with pytest.raises(reservation_detail.HTTPException) as exc:
        await reservation_detail.record_payment(
            "booking-a",
            reservation_detail.PaymentRecord(amount=7500.0, method="cash", payment_type="final"),
            current_user=SimpleNamespace(id="user-a", tenant_id="tenant-a", role="manager", name="Operator"),
            _perm=None,
        )

    assert exc.value.status_code == 409
    assert "mutabakat" in exc.value.detail
    mismatch_probe.assert_awaited_once_with("tenant-a", "booking-a")


def test_summary_preserves_explicit_zero_after_extra_charge_split():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 100.0, "paid_amount": 0.0},
        [],
        [],
        [{"total": 0.0, "amount": 25.0, "voided": False}],
        [],
    )

    assert summary["total_extra"] == 0.0
    assert summary["balance"] == 100.0


@pytest.mark.asyncio
async def test_cari_transfer_rejects_same_source_and_target_before_db_access(monkeypatch):
    find_one = AsyncMock()
    insert_one = AsyncMock()
    update_one = AsyncMock()
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            cari_accounts=SimpleNamespace(find_one=find_one, update_one=update_one),
            cari_transactions=SimpleNamespace(insert_one=insert_one),
        ),
    )

    user = SimpleNamespace(
        role="super_admin",
        tenant_id="tenant-a",
        name="Test Operator",
        email="operator@example.test",
    )
    payload = reservation_detail.CariTransfer(
        amount=10.0,
        cari_account_id="agency-a",
    )

    with pytest.raises(reservation_detail.HTTPException) as exc:
        await reservation_detail.transfer_cari_to_agency(
            "agency-a",
            payload,
            user,
            None,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "Kaynak ve hedef cari hesap farklı olmalı"
    find_one.assert_not_awaited()
    insert_one.assert_not_awaited()
    update_one.assert_not_awaited()


def test_summary_reports_only_remaining_partial_deposit():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 100.0, "paid_amount": 60.0},
        [],
        [{"amount": 60.0, "voided": False}],
        [],
        [
            {
                "amount": 100.0,
                "refunded_amount": 40.0,
                "status": "partially_refunded",
            }
        ],
    )

    assert summary["total_deposits"] == 60.0


@pytest.mark.asyncio
async def test_payment_refreshes_tenant_scoped_checkout_balance(monkeypatch):
    calculate = AsyncMock(return_value=125.5)
    update = AsyncMock()
    monkeypatch.setattr("core.utils.calculate_folio_balance", calculate)
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(folios=SimpleNamespace(update_one=update)),
    )

    balance = await reservation_detail._refresh_cached_folio_balance("tenant-a", "folio-a")

    assert balance == 125.5
    calculate.assert_awaited_once_with("folio-a", "tenant-a")
    update.assert_awaited_once_with(
        {"id": "folio-a", "tenant_id": "tenant-a"},
        {"$set": {"balance": 125.5}},
    )


@pytest.mark.asyncio
async def test_payment_void_reverses_tenant_scoped_booking_paid_amount(monkeypatch):
    find_one = AsyncMock(return_value={"paid_amount": 300.0})
    update_one = AsyncMock()
    monkeypatch.setattr(
        finance_folio,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(find_one=find_one, update_one=update_one),
        ),
    )

    adjustment = await finance_folio._decrement_booking_paid_amount(
        "tenant-a",
        "booking-a",
        125.0,
    )

    assert adjustment == 125.0
    find_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"_id": 0, "paid_amount": 1},
    )
    update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$inc": {"paid_amount": -125.0}},
    )


@pytest.mark.asyncio
async def test_finance_void_payment_blocks_closed_folio_before_writes(monkeypatch):
    payment_update = AsyncMock()
    folio_update = AsyncMock()
    monkeypatch.setattr(
        finance_folio,
        "db",
        SimpleNamespace(
            payments=SimpleNamespace(
                find_one=AsyncMock(
                    return_value={
                        "id": "payment-a",
                        "folio_id": "folio-a",
                        "tenant_id": "tenant-a",
                        "voided": False,
                        "amount": 1.0,
                    }
                ),
                update_one=payment_update,
            ),
            folios=SimpleNamespace(
                find_one=AsyncMock(return_value={"status": "closed"}),
                update_one=folio_update,
            ),
        ),
    )
    user = SimpleNamespace(
        role="super_admin",
        tenant_id="tenant-a",
        id="user-a",
        name="Operator",
        email="operator@example.test",
    )

    with pytest.raises(finance_folio.HTTPException) as exc:
        await finance_folio.void_payment(
            "folio-a",
            "payment-a",
            {"reason": "test"},
            user,
        )

    assert exc.value.status_code == 409
    payment_update.assert_not_awaited()
    folio_update.assert_not_awaited()
