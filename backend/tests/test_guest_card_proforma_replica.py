"""Guest-card live regressions, run only against the disposable LOCAL database."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.pagination import PaginationParams
from modules.folio import repository
from routers.finance import folio as router
from tests import test_pos_final_consistency_replica as replica_fixtures

db = replica_fixtures.db


@pytest.fixture
def actor():
    return SimpleNamespace(tenant_id="t", id="manager")


async def seed(db, monkeypatch):
    monkeypatch.setattr(router, "db", db)
    monkeypatch.setattr(repository, "db", db)
    monkeypatch.setattr("core.tenant_currency.get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await db.tenants.insert_one({"id": "t", "name": "Hotel"})
    await db.folios.insert_one({"id": "f", "tenant_id": "t", "booking_id": "b", "currency": "TRY", "status": "open", "opening_balance": 50})
    await db.bookings.insert_one({"id": "b", "tenant_id": "t", "room_id": "r", "guest_id": "g", "guest_name": "Ayşe Deniz"})
    await db.rooms.insert_many([{"id": "r", "tenant_id": "t", "room_number": "105"}, {"id": "r", "tenant_id": "other", "room_number": "999"}])
    await db.guests.insert_many([{"id": "g", "tenant_id": "t", "name": "Ayşe Deniz"}, {"id": "g", "tenant_id": "other", "name": "Wrong guest"}])
    await db.spa_appointments.insert_many([{"id": "spa", "tenant_id": "t", "starts_at": "2026-11-10T12:00:00Z"}, {"id": "spa", "tenant_id": "other", "starts_at": "2026-11-20T12:00:00Z"}])
    # Missing voided flags are valid legacy rows; total=0 must stay zero.
    await db.folio_charges.insert_many([
        {"id": "spa", "tenant_id": "t", "folio_id": "f", "total": 120, "amount": 100, "vat_amount": 20, "source_spa_appointment_id": "spa", "created_at": "2026-11-14T08:00:00Z"},
        {"id": "zero", "tenant_id": "t", "folio_id": "f", "total": 0, "amount": 999, "vat_amount": 0, "vat_rate": 0},
        {"id": "void", "tenant_id": "t", "folio_id": "f", "total": 800, "voided": True},
        {"id": "foreign", "tenant_id": "other", "folio_id": "f", "total": 600},
    ])
    rows = [
        {"id": "cash", "amount": 100, "method": "cash", "provider_ref": "receipt-1"},
        {"id": "cash-retry", "amount": 100, "method": "cash", "provider_ref": "receipt-1"},
        {"id": "refund", "amount": 20, "method": "cash", "payment_type": "refund"},
        {"id": "comp", "amount": 10, "method": "discount"},
        {"id": "security", "amount": 30, "method": "security_deposit_application"},
        {"id": "pending", "amount": 800, "method": "card", "status": "pending"},
        {"id": "void", "amount": 900, "method": "cash", "voided": True},
    ]
    await db.payments.insert_many([dict(row, tenant_id="t", folio_id="f") for row in rows])


@pytest.mark.asyncio
async def test_proforma_matches_ledger_without_turning_offsets_into_collection(db, actor, monkeypatch):
    await seed(db, monkeypatch)
    result = await router.generate_folio_proforma("f", actor, None)
    totals = result["totals"]
    assert (totals["grand_total"], totals["net_total"], totals["vat_total"]) == (120, 100, 20)
    assert (totals["payments_total"], totals["collections_total"], totals["non_cash_total"]) == (120, 80, 40)
    assert totals["opening_balance"] == 50 and totals["balance_due"] == 50
    assert result["guest"]["name"] == "Ayşe Deniz" and result["booking"]["room_number"] == "105"
    spa = next(row for row in result["charges"] if row["id"] == "spa")
    assert spa["service_date"] == "2026-11-10" and spa["service_time"] == "15:00"
    assert spa["vat_rate"] is None and spa["net_amount"] == 100
    assert {row["vat_rate"] for row in result["vat_breakdown"]} == {None, 0}
    assert not (await db.folio_charges.find_one({"id": "spa"})).get("service_date"), "Read-only projection must not rewrite history"
    assert await db.payments.count_documents({}) == 7
    assert (await db.folios.find_one({"id": "f"}))["status"] == "open"


@pytest.mark.asyncio
async def test_proforma_surfaces_missing_tax_and_rejects_mixed_currency(db, actor, monkeypatch):
    await seed(db, monkeypatch)
    await db.folio_charges.insert_one({"tenant_id": "t", "folio_id": "f", "id": "legacy", "amount": 15})
    result = await router.generate_folio_proforma("f", actor, None)
    assert result["totals"]["grand_total"] == 135
    assert result["totals"]["tax_breakdown_complete"] is False
    assert result["totals"]["net_total"] is None
    assert result["totals"]["subtotal"] is None
    assert result["totals"]["vat_total"] is None
    assert result["totals"]["balance_due"] == 65
    legacy = next(row for row in result["charges"] if row["id"] == "legacy")
    assert legacy["net_amount"] is None and legacy["subtotal"] is None
    unknown = next(row for row in result["vat_breakdown"] if row["vat_rate"] is None)
    assert unknown["net"] is None and unknown["vat_amount"] is None
    await db.folio_charges.insert_one({"tenant_id": "t", "folio_id": "f", "id": "usd", "total": 10, "currency": "USD"})
    with pytest.raises(HTTPException) as exc:
        await router.generate_folio_proforma("f", actor, None)
    assert exc.value.status_code == 409
    assert "farklı para birimleri" in exc.value.detail


@pytest.mark.asyncio
async def test_folio_details_keep_all_rows_and_use_the_source_service_date(db, monkeypatch):
    await seed(db, monkeypatch)
    await db.folio_charges.insert_many([{"id": f"c-{i}", "tenant_id": "t", "folio_id": "f", "total": 1} for i in range(1001)])
    await db.payments.insert_many([{"id": f"p-{i}", "tenant_id": "t", "folio_id": "f", "amount": 1} for i in range(1001)])
    repo = repository.FolioRepository()
    charges = await repo.get_charges("t", "f")
    assert len(charges) == 1004 and len(await repo.get_payments("t", "f")) == 1008
    assert next(row for row in charges if row["id"] == "spa")["service_date"] == "2026-11-10"
    assert all(row["tenant_id"] == "t" for row in charges)


@pytest.mark.asyncio
async def test_transfer_picker_resolves_room_in_the_same_tenant(db, actor, monkeypatch):
    await seed(db, monkeypatch)
    result = await router.list_folios(status="open", p=PaginationParams(offset=0, limit=50), current_user=actor)
    assert result["folios"][0]["room_number"] == "105"
