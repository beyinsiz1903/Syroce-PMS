from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.pms_core import folio_detail_service as module
from modules.pms_core.folio_detail_service import FolioDetailService, _enrich_payment_currency


@pytest.mark.parametrize("method", ["gift_card_redemption", "wallet", "loyalty_redemption", "barter", "write_off", "cash", "bank_transfer", "city_ledger"])
@pytest.mark.parametrize("refund_amount", [-2, 2])
def test_refund_and_linked_reversal_restore_balance_for_both_legacy_signs(method, refund_amount):
    payments = [
        {"id": "payment", "processed_at": "2026-10-24T10:00:00Z", "amount": 2, "method": method},
        {"id": "refund", "processed_at": "2026-10-24T11:00:00Z", "amount": refund_amount, "method": method, "payment_type": "refund"},
    ]
    timeline = FolioDetailService()._build_timeline([{"id": "charge", "date": "2026-10-24", "total": 20}], payments)
    assert [row["running_balance"] for row in timeline] == [20, 18, 20]
    assert timeline[-1]["balance_effect"] == 2
    assert not timeline[-1]["can_void"]


@pytest.mark.parametrize("status", ["pending", "failed", "authorized", "declined", "processing", "voided"])
def test_non_effective_payment_never_changes_the_timeline_balance(status):
    event = FolioDetailService()._build_timeline([], [{"amount": 100, "method": "cash", "status": status}])[0]
    assert event["running_balance"] == event["balance_effect"] == 0
    assert not event["can_void"]


def test_non_cash_source_does_not_invent_a_received_cash_amount():
    payment = _enrich_payment_currency({"amount": 2, "method": "barter"}, "USD")
    assert "received_amount" not in payment and "received_currency" not in payment


def test_legacy_negative_payment_is_an_offset_reversal_not_another_refundable_receipt():
    event = FolioDetailService()._build_timeline([], [{"amount": -20, "method": "cash"}])[0]
    assert event["type"] == "refund" and event["running_balance"] == 20
    assert not event["can_void"]


@pytest.mark.parametrize("field", ["billing_settlement_id", "security_fund_id", "concession_id", "provider_ref", "mice_event_id"])
def test_protected_cash_looking_sources_do_not_offer_a_generic_void(field):
    event = FolioDetailService()._build_timeline([], [{"amount": 100, "method": "bank_transfer", field: "linked-source"}])[0]
    assert not event["can_void"]


async def test_summary_timeline_and_audit_use_the_same_signed_source_records(monkeypatch):
    payments = [
        {"id": "barter", "method": "barter", "amount": 2, "billing_settlement_id": "application", "processed_at": "2026-10-24T10:00:00Z"},
        {"id": "undo", "method": "barter", "amount": -2, "billing_settlement_id": "reversal", "payment_type": "refund", "processed_at": "2026-10-24T11:00:00Z"},
        {"id": "writeoff", "method": "write_off", "amount": 1, "processed_at": "2026-10-24T12:00:00Z"},
        {"id": "cash", "method": "cash", "amount": 5, "processed_at": "2026-10-24T13:00:00Z"},
        {"id": "cash-back", "method": "cash", "amount": 2, "payment_type": "refund", "processed_at": "2026-10-24T14:00:00Z"},
        {"id": "pending", "method": "cash", "amount": 500, "status": "pending", "processed_at": "2026-10-24T15:00:00Z"},
    ]
    def collection(rows):
        value = MagicMock()
        value.find.return_value.sort.return_value.to_list = AsyncMock(return_value=rows)
        return value
    db = SimpleNamespace(folios=SimpleNamespace(find_one=AsyncMock(return_value={"id": "f", "booking_id": "b", "currency": "USD"})),
        bookings=SimpleNamespace(find_one=AsyncMock(return_value={"currency": "USD"})),
        folio_charges=collection([{"id": "charge", "date": "2026-10-24", "total": 20}]), payments=collection(payments),
        pms_audit_trail=collection([]), audit_logs=collection([{"id": "log", "action": "billing_instrument_reverse", "after_snapshot": {"payment_id": "undo"}}]))
    monkeypatch.setattr(module, "db", db)
    service = FolioDetailService()
    for name in ["_get_split_folio_info", "_get_city_ledger_history", "_get_associated_invoices"]:
        monkeypatch.setattr(service, name, AsyncMock(return_value=[]))
    result = await service.get_folio_detail("A", "f")
    summary = result["summary"]
    assert summary["total_payments"] == 4
    assert summary["cash_collection_total"] == 3
    assert summary["non_cash_settlement_total"] == summary["instrument_settlement_total"] == 1
    assert summary["balance"] == result["timeline"][-1]["running_balance"] == 16
    assert result["audit_trail"][0]["action"] == "billing_instrument_reverse"
    query = db.audit_logs.find.call_args.args[0]
    assert query["tenant_id"] == "A"
    assert {"after_snapshot.payment_id": {"$in": [p["id"] for p in payments]}} in query["$or"]
