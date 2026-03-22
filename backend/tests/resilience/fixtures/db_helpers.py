"""
Database helpers — cleanup, state assertions, synthetic data utilities.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


CHAOS_TENANT_PREFIX = "chaos-test-"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_past(hours: int = 0, minutes: int = 0) -> str:
    """Return ISO timestamp in the past."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)).isoformat()


def utc_future(hours: int = 0, minutes: int = 0) -> str:
    """Return ISO timestamp in the future."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)).isoformat()


async def count_bookings_for_ext_res(db, tenant_id: str, provider: str, ext_res_id: str) -> int:
    """Count bookings with a specific external reservation ID."""
    return await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "source.provider": provider,
        "source.external_reservation_id": ext_res_id,
    })


async def count_outbox_by_status(db, tenant_id: str, status: str) -> int:
    """Count outbox events by status for a tenant."""
    return await db.outbox_events.count_documents({
        "tenant_id": tenant_id,
        "status": status,
    })


async def count_failures_by_type(db, tenant_id: str, failure_type: str) -> int:
    """Count control plane failures by type."""
    return await db.cp_failures.count_documents({
        "tenant_id": tenant_id,
        "failure_type": failure_type,
    })


async def get_import_record(db, import_id: str) -> Optional[Dict[str, Any]]:
    """Get an import record by ID."""
    return await db.imported_reservations.find_one(
        {"id": import_id}, {"_id": 0}
    )


async def get_outbox_event(db, event_id: str) -> Optional[Dict[str, Any]]:
    """Get an outbox event by ID."""
    return await db.outbox_events.find_one(
        {"id": event_id}, {"_id": 0}
    )


async def get_failure(db, failure_id: str) -> Optional[Dict[str, Any]]:
    """Get a control plane failure by ID."""
    return await db.cp_failures.find_one(
        {"id": failure_id}, {"_id": 0}
    )


async def insert_room_mapping(
    db,
    tenant_id: str,
    provider: str,
    provider_room_code: str,
    pms_room_type_id: str,
) -> None:
    """Insert a room mapping for test setup."""
    await db.room_mappings.insert_one({
        "tenant_id": tenant_id,
        "property_id": tenant_id,
        "provider": provider,
        "provider_room_code": provider_room_code,
        "pms_room_type_id": pms_room_type_id,
        "is_active": True,
        "created_at": utc_now(),
    })


async def insert_rate_plan_mapping(
    db,
    tenant_id: str,
    provider: str,
    provider_rate_code: str,
    pms_rate_plan_id: str,
) -> None:
    """Insert a rate plan mapping for test setup."""
    await db.rate_plan_mappings.insert_one({
        "tenant_id": tenant_id,
        "property_id": tenant_id,
        "provider": provider,
        "provider_rate_code": provider_rate_code,
        "pms_rate_plan_id": pms_rate_plan_id,
        "is_active": True,
        "created_at": utc_now(),
    })
