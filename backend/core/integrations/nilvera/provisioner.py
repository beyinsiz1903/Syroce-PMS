"""Nilvera tenant provisioning and settings management."""

import logging
from typing import Any

from pymongo import ReturnDocument

from core.crypto import AADContext, get_crypto_service
from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)


def _aad(tenant_id: str) -> AADContext:
    """AAD context for Nilvera API key encryption."""
    return AADContext(
        tenant_id=tenant_id,
        provider="nilvera",
        context_type="nilvera_api_key_v1"
    )


async def get_nilvera_tenant_config(tenant_id: str, *, decrypt_api_key: bool = False) -> dict[str, Any]:
    """Retrieve Nilvera settings for a tenant.

    Returns a dict with 'enabled' (bool), 'api_key' (str | None), and 'seller' (dict).
    If `decrypt_api_key` is False, the API key is omitted/masked.
    """
    sysdb = get_system_db()
    doc = await sysdb.tenant_settings.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "nilvera": 1}
    )

    cfg = (doc or {}).get("nilvera") or {}
    seller_cfg = cfg.get("seller") or {}
    out = {
        "enabled": bool(cfg.get("enabled")),
        "api_key_set": bool(cfg.get("api_key_enc")),
        "api_key": None,
        "seller": seller_cfg,
    }

    if decrypt_api_key and cfg.get("api_key_enc"):
        try:
            svc = get_crypto_service()
            out["api_key"] = svc.decrypt(cfg["api_key_enc"], aad=_aad(tenant_id))
        except Exception as exc:
            logger.warning("[nilvera] api_key decrypt failed tenant=%s error_type=%s", tenant_id, type(exc).__name__)
            out["api_key"] = None

    return out


async def update_nilvera_tenant_config(
    tenant_id: str,
    *,
    enabled: bool | None = None,
    api_key: str | None = None,
    seller: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update Nilvera settings for a tenant.

    If `api_key` is provided, it is encrypted and saved.
    If `api_key` is empty string (""), the key is cleared.
    If `enabled` is provided, the integration toggle is updated.
    If `seller` is provided, the seller info is updated.
    """
    sysdb = get_system_db()
    updates: dict[str, Any] = {}

    if enabled is not None:
        updates["nilvera.enabled"] = bool(enabled)

    if api_key is not None:
        if api_key.strip():
            svc = get_crypto_service()
            encrypted = svc.encrypt(api_key.strip(), aad=_aad(tenant_id))
            updates["nilvera.api_key_enc"] = encrypted
        else:
            # Clear key
            updates["nilvera.api_key_enc"] = None

    if seller is not None:
        updates["nilvera.seller"] = seller

    if not updates:
        return await get_nilvera_tenant_config(tenant_id)

    doc = await sysdb.tenant_settings.find_one_and_update(
        {"tenant_id": tenant_id},
        {"$set": updates},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "nilvera": 1}
    )

    # Return safe summary
    cfg = (doc or {}).get("nilvera") or {}
    return {
        "enabled": bool(cfg.get("enabled")),
        "api_key_set": bool(cfg.get("api_key_enc")),
        "api_key": None,
        "seller": cfg.get("seller") or {}
    }
