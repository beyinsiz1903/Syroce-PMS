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

from ..connectors.hotelrunner_v2.auth import HotelRunnerAuth
from ..connectors.hotelrunner_v2.v1_client import HotelRunnerClient
from ..connectors.hotelrunner_v2.v1_errors import AuthenticationError, ConnectorError
from ..infrastructure.credential_vault import CredentialVault
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

    async def fetch_external_data_from_channel(
        self, tenant_id: str, connector_id: str,
    ) -> dict[str, Any]:
        """
        Fetch real room types and rate plans from HotelRunner API
        and persist them into cm_external_room_types / cm_external_rate_plans.
        """
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"success": False, "error": "Connector bulunamadi"}

        provider = connector.get("provider", "")
        if provider != "hotelrunner":
            return {"success": False, "error": f"Provider '{provider}' icin otomatik veri cekme henuz desteklenmiyor"}

        # Decrypt credentials
        try:
            vault = CredentialVault(repo=self._repo)
            creds = await vault.retrieve_credentials(tenant_id, connector_id)
        except Exception:
            # Fallback: try legacy decryption with default key
            try:
                raw_creds = connector.get("credentials", {})
                if connector.get("credentials_encrypted"):
                    import base64  # noqa: I001
                    import hashlib
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    prefix = "aes256gcm:"
                    creds = {}
                    for k, v in raw_creds.items():
                        if isinstance(v, str) and v.startswith(prefix):
                            # Try env key first, then default
                            import os
                            keys_to_try = [
                                os.environ.get("CM_CREDENTIAL_KEY", ""),
                                "syroce-pms-default-key-change-in-production",
                            ]
                            decrypted = False
                            for key_material in keys_to_try:
                                if not key_material:
                                    continue
                                try:
                                    aes_key = hashlib.sha256(key_material.encode()).digest()
                                    raw = base64.b64decode(v[len(prefix):])
                                    nonce, ct = raw[:12], raw[12:]
                                    plaintext = AESGCM(aes_key).decrypt(nonce, ct, None)
                                    creds[k] = plaintext.decode("utf-8")
                                    decrypted = True
                                    break
                                except Exception:
                                    continue
                            if not decrypted:
                                creds[k] = v
                        else:
                            creds[k] = v
                else:
                    creds = raw_creds
            except Exception as e:
                logger.error("All credential decryption failed for connector %s: %s", connector_id, e)
                return {"success": False, "error": f"Kimlik bilgileri cozulemedi: {str(e)[:200]}"}

        # Build client and fetch rooms
        try:
            auth = HotelRunnerAuth.from_credentials(creds)
            client = HotelRunnerClient(auth=auth, sandbox=True)
        except AuthenticationError as e:
            return {"success": False, "error": f"Auth hatasi: {str(e)[:200]}"}

        try:
            # Fetch rooms from HotelRunner REST API
            resp_text = await client._request_json("GET", "/apps/rooms", params={"per_page": "200"})
            raw_data, _audit = resp_text
            rooms_raw = raw_data if isinstance(raw_data, list) else raw_data.get("rooms", []) if isinstance(raw_data, dict) else []
        except (ConnectorError, Exception) as e:
            logger.error("Room fetch failed for connector %s: %s", connector_id, e)
            await client.close()
            return {"success": False, "error": f"HotelRunner'dan oda verileri cekilemedi: {str(e)[:200]}"}
        finally:
            await client.close()

        # Parse rooms: group by inv_code to get unique room types, collect rate plans
        room_types: dict[str, dict] = {}
        rate_plans: dict[str, dict] = {}

        for room in rooms_raw:
            inv_code = room.get("inv_code", "")
            rate_code = room.get("rate_code", "")
            name = room.get("name", "")
            description = room.get("description", "")
            room_capacity = room.get("room_capacity", 0)
            adult_capacity = room.get("adult_capacity", 0)

            # Room type (grouped by inv_code)
            if inv_code and inv_code not in room_types:
                room_types[inv_code] = {
                    "tenant_id": tenant_id,
                    "connector_id": connector_id,
                    "external_id": inv_code,
                    "name": name,
                    "description": description,
                    "max_occupancy": room_capacity or adult_capacity or 0,
                    "is_active": True,
                }

            # Rate plan (each rate_code is a plan)
            if rate_code and rate_code not in rate_plans:
                rate_plans[rate_code] = {
                    "tenant_id": tenant_id,
                    "connector_id": connector_id,
                    "external_id": rate_code,
                    "name": name if rate_code == inv_code else f"{name} ({rate_code})",
                    "external_room_type_id": inv_code,
                    "is_active": True,
                }

        # Clear old data and persist new
        await db.cm_external_room_types.delete_many({"tenant_id": tenant_id, "connector_id": connector_id})
        await db.cm_external_rate_plans.delete_many({"tenant_id": tenant_id, "connector_id": connector_id})

        for doc in room_types.values():
            await self._repo.upsert_external_room_type(doc)
        for doc in rate_plans.values():
            await self._repo.upsert_external_rate_plan(doc)

        logger.info(
            "Fetched %d room types and %d rate plans from HotelRunner for connector %s",
            len(room_types), len(rate_plans), connector_id,
        )

        return {
            "success": True,
            "room_types_count": len(room_types),
            "rate_plans_count": len(rate_plans),
            "room_types": [
                {"external_id": rt["external_id"], "name": rt["name"], "max_occupancy": rt["max_occupancy"]}
                for rt in room_types.values()
            ],
            "rate_plans": [
                {"external_id": rp["external_id"], "name": rp["name"]}
                for rp in rate_plans.values()
            ],
        }

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
