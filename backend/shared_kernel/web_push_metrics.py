"""
Task #32 — Web push gönderim sayaçları (günlük rollup).

`dispatch_internal_message_push` her çağrılışında attempted/sent/failed/
pruned sayaçlarını döner; bunlar `record_dispatch` ile günlük rollup
dokümanına yazılır. Cleanup worker'ın sildiği yaş tabanlı abonelikler
ayrı `scheduled_pruned` sayacında tutulur (ana iş yükü ile karışmasın).

Şema (collection: `web_push_metrics_daily`):
    {
      tenant_id: str | "_system_",   # cleanup worker tenant'a aitseçimsiz çalıştığı için
                                     # global olabilir
      date: "YYYY-MM-DD" (UTC),
      attempted, sent, failed, pruned, scheduled_pruned: int,
      last_updated: ISO datetime str,
    }

Index: unique (tenant_id, date) — upsert ile günlük tek doküman.

Bütün yazımlar best-effort: hata durumunda exception yutulur ve loglanır;
metric kaydı kullanıcı isteğini bloklamamalı.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

COLL_NAME = "web_push_metrics_daily"
SYSTEM_TENANT = "_system_"

_indexes_ensured = False


async def ensure_indexes(db: Any) -> None:
    """İlk yazımda unique compound index'i kur (idempotent)."""
    global _indexes_ensured
    if _indexes_ensured:
        return
    try:
        await db[COLL_NAME].create_index(
            [("tenant_id", 1), ("date", 1)],
            unique=True,
            name="tenant_date_unique",
        )
        _indexes_ensured = True
    except Exception as exc:  # pragma: no cover — index hatası fatal değil
        logger.warning("web_push_metrics: ensure_indexes warning: %s", exc)


def _today_utc(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m-%d")


async def _inc(
    db: Any,
    *,
    tenant_id: str,
    date: str,
    inc: dict[str, int],
    now: datetime | None = None,
) -> None:
    """Generic upsert+inc; çağıran ensure_indexes'i tetikler."""
    if not inc:
        return
    await ensure_indexes(db)
    try:
        await db[COLL_NAME].update_one(
            {"tenant_id": tenant_id, "date": date},
            {
                "$inc": inc,
                "$set": {"last_updated": (now or datetime.now(UTC)).isoformat()},
                "$setOnInsert": {"tenant_id": tenant_id, "date": date},
            },
            upsert=True,
        )
    except Exception:
        logger.exception("web_push_metrics: failed to increment counters")


async def record_dispatch(
    db: Any,
    *,
    tenant_id: str,
    attempted: int,
    sent: int,
    failed: int,
    pruned: int,
    now: datetime | None = None,
) -> None:
    """`dispatch_internal_message_push` sonucunu rollup'a yaz."""
    inc = {
        k: int(v)
        for k, v in {
            "attempted": attempted,
            "sent": sent,
            "failed": failed,
            "pruned": pruned,
        }.items()
        if v
    }
    if not inc:
        return
    await _inc(
        db,
        tenant_id=tenant_id or SYSTEM_TENANT,
        date=_today_utc(now),
        inc=inc,
        now=now,
    )


async def record_scheduled_prune(
    db: Any,
    *,
    count: int,
    tenant_id: str | None = None,
    now: datetime | None = None,
) -> None:
    """Cleanup worker'ın sildiği abonelik sayısını sayacına ekle.

    Worker tüm tenant'lara karşı global çalıştığı için varsayılan olarak
    `_system_` rollup'ına yazar; ileride tenant başına çalışır hale
    gelirse parametre verilebilir.
    """
    if count <= 0:
        return
    await _inc(
        db,
        tenant_id=tenant_id or SYSTEM_TENANT,
        date=_today_utc(now),
        inc={"scheduled_pruned": int(count)},
        now=now,
    )


async def get_metrics_summary(
    db: Any,
    *,
    tenant_id: str,
    days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Tenant için son N günün rollup özeti.

    Tasarım kararları:
    - `today` ve `totals` SADECE tenant'ın kendi sayaçlarını içerir.
      `_system_` rollup'ı (cleanup worker tarafından silinen yaş tabanlı
      abonelik sayısı) altyapı geneli bir metriktir; tenant admin'e
      cross-tenant aktivite sızdırmamak için ayrı `system_scheduled_pruned`
      ve `system_scheduled_pruned_today` alanlarında döner.
    - `last_24h` etiketi yanıltıcıydı (gün-bazlı agregasyon takvim
      gününden ibaret). Bu nedenle alan adı `today` olarak değiştirildi
      ve UI'da "Bugün" olarak gösterilir.

    Dönen yapı:
      {
        tenant_id, range_days,
        totals: {attempted, sent, failed, pruned},
        today:  {attempted, sent, failed, pruned},
        daily:  [{date, attempted, sent, failed, pruned}, ...],
        system_scheduled_pruned: int,        # son N gün, _system_ rollup
        system_scheduled_pruned_today: int,  # bugün, _system_ rollup
      }
    """
    days = max(1, min(int(days if days is not None else 30), 365))
    now = now or datetime.now(UTC)
    start_date = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    today = _today_utc(now)

    # Tenant satırları tenant-scoped db üzerinden (TenantAwareDBProxy
    # `$in` filtresinde tenant_id eşleşmesini sağlayamadığı için cross-tenant
    # ihlal sayıp 403 üretiyordu — bkz. core/tenant_db._inject_filter).
    # Bu nedenle tenant sorgusu ve `_system_` rollup sorgusu ayrılır;
    # `_system_` cross-tenant bir altyapı sayacı olduğu için raw db ile
    # okunur ve tenant_id="_system_" sabit filtresiyle scope dışı bırakılır.
    cursor = db[COLL_NAME].find(
        {
            "tenant_id": tenant_id,
            "date": {"$gte": start_date},
        },
        {"_id": 0},
    )

    daily_map: dict[str, dict[str, int]] = {}
    totals = {"attempted": 0, "sent": 0, "failed": 0, "pruned": 0}
    today_counts = {"attempted": 0, "sent": 0, "failed": 0, "pruned": 0}
    system_scheduled = 0
    system_scheduled_today = 0

    async for doc in cursor:
        d = doc.get("date") or ""
        bucket = daily_map.setdefault(
            d,
            {"attempted": 0, "sent": 0, "failed": 0, "pruned": 0},
        )
        for k in ("attempted", "sent", "failed", "pruned"):
            v = int(doc.get(k) or 0)
            bucket[k] += v
            totals[k] += v
            if d == today:
                today_counts[k] += v

    try:
        from core.tenant_db import get_system_db
        sys_db = get_system_db()
        sys_cursor = sys_db[COLL_NAME].find(
            {"tenant_id": SYSTEM_TENANT, "date": {"$gte": start_date}},
            {"_id": 0},
        )
        async for doc in sys_cursor:
            n = int(doc.get("scheduled_pruned") or 0)
            system_scheduled += n
            if (doc.get("date") or "") == today:
                system_scheduled_today += n
    except Exception:
        logger.exception("web_push_metrics: system rollup read failed")

    daily = [
        {"date": d, **counts} for d, counts in sorted(daily_map.items())
    ]

    return {
        "tenant_id": tenant_id,
        "range_days": days,
        "totals": totals,
        "today": today_counts,
        "daily": daily,
        "system_scheduled_pruned": system_scheduled,
        "system_scheduled_pruned_today": system_scheduled_today,
    }
