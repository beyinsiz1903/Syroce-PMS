"""CapX tenant-aware credentials.

Pattern:
  - Tek-tenant kurulumda eski env-only davranış korunur (CAPX_BASE_URL, CAPX_API_KEY,
    CAPX_WEBHOOK_SECRET).
  - Multi-tenant SaaS kurulumda her tenant farklı CapX hesabı kullanabilir.
  - Tenant credential'ları `capx_tenant_credentials` koleksiyonunda şifreli saklanır.

Resolution sırası (`resolve_credentials(tenant_id)`):
  1) tenant_id verilmişse koleksiyondan oku
  2) yoksa env'den oku (fallback)
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.crypto import get_crypto_service
from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)

COLLECTION = "capx_tenant_credentials"
_CACHE_TTL = 300  # 5 dk
_cache: dict[str, tuple[float, "CapXCreds"]] = {}


@dataclass(frozen=True)
class CapXCreds:
    base_url: str = ""
    api_key: str = ""
    webhook_secret: str = ""
    source: str = "env"  # "env" | "tenant"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)


def _from_env() -> CapXCreds:
    return CapXCreds(
        base_url=(os.getenv("CAPX_BASE_URL") or "").rstrip("/"),
        api_key=os.getenv("CAPX_API_KEY") or "",
        webhook_secret=os.getenv("CAPX_WEBHOOK_SECRET") or "",
        source="env",
    )


def invalidate(tenant_id: str | None = None) -> None:
    """Cache'i temizle. tenant_id=None → tüm cache, aksi halde sadece o tenant."""
    global _cache
    if tenant_id is None:
        _cache.clear()
    else:
        _cache.pop(tenant_id, None)
        _cache.pop("__env__", None)


async def resolve_credentials(tenant_id: str | None = None) -> CapXCreds:
    """Tenant kimliği verilirse o tenant'ın credential'larını oku, yoksa env.

    Cache: tenant_id (veya '__env__') → CapXCreds, TTL 5 dk.
    """
    cache_key = tenant_id or "__env__"
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    creds: CapXCreds
    if tenant_id:
        try:
            doc = await get_system_db()[COLLECTION].find_one(
                {"tenant_id": tenant_id}, {"_id": 0}
            )
        except Exception as exc:
            logger.warning("CapX tenant creds lookup failed (%s): %s", tenant_id, exc)
            doc = None

        if doc and doc.get("api_key_encrypted"):
            crypto = get_crypto_service()
            try:
                api_key = crypto.decrypt(doc["api_key_encrypted"])
            except Exception:
                api_key = ""
            try:
                webhook_secret = (
                    crypto.decrypt(doc["webhook_secret_encrypted"])
                    if doc.get("webhook_secret_encrypted") else ""
                )
            except Exception:
                webhook_secret = ""
            creds = CapXCreds(
                base_url=(doc.get("base_url") or "").rstrip("/"),
                api_key=api_key,
                webhook_secret=webhook_secret,
                source="tenant",
            )
        else:
            creds = _from_env()
    else:
        creds = _from_env()

    _cache[cache_key] = (now + _CACHE_TTL, creds)
    return creds


async def upsert_tenant_credentials(
    *, tenant_id: str, base_url: str, api_key: str,
    webhook_secret: str = "", actor_id: str = "system",
) -> dict[str, Any]:
    """Super-admin / tenant admin tarafından çağrılır."""
    crypto = get_crypto_service()
    now = datetime.now(UTC).isoformat()
    set_doc: dict[str, Any] = {
        "tenant_id": tenant_id,
        "base_url": base_url.rstrip("/"),
        "api_key_encrypted": crypto.encrypt(api_key),
        "updated_at": now,
        "updated_by": actor_id,
    }
    if webhook_secret:
        set_doc["webhook_secret_encrypted"] = crypto.encrypt(webhook_secret)
    await get_system_db()[COLLECTION].update_one(
        {"tenant_id": tenant_id},
        {"$set": set_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    invalidate(tenant_id)
    return {"tenant_id": tenant_id, "configured": True, "updated_at": now}


async def delete_tenant_credentials(tenant_id: str) -> dict[str, Any]:
    res = await get_system_db()[COLLECTION].delete_one({"tenant_id": tenant_id})
    invalidate(tenant_id)
    return {"tenant_id": tenant_id, "deleted": res.deleted_count > 0}


async def get_tenant_status(tenant_id: str) -> dict[str, Any]:
    doc = await get_system_db()[COLLECTION].find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "tenant_id": 1, "base_url": 1, "updated_at": 1, "updated_by": 1,
         "api_key_encrypted": 1, "webhook_secret_encrypted": 1},
    )
    if not doc:
        return {"tenant_id": tenant_id, "configured": False, "source": "env"}
    return {
        "tenant_id": tenant_id,
        "configured": bool(doc.get("api_key_encrypted")),
        "base_url": doc.get("base_url"),
        "has_webhook_secret": bool(doc.get("webhook_secret_encrypted")),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
        "source": "tenant",
    }


async def list_tenant_status() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async for doc in get_system_db()[COLLECTION].find(
        {},
        {"_id": 0, "tenant_id": 1, "base_url": 1, "updated_at": 1, "updated_by": 1,
         "api_key_encrypted": 1, "webhook_secret_encrypted": 1},
    ):
        items.append({
            "tenant_id": doc.get("tenant_id"),
            "configured": bool(doc.get("api_key_encrypted")),
            "base_url": doc.get("base_url"),
            "has_webhook_secret": bool(doc.get("webhook_secret_encrypted")),
            "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by"),
        })
    return items
