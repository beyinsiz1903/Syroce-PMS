"""
Learning Loop System
=====================
Closed-loop incident learning: auto-classification, recurrence detection,
RCA tracking, and never-again rule enforcement.
"""
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db

logger = logging.getLogger(__name__)

CLASSIFICATION_RULES = [
    {"keywords": ["exely", "hotelrunner", "provider", "503", "502", "ota"],
     "category": "provider", "subcategory": "provider_error"},
    {"keywords": ["timeout", "timed out", "connection refused"],
     "category": "infrastructure", "subcategory": "timeout"},
    {"keywords": ["memory", "oom", "disk", "cpu", "resource"],
     "category": "infrastructure", "subcategory": "resource_exhaustion"},
    {"keywords": ["mongodb", "redis", "connection pool", "replica"],
     "category": "infrastructure", "subcategory": "database"},
    {"keywords": ["mapping error", "validation", "schema", "corrupt"],
     "category": "data", "subcategory": "data_corruption"},
    {"keywords": ["duplicate", "conflict", "idempotency"],
     "category": "data", "subcategory": "duplicate"},
    {"keywords": ["unauthorized", "forbidden", "token", "credential", "breach"],
     "category": "security", "subcategory": "auth_failure"},
    {"keywords": ["null pointer", "attribute error", "type error", "unhandled", "traceback"],
     "category": "code_bug", "subcategory": "unhandled_exception"},
    {"keywords": ["race condition", "concurrent", "deadlock"],
     "category": "code_bug", "subcategory": "race_condition"},
    {"keywords": ["config", "configuration", "env", "environment"],
     "category": "human_error", "subcategory": "config_error"},
]


def _compute_pattern_signature(category: str, subcategory: str, affected_service: str) -> str:
    raw = f"{category}:{subcategory}:{affected_service}"
    return hashlib.sha256(raw.encode()).hexdigest()


class IncidentClassifier:
    """Auto-classifies and tags incidents based on keyword matching."""

    def classify(self, title: str, description: str) -> Dict[str, Any]:
        text = f"{title} {description}".lower()
        best_match = None
        best_score = 0

        for rule in CLASSIFICATION_RULES:
            score = sum(1 for kw in rule["keywords"] if kw in text)
            if score > best_score:
                best_score = score
                best_match = rule

        if best_match and best_score > 0:
            return {
                "category": best_match["category"],
                "subcategory": best_match["subcategory"],
                "auto_classified": True,
                "confidence": min(0.5 + best_score * 0.15, 0.95),
                "tags": self._extract_tags(text),
                "auto_tagged": True,
            }

        return {
            "category": "unknown",
            "subcategory": "unknown",
            "auto_classified": True,
            "confidence": 0.0,
            "tags": self._extract_tags(text),
            "auto_tagged": True,
        }

    def _extract_tags(self, text: str) -> List[str]:
        tag_candidates = [
            "exely", "hotelrunner", "timeout", "reservation", "booking",
            "channel", "sync", "import", "outbox", "night_audit",
            "folio", "payment", "checkin", "checkout", "mapping",
            "rate", "availability", "webhook", "provider",
        ]
        return [tag for tag in tag_candidates if tag in text]


class RCAEngine:
    """Root Cause Analysis tracking and management."""

    async def create_rca(
        self,
        tenant_id: str,
        incident_id: str,
        summary: str,
        contributing_factors: List[str],
        five_whys: Optional[List[str]] = None,
        root_cause_type: str = "internal_bug",
        actor_id: str = "system",
    ) -> Dict[str, Any]:
        rca_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        rca = {
            "id": rca_id,
            "status": "in_progress",
            "summary": summary,
            "contributing_factors": contributing_factors,
            "five_whys": five_whys or [],
            "root_cause_type": root_cause_type,
            "fix_applied": None,
            "fix_deployed_at": None,
            "completed_at": None,
            "completed_by": None,
        }

        result = await db.incidents.update_one(
            {"id": incident_id, "tenant_id": tenant_id},
            {
                "$set": {
                    "root_cause_analysis": rca,
                    "status": "postmortem",
                    "updated_at": now,
                },
                "$push": {
                    "timeline": {
                        "action": "postmortem_started",
                        "actor": actor_id,
                        "timestamp": now,
                        "note": summary,
                    }
                },
            },
        )
        if result.modified_count == 0:
            raise ValueError(f"Incident {incident_id} not found")
        return {"rca_id": rca_id, "status": "in_progress"}

    async def track_fix(
        self,
        tenant_id: str,
        incident_id: str,
        fix_applied: str,
        actor_id: str = "system",
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        result = await db.incidents.update_one(
            {"id": incident_id, "tenant_id": tenant_id},
            {
                "$set": {
                    "root_cause_analysis.fix_applied": fix_applied,
                    "root_cause_analysis.fix_deployed_at": now,
                    "root_cause_analysis.status": "completed",
                    "root_cause_analysis.completed_at": now,
                    "root_cause_analysis.completed_by": actor_id,
                    "updated_at": now,
                },
                "$push": {
                    "timeline": {
                        "action": "fix_deployed",
                        "actor": actor_id,
                        "timestamp": now,
                        "note": fix_applied,
                    }
                },
            },
        )
        if result.modified_count == 0:
            raise ValueError(f"Incident {incident_id} not found")
        return {"incident_id": incident_id, "fix_applied": fix_applied}

    async def create_never_again_rule(
        self,
        tenant_id: str,
        incident_id: str,
        rule_type: str,
        description: str,
        implementation: str,
        verification_type: str = "test_exists",
        verification_detail: str = "",
        assigned_to: str = "backend_team",
        due_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        rule_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        rule = {
            "id": rule_id,
            "rule_type": rule_type,
            "description": description,
            "implementation": implementation,
            "verification": {
                "type": verification_type,
                "detail": verification_detail,
            },
            "status": "pending",
            "assigned_to": assigned_to,
            "due_date": due_date,
            "created_at": now,
            "verified_at": None,
        }

        result = await db.incidents.update_one(
            {"id": incident_id, "tenant_id": tenant_id},
            {
                "$push": {"never_again_rules": rule},
                "$set": {"updated_at": now},
            },
        )
        if result.modified_count == 0:
            raise ValueError(f"Incident {incident_id} not found")
        return {"rule_id": rule_id, "status": "pending"}

    async def verify_prevention(
        self,
        tenant_id: str,
        incident_id: str,
    ) -> Dict[str, Any]:
        incident = await db.incidents.find_one(
            {"id": incident_id, "tenant_id": tenant_id},
            {"_id": 0, "never_again_rules": 1},
        )
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        rules = incident.get("never_again_rules", [])
        pending = [r for r in rules if r["status"] not in ("verified", "enforced")]
        return {
            "all_verified": len(pending) == 0,
            "total_rules": len(rules),
            "verified_count": len(rules) - len(pending),
            "pending_rules": pending,
        }


class RecurrenceDetector:
    """Detects recurring incidents based on pattern signatures."""

    async def detect_recurrence(
        self,
        tenant_id: str,
        incident_id: str,
        category: str,
        subcategory: str,
        affected_service: str,
    ) -> Dict[str, Any]:
        signature = _compute_pattern_signature(category, subcategory, affected_service)

        # Store signature on incident
        await db.incidents.update_one(
            {"id": incident_id, "tenant_id": tenant_id},
            {"$set": {"recurrence.pattern_signature": signature}},
        )

        previous = await db.incidents.find(
            {
                "tenant_id": tenant_id,
                "recurrence.pattern_signature": signature,
                "id": {"$ne": incident_id},
                "status": {"$in": ["resolved", "postmortem", "closed"]},
            },
            {"_id": 0, "id": 1, "title": 1, "created_at": 1, "never_again_rules": 1},
        ).sort("created_at", -1).limit(5).to_list(5)

        if previous:
            violated_rules = []
            for prev in previous:
                for rule in prev.get("never_again_rules", []):
                    if rule.get("status") in ("implemented", "verified", "enforced"):
                        violated_rules.append({
                            "rule_id": rule["id"],
                            "description": rule["description"],
                            "from_incident": prev["id"],
                        })

            recurrence_data = {
                "is_recurrence": True,
                "previous_incident_ids": [p["id"] for p in previous],
                "recurrence_count": len(previous),
                "violated_never_again_rules": violated_rules,
                "severity_escalation": bool(violated_rules),
            }
        else:
            recurrence_data = {
                "is_recurrence": False,
                "previous_incident_ids": [],
                "recurrence_count": 0,
                "violated_never_again_rules": [],
                "severity_escalation": False,
            }

        await db.incidents.update_one(
            {"id": incident_id, "tenant_id": tenant_id},
            {"$set": {"recurrence": {**recurrence_data, "pattern_signature": signature}}},
        )

        return recurrence_data


class LearningDashboard:
    """Aggregate learning metrics."""

    async def get_metrics(self, tenant_id: str) -> Dict[str, Any]:
        total = await db.incidents.count_documents({"tenant_id": tenant_id})
        resolved = await db.incidents.count_documents(
            {"tenant_id": tenant_id, "status": {"$in": ["resolved", "closed"]}}
        )
        recurring = await db.incidents.count_documents(
            {"tenant_id": tenant_id, "recurrence.is_recurrence": True}
        )

        # MTTR calculation
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "status": {"$in": ["resolved", "closed"]}}},
            {"$addFields": {
                "metrics_total": {"$ifNull": ["$metrics.total_duration_seconds", 0]}
            }},
            {"$group": {
                "_id": None,
                "avg_mttr": {"$avg": "$metrics_total"},
            }},
        ]
        mttr_result = await db.incidents.aggregate(pipeline).to_list(1)
        avg_mttr = mttr_result[0]["avg_mttr"] if mttr_result else 0

        # Never-again rule stats
        rule_pipeline = [
            {"$match": {"tenant_id": tenant_id, "never_again_rules": {"$exists": True, "$ne": []}}},
            {"$unwind": "$never_again_rules"},
            {"$group": {
                "_id": "$never_again_rules.status",
                "count": {"$sum": 1},
            }},
        ]
        rule_stats = await db.incidents.aggregate(rule_pipeline).to_list(20)
        rules_by_status = {r["_id"]: r["count"] for r in rule_stats}
        total_rules = sum(rules_by_status.values())
        verified_rules = rules_by_status.get("verified", 0) + rules_by_status.get("enforced", 0)

        recurrence_rate = round((recurring / total * 100), 1) if total > 0 else 0.0

        return {
            "total_incidents": total,
            "resolved_incidents": resolved,
            "recurring_incidents": recurring,
            "recurrence_rate": recurrence_rate,
            "avg_mttr_seconds": round(avg_mttr, 0),
            "never_again_rules_total": total_rules,
            "never_again_rules_verified": verified_rules,
            "rules_by_status": rules_by_status,
        }


async def ensure_learning_loop_indexes():
    await db.incidents.create_index(
        [("tenant_id", 1), ("recurrence.pattern_signature", 1)],
        name="idx_incident_recurrence_pattern",
    )
    await db.incidents.create_index(
        [("tenant_id", 1), ("classification.category", 1), ("created_at", -1)],
        name="idx_incident_classification",
    )
    logger.info("Learning loop indexes ensured")
