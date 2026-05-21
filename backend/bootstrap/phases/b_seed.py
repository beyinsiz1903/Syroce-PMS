"""Phase B — Auto-seed + Exely webhook connection ensure."""
import asyncio
import logging
import os
from datetime import UTC, datetime

from core.database import _raw_db

logger = logging.getLogger(__name__)

# Supplies-market ensure bütçesi — bu seeder asla boot'u bloke etmemeli.
# CI/stress cold-start'larda Atlas RTT yüksek olabilir; ensure (find_one +
# count_documents, gerekirse 30+ insert) bütün boot'u tutarsa `/health/ready`
# hiç açılmıyor ve stress suite warm-up loop'u 60 deneme sonrası giveup.
# Bütçe aşılırsa healthy path için sessizce devam, strict mod (prod+override)
# için fail-closed re-raise.
_SUPPLIES_ENSURE_BUDGET_SEC = float(os.environ.get("SUPPLIES_ENSURE_BUDGET_SEC", "20"))


async def phase_b_seed_and_exely_conn(app):
    # Auto-seed demo data
    from infra.production_config import is_production_env
    _seed_override = os.environ.get("ALLOW_AUTO_SEED_IN_PROD", "").lower() in {"1", "true", "yes"}
    if is_production_env() and not _seed_override:
        logger.info("Auto-seed skipped — production mode (set ALLOW_AUTO_SEED_IN_PROD=1 to override)")
    else:
        try:
            from auto_seed import auto_seed_if_empty
            await auto_seed_if_empty(_raw_db)
        except Exception as e:
            logger.warning(f"Auto-seed error: {e}")

    # Ensure supplies-market (Tedarik Pazarı) demo vendor + starter catalogue.
    # Seeder idempotent — yalnız vendor veya katalog eksikse re-run; aksi halde no-op.
    # Geçmiş gotcha: katalog elle temizlendiğinde sekme boş kaldı (Task #257),
    # bu kanca aynı kaybın bir sonraki restart'ta otomatik kapatılmasını sağlar.
    if is_production_env() and not _seed_override:
        logger.info("Supplies market ensure skipped — production mode")
    else:
        # prod + override aktifse operatör seed'i bilinçli istiyor → fail-closed.
        _strict = is_production_env() and _seed_override

        async def _supplies_ensure():
            from modules.supplies_market.repository import (
                products_col as _mp_products,
            )
            from modules.supplies_market.repository import (
                vendors_col as _mp_vendors,
            )
            # EXPECTED_CATALOGUE_COUNT: önceki seed run'u timeout/cancel ile yarıda
            # kesildiyse katalog `0 < count < expected` durumunda kalabilir; sadece
            # `count == 0` kontrolü bu partial-seed durumunu "healthy" sayıp asla
            # onarmaz. Eksik adetle gelirse yeniden idempotent seed tetikleniyor.
            from scripts.seed_supplies_market import EXPECTED_CATALOGUE_COUNT
            _need_seed = False
            _demo_vendor = await _mp_vendors.find_one(
                {"email": "demo-vendor@syroce.com"}, {"_id": 0, "id": 1}
            )
            if not _demo_vendor:
                _need_seed = True
            else:
                _catalogue_count = await _mp_products.count_documents(
                    {"vendor_id": _demo_vendor["id"]}
                )
                if _catalogue_count < EXPECTED_CATALOGUE_COUNT:
                    _need_seed = True
            if _need_seed:
                # Seeder kendi içinde upsert mantığı taşıyor; tam dolu durumda
                # zaten tetiklemiyoruz, kısmen dolu / boş durumda güvenle koşar.
                from scripts.seed_supplies_market import main as _seed_market
                await _seed_market()
                logger.info("Supplies market seed ensured on startup (vendor/catalogue was missing)")
            else:
                logger.info("Supplies market ensure no-op — vendor + catalogue healthy")

        try:
            # Bütçeli koşum: cold-start'ta Atlas yavaşsa boot'u bloke etmesin.
            # Strict modda (prod+override) timeout ya da hata → fail-closed.
            # Dev/CI modunda warning + devam, ensure best-effort.
            await asyncio.wait_for(_supplies_ensure(), timeout=_SUPPLIES_ENSURE_BUDGET_SEC)
        except asyncio.TimeoutError:
            logger.warning(
                f"Supplies market ensure exceeded {_SUPPLIES_ENSURE_BUDGET_SEC}s budget — "
                "skipping to keep boot moving (set SUPPLIES_ENSURE_BUDGET_SEC to tune)"
            )
            if _strict:
                raise
        except Exception as e:
            logger.warning(f"Supplies market ensure error: {e}")
            if _strict:
                # Operatör prod'da seed'i ALLOW_AUTO_SEED_IN_PROD=1 ile istedi;
                # sessizce devam etmek yerine boot'u kapatıyoruz (fail-closed).
                raise

    # Ensure Exely webhook test connection exists
    try:
        existing = await _raw_db.exely_connections.find_one({"hotel_code": "501694"}, {"_id": 1})
        if not existing:
            tenant = await _raw_db.tenants.find_one({}, {"_id": 0, "id": 1})
            tid = tenant["id"] if tenant else "demo"
            import uuid
            await _raw_db.exely_connections.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "hotel_code": "501694",
                "credentials_ref": "",
                "endpoint_url": "",
                "property_name": "Exely Webhook Connection",
                "auto_sync_reservations": True,
                "sync_interval_minutes": 15,
                "mode": "sandbox",
                "currency": "TRY",
                "is_active": True,
                "room_types": [],
                "rate_plans": [],
                "connected_at": datetime.now(UTC).isoformat(),
                "last_sync_at": None,
                "created_by": "startup_ensure",
            })
            logger.info("Exely webhook connection (501694) ensured on startup")
    except Exception as e:
        logger.warning(f"Exely connection ensure error: {e}")
