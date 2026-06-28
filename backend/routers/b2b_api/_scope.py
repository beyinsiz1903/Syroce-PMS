"""
B2B per-subrouter scope enforcement (Task #174).

Single source of truth for B2B API-key authentication + per-subrouter scope
checks. Each X-API-Key sub-router delegates its `get_b2b_agency` dependency to
`authenticate_b2b_agency(x_api_key, required_scope=<subrouter>)`.

Scope model (fail-closed for scoped keys, backward-compatible for legacy keys):
  - key_doc["scopes"] is a list[str]  -> RESTRICTED. The requested sub-router
    must be present in the list, otherwise the call is denied with 403.
  - key_doc["scopes"] is None / missing -> UNRESTRICTED (legacy single-key
    Syroce Agency model). Full access preserved for backward compatibility.

A key can therefore be provisioned with least-privilege access to a subset of
sub-routers; any sub-router outside the granted scope returns 403.
"""

import hashlib
from datetime import UTC, datetime

from fastapi import HTTPException

# Canonical X-API-Key sub-router scope names. Mirrors the API-key auth
# sub-routers mounted in routers/b2b_api/__init__.py (admin api-keys CRUD is
# JWT-auth and therefore not a B2B scope).
B2B_SCOPES = [
    "booking_engine",
    "folio",
    "groups",
    "guest_journey",
    "guests",
    "housekeeping",
    "identity",
    "kbs",
    "lost_found",
    "services",
    "wake_up",
    "webhooks",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def normalize_scopes(scopes) -> list[str] | None:
    """Validate + normalize a requested scope list.

    Returns None for an unrestricted key (no scopes supplied) or a de-duplicated
    list of valid scope names. Raises 400 for any unknown scope (fail-closed —
    typos do not silently grant nothing/everything).
    """
    if scopes is None:
        return None
    cleaned = [s.strip() for s in scopes if s and s.strip()]
    if not cleaned:
        return None
    invalid = sorted({s for s in cleaned if s not in B2B_SCOPES})
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(f"Gecersiz scope(lar): {', '.join(invalid)}. Gecerli scope'lar: {', '.join(B2B_SCOPES)}"),
        )
    # Preserve canonical ordering, de-duplicated.
    return [s for s in B2B_SCOPES if s in set(cleaned)]


async def authenticate_b2b_agency(x_api_key: str | None, required_scope: str | None = None) -> dict:
    """Authenticate an X-API-Key caller and enforce per-subrouter scope.

    Raises:
        401 — missing / invalid / revoked key.
        403 — agency inactive, or key scoped without `required_scope`.
    """
    from core.tenant_db import get_system_db, set_tenant_context

    sysdb = get_system_db()

    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key gerekli")

    key_hash = _hash_api_key(x_api_key)
    key_doc = await sysdb.agency_api_keys.find_one({"key_hash": key_hash, "is_active": True}, {"_id": 0})
    if not key_doc:
        raise HTTPException(status_code=401, detail="Gecersiz veya devre disi API key")

    # Tenant-scoped agency lookup: agency ids are only unique WITHIN a tenant, so
    # a tenant-blind {id, status:active} match lets a key for tenant A authenticate
    # against a colliding active agency record under tenant B (cross-tenant auth /
    # commission leak). Bind the agency record to the key's own tenant.
    agency = await sysdb.agencies.find_one(
        {"id": key_doc["agency_id"], "tenant_id": key_doc["tenant_id"], "status": "active"},
        {"_id": 0},
    )
    if not agency:
        raise HTTPException(status_code=403, detail="Acente hesabi aktif degil")

    # ── Per-subrouter scope enforcement (fail-closed for scoped keys) ──
    scopes = key_doc.get("scopes")
    if scopes is not None and required_scope is not None and required_scope not in scopes:
        raise HTTPException(
            status_code=403,
            detail=f"API key '{required_scope}' alt-router'i icin yetkili degil (scope)",
        )

    # Set tenant context for downstream DB queries.
    set_tenant_context(key_doc["tenant_id"])

    # Update last_used.
    await sysdb.agency_api_keys.update_one(
        {"key_hash": key_hash},
        {"$set": {"last_used_at": _now_iso()}, "$inc": {"usage_count": 1}},
    )

    return {
        "agency_id": key_doc["agency_id"],
        "tenant_id": key_doc["tenant_id"],
        "agency_name": agency.get("name", ""),
        "commission_rate": agency.get("commission_rate", 0),
        "scopes": scopes,
    }
