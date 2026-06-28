"""Purge legacy auto-generated VAPID keys from `db.web_push_keys`.

Background
----------
Production reads the active VAPID keypair from the ``VAPID_PUBLIC_KEY`` and
``VAPID_PRIVATE_KEY`` environment variables (Replit Secrets). Before that
contract was enforced, the backend would auto-generate a P-256 keypair on
first use and persist it to ``db.web_push_keys`` so subsequent restarts
reused the same identifier. Those records are now obsolete in production
and represent a plaintext private key sitting in MongoDB / backups for no
operational benefit.

This one-shot maintenance script:

  1. Lists every document in ``web_push_keys`` (private material is **never**
     printed — only the public key prefix and metadata).
  2. Deletes documents marked ``auto_generated: true`` (the marker the
     fallback writer in ``backend/domains/guest/messaging/web_push.py``
     stamps on every record it creates).
  3. In ``--mark-only`` mode, re-stamps the marker on any pre-marker record
     so the remaining dev fallback row is unambiguously "developer fallback,
     not a real secret". This mode never deletes anything.

Usage
-----
    # Default: delete ONLY rows already marked auto_generated=true. Anything
    # else is left strictly untouched.
    python -m scripts.cleanup_legacy_web_push_keys

    # Preview without writing.
    python -m scripts.cleanup_legacy_web_push_keys --dry-run

    # Override the auto_generated guard (only if you really know what you
    # are doing — e.g. a manually inserted dev record you also want gone).
    python -m scripts.cleanup_legacy_web_push_keys --force

    # Stamp auto_generated=true on legacy unmarked rows. Mutually exclusive
    # with the destructive modes — use this in dev to surface the fallback
    # row, then run the default mode separately if you want it deleted.
    python -m scripts.cleanup_legacy_web_push_keys --mark-only

Safety
------
- The default mode NEVER touches a row missing ``auto_generated: true``.
  ``--force`` is required to delete unmarked rows.
- ``--mark-only`` is mutually exclusive with ``--force``: marking and
  destructive deletion are never combined in a single run, so a re-stamp
  cannot escalate into an unintended delete.
- Idempotent: re-running after a successful purge is a no-op.
- Never logs the private key material.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow running as a script (python backend/scripts/cleanup_legacy_web_push_keys.py)
# as well as a module (python -m scripts.cleanup_legacy_web_push_keys).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup_legacy_web_push_keys")


def _redact_mongo_url(url: str) -> str:
    """Strip embedded `user:pass@` credentials from a Mongo connection URL.

    Operators occasionally keep credentials inline in MONGO_URL. We must
    never echo those into logs (especially error logs which often end up
    forwarded to aggregators with broader read access).
    """
    try:
        scheme_sep = url.find("://")
        if scheme_sep == -1:
            return url
        scheme = url[: scheme_sep + 3]
        rest = url[scheme_sep + 3 :]
        at_sign = rest.find("@")
        if at_sign == -1:
            return url
        return f"{scheme}***:***@{rest[at_sign + 1 :]}"
    except Exception:
        return "<unprintable mongo url>"


def _safe_summary(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a log-safe view of a `web_push_keys` document.

    The private key material is reduced to a length so we can prove the row
    was inspected without echoing the secret to stdout / log aggregators.
    """
    pub = doc.get("public_key") or ""
    priv = doc.get("private_key") or ""
    return {
        "_id": doc.get("_id"),
        "public_key_prefix": pub[:12] + "…" if pub else None,
        "private_key_len": len(priv) if priv else 0,
        "created_at": doc.get("created_at"),
        "auto_generated": bool(doc.get("auto_generated")),
    }


async def _run(args: argparse.Namespace) -> int:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]

    try:
        await client.admin.command("ping")
    except Exception as exc:
        logger.error("Could not reach MongoDB at %s: %s", _redact_mongo_url(mongo_url), exc)
        return 2

    coll = db.web_push_keys
    # Iterate via cursor instead of a fixed-size to_list — `web_push_keys`
    # should hold at most a handful of rows in practice, but a hard cap
    # would silently hide rows from the operator's view of the cleanup plan.
    docs: list[dict[str, Any]] = []
    async for d in coll.find({}):
        docs.append(d)

    if not docs:
        logger.info("web_push_keys is already empty in db=%s — nothing to clean up.", db_name)
        return 0

    logger.info("Found %d record(s) in db=%s.web_push_keys:", len(docs), db_name)
    for d in docs:
        logger.info("  %s", _safe_summary(d))

    # --mark-only branch: stamp the auto_generated marker on legacy rows
    # that predate the marker contract. NEVER deletes anything. This branch
    # is mutually exclusive with the destructive flow (enforced in argparse)
    # so re-stamping cannot accidentally escalate into a deletion in the
    # same invocation.
    if args.mark_only:
        unmarked = [d for d in docs if not d.get("auto_generated")]
        if not unmarked:
            logger.info("No unmarked records found; auto_generated marker is already present on every row.")
            return 0
        logger.info(
            "Stamping auto_generated=true on %d unmarked record(s) (these predate the fallback marker contract).",
            len(unmarked),
        )
        for d in unmarked:
            if args.dry_run:
                logger.info("  [dry-run] would mark _id=%s", d.get("_id"))
                continue
            await coll.update_one(
                {"_id": d["_id"]},
                {
                    "$set": {
                        "auto_generated": True,
                        "auto_generated_marked_at": datetime.now(UTC).isoformat(),
                    }
                },
            )
            logger.info("  marked _id=%s", d.get("_id"))
        return 0

    # Destructive flow — delete auto_generated rows (or every row with
    # --force). Crucially: we do NOT touch the auto_generated marker on
    # unmarked rows in this flow, so the default mode is safe by
    # construction — a row that arrived without the marker stays put
    # unless the operator opts in with --force.
    if args.force:
        delete_filter: dict[str, Any] = {}
        target_label = "ALL records (--force)"
    else:
        delete_filter = {"auto_generated": True}
        target_label = "records with auto_generated=true"

    if args.dry_run:
        to_delete = await coll.count_documents(delete_filter)
        logger.info(
            "[dry-run] would delete %d %s. Re-run without --dry-run to apply.",
            to_delete,
            target_label,
        )
        return 0

    result = await coll.delete_many(delete_filter)
    logger.info("Deleted %d %s.", result.deleted_count or 0, target_label)

    remaining = await coll.count_documents({})
    if remaining:
        logger.info(
            "%d record(s) remain in web_push_keys (left untouched: missing auto_generated marker).",
            remaining,
        )
        if not args.force:
            logger.info("Use --force to also remove rows missing the auto_generated marker, or --mark-only on a separate run to stamp the marker first.")
    else:
        logger.info("web_push_keys is now empty.")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing to MongoDB.",
    )
    # --force and --mark-only are intentionally mutually exclusive: one
    # escalates the delete blast-radius, the other is purely additive
    # metadata. Allowing both at once would let a re-stamp inflate the
    # count of rows the destructive flow would then sweep away.
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--force",
        action="store_true",
        help="Delete every web_push_keys row, even those missing the auto_generated marker.",
    )
    mode.add_argument(
        "--mark-only",
        action="store_true",
        help="Only re-stamp auto_generated=true on legacy rows; skip the delete step.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
