"""
Deploy Tracker — CI/CD → Control Plane Bridge
================================================
Records deployment events from CI/CD pipelines into MongoDB,
making deploy history visible in the Control Plane dashboard.

Collections:
  deploy_events — Append-only log of all deployment attempts

This module bridges the gap between CI/CD (GitHub Actions) and
the operational dashboard, giving teams a single pane of glass
for deploy history, success rates, rollback events, and smoke
test results.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from core.database import _raw_db as db

logger = logging.getLogger("controlplane.deploy_tracker")

COLL_DEPLOYS = "deploy_events"


async def ensure_deploy_indexes():
    """Create indexes for deploy_events collection."""
    col = db[COLL_DEPLOYS]
    await col.create_index(
        [("recorded_at", -1)],
        name="idx_deploy_recorded_desc",
    )
    await col.create_index(
        [("environment", 1), ("recorded_at", -1)],
        name="idx_deploy_env_recorded",
    )
    await col.create_index(
        [("status", 1)],
        name="idx_deploy_status",
    )
    await col.create_index(
        [("recorded_at", 1)],
        name="idx_deploy_ttl",
        expireAfterSeconds=7776000,  # 90 days
    )
    logger.info("Deploy event indexes ensured")


async def record_deploy_event(event: dict) -> dict:
    """Record a deploy event from CI/CD pipeline.

    Expected fields:
      sha, environment, status, actor, branch,
      smoke_test (optional), rollback (bool), rollback_reason,
      images (dict), duration_seconds
    """
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "sha": event.get("sha", "unknown"),
        "short_sha": event.get("sha", "unknown")[:8],
        "environment": event.get("environment", "unknown"),
        "status": event.get("status", "unknown"),
        "actor": event.get("actor", "unknown"),
        "branch": event.get("branch", "unknown"),
        "smoke_test": event.get("smoke_test", {}),
        "rollback": event.get("rollback", False),
        "rollback_reason": event.get("rollback_reason"),
        "images": event.get("images", {}),
        "duration_seconds": event.get("duration_seconds"),
        "recorded_at": now,
    }
    await db[COLL_DEPLOYS].insert_one(doc)
    logger.info(
        "Deploy event recorded: %s → %s (%s)",
        doc["short_sha"], doc["environment"], doc["status"],
    )
    return {
        "recorded": True,
        "sha": doc["short_sha"],
        "environment": doc["environment"],
        "status": doc["status"],
    }


async def get_deploy_history(
    environment: Optional[str] = None,
    limit: int = 20,
) -> list:
    """Get recent deploy events, newest first."""
    query = {}
    if environment:
        query["environment"] = environment

    cursor = (
        db[COLL_DEPLOYS]
        .find(query, {"_id": 0})
        .sort("recorded_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(limit)


async def get_deploy_stats() -> dict:
    """Aggregate deploy statistics per environment."""
    pipeline = [
        {
            "$group": {
                "_id": "$environment",
                "total": {"$sum": 1},
                "success": {
                    "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                },
                "failure": {
                    "$sum": {"$cond": [{"$eq": ["$status", "failure"]}, 1, 0]}
                },
                "rollback_count": {
                    "$sum": {"$cond": [{"$eq": ["$rollback", True]}, 1, 0]}
                },
                "last_deploy": {"$max": "$recorded_at"},
                "last_sha": {"$last": "$short_sha"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "environment": "$_id",
                "total": 1,
                "success": 1,
                "failure": 1,
                "rollback_count": 1,
                "success_rate": {
                    "$cond": [
                        {"$gt": ["$total", 0]},
                        {
                            "$round": [
                                {"$multiply": [{"$divide": ["$success", "$total"]}, 100]},
                                1,
                            ]
                        },
                        0,
                    ]
                },
                "last_deploy": 1,
                "last_sha": 1,
            }
        },
        {"$sort": {"environment": 1}},
    ]
    stats = await db[COLL_DEPLOYS].aggregate(pipeline).to_list(10)

    total_all = sum(s["total"] for s in stats)
    success_all = sum(s["success"] for s in stats)

    return {
        "by_environment": stats,
        "overall": {
            "total_deploys": total_all,
            "total_success": success_all,
            "total_failure": sum(s["failure"] for s in stats),
            "total_rollbacks": sum(s["rollback_count"] for s in stats),
            "overall_success_rate": round(
                (success_all / total_all * 100) if total_all > 0 else 0, 1
            ),
        },
    }
