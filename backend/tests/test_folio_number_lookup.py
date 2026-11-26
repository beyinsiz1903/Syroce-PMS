"""Human folio numbers resolve to a tenant-scoped canonical account."""
from modules.pms_core import folio_detail_service as detail

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


async def seed(db, tenant, folio_id, amount):
    await db.folios.insert_one({"tenant_id": tenant, "id": folio_id, "folio_number": "F-2026-00413", "booking_id": "b", "currency": "TRY", "status": "open"})
    await db.bookings.insert_one({"tenant_id": tenant, "id": "b", "currency": "TRY"})
    await db.folio_charges.insert_one({"tenant_id": tenant, "id": "c", "folio_id": folio_id, "amount": amount, "currency": "TRY", "date": "2026-11-12"})


async def test_number_resolves_canonical_folio_and_only_its_ledger(ledger_db, monkeypatch):
    monkeypatch.setattr(detail, "db", ledger_db)
    await seed(ledger_db, "A", "own", 25)
    await seed(ledger_db, "B", "foreign", 999)
    result = await detail.FolioDetailService().get_folio_detail("A", "F-2026-00413")
    assert result["success"] is True
    assert result["folio"]["id"] == "own"
    assert result["summary"]["balance"] == 25
    assert len(result["charges"]) == 1


async def test_foreign_number_is_not_resolved(ledger_db, monkeypatch):
    monkeypatch.setattr(detail, "db", ledger_db)
    await seed(ledger_db, "B", "foreign", 999)
    result = await detail.FolioDetailService().get_folio_detail("A", "F-2026-00413")
    assert result["success"] is False


async def test_duplicate_number_does_not_select_arbitrary_account(ledger_db, monkeypatch):
    monkeypatch.setattr(detail, "db", ledger_db)
    await seed(ledger_db, "A", "one", 25)
    await seed(ledger_db, "A", "two", 30)
    result = await detail.FolioDetailService().get_folio_detail("A", "F-2026-00413")
    assert result["success"] is False
