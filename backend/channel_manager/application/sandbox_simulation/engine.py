"""
Sandbox Simulation Engine — Orchestrates all scenarios for Exely and HotelRunner.

Produces a complete simulation report with per-provider result tables.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

from ...infrastructure.repository import ChannelManagerRepository
from .provider_harness import PROVIDER_PROFILES
from .scenarios import (
    SANDBOX_RESULTS,
    SANDBOX_TIMELINE,
    run_delayed_ack,
    run_duplicate_delivery,
    run_modify_cancel_race,
    run_retry_storm,
    run_stale_provider_state,
)

logger = logging.getLogger("channel_manager.sandbox_simulation.engine")

SANDBOX_CONNECTORS = "cm_connectors"
SANDBOX_MAPPINGS = "cm_mappings"


class SandboxSimulationEngine:
    """Orchestrates all sandbox simulation scenarios."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def run_full_simulation(
        self,
        tenant_id: str,
        property_id: str,
        providers: list[str] | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run all scenarios for all specified providers.
        Returns a complete simulation report.
        """
        run_id = f"sim-{uuid.uuid4().hex[:12]}"
        providers = providers or list(PROVIDER_PROFILES.keys())
        started_at = datetime.now(UTC).isoformat()

        logger.info("Starting sandbox simulation %s for providers: %s", run_id, providers)

        # Create test fixtures for each provider
        fixtures = {}
        for provider in providers:
            fixtures[provider] = await self._setup_provider_fixtures(
                tenant_id,
                property_id,
                provider,
                run_id,
            )

        # Run all scenarios per provider
        all_results: dict[str, list[dict[str, Any]]] = {}
        for provider in providers:
            fix = fixtures[provider]
            connector_id = fix["connector_id"]
            sandbox_prop_id = fix["property_id"]
            room_reverse = fix["room_reverse"]
            rate_reverse = fix["rate_reverse"]

            provider_results = []

            # Scenario 1: Duplicate Delivery
            try:
                res = await run_duplicate_delivery(
                    tenant_id,
                    sandbox_prop_id,
                    connector_id,
                    run_id,
                    provider,
                    room_reverse,
                    rate_reverse,
                    self._repo,
                )
                provider_results.append(res)
            except Exception as e:
                logger.error("Scenario duplicate_delivery failed for %s: %s", provider, e)
                provider_results.append(
                    {
                        "scenario": "duplicate_delivery",
                        "provider": provider,
                        "passed": False,
                        "error": str(e),
                    }
                )

            # Scenario 2: Delayed ACK
            try:
                res = await run_delayed_ack(
                    tenant_id,
                    sandbox_prop_id,
                    connector_id,
                    run_id,
                    provider,
                    room_reverse,
                    rate_reverse,
                    self._repo,
                )
                provider_results.append(res)
            except Exception as e:
                logger.error("Scenario delayed_ack failed for %s: %s", provider, e)
                provider_results.append(
                    {
                        "scenario": "delayed_ack",
                        "provider": provider,
                        "passed": False,
                        "error": str(e),
                    }
                )

            # Scenario 3: Retry Storm
            try:
                res = await run_retry_storm(
                    tenant_id,
                    sandbox_prop_id,
                    connector_id,
                    run_id,
                    provider,
                    room_reverse,
                    rate_reverse,
                    self._repo,
                )
                provider_results.append(res)
            except Exception as e:
                logger.error("Scenario retry_storm failed for %s: %s", provider, e)
                provider_results.append(
                    {
                        "scenario": "retry_storm",
                        "provider": provider,
                        "passed": False,
                        "error": str(e),
                    }
                )

            # Scenario 4: Stale Provider State
            try:
                res = await run_stale_provider_state(
                    tenant_id,
                    sandbox_prop_id,
                    connector_id,
                    run_id,
                    provider,
                    self._repo,
                )
                provider_results.append(res)
            except Exception as e:
                logger.error("Scenario stale_provider_state failed for %s: %s", provider, e)
                provider_results.append(
                    {
                        "scenario": "stale_provider_state",
                        "provider": provider,
                        "passed": False,
                        "error": str(e),
                    }
                )

            # Scenario 5: Modify/Cancel Race
            try:
                res = await run_modify_cancel_race(
                    tenant_id,
                    sandbox_prop_id,
                    connector_id,
                    run_id,
                    provider,
                    room_reverse,
                    rate_reverse,
                    self._repo,
                )
                provider_results.append(res)
            except Exception as e:
                logger.error("Scenario modify_cancel_race failed for %s: %s", provider, e)
                provider_results.append(
                    {
                        "scenario": "modify_cancel_race",
                        "provider": provider,
                        "passed": False,
                        "error": str(e),
                    }
                )

            all_results[provider] = provider_results

        # Build report
        completed_at = datetime.now(UTC).isoformat()
        report = self._build_report(run_id, tenant_id, providers, all_results, started_at, completed_at, actor_id)

        # Persist report
        await db[SANDBOX_RESULTS].insert_one({**report, "_persist": True})
        logger.info("Sandbox simulation %s complete: %s", run_id, report["summary"])

        return report

    async def get_simulation_results(
        self,
        tenant_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent simulation results."""
        cursor = (
            db[SANDBOX_RESULTS]
            .find(
                {"tenant_id": tenant_id},
                {"_id": 0, "_persist": 0},
            )
            .sort("started_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(limit)

    async def get_simulation_result(
        self,
        tenant_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Get a specific simulation result."""
        return await db[SANDBOX_RESULTS].find_one(
            {"tenant_id": tenant_id, "run_id": run_id},
            {"_id": 0, "_persist": 0},
        )

    async def get_simulation_timeline(
        self,
        tenant_id: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        """Get the event timeline for a specific simulation run."""
        cursor = (
            db[SANDBOX_TIMELINE]
            .find(
                {"tenant_id": tenant_id, "run_id": run_id},
                {"_id": 0},
            )
            .sort("timestamp", 1)
        )
        return await cursor.to_list(500)

    # ─── Private Helpers ─────────────────────────────────────────────

    async def _setup_provider_fixtures(
        self,
        tenant_id: str,
        property_id: str,
        provider: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Create sandbox connector and mappings for a provider."""
        profile = PROVIDER_PROFILES[provider]
        connector_id = f"sandbox-{provider}-{run_id}"
        # Use unique sandbox property to avoid unique index conflict with real connectors
        sandbox_property_id = f"SANDBOX-{run_id[:8]}"

        # Create sandbox connector
        connector_doc = {
            "id": connector_id,
            "tenant_id": tenant_id,
            "property_id": sandbox_property_id,
            "provider": provider,
            "status": "active",
            "environment": "sandbox",
            "display_name": f"Sandbox {profile['display_name']}",
            "credentials": {},
            "created_at": datetime.now(UTC).isoformat(),
            "sandbox_run_id": run_id,
        }
        await self._repo.upsert_connector(connector_doc)

        # Create room type mapping
        pms_room_type = "STD"
        ext_room_type = f"{profile['room_type_prefix']}STD"
        room_mapping = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "entity_type": "room_type",
            "external_id": ext_room_type,
            "pms_id": pms_room_type,
            "external_name": "Standard Room",
            "pms_name": "Standard",
            "status": "active",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db[SANDBOX_MAPPINGS].insert_one(room_mapping)

        # Create rate plan mapping
        pms_rate_plan = "BAR"
        ext_rate_plan = f"{profile['rate_plan_prefix']}BAR"
        rate_mapping = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "entity_type": "rate_plan",
            "external_id": ext_rate_plan,
            "pms_id": pms_rate_plan,
            "external_name": "Best Available Rate",
            "pms_name": "BAR",
            "status": "active",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db[SANDBOX_MAPPINGS].insert_one(rate_mapping)

        return {
            "connector_id": connector_id,
            "property_id": sandbox_property_id,
            "room_reverse": {ext_room_type: pms_room_type},
            "rate_reverse": {ext_rate_plan: pms_rate_plan},
        }

    def _build_report(
        self,
        run_id: str,
        tenant_id: str,
        providers: list[str],
        all_results: dict[str, list[dict[str, Any]]],
        started_at: str,
        completed_at: str,
        actor_id: str | None,
    ) -> dict[str, Any]:
        """Build the final simulation report with per-provider tables."""
        provider_tables = {}
        total_passed = 0
        total_failed = 0
        total_scenarios = 0

        for provider in providers:
            results = all_results.get(provider, [])
            passed = sum(1 for r in results if r.get("passed"))
            failed = len(results) - passed
            total_passed += passed
            total_failed += failed
            total_scenarios += len(results)

            provider_tables[provider] = {
                "display_name": PROVIDER_PROFILES[provider]["display_name"],
                "scenarios": results,
                "passed": passed,
                "failed": failed,
                "total": len(results),
                "pass_rate": f"{(passed / len(results) * 100):.0f}%" if results else "N/A",
            }

        overall_pass_rate = f"{(total_passed / total_scenarios * 100):.0f}%" if total_scenarios else "N/A"

        return {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "triggered_by": actor_id or "system",
            "summary": {
                "total_scenarios": total_scenarios,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate": overall_pass_rate,
                "all_passed": total_failed == 0,
            },
            "provider_results": provider_tables,
        }

    async def cleanup_sandbox_data(self, tenant_id: str, run_id: str):
        """Clean up sandbox data after a simulation run."""
        await db[SANDBOX_CONNECTORS].delete_many(
            {
                "tenant_id": tenant_id,
                "sandbox_run_id": run_id,
            }
        )
        await db.bookings.delete_many(
            {
                "tenant_id": tenant_id,
                "source": "ota_sandbox",
                "created_by": "sandbox_simulation",
            }
        )
        await db.cm_sync_snapshots.delete_many(
            {
                "tenant_id": tenant_id,
                "source": "sandbox_simulation",
            }
        )
        await db.room_type_inventory.delete_many(
            {
                "tenant_id": tenant_id,
                "computation_source": "sandbox_simulation",
            }
        )
        logger.info("Cleaned up sandbox data for run %s", run_id)
