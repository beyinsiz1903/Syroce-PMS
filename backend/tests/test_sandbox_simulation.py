"""
Tests for Sandbox Simulation — Resilience Testing.

Tests each scenario's core logic and the engine orchestration.
Uses the actual MongoDB database to verify end-to-end behavior.
"""
import asyncio

# Adjust path for test runner
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db_connection(event_loop):
    """Provide one isolated database connection for this test module."""
    import os

    from motor.motor_asyncio import AsyncIOMotorClient

    import core.database as database_module

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "syroce_pms")

    previous_db = database_module.db
    client = AsyncIOMotorClient(mongo_url)
    raw_db = client[db_name]

    database_module.db = raw_db

    try:
        yield raw_db
    finally:
        database_module.db = previous_db
        client.close()


TENANT_ID = "test-sandbox-tenant"
PROPERTY_ID = "test-sandbox-property"


@pytest.fixture
def repo(db_connection):
    from channel_manager.infrastructure.repository import ChannelManagerRepository
    return ChannelManagerRepository()


@pytest.fixture
def run_id():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def connector_id(run_id):
    return f"sandbox-hotelrunner-{run_id}"


@pytest.fixture
def room_reverse():
    return {"HR_RT_STD": "STD"}


@pytest.fixture
def rate_reverse():
    return {"HR_RP_BAR": "BAR"}


async def _cleanup(db_conn, tenant_id):
    """Clean up test data."""
    await db_conn.cm_imported_reservations.delete_many({"tenant_id": tenant_id})
    await db_conn.cm_connectors.delete_many({"tenant_id": tenant_id})
    await db_conn.cm_mappings.delete_many({"tenant_id": tenant_id})
    await db_conn.bookings.delete_many({"tenant_id": tenant_id})
    await db_conn.cm_sync_snapshots.delete_many({"tenant_id": tenant_id})
    await db_conn.room_type_inventory.delete_many({"tenant_id": tenant_id, "computation_source": "sandbox_simulation"})
    await db_conn.sandbox_event_timeline.delete_many({"tenant_id": tenant_id})
    await db_conn.sandbox_simulation_results.delete_many({"tenant_id": tenant_id})
    await db_conn.cm_import_batches.delete_many({"tenant_id": tenant_id})


@pytest.fixture(autouse=True)
async def cleanup(db_connection):
    """Clean up before and after each test."""
    await _cleanup(db_connection, TENANT_ID)
    yield
    await _cleanup(db_connection, TENANT_ID)


# ════════════════════════════════════════════════════════════════════
#  Test: Duplicate Delivery
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_duplicate_delivery_hotelrunner(db_connection, repo, run_id, connector_id, room_reverse, rate_reverse):
    """Duplicate delivery → 0 double inventory consumption."""
    from channel_manager.application.sandbox_simulation.scenarios import run_duplicate_delivery

    # Setup connector
    await db_connection.cm_connectors.insert_one({
        "id": connector_id, "tenant_id": TENANT_ID, "property_id": PROPERTY_ID,
        "provider": "hotelrunner", "status": "active",
    })

    result = await run_duplicate_delivery(
        TENANT_ID, PROPERTY_ID, connector_id, run_id, "hotelrunner",
        room_reverse, rate_reverse, repo, duplicate_count=5,
    )

    assert result["passed"] is True
    assert result["new_created"] == 1
    assert result["duplicates_detected"] == 4
    assert result["double_inventory_consumption"] == 0
    assert result["pms_bookings_created"] == 1


@pytest.mark.asyncio
async def test_duplicate_delivery_exely(db_connection, repo, run_id, room_reverse, rate_reverse):
    """Duplicate delivery for Exely → 0 double inventory consumption."""
    from channel_manager.application.sandbox_simulation.scenarios import run_duplicate_delivery

    exely_connector = f"sandbox-exely-{run_id}"
    exely_room_reverse = {"EX_RT_STD": "STD"}
    exely_rate_reverse = {"EX_RP_BAR": "BAR"}

    await db_connection.cm_connectors.insert_one({
        "id": exely_connector, "tenant_id": TENANT_ID, "property_id": PROPERTY_ID,
        "provider": "exely", "status": "active",
    })

    result = await run_duplicate_delivery(
        TENANT_ID, PROPERTY_ID, exely_connector, run_id, "exely",
        exely_room_reverse, exely_rate_reverse, repo, duplicate_count=3,
    )

    assert result["passed"] is True
    assert result["new_created"] == 1
    assert result["duplicates_detected"] == 2
    assert result["double_inventory_consumption"] == 0


# ════════════════════════════════════════════════════════════════════
#  Test: Delayed ACK
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_delayed_ack_hotelrunner(db_connection, repo, run_id, connector_id, room_reverse, rate_reverse):
    """Delayed ACK → 0 inconsistent state."""
    from channel_manager.application.sandbox_simulation.scenarios import run_delayed_ack

    await db_connection.cm_connectors.insert_one({
        "id": connector_id, "tenant_id": TENANT_ID, "property_id": PROPERTY_ID,
        "provider": "hotelrunner", "status": "active",
    })

    result = await run_delayed_ack(
        TENANT_ID, PROPERTY_ID, connector_id, run_id, "hotelrunner",
        room_reverse, rate_reverse, repo,
    )

    assert result["passed"] is True
    assert result["assertions"]["booking_created"] is True
    assert result["assertions"]["ack_recovered"] is True
    assert result["assertions"]["consistent_state"] is True


# ════════════════════════════════════════════════════════════════════
#  Test: Retry Storm
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_retry_storm_hotelrunner(db_connection, repo, run_id, connector_id, room_reverse, rate_reverse):
    """Retry storm → 0 oversell."""
    from channel_manager.application.sandbox_simulation.scenarios import run_retry_storm

    await db_connection.cm_connectors.insert_one({
        "id": connector_id, "tenant_id": TENANT_ID, "property_id": PROPERTY_ID,
        "provider": "hotelrunner", "status": "active",
    })

    result = await run_retry_storm(
        TENANT_ID, PROPERTY_ID, connector_id, run_id, "hotelrunner",
        room_reverse, rate_reverse, repo, storm_size=9,
    )

    assert result["passed"] is True
    assert result["oversell_count"] == 0
    assert result["new_created"] == 3  # 3 unique reservations
    assert result["assertions"]["zero_oversell"] is True
    assert result["assertions"]["idempotent_import"] is True


# ════════════════════════════════════════════════════════════════════
#  Test: Stale Provider State
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stale_provider_state_hotelrunner(db_connection, repo, run_id, connector_id):
    """Stale provider state → reconciliation recovers."""
    from channel_manager.application.sandbox_simulation.scenarios import run_stale_provider_state

    await db_connection.cm_connectors.insert_one({
        "id": connector_id, "tenant_id": TENANT_ID, "property_id": PROPERTY_ID,
        "provider": "hotelrunner", "status": "active",
    })

    result = await run_stale_provider_state(
        TENANT_ID, PROPERTY_ID, connector_id, run_id, "hotelrunner", repo,
    )

    assert result["passed"] is True
    assert result["drift_detected"] is True
    assert result["reconciliation_recovered"] is True
    assert len(result["drift_records"]) == 3  # 3 dates


# ════════════════════════════════════════════════════════════════════
#  Test: Modify / Cancel Race
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_modify_cancel_race_hotelrunner(db_connection, repo, run_id, connector_id, room_reverse, rate_reverse):
    """Modify/cancel race → deterministic outcome."""
    from channel_manager.application.sandbox_simulation.scenarios import run_modify_cancel_race

    await db_connection.cm_connectors.insert_one({
        "id": connector_id, "tenant_id": TENANT_ID, "property_id": PROPERTY_ID,
        "provider": "hotelrunner", "status": "active",
    })

    result = await run_modify_cancel_race(
        TENANT_ID, PROPERTY_ID, connector_id, run_id, "hotelrunner",
        room_reverse, rate_reverse, repo,
    )

    assert result["passed"] is True
    assert result["sequence_results"] == ["new", "modified", "cancelled"]
    assert result["final_pms_status"] == "cancelled"
    assert result["assertions"]["deterministic_sequence"] is True


# ════════════════════════════════════════════════════════════════════
#  Test: Full Engine Orchestration
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_full_simulation_engine(db_connection):
    """Full simulation engine runs all scenarios for all providers."""
    from channel_manager.application.sandbox_simulation.engine import SandboxSimulationEngine

    engine = SandboxSimulationEngine()
    result = await engine.run_full_simulation(
        tenant_id=TENANT_ID,
        property_id=PROPERTY_ID,
        providers=["hotelrunner", "exely"],
        actor_id="test-actor",
    )

    assert result["summary"]["total_scenarios"] == 10  # 5 per provider
    assert result["summary"]["all_passed"] is True
    assert "hotelrunner" in result["provider_results"]
    assert "exely" in result["provider_results"]
    assert result["provider_results"]["hotelrunner"]["passed"] == 5
    assert result["provider_results"]["exely"]["passed"] == 5


@pytest.mark.asyncio
async def test_simulation_results_persistence(db_connection):
    """Simulation results are persisted and retrievable."""
    from channel_manager.application.sandbox_simulation.engine import SandboxSimulationEngine

    engine = SandboxSimulationEngine()
    result = await engine.run_full_simulation(
        tenant_id=TENANT_ID,
        property_id=PROPERTY_ID,
        providers=["hotelrunner"],
    )

    # Retrieve results
    results = await engine.get_simulation_results(TENANT_ID)
    assert len(results) >= 1
    assert results[0]["run_id"] == result["run_id"]

    # Retrieve specific result
    specific = await engine.get_simulation_result(TENANT_ID, result["run_id"])
    assert specific is not None
    assert specific["run_id"] == result["run_id"]


@pytest.mark.asyncio
async def test_simulation_timeline(db_connection):
    """Simulation timeline events are recorded."""
    from channel_manager.application.sandbox_simulation.engine import SandboxSimulationEngine

    engine = SandboxSimulationEngine()
    result = await engine.run_full_simulation(
        tenant_id=TENANT_ID,
        property_id=PROPERTY_ID,
        providers=["hotelrunner"],
    )

    timeline = await engine.get_simulation_timeline(TENANT_ID, result["run_id"])
    assert len(timeline) > 0

    # Should have scenario_start and scenario_complete events
    event_types = {e["event"] for e in timeline}
    assert "scenario_start" in event_types
    assert "scenario_complete" in event_types

@pytest.mark.asyncio
async def test_engine_establishes_tenant_context_for_background_execution(db_connection):
    """Engine must establish its own tenant context since it runs as a background task."""
    from channel_manager.application.sandbox_simulation.engine import SandboxSimulationEngine
    from core.tenant_db import _tenant_ctx

    # Ensure no outer context exists
    _tenant_ctx.set(None)

    engine = SandboxSimulationEngine()
    result = await engine.run_full_simulation(
        tenant_id=TENANT_ID,
        property_id=PROPERTY_ID,
        providers=["hotelrunner"],
        actor_id="test-actor",
    )

    assert result["summary"]["all_passed"] is True
    assert result["tenant_id"] == TENANT_ID

@pytest.mark.asyncio
async def test_engine_establishes_tenant_context_for_cleanup(db_connection):
    """Cleanup must also establish its own tenant context."""
    from channel_manager.application.sandbox_simulation.engine import SandboxSimulationEngine
    from core.tenant_db import _tenant_ctx

    # Ensure no outer context exists
    _tenant_ctx.set(None)

    engine = SandboxSimulationEngine()
    # If it fails to establish context, this will raise TenantViolationError
    await engine.cleanup_sandbox_data(TENANT_ID, "dummy-run-id")

    # Since it's an async task that returns nothing, reaching here means success
    assert True
