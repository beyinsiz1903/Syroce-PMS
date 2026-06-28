"""
Mapping Completeness Validation Service.

Ensures all required PMS<->Provider mappings exist before allowing sync/import operations.

Checks:
  - room_type mapping completeness
  - rate_plan mapping completeness
  - occupancy normalization mapping
  - tax_mode mapping
  - meal_plan mapping

Missing mapping => sync blocked, reservation import manual review, admin alert.
Produces a mapping readiness score visible on admin panel.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.mapping_completeness")

MAPPING_WEIGHTS = {
    "room_type": 40,
    "rate_plan": 30,
    "occupancy": 10,
    "tax_mode": 10,
    "meal_plan": 10,
}

REQUIRED_FOR_SYNC = {"room_type", "rate_plan"}
REQUIRED_FOR_IMPORT = {"room_type"}


class MappingCompletenessService:
    """Validates mapping completeness and controls sync/import gating."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def validate_completeness(
        self,
        tenant_id: str,
        connector_id: str,
    ) -> dict[str, Any]:
        """Full mapping completeness check with per-type breakdown and readiness score."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector not found", "score": 0, "sync_allowed": False, "import_allowed": False}

        property_id = connector.get("property_id", "")
        results = {}
        total_score = 0
        blocked_reasons: list[str] = []

        # Room type completeness
        room_result = await self._check_room_type_completeness(tenant_id, connector_id, property_id)
        results["room_type"] = room_result
        total_score += room_result["score_contribution"]
        if not room_result["complete"]:
            blocked_reasons.extend(room_result.get("missing_details", []))

        # Rate plan completeness
        rate_result = await self._check_rate_plan_completeness(tenant_id, connector_id, property_id)
        results["rate_plan"] = rate_result
        total_score += rate_result["score_contribution"]
        if not rate_result["complete"]:
            blocked_reasons.extend(rate_result.get("missing_details", []))

        # Occupancy normalization
        occ_result = await self._check_occupancy_mapping(tenant_id, connector_id)
        results["occupancy"] = occ_result
        total_score += occ_result["score_contribution"]

        # Tax mode
        tax_result = await self._check_tax_mode_mapping(tenant_id, connector_id)
        results["tax_mode"] = tax_result
        total_score += tax_result["score_contribution"]

        # Meal plan
        meal_result = await self._check_meal_plan_mapping(tenant_id, connector_id)
        results["meal_plan"] = meal_result
        total_score += meal_result["score_contribution"]

        # Determine gates
        sync_allowed = room_result["complete"] and rate_result["complete"]
        import_allowed = room_result["complete"]

        readiness_score = min(round(total_score), 100)

        report = {
            "connector_id": connector_id,
            "property_id": property_id,
            "readiness_score": readiness_score,
            "sync_allowed": sync_allowed,
            "import_allowed": import_allowed,
            "blocked_reasons": blocked_reasons,
            "checks": results,
            "checked_at": datetime.now(UTC).isoformat(),
        }

        # Fire alert if not sync-ready
        if not sync_allowed:
            try:
                from .alerting_service import AlertingService

                alert_svc = AlertingService(repo=self._repo)
                await alert_svc.check_and_fire_alert(
                    tenant_id=tenant_id,
                    trigger="invalid_mapping_detected",
                    connector_id=connector_id,
                    metadata={"blocked_reasons": blocked_reasons, "score": readiness_score},
                )
            except Exception as e:
                logger.warning("Failed to fire mapping alert: %s", e)

        # Audit
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=AuditAction.MAPPING_READINESS_CHECKED,
            metadata={"score": readiness_score, "sync_allowed": sync_allowed, "import_allowed": import_allowed},
        )
        await self._repo.create_audit_log(log.to_doc())

        return report

    async def check_sync_gate(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Quick check if sync is allowed based on mapping completeness."""
        report = await self.validate_completeness(tenant_id, connector_id)
        return {
            "allowed": report.get("sync_allowed", False),
            "score": report.get("readiness_score", 0),
            "blocked_reasons": report.get("blocked_reasons", []),
        }

    async def check_import_gate(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Quick check if reservation import should proceed or go to manual review."""
        report = await self.validate_completeness(tenant_id, connector_id)
        return {
            "allowed": report.get("import_allowed", False),
            "score": report.get("readiness_score", 0),
            "blocked_reasons": report.get("blocked_reasons", []),
        }

    # ─── Per-type Checks ──────────────────────────────────────────────

    async def _check_room_type_completeness(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str,
    ) -> dict[str, Any]:
        """Check that all PMS room types have active mappings to provider."""
        pms_rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id, "status": {"$ne": "out_of_service"}},
            {"_id": 0, "room_type": 1},
        ).to_list(500)
        pms_room_types = list({r.get("room_type", "") for r in pms_rooms if r.get("room_type")})

        active_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "room_type")
        mapped_pms = {m["pms_entity_id"] for m in active_mappings}
        unmapped = [rt for rt in pms_room_types if rt not in mapped_pms]

        total = len(pms_room_types)
        mapped_count = total - len(unmapped)
        coverage = round(mapped_count / max(total, 1) * 100, 1)
        weight = MAPPING_WEIGHTS["room_type"]
        score = round(coverage / 100 * weight, 1)

        missing_details = [f"Unmapped room type: {rt}" for rt in unmapped]

        return {
            "entity_type": "room_type",
            "total_pms_entities": total,
            "mapped_count": mapped_count,
            "unmapped_count": len(unmapped),
            "unmapped_entities": unmapped,
            "coverage_percentage": coverage,
            "complete": len(unmapped) == 0 and total > 0,
            "score_contribution": score,
            "missing_details": missing_details,
        }

    async def _check_rate_plan_completeness(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str,
    ) -> dict[str, Any]:
        """Check that all external rate plans have PMS mappings."""
        ext_rates = await self._repo.get_external_rate_plans(tenant_id, connector_id)
        active_ext = [r for r in ext_rates if r.get("is_active", True)]

        active_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "rate_plan")
        mapped_ext = {m["external_entity_id"] for m in active_mappings}
        unmapped = [r for r in active_ext if r.get("external_id") not in mapped_ext]

        total = len(active_ext)
        mapped_count = total - len(unmapped)
        coverage = round(mapped_count / max(total, 1) * 100, 1)
        weight = MAPPING_WEIGHTS["rate_plan"]
        score = round(coverage / 100 * weight, 1)

        missing_details = [f"Unmapped rate plan: {r.get('name', r.get('external_id'))}" for r in unmapped]

        return {
            "entity_type": "rate_plan",
            "total_external_entities": total,
            "mapped_count": mapped_count,
            "unmapped_count": len(unmapped),
            "unmapped_entities": [r.get("external_id") for r in unmapped],
            "coverage_percentage": coverage,
            "complete": len(unmapped) == 0,
            "score_contribution": score,
            "missing_details": missing_details,
        }

    async def _check_occupancy_mapping(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Check occupancy normalization mappings exist."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "occupancy")
        has_mappings = len(mappings) > 0
        weight = MAPPING_WEIGHTS["occupancy"]
        score = weight if has_mappings else 0.0

        return {
            "entity_type": "occupancy",
            "mapped_count": len(mappings),
            "complete": has_mappings,
            "score_contribution": score,
            "missing_details": [] if has_mappings else ["No occupancy normalization mapping configured"],
        }

    async def _check_tax_mode_mapping(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Check tax mode mappings exist."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "tax_mode")
        has_mappings = len(mappings) > 0
        weight = MAPPING_WEIGHTS["tax_mode"]
        score = weight if has_mappings else 0.0

        return {
            "entity_type": "tax_mode",
            "mapped_count": len(mappings),
            "complete": has_mappings,
            "score_contribution": score,
            "missing_details": [] if has_mappings else ["No tax mode mapping configured"],
        }

    async def _check_meal_plan_mapping(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Check meal plan mappings exist."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "meal_plan")
        has_mappings = len(mappings) > 0
        weight = MAPPING_WEIGHTS["meal_plan"]
        score = weight if has_mappings else 0.0

        return {
            "entity_type": "meal_plan",
            "mapped_count": len(mappings),
            "complete": has_mappings,
            "score_contribution": score,
            "missing_details": [] if has_mappings else ["No meal plan mapping configured"],
        }
