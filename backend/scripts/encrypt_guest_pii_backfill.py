"""Idempotent re-encryption backfill for plaintext guest PII (KVKK at-rest).

Background
----------
The systemic guest-PII encryption patch routes every guest INSERT/UPDATE path
through ``security.guest_write`` so new/changed guest documents are encrypted at
rest (``email`` / ``phone`` / ``id_number`` / ``passport_number`` / ... become
AES-256-GCM envelopes plus a deterministic ``_hash_<field>`` blind-index token)
and every read path is dual-read (``_hash_`` exact match OR legacy plaintext).

Dual-read keeps already-stored *plaintext* rows readable, but those rows stay
unencrypted on disk until they are rewritten. This script is the one-shot (or
periodic) backfill that finds and re-encrypts that legacy plaintext in place.

Why a FULL scan (not ``_enc_version``-missing)
----------------------------------------------
``field_encryption.migrate_collection`` only targets documents that lack
``_enc_version``. That misses a partially-migrated doc that already carries
``_enc_version: 1`` for one field but still has a *different* PII field in
plaintext (e.g. a field that was added to ``ENCRYPTED_FIELDS`` after the doc was
first encrypted). This backfill scans EVERY guest document and re-encrypts any
configured field that is still plaintext, so it converges regardless of history.

Safety contract
---------------
* Default is **dry-run**: the script only lists what *would* be encrypted and
  writes nothing.
* ``--apply`` requires ``ALLOW_GUEST_PII_BACKFILL=true`` (fail-closed). The
  destructive path is opt-in twice (CLI flag + env), mirroring the pilot
  residue sweep.
* ``--tenant-id`` optionally scopes the scan to a single tenant; omitted means
  ALL tenants (the backfill must reach every plaintext row, pilot included —
  that is the whole point — so this is an operator-run tool, not an automated
  agent action).
* Race-safe writes: each ``update_one`` pins the changed field(s) to their
  ORIGINAL plaintext value (``{"_id": ..., "email": "<orig>", ...}``). If a
  concurrent writer changed/encrypted the field between scan and apply,
  ``modified_count == 0`` and the doc is skipped + reported instead of being
  clobbered. The next run picks it up.
* Idempotent: a fully-encrypted document has no plaintext PII, so it is never a
  candidate. Re-running after a successful apply finds zero candidates.
* Names are intentionally left untouched: ``name`` / ``first_name`` /
  ``last_name`` are NOT encrypted (plaintext for the ``_lower`` prefix and
  ``_ng_name`` trigram search companions). This tool only rewrites the
  configured PII fields + their ``_hash_`` tokens + the ``_enc_version`` /
  ``_encrypted_at`` markers, so it never drops the name search companions.

Usage
-----
    # Default: dry-run, list plaintext-PII candidates, no writes
    python -m scripts.encrypt_guest_pii_backfill

    # Scope to one tenant (dry-run)
    python -m scripts.encrypt_guest_pii_backfill --tenant-id <TID>

    # Apply (requires ALLOW_GUEST_PII_BACKFILL=true)
    ALLOW_GUEST_PII_BACKFILL=true python -m scripts.encrypt_guest_pii_backfill --apply

Operational metric
------------------
Every run inserts a summary doc into ``guest_pii_backfill_scans`` (scanned_at,
tenant scope, mode, totals, per-field counts, applied counts, sample ids). A
cron/alert can poll it: any dry-run row with ``candidates_found > 0`` is an
actionable signal that legacy plaintext PII still exists at rest.

Exit codes
----------
* dry-run: ``1`` when plaintext-PII candidates exist (cron/CI alert), else ``0``.
* apply:   ``1`` when any candidate could not be encrypted (race-skip or error)
           so cron knows to re-run, else ``0``.
* ``2`` on a fail-closed guard violation (``--apply`` without the env opt-in).
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

from core.database import db  # noqa: E402
from security.field_encryption import (  # noqa: E402
    ENCRYPTED_FIELDS,
    get_field_encryption_service,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("encrypt_guest_pii_backfill")

_GUESTS = "guests"

# Single source of truth: derive the field list + searchable set from the
# canonical ENCRYPTED_FIELDS config so this stays in lock-step with the
# write/read paths (adding a new guest PII field there auto-extends the
# backfill).
_GUEST_FIELD_CONFIGS = ENCRYPTED_FIELDS.get(_GUESTS, [])
GUEST_PII_FIELDS: tuple[str, ...] = tuple(f["field"] for f in _GUEST_FIELD_CONFIGS)
SEARCHABLE_FIELDS: frozenset[str] = frozenset(f["field"] for f in _GUEST_FIELD_CONFIGS if f.get("searchable"))


def _looks_encrypted(value: object) -> bool:
    """True if a value is already an AES envelope (matches the crypto engine)."""
    return isinstance(value, str) and (value.startswith("SYR1:") or value.startswith("aes256gcm:"))


def _plaintext_pii(doc: dict) -> dict[str, str]:
    """Return ``{field: plaintext_value}`` for every configured PII field that
    is a non-empty plaintext string (i.e. still needs encrypting)."""
    out: dict[str, str] = {}
    for field in GUEST_PII_FIELDS:
        value = doc.get(field)
        if isinstance(value, str) and value and not _looks_encrypted(value):
            out[field] = value
    return out


async def scan(tenant_id: str | None) -> dict:
    """Stream every (optionally tenant-scoped) guest and collect candidates.

    A candidate is the minimal record needed to encrypt it later without a
    re-read: its ``_id`` (race-pin target), public ``id`` (reporting) and the
    map of plaintext PII fields. Projecting only ``_id`` / ``id`` / the PII
    fields keeps memory bounded to the plaintext rows.
    """
    query: dict = {}
    if tenant_id:
        query["tenant_id"] = tenant_id

    projection = {"_id": 1, "id": 1}
    for field in GUEST_PII_FIELDS:
        projection[field] = 1

    total_scanned = 0
    candidates: list[dict] = []
    per_field: dict[str, int] = dict.fromkeys(GUEST_PII_FIELDS, 0)

    cursor = db[_GUESTS].find(query, projection).batch_size(500)
    async for doc in cursor:
        total_scanned += 1
        pii = _plaintext_pii(doc)
        if not pii:
            continue
        for field in pii:
            per_field[field] += 1
        candidates.append({"_id": doc["_id"], "id": doc.get("id"), "pii": pii})

    return {
        "total_scanned": total_scanned,
        "candidates": candidates,
        "per_field": {f: c for f, c in per_field.items() if c},
    }


async def apply(candidates: list[dict]) -> dict:
    """Encrypt each candidate in place with a race-pinned ``update_one``.

    For every plaintext field: write the AES envelope + (for searchable fields)
    the deterministic ``_hash_<field>`` blind-index token, plus the
    ``_enc_version`` / ``_encrypted_at`` markers. The update filter pins each
    field to its original plaintext, so a concurrent writer that already changed
    the value yields ``modified_count == 0`` (skipped, not clobbered).
    """
    svc = get_field_encryption_service()
    now_iso = datetime.now(UTC).isoformat()
    encrypted = 0
    skipped = 0
    errors = 0

    for cand in candidates:
        pii: dict[str, str] = cand["pii"]
        set_fields: dict = {}
        pin: dict = {"_id": cand["_id"]}
        for field, orig in pii.items():
            set_fields[field] = svc.encrypt_value(orig)
            if field in SEARCHABLE_FIELDS:
                set_fields[f"_hash_{field}"] = svc.compute_search_hash(orig)
            # Race-pin: only rewrite while the field still holds the exact
            # plaintext we read during the scan.
            pin[field] = orig
        set_fields["_enc_version"] = 1
        set_fields["_encrypted_at"] = now_iso

        try:
            res = await db[_GUESTS].update_one(pin, {"$set": set_fields})
            if res.modified_count == 1:
                encrypted += 1
            else:
                # modified_count==0: doc changed/encrypted concurrently or was
                # removed between scan and apply. Safe to skip; next run reconciles.
                skipped += 1
        except Exception as e:
            errors += 1
            logger.error("[guest-pii-backfill] update failed id=%s: %s", cand.get("id"), e)

    return {"encrypted": encrypted, "skipped": skipped, "errors": errors}


async def record_scan(summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    try:
        await db.guest_pii_backfill_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover — best-effort metric
        logger.warning("[guest-pii-backfill] metric insert failed: %s", e)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Guest PII plaintext re-encryption backfill (KVKK at-rest).")
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Yalnızca bu tenant'ı tara. Verilmezse TÜM tenant'lar taranır.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Bulunan plaintext PII'yi şifrele. Aksi halde dry-run (yazma yok).",
    )
    args = parser.parse_args()

    if not GUEST_PII_FIELDS:
        logger.error("guests koleksiyonu için ENCRYPTED_FIELDS tanımlı değil — yapılacak iş yok.")
        return 2

    if args.apply and os.environ.get("ALLOW_GUEST_PII_BACKFILL", "").lower() != "true":
        logger.error("--apply için ALLOW_GUEST_PII_BACKFILL=true gerekli — fail-closed.")
        return 2

    scope = args.tenant_id or "ALL"
    logger.info(
        "[guest-pii-backfill] tenant=%s mode=%s",
        scope,
        "APPLY" if args.apply else "DRY-RUN",
    )

    found = await scan(args.tenant_id)
    candidates = found["candidates"]
    candidates_found = len(candidates)

    applied = {"encrypted": 0, "skipped": 0, "errors": 0}
    if args.apply and candidates_found > 0:
        applied = await apply(candidates)

    summary = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "tenant_id": scope,
        "mode": "apply" if args.apply else "dry_run",
        "total_scanned": found["total_scanned"],
        "candidates_found": candidates_found,
        "per_field": found["per_field"],
        "applied": applied,
        "sample_ids": [c.get("id") for c in candidates[:10]],
    }
    await record_scan(summary)

    print("=" * 60)
    print(f"Guest PII backfill ({'APPLY' if args.apply else 'DRY-RUN'}) tenant={scope}")
    print("=" * 60)
    print(f"  {'guests scanned':22s} -> {found['total_scanned']}")
    print(f"  {'plaintext candidates':22s} -> {candidates_found}")
    for field, count in found["per_field"].items():
        print(f"    - {field:18s} -> {count}")
    if args.apply:
        print("  -- applied --")
        for k, v in applied.items():
            print(f"  {k:22s} -> {v}")
    print(f"  metric row             -> guest_pii_backfill_scans @ {summary['scanned_at']}")

    if not args.apply:
        if candidates_found > 0:
            logger.warning(
                "[guest-pii-backfill] %d misafir kaydında plaintext PII bulundu (per_field=%s) — şifrelemek için ALLOW_GUEST_PII_BACKFILL=true ile --apply koştur.",
                candidates_found,
                found["per_field"],
            )
            return 1
        logger.info("[guest-pii-backfill] plaintext PII=0, at-rest temiz.")
        return 0

    # apply mode
    if applied["skipped"] > 0 or applied["errors"] > 0:
        logger.warning(
            "[guest-pii-backfill] apply tamamlandı ancak %d skip / %d hata kaldı — tekrar koştur.",
            applied["skipped"],
            applied["errors"],
        )
        return 1
    logger.info(
        "[guest-pii-backfill] apply tamamlandı: %d kayıt şifrelendi.",
        applied["encrypted"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
