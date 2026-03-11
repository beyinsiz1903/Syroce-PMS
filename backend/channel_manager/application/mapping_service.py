"""
Mapping Service - Manages PMS ↔ External entity mappings with validation.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from ..domain.models.mapping import MappingRule, MappingStatus, MappingEntityType
from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository
from core.database import db

logger = logging.getLogger("channel_manager.application.mapping_service")


class MappingService:
    """Manages PMS entity ↔ external provider entity mappings."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def create_mapping(
        self,
        tenant_id: str,
        property_id: str,
        connector_id: str,
        entity_type: str,
        pms_entity_id: str,
        pms_entity_name: str,
        external_entity_id: str,
        external_entity_name: str,
        actor_id: Optional[str] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new mapping rule."""
        rule = MappingRule(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            entity_type=MappingEntityType(entity_type),
            pms_entity_id=pms_entity_id,
            pms_entity_name=pms_entity_name,
            external_entity_id=external_entity_id,
            external_entity_name=external_entity_name,
            created_by=actor_id,
            status=MappingStatus.ACTIVE,
        )
        if extras:
            if "occupancy_offset" in extras:
                rule.occupancy_offset = extras["occupancy_offset"]
            if "rate_modifier" in extras:
                rule.rate_modifier = extras["rate_modifier"]
            if "rate_offset" in extras:
                rule.rate_offset = extras["rate_offset"]

        await self._repo.upsert_mapping(rule.to_doc())
        await self._audit(tenant_id, property_id, connector_id, AuditAction.MAPPING_CREATED, actor_id, {
            "entity_type": entity_type, "pms_entity_id": pms_entity_id, "external_entity_id": external_entity_id,
        })
        return rule.to_doc()

    async def list_mappings(
        self, tenant_id: str, connector_id: str, entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await self._repo.get_mappings(tenant_id, connector_id, entity_type)

    async def get_mapping(self, tenant_id: str, mapping_id: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_mapping(tenant_id, mapping_id)

    async def delete_mapping(self, tenant_id: str, mapping_id: str, actor_id: Optional[str] = None) -> bool:
        mapping = await self._repo.get_mapping(tenant_id, mapping_id)
        if mapping:
            await self._audit(
                tenant_id, mapping.get("property_id", ""),
                mapping.get("connector_id", ""),
                AuditAction.MAPPING_DELETED, actor_id,
                {"mapping_id": mapping_id},
            )
        return await self._repo.delete_mapping(tenant_id, mapping_id)

    async def validate_mappings(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Validate all mappings for a connector - check PMS entities exist."""
        mappings = await self._repo.get_mappings(tenant_id, connector_id)
        valid = 0
        invalid = 0
        errors = []

        for m in mappings:
            errs = await self._validate_single_mapping(m)
            if errs:
                invalid += 1
                m["status"] = MappingStatus.INVALID.value
                m["validation_errors"] = errs
                errors.extend(errs)
            else:
                valid += 1
                m["status"] = MappingStatus.ACTIVE.value
                m["validation_errors"] = []
            m["last_validated_at"] = datetime.now(timezone.utc).isoformat()
            await self._repo.upsert_mapping(m)

        return {"valid": valid, "invalid": invalid, "errors": errors, "total": len(mappings)}

    async def get_mapping_lookup(
        self, tenant_id: str, connector_id: str, entity_type: str,
    ) -> Dict[str, str]:
        """Get PMS→External mapping lookup dict for a specific entity type."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, entity_type)
        return {m["pms_entity_id"]: m["external_entity_id"] for m in mappings}

    async def get_reverse_lookup(
        self, tenant_id: str, connector_id: str, entity_type: str,
    ) -> Dict[str, str]:
        """Get External→PMS mapping lookup dict."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, entity_type)
        return {m["external_entity_id"]: m["pms_entity_id"] for m in mappings}

    async def check_sync_readiness(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Check if all required mappings are in place for sync to work."""
        room_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "room_type")
        rate_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "rate_plan")

        # Get PMS room types and rate plans for this property
        connector = await self._repo.get_connector(tenant_id, connector_id)
        property_id = connector.get("property_id", "") if connector else ""

        pms_rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id}, {"_id": 0, "id": 1, "room_type": 1}
        ).to_list(500)

        # Distinct room types in PMS
        pms_room_types = list({r.get("room_type", "") for r in pms_rooms if r.get("room_type")})
        mapped_room_types = {m["pms_entity_id"] for m in room_mappings}
        unmapped_rooms = [rt for rt in pms_room_types if rt not in mapped_room_types]

        issues = []
        if not room_mappings:
            issues.append("No room type mappings configured")
        if unmapped_rooms:
            issues.append(f"Unmapped room types: {', '.join(unmapped_rooms)}")
        if not rate_mappings:
            issues.append("No rate plan mappings configured")

        return {
            "ready": len(issues) == 0,
            "room_type_mappings": len(room_mappings),
            "rate_plan_mappings": len(rate_mappings),
            "unmapped_room_types": unmapped_rooms,
            "issues": issues,
        }

    async def _validate_single_mapping(self, mapping: Dict) -> List[str]:
        """Validate a single mapping rule against PMS data."""
        errors = []
        entity_type = mapping.get("entity_type", "")
        pms_id = mapping.get("pms_entity_id", "")

        if entity_type == "room_type":
            # Check room type exists in PMS
            exists = await db.rooms.find_one(
                {"tenant_id": mapping["tenant_id"], "room_type": pms_id}, {"_id": 1}
            )
            if not exists:
                errors.append(f"PMS room type '{pms_id}' not found")

        return errors

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
