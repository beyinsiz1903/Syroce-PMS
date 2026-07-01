"""Folio bakiye mutabakat backstop scheduler (Task #390).

POS folyo kalemleri Outbox/Compensation ("B") yolu ile ASENKRON uygulanır;
bu nedenle nadir de olsa ``folio.balance`` (cache) ile otorite ledger toplamı
(``folio_charges - payments``) arasında sapma birikebilir. Bu worker periyodik
olarak (varsayılan 6 saat) açık folyosu olan her tenant için sapmayı tarar.

Doktrin (cleanup-script ile aynı):
- dry-run DEFAULT: yalnızca raporlar + ``folio_balance_recon_scans`` metric
  satırı yazar; mutasyon yapmaz.
- Apply yalnızca ``FOLIO_RECON_ALLOW_APPLY=true`` ile (fail-closed) ve pilot
  tenant'a asla dokunmaz (pilot_drift=0). Apply modunda bakiyeyi otorite
  toplamdan recompute eder.
- B sağlıklı ise rutin olarak found_total=0 döner; sürekli sapma B'de bir
  regresyon sinyalidir.

Devre dışı: ``FOLIO_RECON_INTERVAL_SECONDS=0``.
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = int(os.environ.get("FOLIO_RECON_INTERVAL_SECONDS", "21600"))  # 6 saat
_started = False


def _apply_enabled() -> bool:
    return os.environ.get("FOLIO_RECON_ALLOW_APPLY", "").lower() == "true"


async def _tick() -> None:
    """Tek tarama: açık folyosu olan her tenant için mutabakat."""
    from scripts.reconcile_folio_balances import (
        DEFAULT_GRACE_MINUTES,
        list_open_folio_tenants,
        reconcile_tenant,
    )

    do_apply = _apply_enabled()
    try:
        tenants = await list_open_folio_tenants()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[folio-recon] tenant listesi alınamadı: %s", exc)
        return
    if not tenants:
        return

    total_drift = 0
    total_repaired = 0
    for tid in tenants:
        try:
            summary = await reconcile_tenant(tid, do_apply, DEFAULT_GRACE_MINUTES)
            total_drift += summary["found_total"]
            total_repaired += summary["repaired"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[folio-recon] tenant=%s mutabakat hatası: %s", tid, exc)
    if total_drift:
        logger.warning("[folio-recon] tick drift=%d repaired=%d mode=%s tenants=%d", total_drift, total_repaired, "apply" if do_apply else "dry_run", len(tenants))


async def _loop(interval_seconds: int) -> None:
    logger.info("[folio-recon] loop started interval=%ss apply=%s", interval_seconds, _apply_enabled())
    # Boot fazında ağır iş yapmayalım — diğer index/init işleri otursun.
    await asyncio.sleep(90)
    while True:
        try:
            await _tick()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[folio-recon] tick error: %s", exc)
        await asyncio.sleep(interval_seconds)


def start() -> bool:
    """Bootstrap çağrısı. False = devre dışı."""
    global _started
    if _started:
        return True
    if DEFAULT_INTERVAL_SECONDS <= 0:
        logger.info("[folio-recon] disabled via env (interval=0)")
        return False
    asyncio.create_task(_loop(DEFAULT_INTERVAL_SECONDS), name="folio-recon-scheduler")
    _started = True
    return True
