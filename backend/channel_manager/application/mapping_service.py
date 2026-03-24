"""
Mapping Service - Full business logic for PMS <-> External entity mappings.

Features:
  - CRUD with duplicate detection
  - 5 mapping types: room_type, rate_plan, occupancy, meal_plan, tax_mode
  - Per-mapping validation (PMS entity exists, external entity active, no duplicates)
  - Sync readiness score (0-100)
  - Blocked reasons generation
  - Missing vs invalid classification
  - Revalidation hook on create/update/delete
  - Frontend-ready structured responses
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..domain.models.mapping import (
    SUPPORTED_MAPPING_TYPES,
    MappingEntityType,
    MappingRule,
    MappingStatus,
    ValidationStatus,
)
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.mapping_service")


class MappingService:
    """Manages PMS entity <-> external provider entity mappings with full validation."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    # ------------------------------------------------------------------ #
    #  CRUD                                                                #
    # ------------------------------------------------------------------ #

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
        """Create a new mapping rule with duplicate check."""

        # Duplicate detection
        dupes = await self._repo.find_duplicate_mappings(
            tenant_id, connector_id, entity_type, pms_entity_id, external_entity_id,
        )
        if dupes:
            for d in dupes:
                if d.get("pms_entity_id") == pms_entity_id and d.get("status") in ("active", "draft"):
                    raise ValueError(
                        f"PMS entity '{pms_entity_id}' is already mapped "
                        f"(mapping {d['id']}, external: {d.get('external_entity_id')})"
                    )
                if d.get("external_entity_id") == external_entity_id and d.get("status") in ("active", "draft"):
                    raise ValueError(
                        f"External entity '{external_entity_id}' is already mapped "
                        f"(mapping {d['id']}, PMS: {d.get('pms_entity_id')})"
                    )

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
            validation_status=ValidationStatus.PENDING,
        )
        if extras:
            if "occupancy_offset" in extras:
                rule.occupancy_offset = extras["occupancy_offset"]
            if "rate_modifier" in extras:
                rule.rate_modifier = extras["rate_modifier"]
            if "rate_offset" in extras:
                rule.rate_offset = extras["rate_offset"]

        # Validate before save
        errs = await self._validate_single_mapping(rule.to_doc())
        if errs:
            rule.validation_status = ValidationStatus.INVALID
            rule.invalid_reason = errs[0]
            rule.validation_errors = errs
        else:
            rule.validation_status = ValidationStatus.VALID
            rule.invalid_reason = None
            rule.validation_errors = []
        rule.last_validated_at = datetime.now(timezone.utc).isoformat()

        await self._repo.upsert_mapping(rule.to_doc())

        await self._audit(tenant_id, property_id, connector_id, AuditAction.MAPPING_CREATED, actor_id, {
            "entity_type": entity_type,
            "pms_entity_id": pms_entity_id,
            "external_entity_id": external_entity_id,
            "validation_status": rule.validation_status.value,
        })

        # Trigger revalidation hook
        await self._on_mapping_changed(tenant_id, connector_id, entity_type)

        return rule.to_doc()

    async def list_mappings(
        self, tenant_id: str, connector_id: str, entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await self._repo.get_mappings(tenant_id, connector_id, entity_type)

    async def get_mapping(self, tenant_id: str, mapping_id: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_mapping(tenant_id, mapping_id)

    async def delete_mapping(self, tenant_id: str, mapping_id: str, actor_id: Optional[str] = None) -> bool:
        mapping = await self._repo.get_mapping(tenant_id, mapping_id)
        if not mapping:
            return False
        connector_id = mapping.get("connector_id", "")
        entity_type = mapping.get("entity_type", "")
        await self._audit(
            tenant_id, mapping.get("property_id", ""),
            connector_id,
            AuditAction.MAPPING_DELETED, actor_id,
            {"mapping_id": mapping_id, "entity_type": entity_type},
        )
        deleted = await self._repo.delete_mapping(tenant_id, mapping_id)
        if deleted:
            await self._on_mapping_changed(tenant_id, connector_id, entity_type)
        return deleted

    # ------------------------------------------------------------------ #
    #  Lookups                                                             #
    # ------------------------------------------------------------------ #

    async def get_mapping_lookup(
        self, tenant_id: str, connector_id: str, entity_type: str,
    ) -> Dict[str, str]:
        """Get PMS->External mapping lookup dict for a specific entity type."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, entity_type)
        return {m["pms_entity_id"]: m["external_entity_id"] for m in mappings}

    async def get_reverse_lookup(
        self, tenant_id: str, connector_id: str, entity_type: str,
    ) -> Dict[str, str]:
        """Get External->PMS mapping lookup dict."""
        mappings = await self._repo.get_active_mappings(tenant_id, connector_id, entity_type)
        return {m["external_entity_id"]: m["pms_entity_id"] for m in mappings}

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #

    async def validate_mappings(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Validate all mappings for a connector. Returns detailed report."""
        mappings = await self._repo.get_mappings(tenant_id, connector_id)
        now = datetime.now(timezone.utc).isoformat()

        valid = 0
        invalid = 0
        missing_list: List[Dict[str, Any]] = []
        invalid_list: List[Dict[str, Any]] = []

        for m in mappings:
            errs = await self._validate_single_mapping(m)
            if errs:
                invalid += 1
                m["status"] = MappingStatus.ACTIVE.value  # keep active, validation separate
                m["validation_status"] = ValidationStatus.INVALID.value
                m["invalid_reason"] = errs[0]
                m["validation_errors"] = errs
                invalid_list.append({
                    "mapping_id": m["id"],
                    "entity_type": m.get("entity_type"),
                    "pms_entity_id": m.get("pms_entity_id"),
                    "external_entity_id": m.get("external_entity_id"),
                    "errors": errs,
                })
            else:
                valid += 1
                m["validation_status"] = ValidationStatus.VALID.value
                m["invalid_reason"] = None
                m["validation_errors"] = []
            m["last_validated_at"] = now
            await self._repo.upsert_mapping(m)

        # Check for missing required mapping types
        connector = await self._repo.get_connector(tenant_id, connector_id)
        property_id = connector.get("property_id", "") if connector else ""
        missing_list = await self._detect_missing_mappings(tenant_id, connector_id, property_id)

        await self._audit(
            tenant_id, property_id, connector_id,
            AuditAction.MAPPING_REVALIDATED, metadata={
                "valid": valid, "invalid": invalid,
                "missing_count": len(missing_list), "total": len(mappings),
            },
        )

        return {
            "valid": valid,
            "invalid": invalid,
            "missing_count": len(missing_list),
            "total": len(mappings),
            "invalid_mappings": invalid_list,
            "missing_mappings": missing_list,
            "validated_at": now,
        }

    async def validate_single(self, tenant_id: str, mapping_id: str) -> Dict[str, Any]:
        """Validate a single mapping and persist status."""
        m = await self._repo.get_mapping(tenant_id, mapping_id)
        if not m:
            raise ValueError("Mapping not found")

        errs = await self._validate_single_mapping(m)
        now = datetime.now(timezone.utc).isoformat()
        if errs:
            m["validation_status"] = ValidationStatus.INVALID.value
            m["invalid_reason"] = errs[0]
            m["validation_errors"] = errs
        else:
            m["validation_status"] = ValidationStatus.VALID.value
            m["invalid_reason"] = None
            m["validation_errors"] = []
        m["last_validated_at"] = now
        await self._repo.upsert_mapping(m)
        return {
            "mapping_id": mapping_id,
            "validation_status": m["validation_status"],
            "invalid_reason": m.get("invalid_reason"),
            "errors": m.get("validation_errors", []),
            "validated_at": now,
        }

    # ------------------------------------------------------------------ #
    #  Sync Readiness & Blocked Reasons                                    #
    # ------------------------------------------------------------------ #

    async def check_sync_readiness(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Compute sync readiness score (0-100) and blocked reasons."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"ready": False, "score": 0, "blocked_reasons": ["Connector not found"]}
        property_id = connector.get("property_id", "")

        all_mappings = await self._repo.get_mappings(tenant_id, connector_id)

        # Classify by type & status
        type_counts: Dict[str, Dict[str, int]] = {}
        invalid_by_type: Dict[str, int] = {}
        for m in all_mappings:
            et = m.get("entity_type", "unknown")
            st = m.get("status", "draft")
            vs = m.get("validation_status", "pending")
            if et not in type_counts:
                type_counts[et] = {"total": 0, "active": 0, "invalid_validation": 0}
            type_counts[et]["total"] += 1
            if st == "active":
                type_counts[et]["active"] += 1
            if vs == "invalid":
                type_counts[et]["invalid_validation"] += 1
                invalid_by_type[et] = invalid_by_type.get(et, 0) + 1

        # PMS entities
        pms_room_types = await self._get_pms_room_types(tenant_id, property_id)
        pms_rate_plans = await self._get_pms_rate_plans(tenant_id, property_id)

        # External entities (for summary)
        ext_room_count = len(await self._repo.get_external_room_types(tenant_id, connector_id))
        ext_rate_count = len(await self._repo.get_external_rate_plans(tenant_id, connector_id))

        # Active mappings per required type
        room_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "room_type")
        rate_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "rate_plan")

        mapped_pms_rooms = {m["pms_entity_id"] for m in room_mappings}
        mapped_pms_rates = {m["pms_entity_id"] for m in rate_mappings}

        unmapped_rooms = [r for r in pms_room_types if r not in mapped_pms_rooms]
        unmapped_rates = [r for r in pms_rate_plans if r not in mapped_pms_rates]

        # Missing mappings
        missing = await self._detect_missing_mappings(tenant_id, connector_id, property_id)

        # Blocked reasons
        blocked_reasons: List[str] = []
        if not room_mappings:
            blocked_reasons.append("Oda tipi mapping'i yapilmamis")
        if not rate_mappings:
            blocked_reasons.append("Rate plan mapping'i yapilmamis")
        if unmapped_rooms:
            blocked_reasons.append(f"Eslestirilmemis oda tipi: {', '.join(unmapped_rooms)}")
        if unmapped_rates:
            blocked_reasons.append(f"Eslestirilmemis rate plan: {', '.join(unmapped_rates)}")
        for et, cnt in invalid_by_type.items():
            blocked_reasons.append(f"{et} icin {cnt} adet gecersiz mapping")

        # Score calculation (0-100)
        score = self._calculate_readiness_score(
            room_mappings=len(room_mappings),
            rate_mappings=len(rate_mappings),
            total_pms_rooms=len(pms_room_types),
            total_pms_rates=len(pms_rate_plans),
            invalid_count=sum(invalid_by_type.values()),
            total_mappings=len(all_mappings),
        )

        ready = score >= 80 and len(blocked_reasons) == 0

        await self._audit(
            tenant_id, property_id, connector_id,
            AuditAction.MAPPING_READINESS_CHECKED, metadata={
                "score": score, "ready": ready,
                "blocked_reasons_count": len(blocked_reasons),
            },
        )

        return {
            "ready": ready,
            "score": score,
            "blocked_reasons": blocked_reasons,
            "summary": {
                "room_type": {
                    "mapped": len(room_mappings),
                    "total_pms": len(pms_room_types),
                    "total_external": ext_room_count,
                    "unmapped": unmapped_rooms,
                    "invalid": invalid_by_type.get("room_type", 0),
                },
                "rate_plan": {
                    "mapped": len(rate_mappings),
                    "total_pms": len(pms_rate_plans),
                    "total_external": ext_rate_count,
                    "unmapped": unmapped_rates,
                    "invalid": invalid_by_type.get("rate_plan", 0),
                },
            },
            "type_counts": type_counts,
            "missing_mappings": missing,
            "invalid_mappings_count": sum(invalid_by_type.values()),
            "total_mappings": len(all_mappings),
        }

    # ------------------------------------------------------------------ #
    #  Frontend Readiness Report (structured for Mapping Screen)           #
    # ------------------------------------------------------------------ #

    async def get_readiness_report(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Comprehensive report for the Mapping screen on frontend."""
        readiness = await self.check_sync_readiness(tenant_id, connector_id)
        all_mappings = await self._repo.get_mappings(tenant_id, connector_id)

        # Group mappings by entity_type
        by_type: Dict[str, List[Dict]] = {}
        for m in all_mappings:
            et = m.get("entity_type", "unknown")
            by_type.setdefault(et, []).append(m)

        # External entities for selection
        ext_rooms = await self._repo.get_external_room_types(tenant_id, connector_id)
        ext_rates = await self._repo.get_external_rate_plans(tenant_id, connector_id)

        # PMS entities
        connector = await self._repo.get_connector(tenant_id, connector_id)
        property_id = connector.get("property_id", "") if connector else ""
        pms_rooms_raw = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id},
            {"_id": 0, "id": 1, "room_type": 1, "room_number": 1, "status": 1},
        ).to_list(500)
        pms_room_types_set = {}
        for r in pms_rooms_raw:
            rt = r.get("room_type", "")
            if rt and rt not in pms_room_types_set:
                pms_room_types_set[rt] = {"id": rt, "name": rt, "active": r.get("status") != "out_of_service"}

        return {
            "readiness": readiness,
            "mappings_by_type": by_type,
            "pms_entities": {
                "room_types": list(pms_room_types_set.values()),
                "rate_plans": await self._get_pms_rate_plan_details(tenant_id, property_id),
            },
            "external_entities": {
                "room_types": ext_rooms,
                "rate_plans": ext_rates,
            },
            "supported_mapping_types": [t.value for t in SUPPORTED_MAPPING_TYPES],
        }

    # ------------------------------------------------------------------ #
    #  Internal: Validation per entity type                                #
    # ------------------------------------------------------------------ #

    async def _validate_single_mapping(self, mapping: Dict) -> List[str]:
        """Validate a single mapping rule against PMS and external data."""
        errors = []
        entity_type = mapping.get("entity_type", "")
        pms_id = mapping.get("pms_entity_id", "")
        external_id = mapping.get("external_entity_id", "")
        tenant_id = mapping.get("tenant_id", "")
        connector_id = mapping.get("connector_id", "")

        if not pms_id:
            errors.append("PMS entity ID bos")
        if not external_id:
            errors.append("External entity ID bos")
        if errors:
            return errors

        if entity_type == "room_type":
            exists = await db.rooms.find_one(
                {"tenant_id": tenant_id, "room_type": pms_id}, {"_id": 1, "status": 1},
            )
            if not exists:
                errors.append(f"PMS oda tipi '{pms_id}' bulunamadi")
            elif exists.get("status") == "out_of_service":
                errors.append(f"PMS oda tipi '{pms_id}' aktif degil (out_of_service)")

            ext = await db.cm_external_room_types.find_one(
                {"tenant_id": tenant_id, "connector_id": connector_id, "external_id": external_id},
                {"_id": 1, "is_active": 1},
            )
            if not ext:
                errors.append(f"External oda tipi '{external_id}' bulunamadi (provider'da silinmis olabilir)")
            elif not ext.get("is_active", True):
                errors.append(f"External oda tipi '{external_id}' aktif degil")

        elif entity_type == "rate_plan":
            rp = await db.cm_external_rate_plans.find_one(
                {"tenant_id": tenant_id, "connector_id": connector_id, "external_id": external_id},
                {"_id": 1, "is_active": 1, "external_room_type_id": 1},
            )
            if not rp:
                errors.append(f"External rate plan '{external_id}' bulunamadi (provider'da silinmis olabilir)")
            elif not rp.get("is_active", True):
                errors.append(f"External rate plan '{external_id}' aktif degil")

            # Verify PMS rate plan reference
            pms_rp = await db.rooms.find_one(
                {"tenant_id": tenant_id, "room_type": pms_id}, {"_id": 1},
            )
            if not pms_rp:
                # Maybe pms_id is a rate plan id from a rate plans collection
                # For now, just log it - PMS rate plan validation depends on data model
                pass

        elif entity_type == "occupancy":
            offset = mapping.get("occupancy_offset", 0)
            if not isinstance(offset, int):
                errors.append("occupancy_offset tamsayi olmali")

        elif entity_type == "meal_plan":
            valid_plans = {"RO", "BB", "HB", "FB", "AI", "SC"}
            if external_id not in valid_plans and pms_id not in valid_plans:
                pass  # flexible, no strict validation on meal plan codes

        elif entity_type == "tax_mode":
            valid_modes = {"inclusive", "exclusive", "exempt", "net", "gross"}
            if external_id.lower() not in valid_modes and pms_id.lower() not in valid_modes:
                errors.append(f"Gecersiz tax mode: '{pms_id}' -> '{external_id}'")

        # Duplicate check (same entity_type + same pms or ext id)
        dupes = await self._repo.find_duplicate_mappings(
            tenant_id, connector_id, entity_type,
            pms_id, external_id,
            exclude_mapping_id=mapping.get("id"),
        )
        for d in dupes:
            if d.get("pms_entity_id") == pms_id and d.get("status") in ("active", "draft"):
                errors.append(
                    f"PMS entity '{pms_id}' baska bir mapping'de zaten kullaniliyor "
                    f"(mapping: {d['id']})"
                )
            if d.get("external_entity_id") == external_id and d.get("status") in ("active", "draft"):
                errors.append(
                    f"External entity '{external_id}' baska bir mapping'de zaten kullaniliyor "
                    f"(mapping: {d['id']})"
                )

        return errors

    # ------------------------------------------------------------------ #
    #  Internal: Missing mapping detection                                 #
    # ------------------------------------------------------------------ #

    async def _detect_missing_mappings(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[Dict[str, Any]]:
        """Detect PMS entities that have no active mapping."""
        missing: List[Dict[str, Any]] = []

        # Room types
        pms_room_types = await self._get_pms_room_types(tenant_id, property_id)
        room_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "room_type")
        mapped_rooms = {m["pms_entity_id"] for m in room_mappings}
        for rt in pms_room_types:
            if rt not in mapped_rooms:
                missing.append({
                    "entity_type": "room_type",
                    "pms_entity_id": rt,
                    "pms_entity_name": rt,
                    "reason": f"Oda tipi '{rt}' icin mapping yapilmamis",
                })

        # Rate plans (based on external rate plans that have no mapping)
        ext_rates = await self._repo.get_external_rate_plans(tenant_id, connector_id)
        rate_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "rate_plan")
        mapped_ext_rates = {m["external_entity_id"] for m in rate_mappings}
        for er in ext_rates:
            if er.get("external_id") not in mapped_ext_rates and er.get("is_active", True):
                missing.append({
                    "entity_type": "rate_plan",
                    "external_entity_id": er.get("external_id"),
                    "external_entity_name": er.get("name", ""),
                    "reason": f"External rate plan '{er.get('name', er.get('external_id'))}' icin mapping yapilmamis",
                })

        return missing

    # ------------------------------------------------------------------ #
    #  Internal: Readiness Score                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _calculate_readiness_score(
        room_mappings: int,
        rate_mappings: int,
        total_pms_rooms: int,
        total_pms_rates: int,
        invalid_count: int,
        total_mappings: int,
    ) -> int:
        """
        Weighted score:
          - Room coverage:  40%
          - Rate coverage:  30%
          - Validity ratio: 30%
        """
        # Room coverage (40 pts)
        if total_pms_rooms > 0:
            room_score = min(room_mappings / total_pms_rooms, 1.0) * 40
        else:
            room_score = 40.0 if room_mappings > 0 else 0.0

        # Rate coverage (30 pts)
        if total_pms_rates > 0:
            rate_score = min(rate_mappings / total_pms_rates, 1.0) * 30
        else:
            rate_score = 30.0 if rate_mappings > 0 else 0.0

        # Validity ratio (30 pts)
        if total_mappings > 0:
            valid_count = total_mappings - invalid_count
            validity_score = (valid_count / total_mappings) * 30
        else:
            validity_score = 0.0

        return int(room_score + rate_score + validity_score)

    # ------------------------------------------------------------------ #
    #  Internal: PMS data helpers                                          #
    # ------------------------------------------------------------------ #

    async def _get_pms_room_types(self, tenant_id: str, property_id: str) -> List[str]:
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id, "status": {"$ne": "out_of_service"}},
            {"_id": 0, "room_type": 1},
        ).to_list(500)
        return list({r.get("room_type", "") for r in rooms if r.get("room_type")})

    async def _get_pms_rate_plans(self, tenant_id: str, property_id: str) -> List[str]:
        # Rate plans may come from rooms or a separate collection
        # For now, derive from room types as implicit rate plans
        room_types = await self._get_pms_room_types(tenant_id, property_id)
        return room_types  # PMS may use room_type as rate plan key

    async def _get_pms_rate_plan_details(self, tenant_id: str, property_id: str) -> List[Dict]:
        room_types = await self._get_pms_room_types(tenant_id, property_id)
        return [{"id": rt, "name": rt} for rt in room_types]

    # ------------------------------------------------------------------ #
    #  Revalidation Hook                                                   #
    # ------------------------------------------------------------------ #

    async def _on_mapping_changed(
        self, tenant_id: str, connector_id: str, entity_type: str,
    ) -> None:
        """
        Hook: when a mapping is created/deleted, revalidate related data.
        - Mark stale review-queue reservations for re-evaluation
        - Invalidate sync snapshots if room/rate mapping changed
        """
        if entity_type in ("room_type", "rate_plan"):
            # Find review-queue reservations that might now have valid mappings
            review_reservations = await db.cm_imported_reservations.find(
                {
                    "tenant_id": tenant_id,
                    "connector_id": connector_id,
                    "import_status": {"$in": ["review"]},
                    "review_reason_code": {
                        "$in": ["missing_room_mapping", "missing_rate_mapping"],
                    },
                },
                {"_id": 0, "id": 1, "room_type_external_id": 1, "rate_plan_external_id": 1},
            ).to_list(200)

            if not review_reservations:
                return

            # Get fresh reverse lookups
            room_reverse = await self.get_reverse_lookup(tenant_id, connector_id, "room_type")
            rate_reverse = await self.get_reverse_lookup(tenant_id, connector_id, "rate_plan")

            revalidated_ids = []
            for res in review_reservations:
                ext_room = res.get("room_type_external_id", "")
                ext_rate = res.get("rate_plan_external_id", "")
                now_mapped = True
                if ext_room and ext_room not in room_reverse:
                    now_mapped = False
                if ext_rate and ext_rate not in rate_reverse:
                    now_mapped = False
                if now_mapped:
                    revalidated_ids.append(res["id"])

            if revalidated_ids:
                now_ts = datetime.now(timezone.utc).isoformat()
                for rid in revalidated_ids:
                    await db.cm_imported_reservations.update_one(
                        {"tenant_id": tenant_id, "id": rid},
                        {"$set": {
                            "import_status": "pending",
                            "review_reason": None,
                            "review_reason_code": None,
                            "suggested_action": None,
                            "revalidated_at": now_ts,
                            "revalidation_trigger": "mapping_changed",
                        }},
                    )
                logger.info(
                    "Revalidated %d review-queue reservations after %s mapping change",
                    len(revalidated_ids), entity_type,
                )

    # ------------------------------------------------------------------ #
    #  Audit                                                               #
    # ------------------------------------------------------------------ #

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
