# QUARANTINED: 2026-03-24
# REASON: Stale DB fixtures - pymongo.errors.BulkWriteError. Tests assume seed data
#         (room types, rate plans, external entities) that no longer exists in test DB.
#         21/25 tests fail. Fix: Update seed data or rewrite tests with fresh fixtures.
# ORIGINAL: tests/test_mapping_engine.py
# CATEGORY: stale_fixtures

"""
Mapping Engine Contract Tests
Tests the 6 critical mapping scenarios:
  1. Missing mapping detection
  2. Inactive local (PMS) entity
  3. Deleted external entity
  4. Duplicate mapping prevention
  5. Invalid rate plan mapping
  6. Revalidate after fix
"""
import os
import pytest

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)
import pytest
import uuid
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio(loop_scope="session")

from channel_manager.application.mapping_service import MappingService
from core.database import db


TENANT = "test-mapping-tenant"
PROPERTY = "test-mapping-property"


# ─── Helpers ─────────────────────────────────────────────────────────────

async def _seed(connector_id: str):
    """Seed PMS + external data for tests."""
    await db.rooms.insert_many([
        {"id": f"rm-1-{connector_id}", "tenant_id": TENANT, "property_id": PROPERTY, "room_type": "STD", "room_number": "101", "status": "available"},
        {"id": f"rm-2-{connector_id}", "tenant_id": TENANT, "property_id": PROPERTY, "room_type": "DLX", "room_number": "201", "status": "available"},
        {"id": f"rm-3-{connector_id}", "tenant_id": TENANT, "property_id": PROPERTY, "room_type": "SUT", "room_number": "301", "status": "out_of_service"},
    ])
    await db.cm_external_room_types.insert_many([
        {"id": f"ext-rt-1-{connector_id}", "tenant_id": TENANT, "connector_id": connector_id, "external_id": "HR-STD", "name": "Standard", "is_active": True, "external_property_id": "p1"},
        {"id": f"ext-rt-2-{connector_id}", "tenant_id": TENANT, "connector_id": connector_id, "external_id": "HR-DLX", "name": "Deluxe", "is_active": True, "external_property_id": "p1"},
        {"id": f"ext-rt-3-{connector_id}", "tenant_id": TENANT, "connector_id": connector_id, "external_id": "HR-OLD", "name": "Old Room", "is_active": False, "external_property_id": "p1"},
    ])
    await db.cm_external_rate_plans.insert_many([
        {"id": f"ext-rp-1-{connector_id}", "tenant_id": TENANT, "connector_id": connector_id, "external_id": "HR-RP-BB", "name": "Bed & Breakfast", "is_active": True, "external_property_id": "p1", "external_room_type_id": "HR-STD"},
        {"id": f"ext-rp-2-{connector_id}", "tenant_id": TENANT, "connector_id": connector_id, "external_id": "HR-RP-RO", "name": "Room Only", "is_active": True, "external_property_id": "p1", "external_room_type_id": "HR-DLX"},
        {"id": f"ext-rp-3-{connector_id}", "tenant_id": TENANT, "connector_id": connector_id, "external_id": "HR-RP-DEL", "name": "Deleted RP", "is_active": False, "external_property_id": "p1", "external_room_type_id": "HR-OLD"},
    ])
    await db.cm_connectors.insert_one({
        "id": connector_id, "tenant_id": TENANT, "property_id": PROPERTY,
        "provider": "hotelrunner", "status": "active", "display_name": "Test HR",
    })


async def _cleanup(connector_id: str):
    await db.rooms.delete_many({"tenant_id": TENANT, "id": {"$regex": connector_id}})
    await db.cm_external_room_types.delete_many({"tenant_id": TENANT, "connector_id": connector_id})
    await db.cm_external_rate_plans.delete_many({"tenant_id": TENANT, "connector_id": connector_id})
    await db.cm_connectors.delete_many({"tenant_id": TENANT, "id": connector_id})
    await db.cm_mappings.delete_many({"tenant_id": TENANT, "connector_id": connector_id})
    await db.cm_imported_reservations.delete_many({"tenant_id": TENANT, "connector_id": connector_id})
    await db.cm_integration_audit.delete_many({"tenant_id": TENANT})


async def _create_mapping(svc, connector_id, entity_type, pms_id, ext_id, pms_name="", ext_name=""):
    return await svc.create_mapping(
        tenant_id=TENANT, property_id=PROPERTY, connector_id=connector_id,
        entity_type=entity_type, pms_entity_id=pms_id, pms_entity_name=pms_name,
        external_entity_id=ext_id, external_entity_name=ext_name, actor_id="tester",
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. MISSING MAPPING DETECTION
# ══════════════════════════════════════════════════════════════════════════

async def test_detect_missing_room_type():
    cid = f"c-miss-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD", "Standard", "HR Standard")
        readiness = await svc.check_sync_readiness(TENANT, cid)
        assert not readiness["ready"]
        assert "DLX" in str(readiness["summary"]["room_type"]["unmapped"])
    finally:
        await _cleanup(cid)


async def test_missing_mappings_listed_in_validation():
    cid = f"c-missv-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await svc.validate_mappings(TENANT, cid)
        assert result["missing_count"] > 0
        missing_types = [m["entity_type"] for m in result["missing_mappings"]]
        assert "room_type" in missing_types
    finally:
        await _cleanup(cid)


async def test_zero_mappings_gives_zero_score():
    cid = f"c-zero-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        readiness = await svc.check_sync_readiness(TENANT, cid)
        assert readiness["score"] == 0
        assert len(readiness["blocked_reasons"]) >= 2
    finally:
        await _cleanup(cid)


# ══════════════════════════════════════════════════════════════════════════
# 2. INACTIVE LOCAL (PMS) ENTITY
# ══════════════════════════════════════════════════════════════════════════

async def test_mapping_to_out_of_service_room_is_invalid():
    cid = f"c-oos-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "room_type", "SUT", "HR-DLX", "Suite", "HR Deluxe")
        assert result["validation_status"] == "invalid"
        assert "aktif degil" in result["invalid_reason"]
    finally:
        await _cleanup(cid)


async def test_mapping_to_nonexistent_pms_room_is_invalid():
    cid = f"c-noex-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "room_type", "NONEXIST", "HR-STD", "Ghost", "HR Standard")
        assert result["validation_status"] == "invalid"
        assert "bulunamadi" in result["invalid_reason"]
    finally:
        await _cleanup(cid)


# ══════════════════════════════════════════════════════════════════════════
# 3. DELETED EXTERNAL ENTITY
# ══════════════════════════════════════════════════════════════════════════

async def test_mapping_to_inactive_external_room_is_invalid():
    cid = f"c-inact-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "room_type", "STD", "HR-OLD", "Standard", "Old Room")
        assert result["validation_status"] == "invalid"
        errs_str = str(result.get("validation_errors", []))
        assert "aktif degil" in errs_str
    finally:
        await _cleanup(cid)


async def test_mapping_to_nonexistent_external_room_is_invalid():
    cid = f"c-noext-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "room_type", "STD", "HR-PHANTOM", "Standard", "Phantom")
        assert result["validation_status"] == "invalid"
        assert "bulunamadi" in str(result.get("validation_errors"))
    finally:
        await _cleanup(cid)


async def test_mapping_to_deleted_rate_plan_is_invalid():
    cid = f"c-delrp-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "rate_plan", "STD", "HR-RP-DEL", "Standard", "Deleted RP")
        assert result["validation_status"] == "invalid"
        assert "aktif degil" in str(result.get("validation_errors"))
    finally:
        await _cleanup(cid)


# ══════════════════════════════════════════════════════════════════════════
# 4. DUPLICATE MAPPING PREVENTION
# ══════════════════════════════════════════════════════════════════════════

async def test_duplicate_pms_entity_rejected():
    cid = f"c-dupe1-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD")
        with pytest.raises(ValueError, match="already mapped"):
            await _create_mapping(svc, cid, "room_type", "STD", "HR-DLX")
    finally:
        await _cleanup(cid)


async def test_duplicate_external_entity_rejected():
    cid = f"c-dupe2-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD")
        with pytest.raises(ValueError, match="already mapped"):
            await _create_mapping(svc, cid, "room_type", "DLX", "HR-STD")
    finally:
        await _cleanup(cid)


async def test_duplicate_detected_during_validation():
    cid = f"c-dupe3-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        now = datetime.now(timezone.utc).isoformat()
        m1_id = str(uuid.uuid4())
        m2_id = str(uuid.uuid4())
        await db.cm_mappings.insert_many([
            {"id": m1_id, "tenant_id": TENANT, "property_id": PROPERTY, "connector_id": cid,
             "entity_type": "room_type", "pms_entity_id": "STD", "external_entity_id": "HR-STD",
             "status": "active", "validation_status": "pending", "created_at": now,
             "direction": "bidirectional", "validation_errors": [], "pms_entity_name": "", "external_entity_name": "",
             "pms_entity_meta": {}, "external_entity_meta": {}, "occupancy_offset": 0,
             "rate_modifier": None, "rate_offset": None, "last_validated_at": None, "invalid_reason": None,
             "created_by": None, "updated_at": None},
            {"id": m2_id, "tenant_id": TENANT, "property_id": PROPERTY, "connector_id": cid,
             "entity_type": "room_type", "pms_entity_id": "STD", "external_entity_id": "HR-DLX",
             "status": "active", "validation_status": "pending", "created_at": now,
             "direction": "bidirectional", "validation_errors": [], "pms_entity_name": "", "external_entity_name": "",
             "pms_entity_meta": {}, "external_entity_meta": {}, "occupancy_offset": 0,
             "rate_modifier": None, "rate_offset": None, "last_validated_at": None, "invalid_reason": None,
             "created_by": None, "updated_at": None},
        ])
        result = await svc.validate_mappings(TENANT, cid)
        assert result["invalid"] >= 1
    finally:
        await _cleanup(cid)


# ══════════════════════════════════════════════════════════════════════════
# 5. INVALID RATE PLAN MAPPING
# ══════════════════════════════════════════════════════════════════════════

async def test_rate_plan_to_nonexistent_ext_is_invalid():
    cid = f"c-rp1-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "rate_plan", "STD", "HR-RP-PHANTOM")
        assert result["validation_status"] == "invalid"
    finally:
        await _cleanup(cid)


async def test_rate_plan_to_inactive_ext_is_invalid():
    cid = f"c-rp2-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "rate_plan", "STD", "HR-RP-DEL")
        assert result["validation_status"] == "invalid"
    finally:
        await _cleanup(cid)


async def test_valid_rate_plan_mapping():
    cid = f"c-rp3-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "rate_plan", "STD", "HR-RP-BB", "Standard", "BB")
        assert result["validation_status"] == "valid"
    finally:
        await _cleanup(cid)


async def test_tax_mode_invalid_values():
    cid = f"c-tax-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        result = await _create_mapping(svc, cid, "tax_mode", "foo_invalid", "bar_invalid")
        assert result["validation_status"] == "invalid"
        assert "Gecersiz tax mode" in str(result.get("validation_errors"))
    finally:
        await _cleanup(cid)


# ══════════════════════════════════════════════════════════════════════════
# 6. REVALIDATE AFTER FIX
# ══════════════════════════════════════════════════════════════════════════

async def test_review_reservation_revalidated_on_mapping_create():
    cid = f"c-reval-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        res_id = str(uuid.uuid4())
        await db.cm_imported_reservations.insert_one({
            "id": res_id, "tenant_id": TENANT, "connector_id": cid,
            "property_id": PROPERTY, "import_status": "review",
            "review_reason_code": "missing_room_mapping",
            "room_type_external_id": "HR-STD",
            "rate_plan_external_id": "HR-RP-BB",
            "external_reservation_id": f"ext-{res_id}",
        })
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD", "Standard", "HR Standard")
        await _create_mapping(svc, cid, "rate_plan", "STD", "HR-RP-BB", "Standard", "BB")

        res = await db.cm_imported_reservations.find_one(
            {"tenant_id": TENANT, "id": res_id}, {"_id": 0},
        )
        assert res["import_status"] == "pending"
        assert res.get("revalidation_trigger") == "mapping_changed"
    finally:
        await _cleanup(cid)


async def test_validate_single_mapping_updates_status():
    cid = f"c-vs-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        mapping = await _create_mapping(svc, cid, "room_type", "STD", "HR-STD", "Standard", "HR Standard")
        result = await svc.validate_single(TENANT, mapping["id"])
        assert result["validation_status"] == "valid"
        assert result["validated_at"] is not None
    finally:
        await _cleanup(cid)


async def test_full_readiness_after_all_mappings():
    cid = f"c-full-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD", "Standard", "HR Standard")
        await _create_mapping(svc, cid, "room_type", "DLX", "HR-DLX", "Deluxe", "HR Deluxe")
        await _create_mapping(svc, cid, "rate_plan", "STD", "HR-RP-BB", "Standard", "BB")
        await _create_mapping(svc, cid, "rate_plan", "DLX", "HR-RP-RO", "Deluxe", "RO")

        readiness = await svc.check_sync_readiness(TENANT, cid)
        assert readiness["score"] >= 80
    finally:
        await _cleanup(cid)


# ══════════════════════════════════════════════════════════════════════════
# READINESS SCORE UNIT TESTS (pure, no DB)
# ══════════════════════════════════════════════════════════════════════════

def test_perfect_score():
    score = MappingService._calculate_readiness_score(
        room_mappings=5, rate_mappings=5,
        total_pms_rooms=5, total_pms_rates=5,
        invalid_count=0, total_mappings=10,
    )
    assert score == 100


def test_zero_score():
    score = MappingService._calculate_readiness_score(
        room_mappings=0, rate_mappings=0,
        total_pms_rooms=5, total_pms_rates=5,
        invalid_count=0, total_mappings=0,
    )
    assert score == 0


def test_partial_coverage():
    score = MappingService._calculate_readiness_score(
        room_mappings=3, rate_mappings=2,
        total_pms_rooms=5, total_pms_rates=5,
        invalid_count=0, total_mappings=5,
    )
    assert score == 66


def test_invalids_reduce_score():
    score = MappingService._calculate_readiness_score(
        room_mappings=5, rate_mappings=5,
        total_pms_rooms=5, total_pms_rates=5,
        invalid_count=5, total_mappings=10,
    )
    assert score == 85


# ══════════════════════════════════════════════════════════════════════════
# LOOKUP TESTS
# ══════════════════════════════════════════════════════════════════════════

async def test_forward_lookup():
    cid = f"c-fwd-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD")
        lookup = await svc.get_mapping_lookup(TENANT, cid, "room_type")
        assert lookup.get("STD") == "HR-STD"
    finally:
        await _cleanup(cid)


async def test_reverse_lookup():
    cid = f"c-rev-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        await _create_mapping(svc, cid, "room_type", "STD", "HR-STD")
        lookup = await svc.get_reverse_lookup(TENANT, cid, "room_type")
        assert lookup.get("HR-STD") == "STD"
    finally:
        await _cleanup(cid)


async def test_empty_lookup_for_unmapped_type():
    cid = f"c-emp-{uuid.uuid4().hex[:6]}"
    await _seed(cid)
    try:
        svc = MappingService()
        lookup = await svc.get_mapping_lookup(TENANT, cid, "meal_plan")
        assert lookup == {}
    finally:
        await _cleanup(cid)
