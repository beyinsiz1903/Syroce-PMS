"""
NA-001 / NA-002: Night Audit Hardening — Comprehensive Test Suite
=================================================================
Tests the complete night audit lifecycle:
A. Successful full audit run
B. Blocking folio validation
C. Duplicate posting prevention
D. Partial failure / item-level recovery
E. Stale run detection
F. Safe resume behavior
G. No double close for same business_date
H. Business date advancement only after success
I. Abort flow
J. Query endpoints
K. Health metrics
L. No-show handling
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

TENANT = f"test_na_{uuid.uuid4().hex[:8]}"
PROPERTY = "test_property"
BD = "2026-03-22"
BD_NEXT = "2026-03-23"

STALE_THRESHOLD_SECONDS = 900

S_RUNNING = "running"
S_BLOCKED = "blocked"
S_FAILED = "failed"
S_COMPLETED = "completed"
S_PARTIAL = "partial_recovery_required"
IS_PENDING = "pending"
IS_POSTED = "posted"
IS_SKIPPED = "skipped"
ST_COMPLETED = "completed"
ST_POSTING = "posting_charges"
ST_RECONCILING = "reconciling"
ST_VALIDATING = "validating"
DEFAULT_PROPERTY = "default"

COLLECTIONS = [
    "night_audit_runs", "night_audit_run_items", "folio_charges",
    "folios", "bookings", "rooms", "tenant_settings",
    "pms_audit_trail", "night_audit_locks",
]


async def _get_db():
    """Create a fresh Motor client bound to the current event loop."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")
    c = AsyncIOMotorClient(mongo_url)
    return c, c[db_name]


async def _cleanup(db):
    for c in COLLECTIONS:
        await db[c].delete_many({"tenant_id": TENANT})


async def _seed_booking(db, room_rate=1000.0, status="checked_in", booking_id=None, folio_id=None, room_id=None, no_folio=False, no_room=False):
    """Seed a booking with room and folio."""
    bid = booking_id or str(uuid.uuid4())
    rid = room_id or str(uuid.uuid4())
    fid = folio_id or str(uuid.uuid4())

    booking = {
        "id": bid, "tenant_id": TENANT, "status": status,
        "room_id": None if no_room else rid, "folio_id": None if no_folio else fid,
        "room_rate": room_rate, "currency": "TRY",
        "guest_name": "Test Guest",
        "check_in": "2026-03-20", "check_out": "2026-03-25",
    }
    await db.bookings.insert_one({**booking})

    if not no_room:
        await db.rooms.insert_one({
            "id": rid, "tenant_id": TENANT,
            "room_number": f"R-{rid[:6]}", "status": "occupied",
        })

    if not no_folio:
        await db.folios.insert_one({
            "id": fid, "tenant_id": TENANT,
            "booking_id": bid, "status": "open",
            "folio_number": f"F-{fid[:6]}", "balance": 0.0,
        })

    return {"booking_id": bid, "room_id": rid, "folio_id": fid}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _call_engine(func_name, test_client, test_db, *args, **kwargs):
    """Call a core engine function with patched db and client."""
    with patch("core.night_audit_hardened.db", test_db), \
         patch("core.night_audit_hardened.client", test_client):
        from core.night_audit_hardened import (
            start_night_audit, resume_night_audit, abort_night_audit,
            get_run_status, get_runs, get_run_detail, get_run_items,
            detect_stale_runs, get_health_metrics, ensure_night_audit_indexes,
        )
        fn_map = {
            "start_night_audit": start_night_audit,
            "resume_night_audit": resume_night_audit,
            "abort_night_audit": abort_night_audit,
            "get_run_status": get_run_status,
            "get_runs": get_runs,
            "get_run_detail": get_run_detail,
            "get_run_items": get_run_items,
            "detect_stale_runs": detect_stale_runs,
            "get_health_metrics": get_health_metrics,
            "ensure_night_audit_indexes": ensure_night_audit_indexes,
        }
        return await fn_map[func_name](*args, **kwargs)


# ═══════════════════════════════════════════════════════════════
#  A. SUCCESSFUL FULL AUDIT RUN
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_successful_full_audit():
    """Full lifecycle: start → validate → candidates → post → reconcile → date roll → complete."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        seed = await _seed_booking(db, room_rate=2500.0)

        result = await _call_engine("start_night_audit", c, db,
                                     TENANT, PROPERTY, BD, "manual", {"id": "tester"})

        assert result["success"] is True
        run = result["run"]
        assert run["status"] == S_COMPLETED
        assert run["stage"] == ST_COMPLETED
        assert run["candidate_count"] >= 1
        assert run["processed_count"] >= 1
        assert run["failed_count"] == 0
        assert run["completed_at"] is not None

        # Verify folio charge created
        charge = await db.folio_charges.find_one({
            "tenant_id": TENANT, "booking_id": seed["booking_id"],
            "business_date": BD, "charge_type": "room_charge",
        }, {"_id": 0})
        assert charge is not None
        assert charge["amount"] == 2500.0
        assert charge["voided"] is False

        # Verify folio balance updated
        folio = await db.folios.find_one({"id": seed["folio_id"]}, {"_id": 0})
        assert folio["balance"] > 0

        # Verify business date advanced
        settings = await db.tenant_settings.find_one({"tenant_id": TENANT}, {"_id": 0})
        assert settings["business_date"] == BD_NEXT

        # Verify audit trail
        journal = await db.pms_audit_trail.find_one({
            "tenant_id": TENANT, "action": "night_audit_room_charge",
        }, {"_id": 0})
        assert journal is not None
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_successful_audit_multiple_bookings():
    """Multiple bookings processed in single run."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        for rate in [1500.0, 2000.0, 3000.0]:
            await _seed_booking(db, room_rate=rate)

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is True
        assert result["run"]["candidate_count"] >= 3
        assert result["run"]["processed_count"] >= 3

        charges = await db.folio_charges.find({
            "tenant_id": TENANT, "business_date": BD, "charge_type": "room_charge",
        }, {"_id": 0}).to_list(100)
        assert len(charges) >= 3
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  B. BLOCKING FOLIO VALIDATION
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_blocked_on_missing_folio():
    """Booking without folio blocks the audit."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0, no_folio=True)

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is False
        assert result["code"] == "VALIDATION_BLOCKED"

        run = await db.night_audit_runs.find_one({
            "tenant_id": TENANT, "property_id": PROPERTY, "business_date": BD,
        }, {"_id": 0})
        assert run["status"] == S_BLOCKED

        charges = await db.folio_charges.count_documents({"tenant_id": TENANT, "business_date": BD})
        assert charges == 0
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_blocked_on_orphan_checkin():
    """Checked-in booking without room assignment blocks."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0, no_room=True)

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is False
        assert result["code"] == "VALIDATION_BLOCKED"
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  C. DUPLICATE POSTING PREVENTION
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_duplicate_posting_prevented():
    """Same booking/business_date/charge_type cannot be double-posted."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        seed = await _seed_booking(db, room_rate=2000.0)

        # Pre-insert a charge
        await db.folio_charges.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": TENANT,
            "booking_id": seed["booking_id"], "folio_id": seed["folio_id"],
            "charge_category": "room", "charge_type": "room_charge",
            "business_date": BD, "amount": 2000.0, "total": 2240.0,
            "tax_amount": 240.0, "voided": False, "posted_by": "manual",
            "date": _now_iso(), "created_at": _now_iso(),
        })

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is True

        charges = await db.folio_charges.find({
            "tenant_id": TENANT, "booking_id": seed["booking_id"],
            "business_date": BD, "charge_type": "room_charge",
        }, {"_id": 0}).to_list(10)
        assert len(charges) == 1  # Only the original

        # Run item should be skipped
        items = await db.night_audit_run_items.find({
            "run_id": result["run"]["id"], "booking_id": seed["booking_id"],
        }, {"_id": 0}).to_list(5)
        assert len(items) == 1
        assert items[0]["status"] == IS_SKIPPED
        assert items[0]["reason"] == "already_posted_for_business_date"
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  D. PARTIAL FAILURE (ITEM-LEVEL)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_zero_rate_booking_skipped():
    """Zero rate bookings are skipped, not failing the audit."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=0.0)
        seed_good = await _seed_booking(db, room_rate=1500.0)

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is True
        assert result["run"]["skipped_count"] >= 1
        assert result["run"]["processed_count"] >= 1

        charge = await db.folio_charges.find_one({
            "tenant_id": TENANT, "booking_id": seed_good["booking_id"],
            "business_date": BD, "charge_type": "room_charge",
        }, {"_id": 0})
        assert charge is not None
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  E. STALE RUN DETECTION
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stale_run_detection():
    """Running run with expired heartbeat detected as stale."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
        await db.night_audit_runs.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": TENANT,
            "property_id": PROPERTY, "business_date": BD,
            "status": S_RUNNING, "stage": ST_POSTING,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 10, "processed_count": 3,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": [],
            "started_at": stale_time, "completed_at": None,
            "last_heartbeat_at": stale_time,
            "created_at": stale_time, "updated_at": stale_time,
        })

        stale = await _call_engine("detect_stale_runs", c, db)
        assert len(stale) >= 1
        assert any(r["tenant_id"] == TENANT for r in stale)
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_stale_run_auto_recovery():
    """Starting audit when stale one exists marks it for recovery."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 120)).isoformat()
        stale_id = str(uuid.uuid4())
        await db.night_audit_runs.insert_one({
            "id": stale_id, "tenant_id": TENANT,
            "property_id": PROPERTY, "business_date": BD,
            "status": S_RUNNING, "stage": ST_POSTING,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 0, "processed_count": 0,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": [],
            "started_at": stale_time, "completed_at": None,
            "last_heartbeat_at": stale_time,
            "created_at": stale_time, "updated_at": stale_time,
        })

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is False
        assert result["code"] == "STALE_RECOVERED"

        updated = await db.night_audit_runs.find_one({"id": stale_id}, {"_id": 0})
        assert updated["status"] == S_PARTIAL
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  F. SAFE RESUME BEHAVIOR
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_resume_failed_run():
    """Failed run can be resumed; charges post correctly."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        seed = await _seed_booking(db, room_rate=3000.0)

        run_id = str(uuid.uuid4())
        now = _now_iso()
        await db.night_audit_runs.insert_one({
            "id": run_id, "tenant_id": TENANT, "property_id": PROPERTY,
            "business_date": BD, "status": S_FAILED, "stage": ST_POSTING,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 1, "processed_count": 0,
            "failed_count": 1, "skipped_count": 0,
            "warnings": [], "errors": ["Test failure"],
            "started_at": now, "completed_at": now,
            "last_heartbeat_at": now, "created_at": now, "updated_at": now,
        })
        await db.night_audit_run_items.insert_one({
            "id": str(uuid.uuid4()), "run_id": run_id, "tenant_id": TENANT,
            "booking_id": seed["booking_id"], "folio_id": seed["folio_id"],
            "room_id": seed["room_id"], "posting_type": "room_charge",
            "posting_date": BD, "amount": 3000.0,
            "tax_amount": 360.0, "total": 3360.0,
            "tax_breakdown": {"vat": 300.0, "accommodation_tax": 60.0},
            "currency": "TRY", "status": "failed",
            "reason": "Test failure", "journal_entry_id": None,
            "created_at": now, "updated_at": now,
        })

        result = await _call_engine("resume_night_audit", c, db, TENANT, run_id)
        assert result["success"] is True
        assert result["run"]["status"] == S_COMPLETED

        charge = await db.folio_charges.find_one({
            "tenant_id": TENANT, "booking_id": seed["booking_id"],
            "business_date": BD, "charge_type": "room_charge",
        }, {"_id": 0})
        assert charge is not None

        settings = await db.tenant_settings.find_one({"tenant_id": TENANT}, {"_id": 0})
        assert settings["business_date"] == BD_NEXT
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_resume_posted_items_not_reposted():
    """Resume does not re-post already posted items."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        seed = await _seed_booking(db, room_rate=1000.0)

        run_id = str(uuid.uuid4())
        now = _now_iso()
        await db.night_audit_runs.insert_one({
            "id": run_id, "tenant_id": TENANT, "property_id": PROPERTY,
            "business_date": BD, "status": S_PARTIAL, "stage": ST_RECONCILING,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 1, "processed_count": 1,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": ["Partial"],
            "started_at": now, "completed_at": now,
            "last_heartbeat_at": now, "created_at": now, "updated_at": now,
        })
        await db.night_audit_run_items.insert_one({
            "id": str(uuid.uuid4()), "run_id": run_id, "tenant_id": TENANT,
            "booking_id": seed["booking_id"], "folio_id": seed["folio_id"],
            "room_id": seed["room_id"], "posting_type": "room_charge",
            "posting_date": BD, "amount": 1000.0,
            "tax_amount": 120.0, "total": 1120.0,
            "tax_breakdown": {}, "currency": "TRY",
            "status": IS_POSTED, "reason": None, "journal_entry_id": "j1",
            "created_at": now, "updated_at": now,
        })
        await db.folio_charges.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": TENANT,
            "booking_id": seed["booking_id"], "folio_id": seed["folio_id"],
            "charge_category": "room", "charge_type": "room_charge",
            "business_date": BD, "amount": 1000.0, "total": 1120.0,
            "tax_amount": 120.0, "voided": False, "posted_by": "night_audit",
            "date": now, "run_id": run_id, "created_at": now,
        })

        result = await _call_engine("resume_night_audit", c, db, TENANT, run_id)
        assert result["success"] is True

        charges = await db.folio_charges.find({
            "tenant_id": TENANT, "booking_id": seed["booking_id"],
            "business_date": BD, "charge_type": "room_charge",
        }, {"_id": 0}).to_list(10)
        assert len(charges) == 1
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_resume_invalid_state():
    """Cannot resume a completed run."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        run_id = str(uuid.uuid4())
        now = _now_iso()
        await db.night_audit_runs.insert_one({
            "id": run_id, "tenant_id": TENANT, "property_id": PROPERTY,
            "business_date": BD, "status": S_COMPLETED, "stage": ST_COMPLETED,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 0, "processed_count": 0,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": [],
            "started_at": now, "completed_at": now,
            "last_heartbeat_at": now, "created_at": now, "updated_at": now,
        })

        result = await _call_engine("resume_night_audit", c, db, TENANT, run_id)
        assert result["success"] is False
        assert result["code"] == "INVALID_STATE"
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  G. NO DOUBLE CLOSE
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_double_close():
    """Second audit for same date rejected."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0)

        r1 = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert r1["success"] is True

        r2 = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert r2["success"] is False
        assert r2["code"] == "ALREADY_COMPLETED"
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_no_concurrent_runs():
    """Cannot start when one is already running."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        now = _now_iso()
        await db.night_audit_runs.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": TENANT,
            "property_id": PROPERTY, "business_date": BD,
            "status": S_RUNNING, "stage": ST_POSTING,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 0, "processed_count": 0,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": [],
            "started_at": now, "completed_at": None,
            "last_heartbeat_at": now,
            "created_at": now, "updated_at": now,
        })

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is False
        assert result["code"] == "ALREADY_RUNNING"
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  H. BUSINESS DATE ONLY AFTER SUCCESS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_bd_not_advanced_on_block():
    """Business date must NOT advance when audit is blocked."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await db.tenant_settings.update_one(
            {"tenant_id": TENANT}, {"$set": {"business_date": BD, "tenant_id": TENANT}}, upsert=True,
        )
        await _seed_booking(db, room_rate=1000.0, no_folio=True)

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is False

        settings = await db.tenant_settings.find_one({"tenant_id": TENANT}, {"_id": 0})
        assert settings["business_date"] == BD
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_bd_advances_correctly():
    """Business date advances to next day after success."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await db.tenant_settings.update_one(
            {"tenant_id": TENANT}, {"$set": {"business_date": BD, "tenant_id": TENANT}}, upsert=True,
        )
        await _seed_booking(db, room_rate=1000.0)

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is True

        settings = await db.tenant_settings.find_one({"tenant_id": TENANT}, {"_id": 0})
        assert settings["business_date"] == BD_NEXT
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  I. ABORT FLOW
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_abort_running_run():
    """Abort sets status to failed and cancels pending items."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        run_id = str(uuid.uuid4())
        now = _now_iso()
        await db.night_audit_runs.insert_one({
            "id": run_id, "tenant_id": TENANT, "property_id": PROPERTY,
            "business_date": BD, "status": S_RUNNING, "stage": ST_POSTING,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 2, "processed_count": 0,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": [],
            "started_at": now, "completed_at": None,
            "last_heartbeat_at": now, "created_at": now, "updated_at": now,
        })
        await db.night_audit_run_items.insert_many([{
            "id": str(uuid.uuid4()), "run_id": run_id, "tenant_id": TENANT,
            "booking_id": f"b{i}", "folio_id": f"f{i}", "room_id": f"r{i}",
            "posting_type": "room_charge", "posting_date": BD,
            "amount": 1000, "tax_amount": 120, "total": 1120,
            "currency": "TRY", "status": IS_PENDING, "reason": None,
            "journal_entry_id": None, "created_at": now, "updated_at": now,
        } for i in range(2)])

        result = await _call_engine("abort_night_audit", c, db, TENANT, run_id, {"id": "admin"})
        assert result["success"] is True

        run = await db.night_audit_runs.find_one({"id": run_id}, {"_id": 0})
        assert run["status"] == S_FAILED

        pending = await db.night_audit_run_items.count_documents({"run_id": run_id, "status": IS_PENDING})
        assert pending == 0
        skipped = await db.night_audit_run_items.count_documents({
            "run_id": run_id, "status": IS_SKIPPED, "reason": "run_aborted",
        })
        assert skipped == 2
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_abort_completed_fails():
    """Cannot abort a completed run."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        run_id = str(uuid.uuid4())
        now = _now_iso()
        await db.night_audit_runs.insert_one({
            "id": run_id, "tenant_id": TENANT, "property_id": PROPERTY,
            "business_date": BD, "status": S_COMPLETED, "stage": ST_COMPLETED,
            "trigger_source": "test", "started_by": {},
            "lock_token": str(uuid.uuid4()),
            "candidate_count": 0, "processed_count": 0,
            "failed_count": 0, "skipped_count": 0,
            "warnings": [], "errors": [],
            "started_at": now, "completed_at": now,
            "last_heartbeat_at": now, "created_at": now, "updated_at": now,
        })

        result = await _call_engine("abort_night_audit", c, db, TENANT, run_id)
        assert result["success"] is False
        assert result["code"] == "ALREADY_COMPLETED"
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  J. QUERY ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_run_status():
    """get_run_status returns business date and latest run."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0)
        await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)

        status = await _call_engine("get_run_status", c, db, TENANT, PROPERTY)
        assert status["current_business_date"] == BD_NEXT
        assert status["latest_run"] is not None
        assert status["latest_run"]["status"] == S_COMPLETED
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_get_runs_list():
    """get_runs lists all runs."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0)
        await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)

        data = await _call_engine("get_runs", c, db, TENANT)
        assert data["total"] >= 1
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_get_run_items():
    """get_run_items lists items for a run."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0)
        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        run_id = result["run"]["id"]

        items = await _call_engine("get_run_items", c, db, TENANT, run_id)
        assert items["total"] >= 1
    finally:
        await _cleanup(db)
        c.close()


@pytest.mark.asyncio
async def test_get_run_detail():
    """get_run_detail returns a specific run."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        await _seed_booking(db, room_rate=1000.0)
        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        run_id = result["run"]["id"]

        detail = await _call_engine("get_run_detail", c, db, TENANT, run_id)
        assert detail is not None
        assert detail["id"] == run_id
    finally:
        await _cleanup(db)
        c.close()


# ═══════════════════════════════════════════════════════════════
#  K. HEALTH METRICS
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_metrics():
    """Health metrics return valid data."""
    c, db = await _get_db()
    try:
        metrics = await _call_engine("get_health_metrics", c, db)
        assert "running_count" in metrics
        assert "blocked_count" in metrics
        assert "stale_running_count" in metrics
    finally:
        c.close()


# ═══════════════════════════════════════════════════════════════
#  L. NO-SHOW HANDLING
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_show_candidate():
    """Confirmed bookings past check-in are processed as no-show."""
    c, db = await _get_db()
    try:
        await _cleanup(db)
        await _call_engine("ensure_night_audit_indexes", c, db)
        bid = str(uuid.uuid4())
        fid = str(uuid.uuid4())
        await db.bookings.insert_one({
            "id": bid, "tenant_id": TENANT, "status": "confirmed",
            "room_id": str(uuid.uuid4()), "folio_id": fid,
            "room_rate": 1500.0, "check_in": BD, "check_out": "2026-03-24",
            "guest_name": "No Show Guest",
            "cancellation_policy": {"no_show_fee": 500.0},
        })
        await db.folios.insert_one({
            "id": fid, "tenant_id": TENANT, "booking_id": bid,
            "status": "open", "folio_number": "F-NS", "balance": 0.0,
        })

        result = await _call_engine("start_night_audit", c, db, TENANT, PROPERTY, BD)
        assert result["success"] is True

        items = await db.night_audit_run_items.find({
            "run_id": result["run"]["id"], "posting_type": "no_show",
        }, {"_id": 0}).to_list(10)
        assert len(items) >= 1

        booking = await db.bookings.find_one({"id": bid}, {"_id": 0})
        assert booking["status"] == "no_show"
    finally:
        await _cleanup(db)
        c.close()
