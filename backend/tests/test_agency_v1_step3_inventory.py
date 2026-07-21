"""
Agency v1 — Adim 3 atomik envanter seam birim testleri (ADR Karar 5).

Saf test: alttaki atomik primitif (`create_booking_atomic` / `release_booking_nights`,
kendi atomik testleriyle kapsanan) bu seam'in DIS sinirinda; burada SADECE acente
sozlesme cevirisi (BookingConflictError -> InventoryConflict, conflict_date = ilk
catisan gece) dogrulanir. GERCEK BookingConflictError tipi kullanilir (sahte-yesil
yok). Atomik dogruluk burada yeniden test EDILMEZ (tek kaynak korunur).
"""
from __future__ import annotations

import pytest

import core.atomic_booking as atomic
import routers.agency_v1.inventory as inv
from core.atomic_booking import BookingConflictError


@pytest.mark.asyncio
async def test_claim_success_returns_booking(monkeypatch):
    async def fake_create(doc):
        return {**doc, "persisted": True}

    monkeypatch.setattr(atomic, "create_booking_atomic", fake_create)
    out = await inv.claim_reservation_inventory(tenant_id="T-1", booking_doc={"id": "B1", "tenant_id": "T-1"})
    assert out["persisted"] is True
    assert out["id"] == "B1"


@pytest.mark.asyncio
async def test_claim_conflict_maps_first_night(monkeypatch):
    async def fake_create(doc):
        raise BookingConflictError(
            "Night 2026-07-02 already booked",
            conflicting_booking_id="OTHER",
            conflict_type="booking",
            conflicting_nights=["2026-07-02", "2026-07-03"],
        )

    monkeypatch.setattr(atomic, "create_booking_atomic", fake_create)
    with pytest.raises(inv.InventoryConflict) as ei:
        await inv.claim_reservation_inventory(tenant_id="T-1", booking_doc=
            {"id": "B2", "tenant_id": "T-1", "room_id": "R1"}
        )
    assert ei.value.conflict_date == "2026-07-02"  # ilk catisan gece
    assert ei.value.conflict_type == "booking"
    assert ei.value.conflicting_booking_id == "OTHER"


@pytest.mark.asyncio
async def test_claim_conflict_empty_nights_none_date(monkeypatch):
    """bookings-seviyesi overlap guard'i conflicting_nights=[] verebilir ->
    conflict_date None ama tip/booking surface edilir (fail-closed 409)."""
    async def fake_create(doc):
        raise BookingConflictError(
            "Room already booked",
            conflicting_booking_id="X",
            conflict_type="booking",
            conflicting_nights=[],
        )

    monkeypatch.setattr(atomic, "create_booking_atomic", fake_create)
    with pytest.raises(inv.InventoryConflict) as ei:
        await inv.claim_reservation_inventory(tenant_id="T-1", booking_doc={"id": "B3", "tenant_id": "T-1"})
    assert ei.value.conflict_date is None
    assert ei.value.conflicting_booking_id == "X"


@pytest.mark.asyncio
async def test_ooo_conflict_type_preserved(monkeypatch):
    async def fake_create(doc):
        raise BookingConflictError(
            "Room OOO", conflict_type="ooo", conflicting_nights=["2026-07-05"]
        )

    monkeypatch.setattr(atomic, "create_booking_atomic", fake_create)
    with pytest.raises(inv.InventoryConflict) as ei:
        await inv.claim_reservation_inventory(tenant_id="T-1", booking_doc={"id": "B4", "tenant_id": "T-1"})
    assert ei.value.conflict_type == "ooo"
    assert ei.value.conflict_date == "2026-07-05"


@pytest.mark.asyncio
async def test_release_delegates_and_returns_count(monkeypatch):
    seen = {}

    async def fake_release(tenant_id, booking_id, reason="cancelled", correlation_id=None):
        seen.update(tenant_id=tenant_id, booking_id=booking_id, reason=reason)
        return 3

    monkeypatch.setattr(atomic, "release_booking_nights", fake_release)
    n = await inv.release_reservation_inventory(
        "T-1", "B5", reason="no_show", correlation_id="c1"
    )
    assert n == 3
    assert seen == {"tenant_id": "T-1", "booking_id": "B5", "reason": "no_show"}
