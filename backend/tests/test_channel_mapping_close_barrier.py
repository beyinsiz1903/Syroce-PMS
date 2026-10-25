"""Local Mongo proof: quarantine cannot become a check-in/no-show or pass close."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import night_audit_hardened as audit
from core.channel_mapping_issues import group_mapping_issues, is_mapping_hold, load_mapping_issues, mapping_close_blocker
from routers import cm_conflict_queue as queue
from routers import pms_rooms

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
BD = "2026-10-24"


def hold(**fields):
    return {"id": "hold-a", "tenant_id": "A", "property_id": "A", "status": "pending_mapping",
            "source": {"provider": "exely", "kind": "ota_unmatched_hold"},
            "external_reservation_id": "EXT-1", "room_id": None,
            "check_in": "2026-10-15T14:00:00", "check_out": "2026-10-16T12:00:00", **fields}


@pytest.mark.parametrize("arrival,blocked", [("2026-10-23", True), (BD, True), (BD + "T14:00:00+03:00", True),
                                           ("2026-10-25", False), (None, True), ("invalid", True)])
def test_mapping_close_uses_business_date_not_wall_clock(arrival, blocked):
    issues = group_mapping_issues([("bookings", hold(check_in=arrival))], BD)
    assert issues[0]["blocks_close"] is blocked
    blocker = mapping_close_blocker(issues)
    assert bool(blocker) is blocked
    if blocker:
        assert blocker["bypassable"] is False and blocker["action"] == "review_channel_mapping"


def test_exact_source_duplicates_group_without_mutation_or_guessing_guest_identity():
    first, second = hold(), hold(id="hold-b")
    original = deepcopy([first, second])
    issues = group_mapping_issues([("bookings", first), ("bookings", second)], BD)
    assert len(issues) == 1 and issues[0]["booking_ids"] == ["hold-a", "hold-b"]
    assert issues[0]["duplicate_hold_count"] == 1 and [first, second] == original
    for replacement in [{"external_reservation_id": "EXT-2"}, {"source": {"provider": "hotelrunner"}}, {"property_id": "OTHER"}]:
        assert len(group_mapping_issues([("bookings", first), ("bookings", hold(**replacement))], BD)) == 2


@pytest.mark.parametrize("marker", [{"status": "pending_mapping"}, {"booking_source": "ota_unmatched_hold"},
                                    {"source": {"kind": "ota_unmatched_hold"}}, {"is_inventory_hold": True}])
def test_legacy_markers_are_not_normal_operational_arrivals(marker):
    assert is_mapping_hold(marker)
    assert not is_mapping_hold({"status": "confirmed", "allocation_source": "pending_assignment"})


async def seed(db):
    await db.tenant_settings.insert_one({"tenant_id": "A", "business_date": BD})
    await db.bookings.insert_many([hold(), hold(id="hold-b"), hold(id="other-tenant", tenant_id="B"),
                                  hold(id="old-cancel", status="cancelled", external_reservation_id="cancelled")])
    await db.exely_reservations.insert_one({"tenant_id": "A", "id": "inbox", "external_id": "EXT-1", "provider": "exely",
        "state": "confirmed", "pms_status": "pending_mapping", "checkin_date": "2026-10-15", "guest_email": "not-in-projection"})
    await db.night_audit_runs.insert_one({"id": "run", "tenant_id": "A", "property_id": "A", "business_date": BD, "status": "running"})


async def test_mongo_queue_deduplicates_hold_and_inbox_preserves_all_documents_and_selected_tenant(ledger_db, monkeypatch):
    await seed(ledger_db)
    before = await ledger_db.bookings.find({}).to_list(None)
    monkeypatch.setattr(queue, "db", ledger_db)
    async def load(tid, bd):
        return await load_mapping_issues(tid, bd, database=ledger_db)
    monkeypatch.setattr(queue, "load_mapping_issues", load)
    result = await queue.mapping_issues(SimpleNamespace(tenant_id="A", role="super_admin"), None)
    assert result["total"] == 1 and result["business_date"] == BD
    issue = result["items"][0]
    assert issue["blocks_close"] is True and len(issue["booking_ids"]) == 2
    assert len(issue["source_records"]) == 3
    assert "guest_email" not in str(result) and "not-in-projection" not in str(result)
    assert before == await ledger_db.bookings.find({}).to_list(None)
    assert await ledger_db.folio_charges.count_documents({}) == 0


async def test_mongo_new_inbox_only_exely_hotelrunner_and_import_review_are_not_invisible(ledger_db):
    for provider in ("exely", "hotelrunner"):
        await ledger_db[f"{provider}_reservations"].insert_many([
            {"tenant_id": "A", "id": provider, "provider": provider, "external_id": "source-1", "pms_status": "pending_mapping", "state": "confirmed", "checkin_date": BD},
            {"tenant_id": "A", "id": provider + "-cancel", "provider": provider, "external_id": "source-2", "pms_status": "pending_mapping", "state": "cancelled", "checkin_date": BD},
        ])
    await ledger_db.imported_reservations.insert_one({"tenant_id": "A", "id": "unified", "provider": "hotelrunner",
        "external_reservation_id": "new-source", "import_status": "review_required", "review_reason": "unmapped_rate_plan", "arrival_date": BD})
    issues = await load_mapping_issues("A", BD, database=ledger_db)
    assert len(issues) == 3 and all(item["blocks_close"] for item in issues)
    assert all(item["booking_ids"] == [] for item in issues)


@pytest.mark.parametrize("skip", [False, True])
async def test_mongo_normal_and_skipped_validation_close_block_before_any_posting(ledger_db, monkeypatch, skip):
    await seed(ledger_db)
    monkeypatch.setattr(audit, "db", ledger_db)
    result = await audit._execute_pipeline("run", "A", "A", BD, skip_validations=skip)
    assert result["success"] is False and result["code"] == "VALIDATION_BLOCKED"
    assert (await ledger_db.tenant_settings.find_one({"tenant_id": "A"}))["business_date"] == BD
    assert await ledger_db.night_audit_run_items.count_documents({}) == 0
    assert await ledger_db.folio_charges.count_documents({}) == 0
    assert (await ledger_db.bookings.find_one({"id": "hold-a"}))["status"] == "pending_mapping"


async def test_mongo_preview_and_execution_agree_and_future_issues_only_warn(ledger_db, monkeypatch):
    await seed(ledger_db)
    monkeypatch.setattr(audit, "db", ledger_db)
    preview = await audit.build_audit_preview.__wrapped__("A", "A")
    blocker = next(item for item in preview["blockers"] if item["category"] == "unresolved_channel_mapping")
    assert preview["ready"] is False and blocker["count"] == 1
    await ledger_db.bookings.update_many({"tenant_id": "A"}, {"$set": {"check_in": "2026-10-25"}})
    await ledger_db.exely_reservations.update_many({"tenant_id": "A"}, {"$set": {"checkin_date": "2026-10-25"}})
    await ledger_db.night_audit_runs.delete_many({})  # Isolated test run, not a business record repair.
    preview = await audit.build_audit_preview.__wrapped__("A", "A")
    assert not any(item["category"] == "unresolved_channel_mapping" for item in preview["blockers"])
    assert next(item for item in preview["warnings"] if item["category"] == "future_channel_mapping")["count"] == 1


async def test_resume_barrier_and_final_roll_recheck_prevent_partial_run_bypass(ledger_db, monkeypatch):
    await seed(ledger_db)
    monkeypatch.setattr(audit, "db", ledger_db)
    post = AsyncMock()
    monkeypatch.setattr(audit, "_post_charges", post)
    assert (await audit._posting_and_close("run", "A", BD))["code"] == "VALIDATION_BLOCKED"
    post.assert_not_awaited()
    with pytest.raises(ValueError, match="kanal rezervasyonunun"):
        await audit._roll_business_date("A", BD, "run")
    assert (await ledger_db.tenant_settings.find_one({"tenant_id": "A"}))["business_date"] == BD


async def test_mapping_read_failure_is_fail_closed_even_with_skip(ledger_db, monkeypatch):
    await seed(ledger_db)
    monkeypatch.setattr(audit, "db", ledger_db)
    monkeypatch.setattr(audit, "load_mapping_issues", AsyncMock(side_effect=RuntimeError("inbox read unavailable")))
    assert (await audit._execute_pipeline("run", "A", "A", BD, skip_validations=True))["code"] == "VALIDATION_ERROR"
    assert (await ledger_db.tenant_settings.find_one({"tenant_id": "A"}))["business_date"] == BD


async def test_hold_never_becomes_no_show_candidate(ledger_db, monkeypatch):
    await seed(ledger_db)
    monkeypatch.setattr(audit, "db", ledger_db)
    assert await audit._build_candidate_set("A", "A", BD, "run") == 0
    assert await ledger_db.night_audit_run_items.count_documents({"posting_type": "no_show"}) == 0


@pytest.mark.parametrize("status", ["pending_mapping", "confirmed"])
async def test_manual_no_show_api_rejects_mapping_hold_before_virtual_room_creation(ledger_db, monkeypatch, status):
    await ledger_db.bookings.insert_one(hold(status=status))
    monkeypatch.setattr(pms_rooms, "db", ledger_db)
    with pytest.raises(HTTPException) as exc:
        await pms_rooms.no_show_to_virtual_room(pms_rooms.NoShowVirtualRequest(booking_id="hold-a"), SimpleNamespace(tenant_id="A"), None)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "CHANNEL_MAPPING_REQUIRED"
    assert await ledger_db.rooms.count_documents({}) == 0
    assert (await ledger_db.bookings.find_one({"id": "hold-a"}))["status"] == status


async def test_conflict_queue_superadmin_is_scoped_to_selected_tenant(ledger_db, monkeypatch):
    await ledger_db.bookings.insert_many([{"id": "one", "tenant_id": tid, "status": "confirmed", "allocation_source": "pending_assignment", "room_id": None} for tid in ["A", "B"]])
    monkeypatch.setattr(queue, "db", ledger_db)
    user = SimpleNamespace(tenant_id="A", role="super_admin")
    result = await queue.list_conflict_queue(200, 0, user, None)
    assert result["total"] == 1
    assert (await queue.conflict_queue_count(user, None))["count"] == 1
    assert (await queue.conflict_queue_stats(user, None))["total"] == 1


async def test_legacy_engine_and_report_close_cannot_bypass_mapping_barrier(ledger_db, monkeypatch):
    from modules.pms_core import night_audit_engine as legacy
    from routers.reports_pkg import night_audit as reports

    await seed(ledger_db)
    monkeypatch.setattr(legacy, "db", ledger_db)
    engine = legacy.NightAuditEngine()
    assert (await engine.run_night_audit("A", BD, "operator"))["code"] == "CHANNEL_MAPPING_REQUIRED"
    assert await ledger_db.night_audit_locks.count_documents({}) == 0
    with pytest.raises(ValueError):
        await engine._roll_business_date("A", BD, "run", "operator")
    monkeypatch.setattr(reports, "db", ledger_db)
    user = SimpleNamespace(tenant_id="A", id="operator")
    with pytest.raises(HTTPException) as exc:
        await reports.run_night_audit(BD, user, None)
    assert exc.value.status_code == 409
    await ledger_db.night_audits.insert_one({"id": "old-run", "tenant_id": "A", "status": "in_progress", "audit_date": BD})
    monkeypatch.setattr(reports, "get_current_user", AsyncMock(return_value=user))
    with pytest.raises(HTTPException) as exc:
        await reports.end_of_day_audit("old-run", None, None)
    assert exc.value.status_code == 409
    assert (await ledger_db.night_audits.find_one({"id": "old-run"}))["status"] == "in_progress"


async def test_legacy_domain_service_cannot_skip_mapping_barrier(ledger_db):
    from common.context import OperationContext
    from domains.pms.night_audit.service import NightAuditCoreService

    await seed(ledger_db)
    service = object.__new__(NightAuditCoreService)
    service._db = ledger_db
    result = await NightAuditCoreService.run_night_audit.__wrapped__(service, OperationContext(tenant_id="A", actor_id="operator"), BD, skip_validations=True)
    assert not result.ok and result.code == "CHANNEL_MAPPING_REQUIRED"
    with pytest.raises(ValueError):
        await service._roll_business_date(OperationContext(tenant_id="A", actor_id="operator"), BD, "run")
    assert (await ledger_db.tenant_settings.find_one({"tenant_id": "A"}))["business_date"] == BD


@pytest.mark.parametrize("skip", [True, False])
async def test_dry_run_reports_mapping_blocker_without_financial_or_booking_changes(ledger_db, monkeypatch, skip):
    await seed(ledger_db)
    monkeypatch.setattr(audit, "db", ledger_db)
    before = await ledger_db.bookings.find({}).to_list(None)
    result = await audit._execute_pipeline("run", "A", "A", BD, skip_validations=skip, dry_run=True)
    assert result["success"] is True and result["blockers"]
    assert await ledger_db.bookings.find({}).to_list(None) == before
    assert (await ledger_db.tenant_settings.find_one({"tenant_id": "A"}))["business_date"] == BD
    assert await ledger_db.folio_charges.count_documents({}) == 0
