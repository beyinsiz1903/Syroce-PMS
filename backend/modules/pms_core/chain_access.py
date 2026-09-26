"""Authoritative chain-property access resolution.

Properties are always independent tenants.  ``chain_id`` only grants a
*central office* a carefully-scoped cross-property view; it never turns a
chain into a shared tenant or authorizes a member hotel to administer its
siblings.
"""

from __future__ import annotations

from fastapi import HTTPException

from core.security import _is_super_admin
from core.tenant_db import get_system_db
from models.schemas import User


def tenant_id_from_document(document: dict) -> str | None:
    """Read both historical ``tenant_id`` and canonical ``id`` safely."""
    return document.get("tenant_id") or document.get("id")


async def resolve_chain_properties(
    current_user: User,
    *,
    require_headquarters: bool = True,
    include_archived: bool = False,
    system_db=None,
) -> tuple[dict, list[dict]]:
    """Return the caller's own property and permitted chain properties.

    A tenant with no chain remains strictly single-property.  Cross-property
    access is limited to the designated headquarters (or a platform
    super-admin) and to tenants sharing the exact same ``chain_id``.
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Otel bağlamı gerekli")

    # Explicit injection keeps central-office services on the same database
    # handle as their subsequent financial reads.  Production callers omit it;
    # isolated tests and controlled workers can provide their scoped handle.
    system_db = system_db or get_system_db()
    own = await system_db.tenants.find_one(
        {"$or": [{"id": tenant_id}, {"tenant_id": tenant_id}]},
        {"_id": 0},
    )
    if not own:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    chain_id = own.get("chain_id")
    if not chain_id:
        return own, [own]

    # A headquarters *property* flag must not grant every administrator in
    # that property's tenant cross-property access.  Access belongs to an
    # explicitly designated chain user.  For older provisioned headquarters,
    # the tenant's primary contact is the backward-compatible chain owner.
    # Both values come from persisted, server-side records (never request
    # parameters).
    user_email = str(getattr(current_user, "email", "") or "").strip().casefold()
    primary_email = str(own.get("contact_email") or own.get("email") or "").strip().casefold()
    is_chain_user = bool(
        getattr(current_user, "is_chain_admin", False)
        or getattr(current_user, "is_chain_headquarters", False)
        or (own.get("is_chain_headquarters") and user_email and user_email == primary_email)
    )
    if require_headquarters and not (is_chain_user or _is_super_admin(current_user)):
        raise HTTPException(status_code=403, detail="Zincir görünümü yalnızca merkez tesis yetkililerine açıktır")

    query: dict = {"chain_id": chain_id}
    if not include_archived:
        query["subscription_status"] = {"$ne": "archived"}
    cursor = system_db.tenants.find(query, {"_id": 0})
    if hasattr(cursor, "sort"):
        cursor = cursor.sort("property_name", 1)
    members = await cursor.to_list(500)

    # Defensive invariant: never return a malformed document from another
    # tenant, even if a legacy query/mock returns it.
    members = [member for member in members if member.get("chain_id") == chain_id and tenant_id_from_document(member)]
    members.sort(key=lambda member: (member.get("property_name") or member.get("hotel_name") or "").casefold())
    return own, members or [own]
