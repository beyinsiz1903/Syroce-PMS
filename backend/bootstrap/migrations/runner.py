"""Versiyonlu migration runner — sıralı uygulama + rollback + fail-closed.

Davranış:
  - Bekleyen migration'ları versiyon sırasına göre uygular; ledger'da
    ``applied`` olanları atlar (idempotent — ikinci açılışta tekrar koşmaz).
  - Her migration için per-migration timeout uygulanır.
  - ``up()`` hata/timeout verirse aynı migration'ın ``down()`` adımı çağrılır,
    ledger'a ``rolled_back`` (down başarılı) veya ``failed`` (down da hata)
    yazılır ve ``MigrationError`` fırlatılır → fail-closed sinyali.
  - Advisory lock sayesinde aynı anda yalnızca bir instance koşar; lock
    alınamazsa runner çift koşmadan atlar.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from .base import (
    LEDGER_COLLECTION,
    STATUS_APPLIED,
    STATUS_FAILED,
    STATUS_ROLLED_BACK,
    Migration,
)
from .lock import acquire_lock, lock_status, release_lock, renew_lock
from .registry import discover_migrations

logger = logging.getLogger("bootstrap.migrations.runner")

# Migration başına timeout (saniye). Uzun indeks basımları için migration'ın
# kendisi background=True kullanabilir; bu sınır yine de boot'u korur.
DEFAULT_MIGRATION_TIMEOUT = float(os.getenv("MIGRATION_TIMEOUT_SECONDS", "30"))
# Advisory lock lease süresi (saniye). Sahip çökerse bu süre sonunda devralınır.
DEFAULT_LOCK_LEASE = float(os.getenv("MIGRATION_LOCK_LEASE_SECONDS", "300"))


class MigrationError(RuntimeError):
    """Kritik migration başarısızlığı — fail-closed sinyali."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _applied_versions(db) -> set[str]:
    """Ledger'da ``applied`` durumundaki versiyonları döndürür."""
    out: set[str] = set()
    cursor = db[LEDGER_COLLECTION].find(
        {"status": STATUS_APPLIED}, {"_id": 0, "version": 1},
    )
    async for doc in cursor:
        v = doc.get("version")
        if v:
            out.add(v)
    return out


async def _record(db, migration: Migration, *, status: str,
                  duration_ms: int, error: str | None) -> None:
    """Ledger'a migration sonucunu upsert eder (versiyona göre)."""
    now = _now_iso()
    doc = {
        "version": migration.version,
        "description": migration.description,
        "checksum": migration.checksum(),
        "status": status,
        "duration_ms": duration_ms,
        "error": error,
        "updated_at": now,
    }
    if status == STATUS_APPLIED:
        doc["applied_at"] = now
    await db[LEDGER_COLLECTION].update_one(
        {"version": migration.version},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


async def _apply_one(db, migration: Migration, timeout: float) -> None:
    """Tek bir migration'ı uygular. Hata/timeout → down() + ledger + raise."""
    import asyncio

    start = time.monotonic()
    try:
        await asyncio.wait_for(migration.up(db), timeout=timeout)
    except BaseException as up_err:  # noqa: BLE001 - timeout dahil her hatayı yakala
        is_timeout = isinstance(up_err, asyncio.TimeoutError)
        up_msg = "timeout" if is_timeout else f"{type(up_err).__name__}: {up_err}"
        logger.error(
            "MIGRATION_UP_FAILED version=%s — rollback başlatılıyor: %s",
            migration.version, up_msg,
        )
        # ── Rollback: aynı migration'ın down() adımını çağır ──
        try:
            await asyncio.wait_for(migration.down(db), timeout=timeout)
            status = STATUS_ROLLED_BACK
            err_text = f"up failed ({up_msg}); rolled back"
            logger.error(
                "MIGRATION_ROLLED_BACK version=%s — kısmi değişiklik geri alındı",
                migration.version,
            )
        except BaseException as down_err:  # noqa: BLE001
            status = STATUS_FAILED
            err_text = (
                f"up failed ({up_msg}); down ALSO failed "
                f"({type(down_err).__name__}: {down_err})"
            )
            logger.critical(
                "MIGRATION_DOWN_FAILED version=%s — geri alma BAŞARISIZ, "
                "şema tutarsız olabilir: %s", migration.version, down_err,
            )
        duration_ms = int((time.monotonic() - start) * 1000)
        await _record(db, migration, status=status,
                      duration_ms=duration_ms, error=err_text)
        raise MigrationError(
            f"Migration {migration.version} başarısız ({status}): {err_text}"
        ) from up_err

    duration_ms = int((time.monotonic() - start) * 1000)
    await _record(db, migration, status=STATUS_APPLIED,
                  duration_ms=duration_ms, error=None)
    logger.info(
        "MIGRATION_APPLIED version=%s (%d ms)", migration.version, duration_ms,
    )


async def run_migrations(
    db,
    *,
    migrations: list[Migration] | None = None,
    per_migration_timeout: float = DEFAULT_MIGRATION_TIMEOUT,
    lease_seconds: float = DEFAULT_LOCK_LEASE,
) -> dict[str, Any]:
    """Bekleyen migration'ları sıralı uygular. Hata → ``MigrationError``.

    Idempotent: ``applied`` olanları atlar. Advisory lock altında tek-koşma.
    Lock alınamazsa (başka instance koşuyor) çift koşmadan atlar.
    """
    all_migrations = migrations if migrations is not None else discover_migrations()
    all_migrations = sorted(all_migrations, key=lambda m: m.version)

    # ── Hızlı yol: bekleyen yoksa kilit almadan çık (boot hızı) ──
    applied = await _applied_versions(db)
    pending = [m for m in all_migrations if m.version not in applied]
    if not pending:
        logger.info(
            "DB migration: bekleyen yok (%d migration zaten uygulanmış)",
            len(all_migrations),
        )
        return {
            "status": "up_to_date",
            "applied": [], "skipped": sorted(applied),
            "total": len(all_migrations),
            "summary": f"0 uygulandı, {len(applied)} zaten uygulanmış",
        }

    owner = str(uuid.uuid4())
    got_lock = await acquire_lock(db, owner, lease_seconds)
    if not got_lock:
        logger.warning(
            "DB migration: advisory lock alınamadı (başka instance koşuyor) — "
            "çift koşma engellendi, bu instance atlıyor",
        )
        return {
            "status": "skipped_locked",
            "applied": [], "skipped": [],
            "total": len(all_migrations),
            "summary": "advisory lock başka instance'ta — atlandı",
        }

    newly_applied: list[str] = []
    try:
        # Kilit altında ledger'ı tekrar oku (TOCTOU'ya karşı).
        applied = await _applied_versions(db)
        for migration in all_migrations:
            if migration.version in applied:
                continue
            await _apply_one(db, migration, per_migration_timeout)
            newly_applied.append(migration.version)
            # Uzun zincirde lease'i tazele ki sahip çökmediği sürece devralınmasın.
            await renew_lock(db, owner, lease_seconds)
    finally:
        await release_lock(db, owner)

    logger.info(
        "DB migration tamamlandı: %d uygulandı (%s)",
        len(newly_applied), ", ".join(newly_applied) or "-",
    )
    return {
        "status": "applied",
        "applied": newly_applied,
        "skipped": sorted(applied),
        "total": len(all_migrations),
        "summary": f"{len(newly_applied)} uygulandı, {len(applied)} zaten uygulanmış",
    }


async def get_migration_status(db) -> dict[str, Any]:
    """Ops görünürlüğü: uygulanan/bekleyen versiyonlar, son hata, kilit durumu."""
    all_migrations = sorted(discover_migrations(), key=lambda m: m.version)
    known_versions = [m.version for m in all_migrations]

    ledger: list[dict[str, Any]] = []
    cursor = db[LEDGER_COLLECTION].find({}, {"_id": 0})
    async for doc in cursor:
        ledger.append(doc)
    ledger.sort(key=lambda d: d.get("version", ""))

    by_version = {d.get("version"): d for d in ledger}
    applied = [v for v in known_versions if by_version.get(v, {}).get("status") == STATUS_APPLIED]
    pending = [v for v in known_versions if by_version.get(v, {}).get("status") != STATUS_APPLIED]
    failed = [
        {"version": d.get("version"), "status": d.get("status"), "error": d.get("error")}
        for d in ledger
        if d.get("status") in (STATUS_FAILED, STATUS_ROLLED_BACK)
    ]
    last_error = None
    for d in sorted(ledger, key=lambda x: x.get("updated_at", ""), reverse=True):
        if d.get("error"):
            last_error = {
                "version": d.get("version"),
                "status": d.get("status"),
                "error": d.get("error"),
                "updated_at": d.get("updated_at"),
            }
            break

    lock = await lock_status(db)
    return {
        "all_clear": (not pending) and (not failed),
        "known_versions": known_versions,
        "applied": applied,
        "pending": pending,
        "failed": failed,
        "last_error": last_error,
        "lock": lock,
        "ledger": ledger,
    }
