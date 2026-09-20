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
) -> tuple[dict, list[dict]]:
    """Return the caller's own property and permitted chain properties.

    A tenant with no chain remains strictly single-property.  Cross-property
    access is limited to the designated headquarters (or a platform
    super-admin) and to tenants sharing the exact same ``chain_id``.
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Otel bağlamı gerekli")

    system_db = get_system_db()
    own = await system_db.tenants.find_one(
        {"$or": [{"id": tenant_id}, {"tenant_id": tenant_id}]},
        {"_id": 0},
    )
    if not own:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    chain_id = own.get("chain_id")
    if not chain_id:
        return own, [own]

    if require_headquarters and not (own.get("is_chain_headquarters") or _is_super_admin(current_user)):
        raise HTTPException(status_code=403, detail="Zincir görünümü yalnızca merkez tesis yetkililerine açıktır")

    query: dict = {"chain_id": chain_id}
    if not include_archived:
        query["subscription_status"] = {"$ne": "archived"}
    members = await system_db.tenants.find(query, {"_id": 0}).sort("property_name", 1).to_list(500)

    # Defensive invariant: never return a malformed document from another
    # tenant, even if a legacy query/mock returns it.
    members = [member for member in members if member.get("chain_id") == chain_id and tenant_id_from_document(member)]
    return own, members or [own]
