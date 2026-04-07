"""
Auto Room Mapping Wizard Service.

Provides intelligent auto-suggestion for PMS <-> External entity mappings
using fuzzy string matching. Supports bulk creation of confirmed mappings.

Flow:
  1. Fetch PMS room types + external room types for a connector
  2. Run fuzzy matching (difflib.SequenceMatcher) to suggest pairs
  3. Return suggestions with confidence scores
  4. Accept confirmed pairs and bulk-create mappings
"""
import logging
from difflib import SequenceMatcher
from typing import Any

from core.database import db

from ..infrastructure.repository import ChannelManagerRepository
from .mapping_service import MappingService

logger = logging.getLogger("channel_manager.application.auto_mapping")


def _normalize(name: str) -> str:
    """Normalize a name for fuzzy comparison."""
    return name.lower().strip().replace("-", " ").replace("_", " ")


def _similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two strings."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


# Common Turkish/English room type aliases for better matching
_ALIASES = {
    "standart": ["standard", "std"],
    "standard": ["standart", "std"],
    "deluxe": ["delux", "dlx", "lux"],
    "suite": ["suit", "süit"],
    "family": ["aile", "familya"],
    "aile": ["family", "familya"],
    "single": ["tek", "tekli", "sgl"],
    "double": ["çift", "cift", "dbl", "ikili"],
    "twin": ["ikiz", "twn"],
    "triple": ["üçlü", "uclu", "tpl"],
    "king": ["kral"],
    "queen": ["kraliçe", "kralice"],
    "economy": ["ekonomi", "eco"],
    "superior": ["süperior"],
    "junior": ["jünior", "junior"],
    "penthouse": ["çatı katı", "cati kati"],
    "connecting": ["bağlantılı", "baglantili"],
    "sea view": ["deniz manzaralı", "deniz manzarali"],
    "garden": ["bahçe", "bahce"],
    "pool": ["havuz"],
    "bungalow": ["bungalov"],
}


def _alias_boost(a: str, b: str) -> float:
    """Check if names are known aliases and return a boost score."""
    na = _normalize(a)
    nb = _normalize(b)
    for key, aliases in _ALIASES.items():
        if key in na:
            for alias in aliases:
                if alias in nb:
                    return 0.25
        if key in nb:
            for alias in aliases:
                if alias in na:
                    return 0.25
    return 0.0


def _compute_match_score(pms_name: str, ext_name: str) -> float:
    """Compute overall match score with alias boosting."""
    base = _similarity(pms_name, ext_name)
    boost = _alias_boost(pms_name, ext_name)
    return min(base + boost, 1.0)


class AutoMappingService:
    """Intelligent auto-suggestion and bulk creation for entity mappings."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()
        self._mapping_svc = MappingService(repo=self._repo)

    async def suggest_room_mappings(
        self, tenant_id: str, connector_id: str,
    ) -> dict[str, Any]:
        """Suggest room type mappings based on fuzzy name matching."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector bulunamadi", "suggestions": []}

        property_id = connector.get("property_id", "")

        # Fetch PMS room types (distinct) — try with property_id first, fallback to tenant only
        room_query = {"tenant_id": tenant_id, "status": {"$ne": "out_of_service"}}
        if property_id:
            pms_rooms_raw = await db.rooms.find(
                {**room_query, "property_id": property_id},
                {"_id": 0, "room_type": 1, "room_number": 1},
            ).to_list(500)
            if not pms_rooms_raw:
                pms_rooms_raw = await db.rooms.find(
                    room_query, {"_id": 0, "room_type": 1, "room_number": 1},
                ).to_list(500)
        else:
            pms_rooms_raw = await db.rooms.find(
                room_query, {"_id": 0, "room_type": 1, "room_number": 1},
            ).to_list(500)
        pms_types: dict[str, dict] = {}
        room_counts: dict[str, int] = {}
        for r in pms_rooms_raw:
            rt = r.get("room_type", "")
            if rt:
                if rt not in pms_types:
                    pms_types[rt] = {"id": rt, "name": rt}
                room_counts[rt] = room_counts.get(rt, 0) + 1

        # Fetch external room types
        ext_rooms = await self._repo.get_external_room_types(tenant_id, connector_id)
        active_ext = [r for r in ext_rooms if r.get("is_active", True)]

        # Fetch existing active mappings to exclude already-mapped
        existing_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "room_type")
        mapped_pms = {m["pms_entity_id"] for m in existing_mappings}
        mapped_ext = {m["external_entity_id"] for m in existing_mappings}

        # Build suggestions using optimal matching (avoid duplicate assignments)
        suggestions = []
        available_ext = [e for e in active_ext if e.get("external_id") not in mapped_ext]
        available_pms = [p for p in pms_types.values() if p["id"] not in mapped_pms]

        # Build full score matrix: (pms_idx, ext_idx) -> score
        score_matrix: list[tuple[float, int, int]] = []
        for pi, pms in enumerate(available_pms):
            for ei, ext in enumerate(available_ext):
                ext_name = ext.get("name", ext.get("external_id", ""))
                score = _compute_match_score(pms["name"], ext_name)
                if score > 0.0:
                    score_matrix.append((score, pi, ei))

        # Greedy assign: best scores first, no duplicates
        score_matrix.sort(key=lambda x: -x[0])
        assigned_pms: set[int] = set()
        assigned_ext: set[int] = set()
        pms_to_ext: dict[int, tuple[int, float]] = {}

        for score, pi, ei in score_matrix:
            if pi not in assigned_pms and ei not in assigned_ext:
                pms_to_ext[pi] = (ei, score)
                assigned_pms.add(pi)
                assigned_ext.add(ei)

        for pi, pms in enumerate(available_pms):
            if pi in pms_to_ext:
                ei, best_score = pms_to_ext[pi]
                ext = available_ext[ei]
                suggestions.append({
                    "pms_entity_id": pms["id"],
                    "pms_entity_name": pms["name"],
                    "pms_room_count": room_counts.get(pms["id"], 0),
                    "external_entity_id": ext.get("external_id", ""),
                    "external_entity_name": ext.get("name", ext.get("external_id", "")),
                    "confidence": round(best_score * 100),
                    "status": "auto" if best_score >= 0.6 else "review",
                })
            else:
                suggestions.append({
                    "pms_entity_id": pms["id"],
                    "pms_entity_name": pms["name"],
                    "pms_room_count": room_counts.get(pms["id"], 0),
                    "external_entity_id": "",
                    "external_entity_name": "",
                    "confidence": 0,
                    "status": "unmatched",
                })

        # Sort: auto first, then review, then unmatched
        order = {"auto": 0, "review": 1, "unmatched": 2}
        suggestions.sort(key=lambda s: (order.get(s["status"], 3), -s["confidence"]))

        return {
            "connector_id": connector_id,
            "connector_name": connector.get("display_name", ""),
            "provider": connector.get("provider", ""),
            "property_id": property_id,
            "suggestions": suggestions,
            "already_mapped": [
                {
                    "pms_entity_id": m["pms_entity_id"],
                    "pms_entity_name": m.get("pms_entity_name", ""),
                    "external_entity_id": m["external_entity_id"],
                    "external_entity_name": m.get("external_entity_name", ""),
                }
                for m in existing_mappings
            ],
            "pms_room_types": list(pms_types.values()),
            "external_room_types": [
                {
                    "id": e.get("external_id", ""),
                    "name": e.get("name", e.get("external_id", "")),
                    "is_active": e.get("is_active", True),
                }
                for e in active_ext
            ],
            "summary": {
                "total_pms": len(pms_types),
                "total_external": len(active_ext),
                "already_mapped": len(existing_mappings),
                "auto_matched": sum(1 for s in suggestions if s["status"] == "auto"),
                "needs_review": sum(1 for s in suggestions if s["status"] == "review"),
                "unmatched": sum(1 for s in suggestions if s["status"] == "unmatched"),
            },
        }

    async def suggest_rate_plan_mappings(
        self, tenant_id: str, connector_id: str,
    ) -> dict[str, Any]:
        """Suggest rate plan mappings based on fuzzy name matching."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector bulunamadi", "suggestions": []}

        property_id = connector.get("property_id", "")

        # PMS rate plans (derived from room types for now)
        room_query = {"tenant_id": tenant_id, "status": {"$ne": "out_of_service"}}
        if property_id:
            pms_rooms = await db.rooms.find(
                {**room_query, "property_id": property_id},
                {"_id": 0, "room_type": 1},
            ).to_list(500)
            if not pms_rooms:
                pms_rooms = await db.rooms.find(
                    room_query, {"_id": 0, "room_type": 1},
                ).to_list(500)
        else:
            pms_rooms = await db.rooms.find(
                room_query, {"_id": 0, "room_type": 1},
            ).to_list(500)
        pms_rate_plans = list({r.get("room_type", "") for r in pms_rooms if r.get("room_type")})

        # External rate plans
        ext_rates = await self._repo.get_external_rate_plans(tenant_id, connector_id)
        active_ext = [r for r in ext_rates if r.get("is_active", True)]

        # Existing mappings
        existing = await self._repo.get_active_mappings(tenant_id, connector_id, "rate_plan")
        mapped_pms = {m["pms_entity_id"] for m in existing}
        mapped_ext = {m["external_entity_id"] for m in existing}

        suggestions = []
        available_ext = [e for e in active_ext if e.get("external_id") not in mapped_ext]
        unmapped_pms = [rp for rp in pms_rate_plans if rp not in mapped_pms]

        # Build score matrix and do greedy non-duplicate assignment
        score_matrix: list[tuple[float, int, int]] = []
        for pi, pms_rp in enumerate(unmapped_pms):
            for ei, ext in enumerate(available_ext):
                ext_name = ext.get("name", ext.get("external_id", ""))
                score = _compute_match_score(pms_rp, ext_name)
                if score > 0.0:
                    score_matrix.append((score, pi, ei))

        score_matrix.sort(key=lambda x: -x[0])
        assigned_pms: set[int] = set()
        assigned_ext: set[int] = set()
        pms_to_ext: dict[int, tuple[int, float]] = {}

        for score, pi, ei in score_matrix:
            if pi not in assigned_pms and ei not in assigned_ext:
                pms_to_ext[pi] = (ei, score)
                assigned_pms.add(pi)
                assigned_ext.add(ei)

        for pi, pms_rp in enumerate(unmapped_pms):
            if pi in pms_to_ext:
                ei, best_score = pms_to_ext[pi]
                ext = available_ext[ei]
                suggestions.append({
                    "pms_entity_id": pms_rp,
                    "pms_entity_name": pms_rp,
                    "external_entity_id": ext.get("external_id", ""),
                    "external_entity_name": ext.get("name", ext.get("external_id", "")),
                    "confidence": round(best_score * 100),
                    "status": "auto" if best_score >= 0.6 else "review",
                })
            else:
                suggestions.append({
                    "pms_entity_id": pms_rp,
                    "pms_entity_name": pms_rp,
                    "external_entity_id": "",
                    "external_entity_name": "",
                    "confidence": 0,
                    "status": "unmatched",
                })

        order = {"auto": 0, "review": 1, "unmatched": 2}
        suggestions.sort(key=lambda s: (order.get(s["status"], 3), -s["confidence"]))

        return {
            "connector_id": connector_id,
            "suggestions": suggestions,
            "already_mapped": [
                {
                    "pms_entity_id": m["pms_entity_id"],
                    "pms_entity_name": m.get("pms_entity_name", ""),
                    "external_entity_id": m["external_entity_id"],
                    "external_entity_name": m.get("external_entity_name", ""),
                }
                for m in existing
            ],
            "external_rate_plans": [
                {
                    "id": e.get("external_id", ""),
                    "name": e.get("name", e.get("external_id", "")),
                    "is_active": e.get("is_active", True),
                }
                for e in active_ext
            ],
            "summary": {
                "total_pms": len(pms_rate_plans),
                "total_external": len(active_ext),
                "already_mapped": len(existing),
                "auto_matched": sum(1 for s in suggestions if s["status"] == "auto"),
                "needs_review": sum(1 for s in suggestions if s["status"] == "review"),
                "unmatched": sum(1 for s in suggestions if s["status"] == "unmatched"),
            },
        }

    async def bulk_create_mappings(
        self,
        tenant_id: str,
        connector_id: str,
        entity_type: str,
        pairs: list[dict[str, str]],
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Bulk-create mappings from confirmed wizard pairs."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector bulunamadi", "created": 0, "failed": 0}

        property_id = connector.get("property_id", "")
        created = 0
        failed = 0
        errors = []

        for pair in pairs:
            pms_id = pair.get("pms_entity_id", "")
            pms_name = pair.get("pms_entity_name", pms_id)
            ext_id = pair.get("external_entity_id", "")
            ext_name = pair.get("external_entity_name", ext_id)

            if not pms_id or not ext_id:
                failed += 1
                errors.append({"pair": pair, "error": "PMS veya external entity ID bos"})
                continue

            try:
                await self._mapping_svc.create_mapping(
                    tenant_id=tenant_id,
                    property_id=property_id,
                    connector_id=connector_id,
                    entity_type=entity_type,
                    pms_entity_id=pms_id,
                    pms_entity_name=pms_name,
                    external_entity_id=ext_id,
                    external_entity_name=ext_name,
                    actor_id=actor_id,
                )
                created += 1
            except (ValueError, Exception) as e:
                failed += 1
                errors.append({"pair": pair, "error": str(e)})
                logger.warning("Bulk mapping failed for %s -> %s: %s", pms_id, ext_id, e)

        return {
            "created": created,
            "failed": failed,
            "total": len(pairs),
            "errors": errors,
        }
