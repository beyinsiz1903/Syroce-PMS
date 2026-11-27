from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.pms_core import automatic_folio_routing
from modules.pms_core.revenue_report import charge_breakdown
from routers import reservation_detail as detail
from routers import webhook_retry_service


@pytest.mark.asyncio
@pytest.mark.parametrize("scope,expected", [("full", 0), ("room_only", 150)])
async def test_future_manual_extra_preserves_original_tax_and_keeps_scope(scope, expected, monkeypatch):
    booking = {"id": "booking", "tenant_id": "test", "currency": "TRY", "is_complimentary": True, "complimentary_scope": scope}
    monkeypatch.setattr(detail, "db", SimpleNamespace(bookings=SimpleNamespace(find_one=AsyncMock(return_value=booking))))
    monkeypatch.setattr(detail, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(detail, "_ensure_hotel_context", lambda *_: None)
    monkeypatch.setattr(detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(detail, "_log_activity", AsyncMock())
    monkeypatch.setattr(detail, "stamp_open_business_date", AsyncMock())
    insert = AsyncMock(side_effect=lambda _db, _tenant, charge: charge)
    monkeypatch.setattr(automatic_folio_routing, "insert_booking_extra", insert)
    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", lambda *_: None)
    result = await detail.add_extra_charge_detail("booking", detail.ExtraChargeAdd(description="Synthetic minibar", amount=150, quantity=1, vat_rate=20, category="minibar"),
        current_user=SimpleNamespace(id="manager", name="Operator", role="admin", tenant_id="test"), _perm=None)
    charge = result["charge"]
    assert charge["total"] == expected
    assert charge["entered_total"] == 150
    assert insert.await_count == 1
    values = charge_breakdown({**charge, "report_source": "extra"})
    if scope == "full":
        assert charge["complimentary_original_tax_snapshot"]["net_amount"] == 125
        assert charge["complimentary_original_tax_snapshot"]["vat_amount"] == 25
        assert values["subtotal"] == values["discount"] == 125
        assert values["net"] == values["vat"] == values["total"] == 0
    else:
        assert "complimentary_original_tax_snapshot" not in charge
        assert values["net"] == 125 and values["vat"] == 25 and values["total"] == 150


@pytest.mark.asyncio
async def test_department_full_comp_preserves_original_tax_without_changing_posted_zero(monkeypatch):
    from core import department_folio as service

    booking = {"id": "b", "currency": "TRY", "status": "checked_in", "is_complimentary": True, "complimentary_scope": "full"}
    folio = {"id": "f", "currency": "TRY"}
    db = SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(return_value=booking)),
        folio_charges=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock()),
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={"business_date": "2026-11-13"}), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))),
        night_audit_runs=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        folios=SimpleNamespace(update_one=AsyncMock()),
    )
    monkeypatch.setattr(service, "select_booking_folio", AsyncMock(return_value=folio))
    monkeypatch.setattr(service, "folio_snapshots", AsyncMock(return_value={"f": {"balance_by_currency": {"TRY": 0}}}))
    monkeypatch.setattr(service, "refresh_booking_payment_state", AsyncMock())
    monkeypatch.setattr(service, "append_audit_log", AsyncMock())
    monkeypatch.setattr(automatic_folio_routing, "route_new_charge", AsyncMock(return_value=None))
    result = await service.post_source_charge(db, "test", {"id": "s", "kind": "activity", "booking_id": "b", "currency": "TRY", "gross": 150, "tax": 25, "description": "Synthetic activity"}, "actor", session=None)
    charge = result["charge"]
    assert charge["total"] == charge["vat_amount"] == charge["amount"] == 0
    assert charge["complimentary_original_amount"] == 150
    assert charge["complimentary_original_tax_snapshot"]["net_amount"] == 125
    values = charge_breakdown({**charge, "report_source": "folio"})
    assert values["subtotal"] == values["discount"] == 125
    assert values["net"] == values["vat"] == values["total"] == 0
    assert db.folio_charges.insert_one.await_count == 1


@pytest.mark.asyncio
async def test_spa_full_comp_keeps_appointment_tax_snapshot_and_zero_posting(monkeypatch):
    from domains.spa import folio as spa

    booking = {"id": "b", "currency": "TRY", "status": "checked_in", "is_complimentary": True, "complimentary_scope": "full"}
    folio = {"id": "f", "currency": "TRY"}
    db = SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(return_value=booking)),
        folio_charges=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock()),
        folio_postings=SimpleNamespace(insert_one=AsyncMock()),
        folios=SimpleNamespace(update_one=AsyncMock()),
    )
    monkeypatch.setattr(spa, "select_booking_folio", AsyncMock(return_value=folio))
    monkeypatch.setattr(spa, "folio_snapshots", AsyncMock(return_value={"f": {"balance_by_currency": {"TRY": 0}}}))
    monkeypatch.setattr(spa, "refresh_booking_payment_state", AsyncMock())
    monkeypatch.setattr(spa, "audit_log", AsyncMock())
    async def stamp(_db, _tenant, charge):
        charge["business_date"] = "2026-11-13"
    monkeypatch.setattr(spa, "stamp_open_business_date", stamp)
    monkeypatch.setattr(automatic_folio_routing, "route_new_charge", AsyncMock(return_value=None))
    result = await spa.post_charge(db, "test", {"id": "s", "reservation_id": "b", "currency": "TRY", "price": 150, "tax_rate": .2, "service_name": "Synthetic massage", "completed_at": "2026-11-13T10:00:00Z"}, "actor", "Operator", session=object())
    charge = result["charge"]
    assert charge["total"] == charge["vat_amount"] == charge["amount"] == result["posting"]["amount"] == 0
    assert charge["complimentary_original_amount"] == 150
    assert charge["complimentary_original_tax_snapshot"]["net_amount"] == 125
    assert charge["complimentary_original_tax_snapshot"]["vat_amount"] == 25
    values = charge_breakdown({**charge, "report_source": "folio"})
    assert values["subtotal"] == values["discount"] == 125
    assert values["net"] == values["vat"] == values["total"] == 0
    assert db.folio_charges.insert_one.await_count == db.folio_postings.insert_one.await_count == 1
