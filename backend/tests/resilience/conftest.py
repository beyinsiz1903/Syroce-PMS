"""
Resilience Test Fixtures — Shared conftest for all chaos/resilience tests.

Provides:
- Async event loop bound to Motor
- FailureTracker, RetryEngine, AlertingEngine instances
- Tenant/booking/outbox/failure factories
- Automatic cleanup of test data after each test
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

CHAOS_TENANT_PREFIX = "chaos-test-"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Event Loop ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── Database Access ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db(event_loop):
    """Return raw (unproxied) DB for resilience tests.

    Resilience tests always include tenant_id explicitly in documents
    and queries, so the TenantAwareDBProxy scoping is unnecessary.
    Using _raw_db avoids TenantViolationError when STRICT_TENANT_MODE=true.
    """
    from core import database
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    from tests.conftest import (
        _bind_test_database,
        _restore_test_database,
    )

    load_dotenv(BACKEND_ROOT / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")

    previous_client = database.client
    previous_raw_db = getattr(database, "_raw_db", None)
    previous_db = database.db

    client = AsyncIOMotorClient(mongo_url)
    raw_db = client[db_name]

    database.client = client
    database._raw_db = raw_db

    active_db, previous_proxy_target = _bind_test_database(
        database,
        raw_db,
    )

    try:
        yield raw_db
    finally:
        client.close()
        database.client = previous_client
        database._raw_db = previous_raw_db
        _restore_test_database(
            database,
            previous_db=previous_db,
            active_db=active_db,
            previous_proxy_target=previous_proxy_target,
        )


# ── Cleanup ────────────────────────────────────────────────────────

async def _cleanup_chaos_records(db) -> None:
    chaos_filter = {"tenant_id": {"$regex": f"^{CHAOS_TENANT_PREFIX}"}}
    collections_to_clean = [
        "cp_failures",
        "cp_retry_log",
        "cp_alerts",
        "secret_access_audit",
        "outbox_events",
        "imported_reservations",
        "bookings",
        "reservation_lineage",
        "pms_audit_trail",
        "room_mappings",
        "rate_plan_mappings",
        "rooms",
    ]

    for collection_name in collections_to_clean:
        try:
            await db[collection_name].delete_many(chaos_filter)
        except Exception:
            pass


@pytest.fixture(autouse=True)
async def cleanup_chaos_data(db):
    """Clean resilience test records before and after every test."""
    await _cleanup_chaos_records(db)
    try:
        yield
    finally:
        await _cleanup_chaos_records(db)


# ── Service Instances ──────────────────────────────────────────────

@pytest.fixture
def failure_tracker():
    from controlplane.failure_tracker import FailureTracker
    return FailureTracker()


@pytest.fixture
def retry_engine():
    from controlplane.retry_engine import RetryEngine
    return RetryEngine()


@pytest.fixture
def alerting_engine():
    from controlplane.alerting import AlertingEngine
    engine = AlertingEngine()
    engine._last_fired = {}  # Reset cooldowns
    return engine


@pytest.fixture
def secret_access_control():
    from controlplane.secret_audit import SecretAccessControl
    return SecretAccessControl()


@pytest.fixture
def outbox_worker():
    from core.outbox_worker import OutboxWorker
    return OutboxWorker(
        poll_interval=0.1,
        batch_size=5,
        processing_timeout=2,  # Short timeout for tests
        drain_pause=0,
    )


# ── Factories ──────────────────────────────────────────────────────

@pytest.fixture
def tenant_factory():
    """Create isolated test tenant IDs."""

    def _create(suffix: str = "") -> str:
        return f"{CHAOS_TENANT_PREFIX}{suffix or uuid.uuid4().hex[:8]}"

    return _create


@pytest.fixture
def booking_factory(tenant_factory):
    """Create synthetic booking documents."""

    def _create(
        tenant_id: str = "",
        room_id: str = "",
        ext_res_id: str = "",
        provider: str = "exely",
        check_in: str = "2026-04-01",
        check_out: str = "2026-04-03",
        status: str = "confirmed",
    ) -> Dict[str, Any]:
        tid = tenant_id or tenant_factory()
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "property_id": tid,
            "guest_name": "Chaos Test Guest",
            "guest_email": "chaos@test.com",
            "guest_phone": "+90555000000",
            "check_in": check_in,
            "check_out": check_out,
            "room_id": room_id or str(uuid.uuid4()),
            "room_type": "STD",
            "adults": 2,
            "children": 0,
            "total_amount": 500.0,
            "currency": "TRY",
            "status": status,
            "booking_source": "ota_import",
            "source": {
                "provider": provider,
                "external_reservation_id": ext_res_id or f"EXT-{uuid.uuid4().hex[:8]}",
                "connector_id": "conn-test",
                "import_record_id": str(uuid.uuid4()),
            },
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }

    return _create


@pytest.fixture
def outbox_event_factory(tenant_factory):
    """Create synthetic outbox event documents."""

    def _create(
        tenant_id: str = "",
        event_type: str = "booking.created.v1",
        entity_type: str = "booking",
        status: str = "pending",
        created_at: str = "",
        available_at: str = "",
        attempt_count: int = 0,
        max_attempts: int = 5,
        provider: str = "exely",
    ) -> Dict[str, Any]:
        tid = tenant_id or tenant_factory()
        now = _utc_now()
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "property_id": tid,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": str(uuid.uuid4()),
            "provider": provider,
            "connector_id": "conn-test",
            "payload": {"booking_id": str(uuid.uuid4()), "source": "test"},
            "status": status,
            "attempt_count": attempt_count,
            "max_attempts": max_attempts,
            "available_at": available_at or now,
            "last_error": None,
            "last_attempt_at": None,
            "processed_at": None,
            "idempotency_key": f"{tid}:{event_type}:{uuid.uuid4().hex[:8]}",
            "correlation_id": str(uuid.uuid4()),
            "created_at": created_at or now,
            "updated_at": now,
        }

    return _create


@pytest.fixture
def import_record_factory(tenant_factory):
    """Create synthetic imported_reservations documents."""

    def _create(
        tenant_id: str = "",
        ext_res_id: str = "",
        provider: str = "exely",
        import_status: str = "pending_auto_import",
        room_type_code: str = "STD",
        arrival: str = "2026-04-01",
        departure: str = "2026-04-03",
    ) -> Dict[str, Any]:
        tid = tenant_id or tenant_factory()
        now = _utc_now()
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "property_id": tid,
            "provider": provider,
            "connector_id": "conn-test",
            "external_reservation_id": ext_res_id or f"EXT-{uuid.uuid4().hex[:8]}",
            "lineage_id": str(uuid.uuid4()),
            "payload_hash": uuid.uuid4().hex[:16],
            "import_status": import_status,
            "review_reason": None,
            "retry_count": 0,
            "max_retries": 5,
            "next_retry_at": None,
            "booking_id": None,
            "folio_id": None,
            "correlation_id": str(uuid.uuid4()),
            "last_error": None,
            "imported_at": None,
            "guest_name": "Test Guest",
            "guest_email": "test@guest.com",
            "guest_phone": "+905550000",
            "arrival_date": arrival,
            "departure_date": departure,
            "room_type_code": room_type_code,
            "rate_plan_code": "BAR",
            "adults": 2,
            "children": 0,
            "total_amount": 500.0,
            "currency": "TRY",
            "source_system": "exely",
            "created_at": now,
            "updated_at": now,
        }

    return _create


@pytest.fixture
def failure_event_factory(tenant_factory):
    """Create synthetic cp_failures documents."""

    def _create(
        tenant_id: str = "",
        provider: str = "exely",
        operation_type: str = "reservation_import",
        failure_type: str = "retryable",
        severity: str = "warning",
        status: str = "open",
        error_code: str = "TEST_ERROR",
        error_message: str = "Test failure for chaos testing",
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        tid = tenant_id or tenant_factory()
        now = _utc_now()
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "provider": provider,
            "property_id": tid,
            "operation_type": operation_type,
            "failure_type": failure_type,
            "severity": severity,
            "error_code": error_code,
            "error_message": error_message,
            "context": context or {},
            "retry_count": 0,
            "first_seen_at": now,
            "last_seen_at": now,
            "status": status,
            "correlation_id": str(uuid.uuid4()),
            "created_at": now,
            "updated_at": now,
        }

    return _create
