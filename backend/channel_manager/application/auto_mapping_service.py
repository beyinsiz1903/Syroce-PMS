"""
Auto Room Mapping Wizard Service v2.

Provides intelligent auto-suggestion for PMS <-> External entity mappings
using multi-signal matching: name similarity, capacity, base price, and
provider-aware weighting. Includes conflict detection and review queue.

Flow:
  1. Fetch PMS room types + external room types for a connector
  2. Run multi-signal matching to suggest pairs with score breakdowns
  3. Separate auto-apply vs needs-review vs conflict suggestions
  4. Accept confirmed pairs and bulk-create mappings
"""
import asyncio as _aio
import logging
from difflib import SequenceMatcher
from typing import Any

from core.database import db

from ..connectors.hotelrunner_v2.auth import HotelRunnerAuth
from ..connectors.hotelrunner_v2.connector_errors import AuthenticationError, ConnectorError, RateLimitError
from ..connectors.hotelrunner_v2.hr_client import HotelRunnerClient
from ..infrastructure.credential_vault import CredentialVault
from ..infrastructure.repository import ChannelManagerRepository
from .mapping_service import MappingService

logger = logging.getLogger("channel_manager.application.auto_mapping")


def _normalize(name: str) -> str:
    return name.lower().strip().replace("-", " ").replace("_", " ")


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


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


def _capacity_similarity(pms_cap: int, ext_cap: int) -> float:
    if pms_cap <= 0 or ext_cap <= 0:
        return 0.0
    if pms_cap == ext_cap:
        return 1.0
    diff = abs(pms_cap - ext_cap)
    max_cap = max(pms_cap, ext_cap)
    return max(0.0, 1.0 - (diff / max_cap))


def _price_proximity(pms_price: float, ext_price: float) -> float:
    if pms_price <= 0 or ext_price <= 0:
        return 0.0
    if pms_price == ext_price:
        return 1.0
    diff = abs(pms_price - ext_price)
    avg = (pms_price + ext_price) / 2
    ratio = diff / avg
    return max(0.0, 1.0 - ratio)


_PROVIDER_WEIGHTS = {
    "hotelrunner": {"name": 0.50, "capacity": 0.25, "price": 0.15, "alias": 0.10},
    "exely":       {"name": 0.60, "capacity": 0.15, "price": 0.10, "alias": 0.15},
    "default":     {"name": 0.55, "capacity": 0.20, "price": 0.15, "alias": 0.10},
}


def _compute_match_score(pms_name: str, ext_name: str) -> float:
    base = _similarity(pms_name, ext_name)
    boost = _alias_boost(pms_name, ext_name)
    return min(base + boost, 1.0)


def _compute_match_score_v2(
    pms_name: str,
    ext_name: str,
    pms_capacity: int = 0,
    ext_capacity: int = 0,
    pms_price: float = 0.0,
    ext_price: float = 0.0,
    provider: str = "default",
) -> dict[str, Any]:
    weights = _PROVIDER_WEIGHTS.get(provider, _PROVIDER_WEIGHTS["default"])

    name_score = _similarity(pms_name, ext_name)
    alias_score = _alias_boost(pms_name, ext_name)
    cap_score = _capacity_similarity(pms_capacity, ext_capacity)
    price_score = _price_proximity(pms_price, ext_price)

    has_capacity = pms_capacity > 0 and ext_capacity > 0
    has_price = pms_price > 0 and ext_price > 0

    active_signals = {"name": name_score, "alias": alias_score}
    if has_capacity:
        active_signals["capacity"] = cap_score
    if has_price:
        active_signals["price"] = price_score

    active_weight_sum = sum(weights[k] for k in active_signals)
    if active_weight_sum > 0:
        final = sum(
            active_signals[k] * (weights[k] / active_weight_sum)
            for k in active_signals
        )
    else:
        final = 0.0

    final = min(final, 1.0)

    warnings = []
    if has_capacity and cap_score < 0.5:
        warnings.append(f"Kapasite uyumsuz: PMS={pms_capacity}, Kanal={ext_capacity}")
    if has_price and price_score < 0.3:
        warnings.append(f"Fiyat farki yuksek: PMS={pms_price:.0f}, Kanal={ext_price:.0f}")

    return {
        "final_score": round(final, 4),
        "name_similarity": round(name_score * 100),
        "alias_boost": round(alias_score * 100),
        "capacity_match": round(cap_score * 100) if has_capacity else None,
        "price_proximity": round(price_score * 100) if has_price else None,
        "provider_weights": provider,
        "warnings": warnings,
    }


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
            env = creds.pop("environment", "production")
            auth = HotelRunnerAuth.from_credentials(creds)
            client = HotelRunnerClient(auth=auth, environment=env)
        except AuthenticationError as e:
            return {"success": False, "error": f"Auth hatasi: {str(e)[:200]}"}

        try:
            # Fetch rooms from HotelRunner REST API with retry on rate limit
            rooms_raw = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    raw_data, _audit = await client._request_json(
                        "GET", "/apps/rooms", params={"per_page": "200"},
                    )
                    rooms_raw = (
                        raw_data if isinstance(raw_data, list)
                        else raw_data.get("rooms", []) if isinstance(raw_data, dict)
                        else []
                    )
                    break
                except RateLimitError as rle:
                    wait = min(rle.retry_after_seconds, 30) if attempt < max_retries - 1 else 0
                    if attempt < max_retries - 1:
                        logger.warning(
                            "Rate limited on room fetch (attempt %d/%d), waiting %ds",
                            attempt + 1, max_retries, wait,
                        )
                        await _aio.sleep(wait)
                    else:
                        raise

            if rooms_raw is None:
                rooms_raw = []

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
        """Suggest room type mappings using multi-signal v2 scoring."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector bulunamadi", "suggestions": []}

        property_id = connector.get("property_id", "")
        provider = connector.get("provider", "default")

        room_query = {"tenant_id": tenant_id, "status": {"$ne": "out_of_service"}}
        projection = {
            "_id": 0, "room_type": 1, "room_number": 1,
            "capacity": 1, "base_price": 1, "max_occupancy": 1,
        }
        if property_id:
            pms_rooms_raw = await db.rooms.find(
                {**room_query, "property_id": property_id}, projection,
            ).to_list(500)
            if not pms_rooms_raw:
                pms_rooms_raw = await db.rooms.find(room_query, projection).to_list(500)
        else:
            pms_rooms_raw = await db.rooms.find(room_query, projection).to_list(500)

        pms_types: dict[str, dict] = {}
        room_counts: dict[str, int] = {}
        for r in pms_rooms_raw:
            rt = r.get("room_type", "")
            if rt:
                if rt not in pms_types:
                    pms_types[rt] = {
                        "id": rt,
                        "name": rt,
                        "capacity": r.get("capacity") or r.get("max_occupancy") or 0,
                        "base_price": r.get("base_price") or 0,
                    }
                room_counts[rt] = room_counts.get(rt, 0) + 1

        ext_rooms = await self._repo.get_external_room_types(tenant_id, connector_id)
        active_ext = [r for r in ext_rooms if r.get("is_active", True)]

        existing_mappings = await self._repo.get_active_mappings(tenant_id, connector_id, "room_type")
        mapped_pms = {m["pms_entity_id"] for m in existing_mappings}
        mapped_ext = {m["external_entity_id"] for m in existing_mappings}

        available_ext = [e for e in active_ext if e.get("external_id") not in mapped_ext]
        available_pms = [p for p in pms_types.values() if p["id"] not in mapped_pms]

        score_matrix: list[tuple[float, int, int, dict]] = []
        for pi, pms in enumerate(available_pms):
            for ei, ext in enumerate(available_ext):
                ext_name = ext.get("name", ext.get("external_id", ""))
                ext_cap = ext.get("max_occupancy") or 0
                ext_price = ext.get("base_price") or 0
                breakdown = _compute_match_score_v2(
                    pms["name"], ext_name,
                    pms_capacity=pms.get("capacity", 0),
                    ext_capacity=ext_cap,
                    pms_price=pms.get("base_price", 0),
                    ext_price=ext_price,
                    provider=provider,
                )
                if breakdown["final_score"] > 0.0:
                    score_matrix.append((breakdown["final_score"], pi, ei, breakdown))

        score_matrix.sort(key=lambda x: -x[0])

        conflicts = []
        conflicted_ext: set[int] = set()
        conflicted_pms: set[int] = set()

        ext_top_candidates: dict[int, list[tuple[int, float]]] = {}
        threshold = 0.3
        for score, pi, ei, _bd in score_matrix:
            if score >= threshold:
                ext_top_candidates.setdefault(ei, []).append((pi, score))

        for ei, candidates in ext_top_candidates.items():
            if len(candidates) > 1:
                top_score = candidates[0][1]
                close = [c for c in candidates if c[1] >= top_score * 0.85]
                if len(close) > 1:
                    ext = available_ext[ei]
                    ext_name = ext.get("name", ext.get("external_id", ""))
                    pms_names = [available_pms[pi]["name"] for pi, _ in close]
                    conflicts.append({
                        "type": "duplicate_external",
                        "external_entity_id": ext.get("external_id", ""),
                        "external_entity_name": ext_name,
                        "pms_entities": pms_names,
                        "message": f"Kanal oda tipi '{ext_name}' birden fazla PMS tipine benziyor: {', '.join(pms_names)}",
                    })
                    conflicted_ext.add(ei)
                    for pi, _ in close:
                        conflicted_pms.add(pi)

        assigned_pms: set[int] = set()
        assigned_ext: set[int] = set()
        pms_to_ext: dict[int, tuple[int, float, dict]] = {}

        for score, pi, ei, breakdown in score_matrix:
            if pi not in assigned_pms and ei not in assigned_ext:
                pms_to_ext[pi] = (ei, score, breakdown)
                assigned_pms.add(pi)
                assigned_ext.add(ei)

        suggestions = []

        for pi, pms in enumerate(available_pms):
            if pi in pms_to_ext:
                ei, best_score, breakdown = pms_to_ext[pi]
                ext = available_ext[ei]

                has_warnings = len(breakdown.get("warnings", [])) > 0
                is_conflicted = pi in conflicted_pms or ei in conflicted_ext
                if is_conflicted:
                    status = "review"
                elif best_score >= 0.6 and not has_warnings:
                    status = "auto"
                else:
                    status = "review"

                item_warnings = list(breakdown.get("warnings", []))
                if is_conflicted:
                    item_warnings.append("Cakisma: ayni kanal tipi birden fazla PMS tipine benziyor — onay gerekli")

                suggestions.append({
                    "pms_entity_id": pms["id"],
                    "pms_entity_name": pms["name"],
                    "pms_room_count": room_counts.get(pms["id"], 0),
                    "pms_capacity": pms.get("capacity", 0),
                    "pms_base_price": pms.get("base_price", 0),
                    "external_entity_id": ext.get("external_id", ""),
                    "external_entity_name": ext.get("name", ext.get("external_id", "")),
                    "external_capacity": ext.get("max_occupancy") or 0,
                    "external_base_price": ext.get("base_price") or 0,
                    "confidence": round(best_score * 100),
                    "status": status,
                    "score_breakdown": {
                        "name_similarity": breakdown["name_similarity"],
                        "alias_boost": breakdown["alias_boost"],
                        "capacity_match": breakdown["capacity_match"],
                        "price_proximity": breakdown["price_proximity"],
                    },
                    "warnings": item_warnings,
                })
            else:
                suggestions.append({
                    "pms_entity_id": pms["id"],
                    "pms_entity_name": pms["name"],
                    "pms_room_count": room_counts.get(pms["id"], 0),
                    "pms_capacity": pms.get("capacity", 0),
                    "pms_base_price": pms.get("base_price", 0),
                    "external_entity_id": "",
                    "external_entity_name": "",
                    "external_capacity": 0,
                    "external_base_price": 0,
                    "confidence": 0,
                    "status": "unmatched",
                    "score_breakdown": {
                        "name_similarity": 0,
                        "alias_boost": 0,
                        "capacity_match": None,
                        "price_proximity": None,
                    },
                    "warnings": [],
                })

        order = {"auto": 0, "review": 1, "unmatched": 2}
        suggestions.sort(key=lambda s: (order.get(s["status"], 3), -s["confidence"]))

        return {
            "connector_id": connector_id,
            "connector_name": connector.get("display_name", ""),
            "provider": provider,
            "property_id": property_id,
            "suggestions": suggestions,
            "conflicts": conflicts,
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
                    "max_occupancy": e.get("max_occupancy", 0),
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
                "conflicts": len(conflicts),
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
