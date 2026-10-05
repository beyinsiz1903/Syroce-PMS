"""
Multi-Property Night Audit Coordination Service.
Property-level audit status board, exception summary, unresolved blocker list,
escalation flow, and multi-property readiness score.
"""

from datetime import UTC, datetime, timedelta

from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.chain_access import resolve_chain_properties, tenant_id_from_document


class MultiPropertyAuditService:
    """Coordinates night audit across multiple properties."""

    AUDIT_STATUSES = ["completed", "running", "blocked", "failed", "pending"]

    async def _scoped_properties(self, current_user: User) -> tuple[str, list[dict]]:
        """Resolve the only properties visible in a central audit view."""
        own, properties = await resolve_chain_properties(current_user, require_headquarters=True)
        tenant_id = tenant_id_from_document(own)
        if not tenant_id:  # pragma: no cover - guarded by resolver invariant
            raise ValueError("Tenant document has no identifier")
        return tenant_id, properties

    async def get_audit_status_board(self, current_user: User) -> dict:
        """Get audit status for all properties visible to this tenant."""
        tenant_id, properties = await self._scoped_properties(current_user)

        board = []
        total_completed = 0
        total_failed = 0
        total_blocked = 0
        total_exceptions = 0

        for prop in properties:
            pid = tenant_id_from_document(prop) or tenant_id
            status = await self._get_property_audit_status(pid)
            board.append(
                {
                    "property_id": pid,
                    "property_name": prop.get("property_name") or prop.get("name", "Unknown"),
                    **status,
                }
            )
            if status["audit_status"] == "completed":
                total_completed += 1
            elif status["audit_status"] == "failed":
                total_failed += 1
            elif status["audit_status"] == "blocked":
                total_blocked += 1
            total_exceptions += status.get("open_exceptions", 0)

        total_props = len(board)
        readiness = round(total_completed / total_props * 100, 1) if total_props else 0

        return {
            "property_count": total_props,
            "board": board,
            "summary": {
                "completed": total_completed,
                "running": sum(1 for b in board if b["audit_status"] == "running"),
                "blocked": total_blocked,
                "failed": total_failed,
                "pending": sum(1 for b in board if b["audit_status"] == "pending"),
                "total_exceptions": total_exceptions,
            },
            "readiness_score": readiness,
        }

    async def _get_property_audit_status(self, property_id: str) -> dict:
        """Get the latest audit status for a single property."""
        today = datetime.now(UTC).date().isoformat()
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()

        # Check last audit record
        system_db = get_system_db()
        last_audit = await system_db.night_audit_records.find_one(
            {"tenant_id": property_id},
            {"_id": 0},
            sort=[("started_at", -1)],
        )

        # Business date
        settings = await system_db.tenant_settings.find_one({"tenant_id": property_id}, {"_id": 0})
        business_date = settings.get("business_date") if settings else today

        # Open exceptions
        open_exc = await system_db.audit_exceptions.count_documents({"tenant_id": property_id, "status": "open"})

        # Determine status
        audit_status = "pending"
        last_audit_date = None
        exceptions_list = []

        if last_audit:
            last_audit_date = last_audit.get("audit_date")
            raw_status = last_audit.get("status", "pending")

            if raw_status == "completed" and last_audit_date == yesterday:
                audit_status = "completed"
            elif raw_status == "in_progress":
                audit_status = "running"
            elif raw_status == "failed":
                audit_status = "failed"
            elif open_exc > 0 and raw_status == "completed":
                audit_status = "blocked"
            elif raw_status == "completed":
                audit_status = "completed"

            exceptions_list = last_audit.get("exceptions", [])[:5]

        return {
            "audit_status": audit_status,
            "business_date": business_date,
            "last_audit_date": last_audit_date,
            "open_exceptions": open_exc,
            "recent_exceptions": exceptions_list,
        }

    async def get_exception_summary(self, current_user: User) -> dict:
        """Get aggregated exception summary across all properties."""
        _, properties = await self._scoped_properties(current_user)
        tenant_ids = [tenant_id_from_document(prop) for prop in properties]
        system_db = get_system_db()
        exceptions = await system_db.audit_exceptions.find(
            {"tenant_id": {"$in": [tenant_id for tenant_id in tenant_ids if tenant_id]}, "status": "open"}, {"_id": 0}
        ).sort("created_at", -1).to_list(500)

        by_type = {}
        by_property = {}

        for exc in exceptions:
            etype = exc.get("exception_type", "unknown")
            pid = exc.get("tenant_id", "unknown")

            by_type.setdefault(etype, 0)
            by_type[etype] += 1

            by_property.setdefault(pid, 0)
            by_property[pid] += 1

        return {
            "total_open": len(exceptions),
            "by_type": by_type,
            "by_property": by_property,
            "recent": exceptions[:20],
        }

    async def get_unresolved_blockers(self, current_user: User) -> dict:
        """Get unresolved blockers preventing audit completion."""
        _, properties = await self._scoped_properties(current_user)
        tenant_ids = [tenant_id_from_document(prop) for prop in properties]
        system_db = get_system_db()
        blockers = (
            await system_db.audit_exceptions.find(
                {
                    "tenant_id": {"$in": [tenant_id for tenant_id in tenant_ids if tenant_id]},
                    "status": "open",
                    "exception_type": {"$in": ["pending_arrival", "pending_departure", "no_open_folio", "room_charge_failure", "tax_mismatch"]},
                },
                {"_id": 0},
            )
            .sort("created_at", -1)
            .to_list(200)
        )

        critical = [b for b in blockers if b.get("exception_type") in ["no_open_folio", "room_charge_failure"]]
        warning = [b for b in blockers if b.get("exception_type") not in ["no_open_folio", "room_charge_failure"]]

        return {
            "total": len(blockers),
            "critical": critical,
            "warning": warning,
            "critical_count": len(critical),
            "warning_count": len(warning),
        }

    async def escalate_exception(self, current_user: User, exception_id: str, escalation_note: str) -> dict:
        """Escalate an audit exception."""
        tenant_id, properties = await self._scoped_properties(current_user)
        tenant_ids = [tenant_id_from_document(prop) for prop in properties]
        system_db = get_system_db()
        exc = await system_db.audit_exceptions.find_one(
            {"id": exception_id, "tenant_id": {"$in": [value for value in tenant_ids if value]}}, {"_id": 0}
        )
        if not exc:
            return {"success": False, "error": "Exception not found"}

        now = datetime.now(UTC).isoformat()
        await system_db.audit_exceptions.update_one(
            {"id": exception_id, "tenant_id": exc.get("tenant_id")},
            {
                "$set": {
                    "escalated": True,
                    "escalated_by": current_user.id,
                    "escalated_at": now,
                    "escalation_note": escalation_note,
                }
            },
        )

        # Log escalation
        await system_db.pms_audit_trail.insert_one(
            {
                "tenant_id": exc.get("tenant_id", tenant_id),
                "entity_type": "audit_exception",
                "entity_id": exception_id,
                "action": "exception_escalated",
                "performed_by": current_user.id,
                "metadata": {"note": escalation_note},
                "timestamp": now,
            }
        )

        return {"success": True, "exception_id": exception_id}

    async def get_readiness_score(self, current_user: User) -> dict:
        """Calculate multi-property readiness score."""
        board = await self.get_audit_status_board(current_user)
        score = board["readiness_score"]

        # Factor in open exceptions
        total_exc = board["summary"]["total_exceptions"]
        penalty = min(total_exc * 2, 30)  # Max 30% penalty for exceptions
        adjusted_score = max(score - penalty, 0)

        return {
            "raw_score": score,
            "exception_penalty": penalty,
            "adjusted_score": round(adjusted_score, 1),
            "property_count": board["property_count"],
            "completed_count": board["summary"]["completed"],
            "total_exceptions": total_exc,
        }
