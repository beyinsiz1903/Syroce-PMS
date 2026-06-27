"""Birleşik geri bildirim modeli — geri alınabilir backfill migration.

NPS Raporlama Birleştirme görevinin 3. adımı. Üç kaynak koleksiyondaki misafir
geri bildirimini tek kanonik koleksiyona (``feedback_entries``) materyalize eder:

- ``nps_surveys``      → ``source=nps_survey``      (0-10, NPS-uygun)
- ``survey_responses`` → ``source=survey_response`` (NPS'e KARIŞMAZ)
- ``guest_reviews``    → ``source=guest_review``    (1-5, NPS'e KARIŞMAZ)

Kanonik kayıt ``modules.guest_journey.feedback_reporting_service`` ile birebir
aynı normalizasyondan geçer; böylece materyalize veri, legacy ``/nps/*``
uçlarının okuduğu mantıkla tutarlıdır. Operatör kararı gereği canlı NPS sayısı
DEĞİŞMEZ: legacy uçlar hâlâ ``nps_surveys`` kaynağından (authoritative) okur;
bu koleksiyon downstream/analitik tek model materyalizasyonudur.

Güvenlik sözleşmesi
-------------------
* DRY-RUN varsayılan. Hiçbir yazım yapılmaz; yalnız sayım raporlanır.
* ``--apply`` (yazım) ve ``--rollback --apply`` (geri alma) için
  ``ALLOW_FEEDBACK_MIGRATION=true`` env ZORUNLU (fail-closed; çift opt-in:
  CLI bayrağı + env).
* Idempotent: kanonik ``dedup_key = tenant_id|source|source_id`` üzerinde
  upsert + unique index → re-run çift sayım ÜRETMEZ.
* Tenant izolasyonu: ``--tenant-id`` ile tek tenant; verilmezse kaynak
  koleksiyonlardaki tüm tenant'lar taranır. Her kayıt kendi ``tenant_id``'sini
  taşır; cross-tenant karışma yoktur.
* Geri alınabilir: ``--rollback`` yalnız ``feedback_entries``'teki migrate
  kayıtları (``migrated_by`` marker) siler. Legacy koleksiyonlara DOKUNMAZ.
* PII loglanmaz: yalnız sayım/aggregate loglanır.

Kullanım
--------
    # Varsayılan: dry-run, ne yazılacağını raporla
    python -m scripts.migrate_feedback_unified

    # Tek tenant dry-run
    python -m scripts.migrate_feedback_unified --tenant-id <tid>

    # Uygula (ALLOW_FEEDBACK_MIGRATION=true gerekir)
    ALLOW_FEEDBACK_MIGRATION=true python -m scripts.migrate_feedback_unified --apply

    # Geri al (dry-run önce; sonra --apply)
    ALLOW_FEEDBACK_MIGRATION=true python -m scripts.migrate_feedback_unified --rollback --apply

Operasyonel metrik
------------------
Her çalıştırma ``feedback_migration_runs`` koleksiyonuna PII'siz bir özet doc
yazar (mod, kaynak başına bulunan/yazılan sayıları, tenant kapsamı).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.tenant_db import get_system_db  # noqa: E402
from modules.guest_journey import feedback_reporting_service as fr  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("migrate_feedback_unified")

UNIFIED_COLLECTION = "feedback_entries"
RUN_LOG_COLLECTION = "feedback_migration_runs"
MIGRATION_MARKER = "feedback_unified_migration"
ALLOW_ENV = "ALLOW_FEEDBACK_MIGRATION"


def _dedup_key(tenant_id: str, source: str, source_id: str | None) -> str:
    return f"{tenant_id}|{source}|{source_id}"


async def _ensure_unique_index(db) -> None:
    """Idempotency zırhı: dedup_key üzerinde unique index. Mevcut mükerrerler
    varsa build E11000'e düşebilir; bu durumda upsert mantığı yine çift sayımı
    engeller (find-by-key), index yokken de güvenli kalırız."""
    try:
        await db[UNIFIED_COLLECTION].create_index("dedup_key", unique=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "feedback_entries.dedup_key unique index kurulamadı (devam): %s",
            type(exc).__name__,
        )


async def _all_tenant_ids(db) -> list[str]:
    """Üç kaynak koleksiyondaki tüm tenant_id'leri topla (cross-tenant tarama)."""
    tenant_ids: set[str] = set()
    for coll_name in fr.SOURCE_COLLECTIONS.values():
        for tid in await db[coll_name].distinct("tenant_id"):
            if tid:
                tenant_ids.add(tid)
    return sorted(tenant_ids)


async def _migrate_tenant(db, tenant_id: str, apply: bool) -> dict:
    """Tek tenant için üç kaynağı kanonik koleksiyona materyalize et.

    Idempotent: var olan dedup_key atlanır; yeni kayıt $setOnInsert ile yazılır.
    """
    now = datetime.now(UTC).isoformat()
    per_source: dict[str, dict] = {}

    for source, coll_name in fr.SOURCE_COLLECTIONS.items():
        found = 0
        written = 0
        skipped = 0
        # Kaynak tüm kayıtlar tek tek (streaming) işlenir; bellek doc-başına
        # sınırlıdır. Yapay tavan YOK → büyük tenant'larda kayıt atlanmaz.
        # Idempotency dedup_key upsert ile sağlanır.
        cursor = db[coll_name].find({"tenant_id": tenant_id})
        async for doc in cursor:
            found += 1
            source_id = doc.get("id")
            if not source_id:
                # Kararlı dedup anahtarı yoksa atla (çift sayım riskini önler).
                skipped += 1
                continue
            canonical = fr.normalize(source, doc)
            key = _dedup_key(tenant_id, source, source_id)
            canonical["dedup_key"] = key
            canonical["migrated_by"] = MIGRATION_MARKER
            canonical["migrated_at"] = now

            if apply:
                res = await db[UNIFIED_COLLECTION].update_one(
                    {"dedup_key": key},
                    {"$setOnInsert": canonical},
                    upsert=True,
                )
                if res.upserted_id is not None:
                    written += 1
                else:
                    skipped += 1
            else:
                exists = await db[UNIFIED_COLLECTION].find_one(
                    {"dedup_key": key}, {"_id": 1}
                )
                if exists:
                    skipped += 1
                else:
                    written += 1

        per_source[source] = {
            "found": found,
            "written": written,
            "skipped": skipped,
        }
        logger.info(
            "tenant=%s source=%s found=%d written=%d skipped=%d (mode=%s)",
            tenant_id, source, found, written, skipped,
            "apply" if apply else "dry-run",
        )

    return per_source


async def _rollback_tenant(db, tenant_id: str, apply: bool) -> int:
    """feedback_entries'teki bu tenant'a ait migrate kayıtları sil."""
    flt = {"tenant_id": tenant_id, "migrated_by": MIGRATION_MARKER}
    count = await db[UNIFIED_COLLECTION].count_documents(flt)
    if apply and count:
        res = await db[UNIFIED_COLLECTION].delete_many(flt)
        logger.info("tenant=%s rollback deleted=%d", tenant_id, res.deleted_count)
        return res.deleted_count
    logger.info(
        "tenant=%s rollback candidate=%d (mode=%s)",
        tenant_id, count, "apply" if apply else "dry-run",
    )
    return count


async def run(args: argparse.Namespace) -> int:
    apply = bool(args.apply)
    rollback = bool(args.rollback)

    # Fail-closed: herhangi bir yazım için açık env opt-in şart.
    if apply and os.environ.get(ALLOW_ENV, "").lower() != "true":
        logger.error(
            "--apply için %s=true ZORUNLU (fail-closed). Yazım yapılmadı.",
            ALLOW_ENV,
        )
        return 2

    db = get_system_db()

    if apply and not rollback:
        await _ensure_unique_index(db)

    if args.tenant_id:
        tenant_ids = [args.tenant_id]
    else:
        tenant_ids = await _all_tenant_ids(db)
    logger.info(
        "kapsam: %d tenant (mode=%s%s)",
        len(tenant_ids),
        "rollback" if rollback else "migrate",
        ", apply" if apply else ", dry-run",
    )

    summary: dict = {
        "id": f"feedback_mig_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
        "started_at": datetime.now(UTC).isoformat(),
        "mode": "rollback" if rollback else "migrate",
        "applied": apply,
        "tenant_count": len(tenant_ids),
        "tenants": {},
    }

    for tid in tenant_ids:
        if rollback:
            summary["tenants"][tid] = {
                "rollback": await _rollback_tenant(db, tid, apply)
            }
        else:
            summary["tenants"][tid] = await _migrate_tenant(db, tid, apply)

    summary["finished_at"] = datetime.now(UTC).isoformat()

    # PII'siz operasyonel metrik. Dry-run da kaydedilir (gözlemlenebilirlik).
    try:
        await db[RUN_LOG_COLLECTION].insert_one(dict(summary))
    except Exception as exc:  # noqa: BLE001
        logger.warning("run-log yazılamadı (devam): %s", type(exc).__name__)

    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Birleşik geri bildirim modeli backfill migration (geri alınabilir, fail-closed)."
    )
    p.add_argument("--apply", action="store_true",
                   help=f"Gerçek yazım/silme yap (varsayılan dry-run; {ALLOW_ENV}=true gerekir).")
    p.add_argument("--rollback", action="store_true",
                   help="Migrate edilen feedback_entries kayıtlarını sil (legacy'ye dokunmaz).")
    p.add_argument("--tenant-id", default=None,
                   help="Yalnız bu tenant'ı işle (verilmezse tüm tenant'lar).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
