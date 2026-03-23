"""
Sandbox Dashboard Router — Visualization APIs for ops dashboard.

Provides trend, regression, and correlation data for sandbox simulation results.

Endpoints:
  GET  /api/ops/sandbox/dashboard      — Dashboard summary (provider cards, recent run)
  GET  /api/ops/sandbox/trends         — Pass rate trends over last N runs
  GET  /api/ops/sandbox/regressions    — Scenarios that regressed (previously passed, now failing)
  GET  /api/ops/sandbox/correlation    — Correlation with deploys and drift
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from core.database import db
from security.ops_guard import require_ops_access

logger = logging.getLogger("controlplane.sandbox_dashboard")

router = APIRouter(prefix="/api/ops/sandbox", tags=["Sandbox Dashboard"],
                   dependencies=[Depends(require_ops_access)])

SANDBOX_RESULTS = "sandbox_simulation_results"


@router.get("/dashboard")
async def sandbox_dashboard(
    tenant_id: Optional[str] = Query(None),
):
    """Dashboard summary — provider cards with pass/fail, last run time, scenario status."""
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id

    # Get last run
    last_run = await db[SANDBOX_RESULTS].find_one(
        query, {"_id": 0, "_persist": 0},
        sort=[("started_at", -1)],
    )

    if not last_run:
        return {
            "has_data": False,
            "provider_cards": [],
            "last_run": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Build provider cards
    provider_cards = []
    provider_results = last_run.get("provider_results", {})
    for provider, data in provider_results.items():
        scenarios = data.get("scenarios", [])
        card = {
            "provider": provider,
            "display_name": data.get("display_name", provider),
            "passed": data.get("passed", 0),
            "failed": data.get("failed", 0),
            "total": data.get("total", 0),
            "pass_rate": data.get("pass_rate", "N/A"),
            "scenarios": [
                {
                    "name": s.get("scenario", ""),
                    "passed": s.get("passed", False),
                    "details": s.get("details", s.get("error", "")),
                }
                for s in scenarios
            ],
        }
        provider_cards.append(card)

    return {
        "has_data": True,
        "provider_cards": provider_cards,
        "last_run": {
            "run_id": last_run.get("run_id", ""),
            "started_at": last_run.get("started_at", ""),
            "completed_at": last_run.get("completed_at", ""),
            "summary": last_run.get("summary", {}),
            "triggered_by": last_run.get("triggered_by", ""),
        },
        "label": "sandbox_pass",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/trends")
async def sandbox_trends(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    """Pass rate trends over last N simulation runs.

    Returns per-run and per-scenario trend data for charting.
    """
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id

    runs = await db[SANDBOX_RESULTS].find(
        query, {"_id": 0, "_persist": 0},
    ).sort("started_at", -1).limit(limit).to_list(limit)

    runs.reverse()  # Chronological order

    # Overall trend
    overall_trend = []
    # Per-scenario trend
    scenario_trend = {}
    # Per-provider trend
    provider_trend = {}

    for run in runs:
        summary = run.get("summary", {})
        overall_trend.append({
            "run_id": run.get("run_id", ""),
            "date": run.get("started_at", ""),
            "pass_rate": _parse_rate(summary.get("pass_rate", "0%")),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "total": summary.get("total_scenarios", 0),
        })

        # Per provider
        for provider, data in run.get("provider_results", {}).items():
            if provider not in provider_trend:
                provider_trend[provider] = []
            provider_trend[provider].append({
                "run_id": run.get("run_id", ""),
                "date": run.get("started_at", ""),
                "pass_rate": _parse_rate(data.get("pass_rate", "0%")),
                "passed": data.get("passed", 0),
                "failed": data.get("failed", 0),
            })

            # Per scenario
            for s in data.get("scenarios", []):
                sname = s.get("scenario", "")
                key = f"{provider}:{sname}"
                if key not in scenario_trend:
                    scenario_trend[key] = {"provider": provider, "scenario": sname, "history": []}
                scenario_trend[key]["history"].append({
                    "run_id": run.get("run_id", ""),
                    "date": run.get("started_at", ""),
                    "passed": s.get("passed", False),
                })

    # Find most-failing scenario
    failure_counts = {}
    for key, data in scenario_trend.items():
        fails = sum(1 for h in data["history"] if not h["passed"])
        if fails > 0:
            failure_counts[key] = fails
    most_failing = sorted(failure_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "overall_trend": overall_trend,
        "provider_trends": provider_trend,
        "scenario_trends": list(scenario_trend.values()),
        "most_failing_scenarios": [
            {"key": k, "failure_count": v} for k, v in most_failing
        ],
        "total_runs": len(runs),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/regressions")
async def sandbox_regressions(
    tenant_id: Optional[str] = Query(None),
):
    """Detect regressions — scenarios that previously passed but now fail.

    Compares the last two runs to find regressions.
    Returns alert-level information for the ops dashboard.
    """
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id

    runs = await db[SANDBOX_RESULTS].find(
        query, {"_id": 0, "_persist": 0},
    ).sort("started_at", -1).limit(2).to_list(2)

    if len(runs) < 2:
        return {
            "has_regression": False,
            "regressions": [],
            "message": "Not enough runs to detect regressions (need at least 2)",
            "label": "sandbox_regression",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    current = runs[0]
    previous = runs[1]

    regressions = []
    for provider, curr_data in current.get("provider_results", {}).items():
        prev_data = previous.get("provider_results", {}).get(provider, {})
        curr_scenarios = {s["scenario"]: s for s in curr_data.get("scenarios", [])}
        prev_scenarios = {s["scenario"]: s for s in prev_data.get("scenarios", [])}

        for sname, curr_s in curr_scenarios.items():
            prev_s = prev_scenarios.get(sname)
            if prev_s and prev_s.get("passed") and not curr_s.get("passed"):
                regressions.append({
                    "provider": provider,
                    "scenario": sname,
                    "current_run": current.get("run_id", ""),
                    "previous_run": previous.get("run_id", ""),
                    "severity": "critical" if sname in ("duplicate_delivery", "retry_storm") else "warning",
                    "runbook_link": f"/api/ops/runbooks/sandbox_{sname}",
                    "alert_type": "sandbox_regression",
                })

    return {
        "has_regression": len(regressions) > 0,
        "regressions": regressions,
        "current_run": current.get("run_id", ""),
        "previous_run": previous.get("run_id", ""),
        "label": "sandbox_regression",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/correlation")
async def sandbox_correlation(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    """Correlation between sandbox results, deploys, and drift.

    Checks if:
    - Sandbox pass rate dropped after a deploy
    - Drift increased around the same time as sandbox failures
    - Provider health correlated with sandbox results
    """
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id

    # Get recent sandbox runs
    runs = await db[SANDBOX_RESULTS].find(
        query, {"_id": 0, "run_id": 1, "started_at": 1, "summary": 1},
    ).sort("started_at", -1).limit(limit).to_list(limit)

    # Get recent deploys
    deploys = []
    try:
        deploys = await db["cp_deploy_events"].find(
            {}, {"_id": 0, "deploy_id": 1, "started_at": 1, "status": 1, "environment": 1},
        ).sort("started_at", -1).limit(limit).to_list(limit)
    except Exception:
        pass

    # Get recent drift snapshots
    drift_count = 0
    try:
        drift_count = await db["drift_alert_events"].count_documents(
            {"severity": {"$in": ["critical", "severe"]}}
        )
    except Exception:
        pass

    # Build correlation data
    correlations = []
    for i, run in enumerate(runs):
        rate = _parse_rate(run.get("summary", {}).get("pass_rate", "100%"))
        # Find closest deploy before this run
        run_time = run.get("started_at", "")
        closest_deploy = None
        for d in deploys:
            if d.get("started_at", "") <= run_time:
                closest_deploy = d
                break

        correlations.append({
            "run_id": run.get("run_id", ""),
            "date": run_time,
            "pass_rate": rate,
            "closest_deploy": {
                "deploy_id": closest_deploy.get("deploy_id", ""),
                "status": closest_deploy.get("status", ""),
                "environment": closest_deploy.get("environment", ""),
            } if closest_deploy else None,
            "pass_rate_dropped": (
                i > 0 and rate < _parse_rate(runs[i-1].get("summary", {}).get("pass_rate", "100%"))
            ),
        })

    return {
        "correlations": correlations,
        "drift_alerts_active": drift_count,
        "insight": (
            "Sandbox pass rate stable — no correlation with recent deploys"
            if all(not c["pass_rate_dropped"] for c in correlations)
            else "Sandbox pass rate dropped — investigate recent deploy impact"
        ),
        "label": "prod_health",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _parse_rate(rate_str: str) -> float:
    """Parse a percentage string like '100%' into a float."""
    try:
        return float(rate_str.replace("%", ""))
    except (ValueError, AttributeError):
        return 0.0
