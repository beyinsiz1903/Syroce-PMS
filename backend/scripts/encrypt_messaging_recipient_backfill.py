"""Idempotent re-encryption backfill for plaintext messaging recipient PII.

Background
----------
``messaging_consents.recipient`` and ``messaging_delivery_logs.recipient``
historically stored guest phone/e-mail as **plaintext** at rest. The messaging
write paths now seal that value through the existing field-encryption service
(``recipient_enc`` AES-256-GCM envelope + ``recipient_hash`` HMAC blind-index)
and every read path is dual-read (decrypt ``recipient_enc`` else fall back to a
legacy plaintext ``recipient``).

Dual-read keeps already-stored plaintext rows readable, but those rows stay
unencrypted on disk until they are rewritten. This script is the one-shot (or
periodic) backfill that finds and seals that legacy plaintext in place.

Note on the consent collection
------------------------------
``messaging_consents`` is shared by two unrelated document shapes: the legacy
recipient-keyed consent (this script's target, carrying a ``recipient`` field)
and the platform_scaling gateway's ``guest_id``-keyed consent (carrying only
``opted_out_channels`` — NO recipient). The candidate filter keys on a non-empty
plaintext ``recipient`` string, so the ``guest_id`` shape is never touched.

Safety contract
---------------
* Default is **dry-run**: lists what *would* be sealed, writes nothing.
* ``--apply`` requires ``ALLOW_MESSAGING_RECIPIENT_BACKFILL=true`` (fail-closed).
  The destructive path is opt-in twice (CLI flag + env).
* ``--tenant-id`` optionally scopes the scan to a single tenant; omitted means
  ALL tenants (operator-run tool, not an automated agent action).
* Race-safe writes: each ``update_one`` pins ``recipient`` to its ORIGINAL
  plaintext value. A concurrent writer that changed/sealed it yields
  ``modified_count == 0`` (skipped, not clobbered); the next run reconciles.
* Idempotent: a sealed document has its ``recipient`` removed (replaced by
  ``recipient_enc`` + ``recipient_hash``), so it is never a candidate again.

Usage
-----
    # Default: dry-run, list plaintext-recipient candidates, no writes
    python -m scripts.encrypt_messaging_recipient_backfill

    # Scope to one tenant (dry-run)
    python -m scripts.encrypt_messaging_recipient_backfill --tenant-id <TID>

    # Apply (requires ALLOW_MESSAGING_RECIPIENT_BACKFILL=true)
    ALLOW_MESSAGING_RECIPIENT_BACKFILL=true \
        python -m scripts.encrypt_messaging_recipient_backfill --apply

Operational metric
------------------
Every run inserts a summary doc into ``messaging_recipient_backfill_scans``
(scanned_at, tenant scope, mode, per-collection totals, applied counts, sample
ids). A cron/alert can poll it: any dry-run row with ``candidates_found > 0`` is
an actionable signal that legacy plaintext recipient PII still exists at rest.

Exit codes
----------
* dry-run: ``1`` when plaintext-recipient candidates exist, else ``0``.
* apply:   ``1`` when any candidate could not be sealed (race-skip or error),
           else ``0``.
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
from security.field_encryption import get_field_encryption_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("encrypt_messaging_recipient_backfill")

# Collections carrying a legacy plaintext ``recipient`` field.
_COLLECTIONS: tuple[str, ...] = (
    "messaging_consents",
    "messaging_delivery_logs",
)


def _looks_encrypted(value: object) -> bool:
    """True if a value is already an AES envelope (matches the crypto engine)."""
    return isinstance(value, str) and (value.startswith("SYR1:") or value.startswith("aes256gcm:"))


async def scan(collection: str, tenant_id: str | None) -> dict:
    """Stream a collection and collect rows with a plaintext ``recipient``.

    A candidate is the minimal record needed to seal it later without a re-read:
    its ``_id`` (race-pin target), public ``id`` (reporting) and the plaintext
    recipient value.
    """
    query: dict = {"recipient": {"$type": "string", "$ne": ""}}
    if tenant_id:
        query["tenant_id"] = tenant_id

    total_scanned = 0
    candidates: list[dict] = []

    cursor = db[collection].find(query, {"_id": 1, "id": 1, "recipient": 1}).batch_size(500)
    async for doc in cursor:
        total_scanned += 1
        recipient = doc.get("recipient")
        if not isinstance(recipient, str) or not recipient:
            continue
        if _looks_encrypted(recipient):
            continue
        candidates.append({"_id": doc["_id"], "id": doc.get("id"), "recipient": recipient})

    return {"total_scanned": total_scanned, "candidates": candidates}


async def apply(collection: str, candidates: list[dict]) -> dict:
    """Seal each candidate in place with a race-pinned ``update_one``.

    Writes ``recipient_enc`` (AES envelope) + ``recipient_hash`` (blind-index)
    and ``$unset`` the plaintext ``recipient``. The update filter pins
    ``recipient`` to its original plaintext, so a concurrent writer that already
    changed the value yields ``modified_count == 0`` (skipped, not clobbered).
    """
    svc = get_field_encryption_service()
    sealed = 0
    skipped = 0
    errors = 0

    for cand in candidates:
        recipient: str = cand["recipient"]
        set_fields = {
            "recipient_enc": svc.encrypt_value(recipient),
            "recipient_hash": svc.compute_search_hash(recipient),
        }
        pin = {"_id": cand["_id"], "recipient": recipient}
        try:
            res = await db[collection].update_one(pin, {"$set": set_fields, "$unset": {"recipient": ""}})
            if res.modified_count == 1:
                sealed += 1
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            logger.error(
                "[messaging-recipient-backfill] %s update failed id=%s: %s",
                collection,
                cand.get("id"),
                e,
            )

    return {"sealed": sealed, "skipped": skipped, "errors": errors}


async def record_scan(summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    try:
        await db.messaging_recipient_backfill_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover — best-effort metric
        logger.warning("[messaging-recipient-backfill] metric insert failed: %s", e)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Messaging recipient plaintext sealing backfill (KVKK at-rest).")
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Yalnızca bu tenant'ı tara. Verilmezse TÜM tenant'lar taranır.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Bulunan plaintext recipient'ı şifrele. Aksi halde dry-run (yazma yok).",
    )
    args = parser.parse_args()

    if args.apply and os.environ.get("ALLOW_MESSAGING_RECIPIENT_BACKFILL", "").lower() != "true":
        logger.error("--apply için ALLOW_MESSAGING_RECIPIENT_BACKFILL=true gerekli — fail-closed.")
        return 2

    scope = args.tenant_id or "ALL"
    logger.info(
        "[messaging-recipient-backfill] tenant=%s mode=%s",
        scope,
        "APPLY" if args.apply else "DRY-RUN",
    )

    per_collection: dict[str, dict] = {}
    total_candidates = 0
    total_skipped = 0
    total_errors = 0

    for collection in _COLLECTIONS:
        found = await scan(collection, args.tenant_id)
        candidates = found["candidates"]
        candidates_found = len(candidates)
        total_candidates += candidates_found

        applied = {"sealed": 0, "skipped": 0, "errors": 0}
        if args.apply and candidates_found > 0:
            applied = await apply(collection, candidates)
            total_skipped += applied["skipped"]
            total_errors += applied["errors"]

        per_collection[collection] = {
            "total_scanned": found["total_scanned"],
            "candidates_found": candidates_found,
            "applied": applied,
            "sample_ids": [c.get("id") for c in candidates[:10]],
        }

    summary = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "tenant_id": scope,
        "mode": "apply" if args.apply else "dry_run",
        "candidates_found": total_candidates,
        "per_collection": per_collection,
    }
    await record_scan(summary)

    print("=" * 60)
    print(f"Messaging recipient backfill ({'APPLY' if args.apply else 'DRY-RUN'}) tenant={scope}")
    print("=" * 60)
    for collection, stats in per_collection.items():
        print(f"  [{collection}]")
        print(f"    {'scanned':20s} -> {stats['total_scanned']}")
        print(f"    {'plaintext candidates':20s} -> {stats['candidates_found']}")
        if args.apply:
            for k, v in stats["applied"].items():
                print(f"    {k:20s} -> {v}")
    print(f"  metric row -> messaging_recipient_backfill_scans @ {summary['scanned_at']}")

    if not args.apply:
        if total_candidates > 0:
            logger.warning(
                "[messaging-recipient-backfill] %d kayıtta plaintext recipient bulundu — şifrelemek için ALLOW_MESSAGING_RECIPIENT_BACKFILL=true ile --apply koştur.",
                total_candidates,
            )
            return 1
        logger.info("[messaging-recipient-backfill] plaintext recipient=0, at-rest temiz.")
        return 0

    # apply mode
    if total_skipped > 0 or total_errors > 0:
        logger.warning(
            "[messaging-recipient-backfill] apply tamamlandı ancak %d skip / %d hata kaldı — tekrar koştur.",
            total_skipped,
            total_errors,
        )
        return 1
    logger.info("[messaging-recipient-backfill] apply tamamlandı.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
