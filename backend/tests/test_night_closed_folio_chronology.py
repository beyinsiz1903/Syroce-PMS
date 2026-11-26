"""Real Mongo regression: current closed status does not prove a post-close write."""
from datetime import UTC, datetime

from common.context import OperationContext
from domains.pms.night_audit.financial_service import FinancialService

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
DAY = "2026-11-11"

async def run_check(db):
    service = FinancialService()
    service._db = db
    result = await service.get_integrity_check(OperationContext(tenant_id="A", actor_id="u", actor_role="admin"), DAY)
    return {row["check"]: row for row in result.data["checks"]}

async def seed(db, closed_at="2026-11-15T12:00:00Z", **charge):
    await db.folios.insert_one({"tenant_id":"A", "id":"f", "status":"closed", "closed_at":closed_at})
    await db.folio_charges.insert_one({"tenant_id":"A", "id":"c", "folio_id":"f", "date":DAY, "amount":100, **charge})

async def test_valid_historical_charge_is_not_post_close_error(ledger_db):
    await seed(ledger_db, created_at="2026-11-11T12:00:00Z")
    checks = await run_check(ledger_db)
    assert checks["closed_folio_charges"]["count"] == 0
    assert checks["closed_folio_charges"]["status"] == "pass"

async def test_backdated_charge_created_after_closure_is_error(ledger_db):
    await seed(ledger_db, created_at="2026-11-16T12:00:00Z")
    row = (await run_check(ledger_db))["closed_folio_charges"]
    assert row["status"] == "error" and row["count"] == 1
    assert row["items"][0]["folio_id"] == "f"

async def test_unknown_chronology_is_warning_not_false_error_or_pass(ledger_db):
    await seed(ledger_db)
    checks = await run_check(ledger_db)
    assert checks["closed_folio_charges"]["count"] == 0
    assert checks["closed_folio_chronology_unknown"]["status"] == "warning"
    assert checks["closed_folio_chronology_unknown"]["count"] == 1

async def test_bson_and_offset_timestamps_compare_as_instants(ledger_db):
    await seed(ledger_db, closed_at=datetime(2026,11,15,12,tzinfo=UTC), created_at="2026-11-15T14:59:59+03:00")
    assert (await run_check(ledger_db))["closed_folio_charges"]["count"] == 0

async def test_service_date_is_never_used_as_write_timestamp(ledger_db):
    await seed(ledger_db, date=DAY, posted_at=DAY)
    checks = await run_check(ledger_db)
    assert checks["closed_folio_chronology_unknown"]["count"] == 1

async def test_other_tenant_closed_folio_does_not_leak(ledger_db):
    await seed(ledger_db, created_at="2026-11-16T12:00:00Z", tenant_id="B")
    assert (await run_check(ledger_db))["closed_folio_charges"]["count"] == 0

async def test_voided_post_close_charge_is_not_active_error(ledger_db):
    await seed(ledger_db, created_at="2026-11-16T12:00:00Z", voided=True)
    assert (await run_check(ledger_db))["closed_folio_charges"]["count"] == 0

async def test_missing_closure_timestamp_remains_reviewable(ledger_db):
    await seed(ledger_db, closed_at=None, created_at="2026-11-16T12:00:00Z")
    assert (await run_check(ledger_db))["closed_folio_chronology_unknown"]["count"] == 1

async def test_equal_instants_are_not_post_close(ledger_db):
    await seed(ledger_db, created_at="2026-11-15T15:00:00+03:00")
    assert (await run_check(ledger_db))["closed_folio_charges"]["status"] == "pass"

async def test_no_500_closed_folio_cutoff(ledger_db):
    await ledger_db.folios.insert_many([{"tenant_id":"A", "id":f"f{i}", "status":"closed"} for i in range(501)])
    await seed(ledger_db, created_at="2026-11-16T12:00:00Z")
    assert (await run_check(ledger_db))["closed_folio_charges"]["count"] == 1
