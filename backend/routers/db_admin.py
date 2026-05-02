"""
DB Admin — Atlas koleksiyon teşhisi ve güvenli temizlik.

Çoklu tenant tek-koleksiyon mimarisindeyiz; yine de eski/legacy/test
koleksiyonları zamanla birikip Atlas free-tier 500 koleksiyon limitini
zorlayabilir. Bu router yalnız platform süper-admin'in kullanabildiği bir
teşhis + allowlist tabanlı drop arayüzü sağlar.

GÜVENLİK: Operasyon `_raw_db` üzerinde çalışır (tenant scoping by-pass).
Bu nedenle tenant rolündeki "admin" YETERSİZ — yalnız `super_admin`
(`require_super_admin_guard`) ve allowlist + opsiyonel `confirm_name`
ikinci faktörü gerekir.

GET    /api/admin/db/collections                              — liste + count
DELETE /api/admin/db/collections/{name}?dry_run=true          — varsayılan
"""
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from cache_manager import cached
from core.database import _raw_db
from core.helpers import create_audit_log, require_super_admin_guard
from models.schemas import User

logger = logging.getLogger(__name__)
require_super_admin = require_super_admin_guard()

router = APIRouter(prefix="/api/admin/db", tags=["admin-db"])

# Drop edilmesine ASLA izin verilmeyen kritik koleksiyonlar (case-sensitive).
# Bunların dışındaki sadece "_test" / "_tmp" / "_legacy_*" isimleri
# silinebilir. Diğer her şey için 403 dönülür.
PROTECTED_PREFIXES = (
    "tenants", "system_", "users", "bookings", "rooms", "guests",
    "folios", "folio_charges", "folio_payments", "audit_logs",
    "outbox", "city_tax_rules", "tax_declarations",
    "accommodation_tax_postings", "channel_", "rate_", "housekeeping",
    "invoices", "payments", "agencies", "corporate_", "groups",
    "session", "kbs_", "subscriptions", "subscription_", "tenant_",
    "notifications", "ml_", "audit_", "loyalty_", "guest_",
    "reservation_", "rooms_", "permissions", "roles",
)


def _is_droppable(name: str) -> tuple[bool, str]:
    """Allowlist guard. Returns (allowed, reason)."""
    n = name.strip()
    if not n:
        return False, "Boş ad"
    if n.startswith("system."):
        return False, "Sistem koleksiyonu"
    for p in PROTECTED_PREFIXES:
        if n == p or n.startswith(p):
            return False, f"Korumalı koleksiyon ön eki: {p}"
    if n.endswith("_test") or n.endswith("_tmp") or n.startswith("legacy_"):
        return True, "Allowlist: *_test / *_tmp / legacy_*"
    if "__obsolete__" in n or n.startswith("_obsolete_"):
        return True, "Allowlist: __obsolete__"
    return False, "Allowlist dışı (ancak *_test/_tmp/legacy_* silinebilir)"


class DropConfirm(BaseModel):
    confirm_name: str | None = None


@router.get("/collections")
@cached(ttl=120, key_prefix="db_admin_collections")  # 2dk cache (Tur 2 fix)
async def list_collections(
    include_stats: bool = Query(True),
    current_user: User = Depends(require_super_admin),
) -> dict[str, Any]:
    """Koleksiyonları listeler (yalnız platform süper-admin)."""
    names = sorted(await _raw_db.list_collection_names())

    # Bulk count via asyncio.gather (was 500 sequential round-trips → parallel)
    counts: dict[str, Any] = {}
    if include_stats:
        async def _count(n: str):
            try:
                return n, await _raw_db[n].estimated_document_count(), None
            except Exception as e:
                return n, None, str(e)[:120]
        results = await asyncio.gather(*[_count(n) for n in names])
        for n, c, err in results:
            counts[n] = (c, err)

    items: list[dict[str, Any]] = []
    for name in names:
        droppable, reason = _is_droppable(name)
        row: dict[str, Any] = {
            "name": name,
            "droppable": droppable,
            "drop_reason": reason,
        }
        if include_stats:
            c, err = counts.get(name, (None, None))
            row["count"] = c
            if err:
                row["count_error"] = err
        items.append(row)

    droppable_count = sum(1 for r in items if r.get("droppable"))
    logger.info(
        "db_admin.list_collections actor=%s tenant=%s total=%d droppable=%d",
        getattr(current_user, "id", "?"),
        getattr(current_user, "tenant_id", "?"),
        len(items),
        droppable_count,
    )
    return {
        "total": len(items),
        "droppable_count": droppable_count,
        "items": items,
    }


@router.delete("/collections/{name}")
async def drop_collection(
    name: str,
    dry_run: bool = Query(True, description="True ise sadece izin kontrolü"),
    body: DropConfirm | None = None,
    current_user: User = Depends(require_super_admin),
) -> dict[str, Any]:
    """
    Allowlist'teki bir koleksiyonu drop eder. Dry-run varsayılan.
    Gerçek silme için: dry_run=false + body.confirm_name == name.
    """
    actor_id = getattr(current_user, "id", "?")
    tenant_id = getattr(current_user, "tenant_id", "?")
    logger.info(
        "db_admin.drop_collection.attempt actor=%s tenant=%s name=%s dry_run=%s",
        actor_id, tenant_id, name, dry_run,
    )

    allowed, reason = _is_droppable(name)
    if not allowed:
        logger.warning(
            "db_admin.drop_collection.denied actor=%s name=%s reason=%s",
            actor_id, name, reason,
        )
        raise HTTPException(status_code=403, detail=f"Drop reddedildi: {reason}")

    if dry_run:
        return {
            "dropped": False,
            "dry_run": True,
            "name": name,
            "reason": reason,
            "hint": "Gerçek silme için ?dry_run=false + body {confirm_name: '<aynı ad>'} gönderin",
        }

    # ── Destructive path ── ikinci faktör zorunlu
    if not body or body.confirm_name != name:
        raise HTTPException(
            status_code=400,
            detail="Gerçek silme için body.confirm_name değeri koleksiyon adıyla aynı olmalı",
        )

    try:
        existing = await _raw_db.list_collection_names()
        if name not in existing:
            return {"dropped": False, "name": name, "detail": "Zaten yok"}
        await _raw_db.drop_collection(name)
    except Exception as e:
        logger.exception("db_admin.drop_collection.failed name=%s", name)
        raise HTTPException(status_code=500, detail=f"Silme başarısız: {e}")

    logger.warning(
        "db_admin.drop_collection.done actor=%s tenant=%s name=%s reason=%s",
        actor_id, tenant_id, name, reason,
    )
    try:
        await create_audit_log(
            tenant_id=tenant_id,
            user=current_user,
            action="DROP_COLLECTION",
            entity_type="mongodb_collection",
            entity_id=name,
            changes={"reason": reason, "destructive": True},
        )
    except Exception:
        pass
    return {"dropped": True, "name": name, "reason": reason}
