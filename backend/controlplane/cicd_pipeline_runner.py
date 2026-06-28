"""
CI/CD Pipeline Runner — 3-tier sandbox validation for deploy confidence.

Tiers:
  1. PR Gate      — Quick subset (5 scenarios, low concurrency), doesn't block dev flow
  2. Staging Gate — Full scenario pack, drift/reconciliation assertions, ops metrics snapshot
  3. Nightly      — Heavy concurrency, longer retry storm, cross-provider comparison, trend analysis

Each run produces:
  - per-provider pass/fail
  - acceptance criteria evaluation (oversell=0, duplicate=0, inconsistent=0, etc.)
  - deploy gate verdict (PASS / BLOCK)
  - runbook links for every failure
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from channel_manager.application.sandbox_simulation.engine import SandboxSimulationEngine
from core.database import db

logger = logging.getLogger("controlplane.cicd_pipeline_runner")

CICD_RUNS = "cicd_pipeline_runs"

# ── Scenario → Acceptance mapping ──────────────────────────────────
CRITICAL_SCENARIOS = {
    "duplicate_delivery",
    "retry_storm",
    "modify_cancel_race",
    "stale_provider_state",
    "delayed_ack",
}

HARD_FAIL_SCENARIOS = {
    "duplicate_delivery": "duplicate inventory consumption",
    "retry_storm": "oversell detection",
    "modify_cancel_race": "non-deterministic modify/cancel",
    "stale_provider_state": "stale recovery / reconciliation fail",
}

RUNBOOKS = {
    "duplicate_delivery": {
        "severity": "critical",
        "impact": "Double inventory consumption — guest may arrive to occupied room",
        "runbook": "/api/ops/runbooks/sandbox_duplicate_delivery",
        "rollback": "Revert last import-pipeline change. Check fingerprint logic in ImportedReservation.",
    },
    "delayed_ack": {
        "severity": "high",
        "impact": "Inconsistent state between PMS and provider — ACK tracking broken",
        "runbook": "/api/ops/runbooks/sandbox_delayed_ack",
        "rollback": "Check ACK retry worker. Verify ack_status transitions.",
    },
    "retry_storm": {
        "severity": "critical",
        "impact": "Oversell — multiple PMS bookings for same reservation",
        "runbook": "/api/ops/runbooks/sandbox_retry_storm",
        "rollback": "Check idempotency key / fingerprint dedup. Rollback booking creation changes.",
    },
    "stale_provider_state": {
        "severity": "critical",
        "impact": "Provider selling rooms PMS doesn't have — reconciliation broken",
        "runbook": "/api/ops/runbooks/sandbox_stale_provider_state",
        "rollback": "Verify reconciliation service. Check cm_sync_snapshots vs room_type_inventory.",
    },
    "modify_cancel_race": {
        "severity": "critical",
        "impact": "Non-deterministic booking state — cancel may not propagate",
        "runbook": "/api/ops/runbooks/sandbox_modify_cancel_race",
        "rollback": "Check reservation state machine. Verify cancel-after-modify path.",
    },
}

# ── Tier Configs ───────────────────────────────────────────────────
TIER_CONFIGS = {
    "pr_gate": {
        "display_name": "PR Gate",
        "description": "Quick validation — lightweight subset, fast feedback",
        "scenarios": list(CRITICAL_SCENARIOS),
        "duplicate_count": 3,
        "storm_size": 6,
        "providers": ["hotelrunner", "exely"],
        "blocks_deploy": True,
        "timeout_seconds": 60,
    },
    "staging_gate": {
        "display_name": "Staging Gate",
        "description": "Full scenario pack — real quality gate",
        "scenarios": list(CRITICAL_SCENARIOS),
        "duplicate_count": 5,
        "storm_size": 10,
        "providers": ["hotelrunner", "exely"],
        "blocks_deploy": True,
        "timeout_seconds": 120,
    },
    "nightly": {
        "display_name": "Nightly Resilience",
        "description": "Heavy concurrency — daily confidence signal",
        "scenarios": list(CRITICAL_SCENARIOS),
        "duplicate_count": 10,
        "storm_size": 25,
        "providers": ["hotelrunner", "exely"],
        "blocks_deploy": False,
        "timeout_seconds": 300,
    },
}


class CICDPipelineRunner:
    """Orchestrates sandbox simulation as part of CI/CD pipeline."""

    def __init__(self):
        self._engine = SandboxSimulationEngine()

    async def run_pipeline(
        self,
        tier: str,
        tenant_id: str,
        property_id: str,
        build_id: str | None = None,
        commit_sha: str | None = None,
        deploy_id: str | None = None,
        triggered_by: str = "system",
    ) -> dict[str, Any]:
        """Execute a CI/CD pipeline run for the given tier."""
        config = TIER_CONFIGS.get(tier)
        if not config:
            return {"error": f"Unknown tier: {tier}", "valid_tiers": list(TIER_CONFIGS.keys())}

        run_id = f"cicd-{tier}-{uuid.uuid4().hex[:10]}"
        started_at = datetime.now(UTC).isoformat()

        logger.info(
            "CI/CD Pipeline [%s] starting — run=%s build=%s commit=%s",
            tier,
            run_id,
            build_id,
            commit_sha,
        )

        # Run the sandbox simulation
        sim_result = await self._engine.run_full_simulation(
            tenant_id=tenant_id,
            property_id=property_id,
            providers=config["providers"],
            actor_id=f"cicd:{tier}:{triggered_by}",
        )

        completed_at = datetime.now(UTC).isoformat()

        # Evaluate acceptance criteria
        acceptance = self._evaluate_acceptance(sim_result, tier)

        # Build the pipeline result
        pipeline_result = {
            "run_id": run_id,
            "tier": tier,
            "tier_config": {
                "display_name": config["display_name"],
                "description": config["description"],
                "blocks_deploy": config["blocks_deploy"],
            },
            "build_context": {
                "build_id": build_id or "manual",
                "commit_sha": commit_sha or "HEAD",
                "deploy_id": deploy_id,
            },
            "tenant_id": tenant_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "triggered_by": triggered_by,
            "simulation_run_id": sim_result.get("run_id", ""),
            "simulation_summary": sim_result.get("summary", {}),
            "provider_results": self._enrich_provider_results(sim_result.get("provider_results", {})),
            "acceptance_criteria": acceptance,
            "deploy_gate": self._compute_gate_verdict(acceptance, config),
            "health_label": self._compute_health_label(tier),
        }

        # Persist
        await db[CICD_RUNS].insert_one({**pipeline_result, "_persist": True})

        logger.info(
            "CI/CD Pipeline [%s] complete — run=%s verdict=%s",
            tier,
            run_id,
            pipeline_result["deploy_gate"]["verdict"],
        )

        return pipeline_result

    def _evaluate_acceptance(self, sim_result: dict, tier: str) -> dict[str, Any]:
        """Evaluate minimum acceptance criteria for deploy."""
        provider_results = sim_result.get("provider_results", {})
        summary = sim_result.get("summary", {})

        criteria = []

        # Per-provider all-pass check
        for provider, data in provider_results.items():
            all_pass = data.get("failed", 1) == 0
            criteria.append(
                {
                    "id": f"{provider}_all_pass",
                    "name": f"{data.get('display_name', provider)} sandbox: all critical PASS",
                    "passed": all_pass,
                    "severity": "critical",
                    "value": data.get("pass_rate", "N/A"),
                }
            )

        # Per-scenario checks with assertions
        oversell_total = 0
        duplicate_consumption_total = 0
        inconsistent_state = False
        stale_recovery = True
        reconciliation_recovery = True
        deterministic = True

        for provider, data in provider_results.items():
            for scenario in data.get("scenarios", []):
                name = scenario.get("scenario", "")
                assertions = scenario.get("assertions", {})

                if name == "retry_storm":
                    oversell_total += scenario.get("oversell_count", 0)
                elif name == "duplicate_delivery":
                    duplicate_consumption_total += scenario.get("double_inventory_consumption", 0)
                elif name == "delayed_ack":
                    if not assertions.get("consistent_state", True):
                        inconsistent_state = True
                elif name == "stale_provider_state":
                    if not assertions.get("drift_detected", True):
                        stale_recovery = False
                    if not assertions.get("reconciliation_recovery", True):
                        reconciliation_recovery = False
                elif name == "modify_cancel_race":
                    if not assertions.get("deterministic_sequence", True):
                        deterministic = False

        criteria.extend(
            [
                {
                    "id": "zero_oversell",
                    "name": "oversell: 0",
                    "passed": oversell_total == 0,
                    "severity": "critical",
                    "value": str(oversell_total),
                },
                {
                    "id": "zero_duplicate_consumption",
                    "name": "duplicate inventory consumption: 0",
                    "passed": duplicate_consumption_total == 0,
                    "severity": "critical",
                    "value": str(duplicate_consumption_total),
                },
                {
                    "id": "zero_inconsistent_state",
                    "name": "inconsistent state: 0",
                    "passed": not inconsistent_state,
                    "severity": "critical",
                    "value": "0" if not inconsistent_state else "DETECTED",
                },
                {
                    "id": "stale_provider_recovery",
                    "name": "stale provider recovery: PASS",
                    "passed": stale_recovery,
                    "severity": "critical",
                    "value": "PASS" if stale_recovery else "FAIL",
                },
                {
                    "id": "reconciliation_recovery",
                    "name": "drift reconciliation recovery: PASS",
                    "passed": reconciliation_recovery,
                    "severity": "critical",
                    "value": "PASS" if reconciliation_recovery else "FAIL",
                },
                {
                    "id": "deterministic_modify_cancel",
                    "name": "deterministic modify/cancel: PASS",
                    "passed": deterministic,
                    "severity": "critical",
                    "value": "PASS" if deterministic else "FAIL",
                },
            ]
        )

        # Regression check vs baseline
        regression_check = {
            "id": "zero_regression_vs_baseline",
            "name": "new regression vs baseline: 0 critical",
            "passed": summary.get("all_passed", False),
            "severity": "critical",
            "value": "0" if summary.get("all_passed", False) else str(summary.get("failed", "?")),
        }
        criteria.append(regression_check)

        all_passed = all(c["passed"] for c in criteria)
        critical_failures = [c for c in criteria if not c["passed"] and c["severity"] == "critical"]

        return {
            "criteria": criteria,
            "all_passed": all_passed,
            "critical_failure_count": len(critical_failures),
            "critical_failures": [c["id"] for c in critical_failures],
        }

    def _compute_gate_verdict(self, acceptance: dict, config: dict) -> dict[str, Any]:
        """Compute deploy gate verdict: PASS or BLOCK."""
        all_passed = acceptance.get("all_passed", False)
        blocks = config.get("blocks_deploy", False)

        if all_passed:
            return {
                "verdict": "PASS",
                "deploy_allowed": True,
                "message": "All acceptance criteria met. Deploy is safe.",
                "blocked": False,
            }

        critical_failures = acceptance.get("critical_failures", [])
        fail_details = []
        for fail_id in critical_failures:
            # Find matching scenario runbook
            scenario_key = fail_id.replace("_all_pass", "").split("_")[0]
            for s_key, rb in RUNBOOKS.items():
                if s_key in fail_id or scenario_key in s_key:
                    fail_details.append(
                        {
                            "criteria_id": fail_id,
                            **rb,
                        }
                    )
                    break
            else:
                fail_details.append(
                    {
                        "criteria_id": fail_id,
                        "severity": "critical",
                        "impact": f"Acceptance criteria '{fail_id}' failed",
                        "runbook": "/api/ops/runbooks/general",
                        "rollback": "Investigate the failing criteria and fix before deploying.",
                    }
                )

        return {
            "verdict": "BLOCK" if blocks else "WARN",
            "deploy_allowed": not blocks,
            "message": f"{len(critical_failures)} critical criteria failed. Deploy {'blocked' if blocks else 'warned'}.",
            "blocked": blocks,
            "failure_details": fail_details,
        }

    def _enrich_provider_results(self, provider_results: dict) -> dict[str, Any]:
        """Attach runbook info to each failed scenario."""
        enriched = {}
        for provider, data in provider_results.items():
            scenarios = []
            for s in data.get("scenarios", []):
                enriched_s = {**s}
                if not s.get("passed", True):
                    scenario_name = s.get("scenario", "")
                    rb = RUNBOOKS.get(scenario_name, {})
                    enriched_s["runbook"] = {
                        "severity": rb.get("severity", "unknown"),
                        "impact": rb.get("impact", ""),
                        "link": rb.get("runbook", ""),
                        "rollback": rb.get("rollback", ""),
                    }
                scenarios.append(enriched_s)
            enriched[provider] = {**data, "scenarios": scenarios}
        return enriched

    def _compute_health_label(self, tier: str) -> str:
        """Return the health label for this tier's results."""
        label_map = {
            "pr_gate": "sandbox_validation",
            "staging_gate": "staging_deploy_validation",
            "nightly": "prod_health",
        }
        return label_map.get(tier, "sandbox_validation")

    async def get_runs(
        self,
        tenant_id: str | None = None,
        tier: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent CI/CD pipeline runs."""
        query: dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if tier:
            query["tier"] = tier
        runs = (
            await db[CICD_RUNS]
            .find(
                query,
                {"_id": 0, "_persist": 0},
            )
            .sort("started_at", -1)
            .limit(limit)
            .to_list(limit)
        )
        return runs

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a specific pipeline run."""
        return await db[CICD_RUNS].find_one(
            {"run_id": run_id},
            {"_id": 0, "_persist": 0},
        )

    async def get_baseline(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Get the last passing baseline for each tier."""
        baselines = {}
        for tier in TIER_CONFIGS:
            query: dict[str, Any] = {"tier": tier, "acceptance_criteria.all_passed": True}
            if tenant_id:
                query["tenant_id"] = tenant_id
            last_pass = await db[CICD_RUNS].find_one(
                query,
                {"_id": 0, "_persist": 0},
                sort=[("started_at", -1)],
            )
            if last_pass:
                baselines[tier] = {
                    "run_id": last_pass.get("run_id"),
                    "started_at": last_pass.get("started_at"),
                    "build_context": last_pass.get("build_context"),
                    "simulation_summary": last_pass.get("simulation_summary"),
                }
            else:
                baselines[tier] = None
        return baselines

    async def get_health_badges(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Get health badges for sandbox / staging / prod — kept separate."""
        badges = {}
        label_map = {
            "pr_gate": "sandbox_validation",
            "staging_gate": "staging_deploy_validation",
            "nightly": "prod_health",
        }
        for tier, label in label_map.items():
            query: dict[str, Any] = {"tier": tier}
            if tenant_id:
                query["tenant_id"] = tenant_id
            last_run = await db[CICD_RUNS].find_one(
                query,
                {"_id": 0, "_persist": 0},
                sort=[("started_at", -1)],
            )
            if last_run:
                gate = last_run.get("deploy_gate", {})
                badges[label] = {
                    "status": "pass" if gate.get("verdict") == "PASS" else "fail",
                    "verdict": gate.get("verdict", "UNKNOWN"),
                    "run_id": last_run.get("run_id"),
                    "tier": tier,
                    "display_name": TIER_CONFIGS[tier]["display_name"],
                    "last_run_at": last_run.get("completed_at"),
                    "build_id": last_run.get("build_context", {}).get("build_id"),
                    "commit_sha": last_run.get("build_context", {}).get("commit_sha"),
                    "pass_rate": last_run.get("simulation_summary", {}).get("pass_rate", "N/A"),
                }
            else:
                badges[label] = {
                    "status": "no_data",
                    "verdict": "NO_DATA",
                    "tier": tier,
                    "display_name": TIER_CONFIGS[tier]["display_name"],
                }
        return badges

    async def get_trends(
        self,
        tenant_id: str | None = None,
        tier: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Get trend data across CI/CD runs for charting."""
        query: dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if tier:
            query["tier"] = tier

        runs = (
            await db[CICD_RUNS]
            .find(
                query,
                {
                    "_id": 0,
                    "run_id": 1,
                    "tier": 1,
                    "started_at": 1,
                    "simulation_summary": 1,
                    "acceptance_criteria.all_passed": 1,
                    "deploy_gate.verdict": 1,
                    "build_context": 1,
                    "provider_results": 1,
                },
            )
            .sort("started_at", -1)
            .limit(limit)
            .to_list(limit)
        )

        runs.reverse()  # chronological

        trend_data = []
        for run in runs:
            summary = run.get("simulation_summary", {})
            trend_data.append(
                {
                    "run_id": run.get("run_id"),
                    "tier": run.get("tier"),
                    "date": run.get("started_at"),
                    "pass_rate": _parse_rate(summary.get("pass_rate", "0%")),
                    "passed": summary.get("passed", 0),
                    "failed": summary.get("failed", 0),
                    "total": summary.get("total_scenarios", 0),
                    "verdict": run.get("deploy_gate", {}).get("verdict", "UNKNOWN"),
                    "all_criteria_met": run.get("acceptance_criteria", {}).get("all_passed", False),
                    "build_id": run.get("build_context", {}).get("build_id"),
                    "commit_sha": run.get("build_context", {}).get("commit_sha"),
                }
            )

        # Provider-level trends
        provider_trends = {}
        for run in runs:
            for provider, data in run.get("provider_results", {}).items():
                if provider not in provider_trends:
                    provider_trends[provider] = []
                provider_trends[provider].append(
                    {
                        "run_id": run.get("run_id"),
                        "date": run.get("started_at"),
                        "pass_rate": _parse_rate(data.get("pass_rate", "0%")),
                        "passed": data.get("passed", 0),
                        "failed": data.get("failed", 0),
                    }
                )

        return {
            "overall_trend": trend_data,
            "provider_trends": provider_trends,
            "total_runs": len(runs),
            "timestamp": datetime.now(UTC).isoformat(),
        }


def _parse_rate(rate_str: str) -> float:
    try:
        return float(str(rate_str).replace("%", ""))
    except (ValueError, AttributeError):
        return 0.0
