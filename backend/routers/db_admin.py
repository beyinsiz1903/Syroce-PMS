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
from core.atomic_booking import (
    ensure_booking_indexes,
    list_room_night_lock_duplicate_groups,
    manual_resolve_room_night_lock_duplicate,
    resolve_room_night_lock_duplicates,
)
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


# ─── F8N — Duplicate Room-Night Lock Auto-Resolver (Task #222) ────────
#
# `scan_room_night_lock_duplicates` / `ensure_booking_indexes` detect
# duplicate `(tenant_id, room_id, night_date)` rows in `room_night_locks`
# but never delete them automatically (per task guard rules). Until an
# operator adjudicates each group, the UNIQUE `ux_room_night` index
# cannot be created and the F8N CRITICAL post-create log stays hot.
#
# These endpoints give super-admin a sanctioned, audited path to:
#   GET  /api/admin/db/room-night-lock-duplicates           → plan/list
#   POST /api/admin/db/room-night-lock-duplicates/resolve   → apply (gated)
#
# Both routes are super-admin only. The destructive POST requires both
# `dry_run=false` AND `confirm=true` in the body so a fat-finger curl
# cannot delete rows. Only `auto_safe` / `auto_safe_all_inactive` groups
# are touched — `manual_required` groups are reported back unchanged.

class RnlResolveBody(BaseModel):
    confirm: bool = False
    limit: int = 100


@router.get("/room-night-lock-duplicates")
async def list_rnl_duplicates(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_super_admin),
) -> dict[str, Any]:
    """List duplicate room-night-lock groups with auto-resolution
    recommendation. Read-only; never mutates."""
    groups = await list_room_night_lock_duplicate_groups(limit=limit)
    auto = sum(
        1 for g in groups
        if g["recommendation"] in ("auto_safe", "auto_safe_all_inactive")
    )
    manual = sum(1 for g in groups if g["recommendation"] == "manual_required")
    logger.info(
        "db_admin.rnl_duplicates.list actor=%s total=%d auto=%d manual=%d",
        getattr(current_user, "id", "?"), len(groups), auto, manual,
    )
    return {
        "total": len(groups),
        "auto_resolvable": auto,
        "manual_required": manual,
        "groups": groups,
    }


@router.get("/rnl-auto-resolve-runs")
async def list_rnl_auto_resolve_runs(
    limit: int = Query(20, ge=1, le=200),
    current_user: User = Depends(require_super_admin),
) -> dict[str, Any]:
    """List the most recent daily auto-resolver runs (Task #224 beat job).

    Each entry is a summary persisted by `_rnl_duplicate_auto_resolve_async`
    (scanned / resolved / skipped / manual_required / index_rebuild). The view
    lets operators confirm the self-healing loop is running without having to
    grep worker logs.
    """
    cursor = (
        _raw_db["rnl_auto_resolve_runs"]
        .find({}, {"_id": 0})
        .sort("started_at", -1)
        .limit(limit)
    )
    runs = await cursor.to_list(length=limit)
    logger.info(
        "db_admin.rnl_auto_resolve_runs.list actor=%s returned=%d",
        getattr(current_user, "id", "?"), len(runs),
    )
    return {"total": len(runs), "runs": runs}


@router.post("/room-night-lock-duplicates/resolve")
async def resolve_rnl_duplicates(
    body: RnlResolveBody | None = None,
    dry_run: bool = Query(True, description="True ise plan döner, silmez"),
    rebuild_index: bool = Query(
        False,
        description="Apply sonrası ensure_booking_indexes() çağır",
    ),
    current_user: User = Depends(require_super_admin),
) -> dict[str, Any]:
    """Auto-resolve duplicate room-night locks. Dry-run by default.

    Real apply requires `?dry_run=false` AND `body.confirm=true`. Only
    `auto_safe` / `auto_safe_all_inactive` groups are touched; the rest
    are reported back unchanged for manual review.
    """
    body = body or RnlResolveBody()
    actor_id = getattr(current_user, "id", "?")
    actor_name = getattr(current_user, "name", "super_admin")
    actor_role = getattr(current_user, "role", "super_admin")

    logger.info(
        "db_admin.rnl_duplicates.resolve.attempt actor=%s dry_run=%s confirm=%s",
        actor_id, dry_run, body.confirm,
    )

    if not dry_run and not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Gerçek silme için body.confirm=true zorunlu",
        )

    result = await resolve_room_night_lock_duplicates(
        apply=not dry_run,
        limit=body.limit,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role=actor_role,
    )

    index_rebuild: dict[str, Any] | None = None
    if not dry_run and rebuild_index and result["resolved_count"] > 0:
        try:
            await ensure_booking_indexes()
            index_rebuild = {"ran": True}
        except Exception as exc:
            logger.warning("db_admin.rnl_duplicates.resolve.index_rebuild_failed: %s", exc)
            index_rebuild = {"ran": False, "error": str(exc)[:200]}

    logger.warning(
        "db_admin.rnl_duplicates.resolve.done actor=%s applied=%s resolved=%d skipped=%d",
        actor_id, result["applied"], result["resolved_count"], result["skipped_count"],
    )

    if index_rebuild is not None:
        result["index_rebuild"] = index_rebuild
    return result


class RnlManualResolveBody(BaseModel):
    tenant_id: str
    room_id: str
    night_date: str
    keep_booking_id: str
    retire_booking_ids: list[str]
    confirm: bool = False


@router.post("/room-night-lock-duplicates/manual-resolve")
async def manual_resolve_rnl_duplicate(
    body: RnlManualResolveBody,
    dry_run: bool = Query(True, description="True ise sadece doğrulama"),
    current_user: User = Depends(require_super_admin),
) -> dict[str, Any]:
    """Operator-driven resolve for a single `manual_required` lock group.

    Counterpart to `/resolve`, used when two or more active bookings share
    the same (tenant, room, night) and the operator must pick which one
    keeps the lock. Strictly scoped — `delete_many` runs only on the
    (tenant, room, night, booking_id $in retire) quadruple supplied here.

    Real apply requires `?dry_run=false` AND `body.confirm=true`.
    """
    actor_id = getattr(current_user, "id", "?")
    actor_name = getattr(current_user, "name", "super_admin")
    actor_role = getattr(current_user, "role", "super_admin")

    logger.info(
        "db_admin.rnl_duplicates.manual_resolve.attempt actor=%s "
        "tenant=%s room=%s night=%s keep=%s retire=%s dry_run=%s confirm=%s",
        actor_id, body.tenant_id, body.room_id, body.night_date,
        body.keep_booking_id, body.retire_booking_ids, dry_run, body.confirm,
    )

    if not body.retire_booking_ids:
        raise HTTPException(
            status_code=400,
            detail="retire_booking_ids boş olamaz",
        )
    if body.keep_booking_id in body.retire_booking_ids:
        raise HTTPException(
            status_code=400,
            detail="keep_booking_id retire listesinde olamaz",
        )
    if not dry_run and not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Gerçek silme için body.confirm=true zorunlu",
        )

    if dry_run:
        return {
            "applied": False,
            "dry_run": True,
            "tenant_id": body.tenant_id,
            "room_id": body.room_id,
            "night_date": body.night_date,
            "keep_booking_id": body.keep_booking_id,
            "retire_booking_ids": body.retire_booking_ids,
            "hint": "Gerçek silme için ?dry_run=false + body.confirm=true",
        }

    result = await manual_resolve_room_night_lock_duplicate(
        tenant_id=body.tenant_id,
        room_id=body.room_id,
        night_date=body.night_date,
        keep_booking_id=body.keep_booking_id,
        retire_booking_ids=body.retire_booking_ids,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role=actor_role,
    )

    logger.warning(
        "db_admin.rnl_duplicates.manual_resolve.done actor=%s tenant=%s "
        "room=%s night=%s applied=%s deleted=%s skip_reason=%s",
        actor_id, body.tenant_id, body.room_id, body.night_date,
        result.get("applied"), result.get("deleted_count"),
        result.get("skip_reason"),
    )
    return result
