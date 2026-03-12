"""
Audit Completeness - Validates that all critical operations have proper audit trails.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from core.database import db

logger = logging.getLogger("security.audit")

AUDITABLE_OPERATIONS = {
    "auth": ["login", "logout", "token_refresh", "password_change"],
    "booking": ["create", "modify", "cancel", "check_in", "check_out"],
    "folio": ["create", "charge", "payment", "close", "split"],
    "rate": ["rate_change", "autopilot_apply", "rate_override"],
    "guest": ["create", "update", "merge", "delete", "gdpr_request"],
    "messaging": ["send", "retry", "provider_change"],
    "pipeline": ["pipeline_run", "model_deploy", "prediction"],
    "security": ["permission_change", "credential_rotation", "isolation_check"],
    "system": ["config_change", "module_enable", "module_disable"],
}


class AuditCompletenessService:
    """Checks and enforces audit trail completeness."""

    async def check_completeness(self, tenant_id: str, hours: int = 24) -> Dict[str, Any]:
        """Check audit completeness for a tenant over a time period."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # Get all audit entries for the period
        audit_entries = await db.audit_logs.find(
            {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}},
            {"_id": 0, "action": 1, "entity_type": 1, "timestamp": 1},
        ).to_list(10000)

        # Group by entity type
        covered_actions: Dict[str, set] = {}
        for entry in audit_entries:
            etype = entry.get("entity_type", "unknown")
            action = entry.get("action", "unknown")
            covered_actions.setdefault(etype, set()).add(action)

        # Check coverage
        results = []
        total_required = 0
        total_covered = 0

        for category, expected_actions in AUDITABLE_OPERATIONS.items():
            covered = covered_actions.get(category, set())
            missing = [a for a in expected_actions if a not in covered]
            total_required += len(expected_actions)
            total_covered += len(expected_actions) - len(missing)

            results.append({
                "category": category,
                "expected_actions": expected_actions,
                "covered_actions": list(covered),
                "missing_actions": missing,
                "coverage": round(
                    (len(expected_actions) - len(missing)) / max(len(expected_actions), 1), 4
                ),
                "status": "complete" if not missing else "incomplete",
            })

        score = round(total_covered / max(total_required, 1), 4)
        return {
            "tenant_id": tenant_id,
            "period_hours": hours,
            "total_audit_entries": len(audit_entries),
            "completeness_score": score,
            "status": "complete" if score >= 0.9 else "attention_needed" if score >= 0.7 else "incomplete",
            "categories": results,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_audit_gaps(self, tenant_id: str, hours: int = 24) -> List[dict]:
        """Find gaps in audit trail."""
        completeness = await self.check_completeness(tenant_id, hours)
        gaps = []
        for cat in completeness.get("categories", []):
            if cat["missing_actions"]:
                gaps.append({
                    "category": cat["category"],
                    "missing_actions": cat["missing_actions"],
                    "coverage": cat["coverage"],
                })
        return gaps

    async def get_audit_summary(self, tenant_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get audit trail summary with top actors and actions."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        pipeline = [
            {"$match": {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}}},
            {"$group": {
                "_id": {"action": "$action", "entity_type": "$entity_type"},
                "count": {"$sum": 1},
                "latest": {"$max": "$timestamp"},
            }},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        results = await db.audit_logs.aggregate(pipeline).to_list(20)

        actor_pipeline = [
            {"$match": {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$actor_id",
                "action_count": {"$sum": 1},
            }},
            {"$sort": {"action_count": -1}},
            {"$limit": 10},
        ]
        actors = await db.audit_logs.aggregate(actor_pipeline).to_list(10)

        total = await db.audit_logs.count_documents(
            {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}}
        )

        return {
            "tenant_id": tenant_id,
            "period_hours": hours,
            "total_entries": total,
            "top_actions": [
                {
                    "action": r["_id"]["action"],
                    "entity_type": r["_id"]["entity_type"],
                    "count": r["count"],
                    "latest": r["latest"],
                }
                for r in results
            ],
            "top_actors": [
                {"actor_id": a["_id"], "action_count": a["action_count"]}
                for a in actors
            ],
        }


audit_completeness = AuditCompletenessService()
