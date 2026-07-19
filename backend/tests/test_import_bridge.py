"""
DATA-001: Comprehensive Test Suite for Import Bridge
=====================================================
Tests the full lifecycle:
  1. Import decision classification
  2. Import record creation + duplicate rejection
  3. Successful auto-import (booking created via atomic core)
  4. Duplicate prevention (booking source check)
  5. Review required on mapping failure
  6. Retry scheduling on transient failure
  7. Failed after max retries
  8. Atomic claim under concurrency
  9. Admin retry / approve / dismiss flow
  10. Lineage linking
  11. Error classification
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

COLL_IMPORTED = "imported_reservations"
COLL_BOOKINGS = "bookings"
COLL_LINEAGE = "reservation_lineage"
COLL_AUDIT = "pms_audit_trail"

TEST_TENANT = f"test-import-{uuid.uuid4().hex[:6]}"
TEST_PROPERTY = f"prop-import-{uuid.uuid4().hex[:6]}"
TEST_PROVIDER = "exely"
TEST_CONNECTOR = "test-connector-001"


async def _get_db():
    """Create a fresh Motor client for testing (same loop)."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def _cleanup(db):
    for coll in [
        COLL_IMPORTED,
        COLL_BOOKINGS,
        COLL_LINEAGE,
        COLL_AUDIT,
        "outbox_events",
    ]:
        await db[coll].delete_many({"tenant_id": TEST_TENANT})

    await db["room_mappings"].delete_many({"tenant_id": TEST_TENANT})
    await db["rate_plan_mappings"].delete_many({"tenant_id": TEST_TENANT})


async def _setup_mappings(db):
    """Create room and rate plan mappings for test provider."""
    await db["room_mappings"].insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": TEST_TENANT,
        "property_id": TEST_PROPERTY,
        "provider": TEST_PROVIDER,
        "pms_room_type_id": "room-type-std",
        "pms_room_type_name": "Standard Room",
        "provider_room_code": "STD",
        "is_active": True,
    })
    await db["rate_plan_mappings"].insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": TEST_TENANT,
        "property_id": TEST_PROPERTY,
        "provider": TEST_PROVIDER,
        "pms_rate_plan_id": "rate-bar",
        "pms_rate_plan_name": "Best Available Rate",
        "provider_rate_code": "BAR",
        "is_active": True,
    })


def _make_lineage(ext_res_id=None, **overrides):
    """Create a test lineage-like dict."""
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": TEST_TENANT,
        "property_id": TEST_PROPERTY,
        "provider": TEST_PROVIDER,
        "connection_id": TEST_CONNECTOR,
        "external_reservation_id": ext_res_id or f"EXT-{uuid.uuid4().hex[:8]}",
        "payload_hash": uuid.uuid4().hex[:16],
        "guest_name": "Test Guest",
        "guest_email": "test@example.com",
        "guest_phone": "+905551234567",
        "arrival_date": "2026-04-01",
        "departure_date": "2026-04-05",
        "room_type_code": "STD",
        "rate_plan_code": "BAR",
        "adults": 2,
        "children": 0,
        "total_amount": 1500.0,
        "currency": "TRY",
        "status": "confirmed",
        "source_system": "booking.com",
        **overrides,
    }


# ═══════════════════════════════════════════════════════════════════
# 1. Import Decision Classification
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_decision_eligible_for_auto_import():
    from core.import_decision import classify_for_import
    lineage = _make_lineage()
    status, reason = classify_for_import(lineage, {"pms_room_type_id": "std"}, {"pms_rate_plan_id": "bar"})
    assert status == "pending_auto_import"
    assert reason is None


@pytest.mark.asyncio
async def test_decision_review_unmapped_room():
    from core.import_decision import classify_for_import
    lineage = _make_lineage()
    status, reason = classify_for_import(lineage, None, {"pms_rate_plan_id": "bar"})
    assert status == "review_required"
    assert reason == "unmapped_room_type"


@pytest.mark.asyncio
async def test_decision_review_unmapped_rate():
    from core.import_decision import classify_for_import
    lineage = _make_lineage()
    status, reason = classify_for_import(lineage, {"pms_room_type_id": "std"}, None)
    assert status == "review_required"
    assert reason == "unmapped_rate_plan"


@pytest.mark.asyncio
async def test_decision_review_cancelled():
    from core.import_decision import classify_for_import
    lineage = _make_lineage(status="cancelled")
    status, reason = classify_for_import(lineage, {}, {})
    assert status == "review_required"
    assert reason == "reservation_cancelled"


@pytest.mark.asyncio
async def test_decision_review_invalid_dates():
    from core.import_decision import classify_for_import
    lineage = _make_lineage(arrival_date="2026-04-05", departure_date="2026-04-01")
    status, reason = classify_for_import(lineage, {}, {})
    assert status == "review_required"
    assert reason == "invalid_date_range"


@pytest.mark.asyncio
async def test_decision_review_missing_guest():
    from core.import_decision import classify_for_import
    lineage = _make_lineage(guest_name="")
    status, reason = classify_for_import(lineage, {}, {})
    assert status == "review_required"
    assert reason == "missing_guest_identity"


# ═══════════════════════════════════════════════════════════════════
# 2. Import Record Creation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_import_record():
    client, db = await _get_db()
    try:
        await _cleanup(db)

        # Ensure indexes
        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()
        with patch("core.import_bridge_service.db", db):
            from core.import_bridge_service import create_import_record
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)

        assert record is not None
        assert record["import_status"] == "pending_auto_import"
        assert record["external_reservation_id"] == lineage["external_reservation_id"]
    finally:
        await _cleanup(db)
        client.close()


@pytest.mark.asyncio
async def test_duplicate_import_record_rejected():
    client, db = await _get_db()
    try:
        await _cleanup(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        ext_id = f"EXT-DUP-{uuid.uuid4().hex[:8]}"
        l1 = _make_lineage(ext_res_id=ext_id)
        l2 = _make_lineage(ext_res_id=ext_id)

        with patch("core.import_bridge_service.db", db):
            from core.import_bridge_service import create_import_record
            r1 = await create_import_record(l1, "pending_auto_import", connector_id=TEST_CONNECTOR)
            r2 = await create_import_record(l2, "pending_auto_import", connector_id=TEST_CONNECTOR)

        assert r1 is not None
        assert r2 is None
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 3. Successful Auto-Import (booking created via atomic core)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_auto_import_creates_booking():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db), \
             patch("core.atomic_booking.db", db):
            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)
            assert record is not None

            success, message = await auto_import_reservation_to_pms(record["id"])

        assert success is True
        assert "created successfully" in message

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "imported"
        assert imp["booking_id"] is not None

        booking = await db[COLL_BOOKINGS].find_one({"id": imp["booking_id"]}, {"_id": 0})
        assert booking is not None
        assert booking["tenant_id"] == TEST_TENANT
        assert booking["source"]["provider"] == TEST_PROVIDER
        assert booking["source"]["external_reservation_id"] == lineage["external_reservation_id"]
        assert booking["status"] == "confirmed"
    finally:
        await _cleanup(db)
        client.close()


@pytest.mark.asyncio
async def test_import_uses_atomic_booking_core():
    """Verify import calls create_booking_atomic, not a direct insert."""
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db), \
             patch("core.import_bridge_service.create_booking_atomic", new_callable=AsyncMock) as mock_atomic:
            mock_atomic.return_value = {"id": "mock-booking-id"}

            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)
            success, _ = await auto_import_reservation_to_pms(record["id"])

        assert success is True
        mock_atomic.assert_called_once()
        call_doc = mock_atomic.call_args[0][0]
        assert call_doc["tenant_id"] == TEST_TENANT
        assert call_doc["source"]["provider"] == TEST_PROVIDER
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 4. Duplicate Prevention
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_duplicate_booking_not_created():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        ext_id = f"EXT-NODUP-{uuid.uuid4().hex[:8]}"
        lineage = _make_lineage(ext_res_id=ext_id)

        existing_booking_id = str(uuid.uuid4())
        await db[COLL_BOOKINGS].insert_one({
            "id": existing_booking_id,
            "tenant_id": TEST_TENANT,
            "source": {
                "provider": TEST_PROVIDER,
                "external_reservation_id": ext_id,
            },
            "status": "confirmed",
            "check_in": "2026-04-01",
            "check_out": "2026-04-05",
        })

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db):
            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)
            success, message = await auto_import_reservation_to_pms(record["id"])

        assert success is True
        assert "linked to existing booking" in message

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "duplicate"
        assert imp["booking_id"] == existing_booking_id

        count = await db[COLL_BOOKINGS].count_documents({
            "tenant_id": TEST_TENANT,
            "source.external_reservation_id": ext_id,
        })
        assert count == 1
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 5. Review Required (Mapping Failure)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_unmapped_room_triggers_review():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        # Only rate mapping, no room mapping
        await db["rate_plan_mappings"].insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": TEST_TENANT,
            "property_id": TEST_PROPERTY,
            "provider": TEST_PROVIDER,
            "pms_rate_plan_id": "rate-bar",
            "provider_rate_code": "BAR",
            "is_active": True,
        })

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db):
            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)
            success, message = await auto_import_reservation_to_pms(record["id"])

        assert success is False
        assert "unmapped room type" in message

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "review_required"
        assert imp["review_reason"] == "unmapped_room_type"

        # Task #394: HARD-FAIL korunur (otomatik kabul YOK) ama overbooking'i
        # onlemek icin eslesmeyen-tutma (hold) booking + envanter kilidi olusur.
        # GERCEK (confirmed) booking OLUSMAMALI.
        real_count = await db[COLL_BOOKINGS].count_documents(
            {"tenant_id": TEST_TENANT, "status": "confirmed"}
        )
        assert real_count == 0

        assert imp.get("hold_booking_id")
        hold = await db[COLL_BOOKINGS].find_one(
            {"id": imp["hold_booking_id"], "tenant_id": TEST_TENANT}, {"_id": 0}
        )
        assert hold is not None
        assert hold["booking_source"] == "ota_unmatched_hold"
        assert hold["status"] == "pending_mapping"
        assert hold["room_id"] is None
        assert hold["action_needed"] is True
    finally:
        await _cleanup(db)
        # Task #394: tutma kaydinin sentinel kilitlerini de temizle (residue YOK)
        await db["room_night_locks"].delete_many({"tenant_id": TEST_TENANT})
        await db["notifications"].delete_many({"tenant_id": TEST_TENANT})
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 6. Retry on Transient Failure
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_transient_failure_schedules_retry():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db), \
             patch("core.import_bridge_service.create_booking_atomic", new_callable=AsyncMock) as mock_atomic:
            mock_atomic.side_effect = Exception("Connection timeout during write")

            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)
            success, message = await auto_import_reservation_to_pms(record["id"])

        assert success is False

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "retry"
        assert imp["next_retry_at"] is not None
        assert imp["retry_count"] == 1
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 7. Failed After Max Retries
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_max_retries_marks_failed():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db):
            from core.import_bridge_service import create_import_record, DEFAULT_MAX_RETRIES
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)

        # Simulate near max retries
        await db[COLL_IMPORTED].update_one(
            {"id": record["id"]},
            {"$set": {"retry_count": DEFAULT_MAX_RETRIES - 1}},
        )

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db), \
             patch("core.import_bridge_service.create_booking_atomic", new_callable=AsyncMock) as mock_atomic:
            mock_atomic.side_effect = Exception("Connection timeout")

            from core.import_bridge_service import auto_import_reservation_to_pms
            success, _ = await auto_import_reservation_to_pms(record["id"])

        assert success is False

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "failed"
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 8. Atomic Claim (Concurrency Safety)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_concurrent_claim_only_one_wins():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db):
            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)

            results = await asyncio.gather(
                auto_import_reservation_to_pms(record["id"]),
                auto_import_reservation_to_pms(record["id"]),
            )

        successes = [r for r in results if r[0] is True]
        assert len(successes) <= 1

        count = await db[COLL_BOOKINGS].count_documents({"tenant_id": TEST_TENANT})
        assert count <= 1
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 9. Admin Retry / Approve / Dismiss
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_admin_retry_resets_import():
    client, db = await _get_db()
    try:
        await _cleanup(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db):
            from core.import_bridge_service import create_import_record
            record = await create_import_record(lineage, "failed", connector_id=TEST_CONNECTOR)

        now = datetime.now(timezone.utc).isoformat()
        result = await db[COLL_IMPORTED].find_one_and_update(
            {"id": record["id"], "import_status": "failed"},
            {
                "$set": {
                    "import_status": "pending_auto_import",
                    "retry_count": 0,
                    "next_retry_at": None,
                    "review_reason": None,
                    "last_error": None,
                    "updated_at": now,
                },
            },
            projection={"_id": 0, "id": 1},
        )
        assert result is not None

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "pending_auto_import"
        assert imp["retry_count"] == 0
    finally:
        await _cleanup(db)
        client.close()


@pytest.mark.asyncio
async def test_admin_dismiss_marks_dismissed():
    client, db = await _get_db()
    try:
        await _cleanup(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db):
            from core.import_bridge_service import create_import_record
            record = await create_import_record(lineage, "review_required", connector_id=TEST_CONNECTOR)

        now = datetime.now(timezone.utc).isoformat()
        result = await db[COLL_IMPORTED].find_one_and_update(
            {"id": record["id"], "import_status": "review_required"},
            {"$set": {"import_status": "dismissed", "updated_at": now}},
            projection={"_id": 0, "id": 1},
        )
        assert result is not None

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "dismissed"
    finally:
        await _cleanup(db)
        client.close()


@pytest.mark.asyncio
async def test_admin_approve_and_import():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage = _make_lineage()

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db), \
             patch("core.atomic_booking.db", db):
            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "review_required", connector_id=TEST_CONNECTOR)

            # Admin approves: reset to pending
            now = datetime.now(timezone.utc).isoformat()
            await db[COLL_IMPORTED].update_one(
                {"id": record["id"]},
                {"$set": {"import_status": "pending_auto_import", "review_reason": None, "updated_at": now}},
            )

            success, message = await auto_import_reservation_to_pms(record["id"])

        assert success is True

        imp = await db[COLL_IMPORTED].find_one({"id": record["id"]}, {"_id": 0})
        assert imp["import_status"] == "imported"
        assert imp["booking_id"] is not None
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 10. Lineage Linking
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lineage_linked_to_booking():
    client, db = await _get_db()
    try:
        await _cleanup(db)
        await _setup_mappings(db)

        await db[COLL_IMPORTED].create_index(
            [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            name="idx_import_unique_ext_res", unique=True,
        )

        lineage_id = str(uuid.uuid4())
        ext_id = f"EXT-LINK-{uuid.uuid4().hex[:8]}"
        await db[COLL_LINEAGE].insert_one({
            "id": lineage_id,
            "tenant_id": TEST_TENANT,
            "provider": TEST_PROVIDER,
            "external_reservation_id": ext_id,
            "reservation_id": None,
        })

        lineage = _make_lineage(ext_res_id=ext_id)
        lineage["id"] = lineage_id

        with patch("core.import_bridge_service.db", db), \
             patch("core.import_decision.db", db), \
             patch("core.atomic_booking.db", db):
            from core.import_bridge_service import create_import_record, auto_import_reservation_to_pms
            record = await create_import_record(lineage, "pending_auto_import", connector_id=TEST_CONNECTOR)
            success, _ = await auto_import_reservation_to_pms(record["id"])

        assert success is True

        updated_lineage = await db[COLL_LINEAGE].find_one({"id": lineage_id}, {"_id": 0})
        assert updated_lineage["reservation_id"] is not None
    finally:
        await _cleanup(db)
        client.close()


# ═══════════════════════════════════════════════════════════════════
# 11. Error Classification
# ═══════════════════════════════════════════════════════════════════

def test_retryable_errors():
    from core.import_bridge_service import _is_retryable
    assert _is_retryable("Connection timeout during write") is True
    assert _is_retryable("temporary unavailable") is True
    assert _is_retryable("write conflict on collection") is True


def test_permanent_errors():
    from core.import_bridge_service import _is_retryable
    assert _is_retryable("mapping error: room type not found") is False
    assert _is_retryable("invalid payload: missing field") is False
    assert _is_retryable("duplicate key error") is False


def test_unknown_defaults_retryable():
    from core.import_bridge_service import _is_retryable
    assert _is_retryable("some random unknown error") is True
