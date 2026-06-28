"""
Verify Atlas Backup — Atlas Admin API snapshot recency check (optional).

Run from CI / cron when ``ATLAS_API_PUBLIC_KEY`` / ``ATLAS_API_PRIVATE_KEY``
/ ``ATLAS_PROJECT_ID`` / ``ATLAS_CLUSTER_NAME`` are configured. Lists
the most recent cloud snapshot and exports ``ATLAS_BACKUP_VERIFIED_AT``
to a small JSON sidecar (``.local/atlas_backup_verified.json``) which
the readiness validator can surface.

Without API keys the script is a no-op (PASS with reason
"api_keys_unset"). Use this path on M10+ clusters where Atlas is the
backup primary; the readiness URI-detection in
``infra.atlas_backup_check`` already handles the trust signal.

Exit codes:
  0  → snapshot fresh OR api_keys_unset (no-op)
  1  → snapshot older than --max-age-hours
  2  → API call failed / cluster not found

Usage:
  python backend/scripts/verify_atlas_backup.py --max-age-hours 26
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _has_atlas_keys() -> bool:
    return bool(os.environ.get("ATLAS_API_PUBLIC_KEY") and os.environ.get("ATLAS_API_PRIVATE_KEY") and os.environ.get("ATLAS_PROJECT_ID") and os.environ.get("ATLAS_CLUSTER_NAME"))


def _fetch_latest_snapshot() -> dict[str, Any]:
    """Call Atlas Admin API and return the newest snapshot summary.

    Uses HTTP digest auth (Atlas Admin API requirement). Imports
    ``requests`` lazily so the module is importable without the
    dependency in environments where the keys aren't set.
    """
    import requests  # type: ignore[import-not-found]
    from requests.auth import HTTPDigestAuth  # type: ignore[import-not-found]

    project_id = os.environ["ATLAS_PROJECT_ID"]
    cluster = os.environ["ATLAS_CLUSTER_NAME"]
    url = f"https://cloud.mongodb.com/api/atlas/v1.0/groups/{project_id}/clusters/{cluster}/backup/snapshots"
    auth = HTTPDigestAuth(
        os.environ["ATLAS_API_PUBLIC_KEY"],
        os.environ["ATLAS_API_PRIVATE_KEY"],
    )
    resp = requests.get(url, auth=auth, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results", []) or []
    if not results:
        return {}

    # Don't trust API ordering — sort explicitly by createdAt desc.
    # Atlas returns ISO 8601 strings (e.g. "2026-05-12T03:14:00Z");
    # lexicographic sort is correct for this format.
    def _key(s: dict[str, Any]) -> str:
        return s.get("createdAt") or ""

    results.sort(key=_key, reverse=True)
    snap = results[0]
    return {
        "snapshot_id": snap.get("id"),
        "created_at": snap.get("createdAt"),
        "type": snap.get("type"),
        "expires_at": snap.get("expiresAt"),
        "size_mb": snap.get("storageSizeBytes", 0) // (1024 * 1024),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-age-hours", type=int, default=26, help="Fail if newest snapshot older than this (default 26)")
    p.add_argument("--sidecar", default=".local/atlas_backup_verified.json")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if not _has_atlas_keys():
        if not args.quiet:
            print("verify_atlas_backup: api_keys_unset (no-op, exit 0)")
        return 0

    try:
        snap = _fetch_latest_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"verify_atlas_backup: API call failed — {type(exc).__name__}", file=sys.stderr)
        return 2

    if not snap:
        print("verify_atlas_backup: no snapshots found for cluster", file=sys.stderr)
        return 2

    created_iso = snap.get("created_at") or ""
    try:
        created = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
    except ValueError:
        print(f"verify_atlas_backup: cannot parse createdAt={created_iso}", file=sys.stderr)
        return 2

    age_hours = (datetime.now(UTC) - created).total_seconds() / 3600.0
    fresh = age_hours <= args.max_age_hours

    sidecar_path = Path(args.sidecar)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(
        json.dumps(
            {
                "verified_at": datetime.now(UTC).isoformat(),
                "snapshot_id": snap["snapshot_id"],
                "snapshot_age_hours": round(age_hours, 2),
                "snapshot_type": snap.get("type"),
                "fresh": fresh,
                "max_age_hours": args.max_age_hours,
            },
            indent=2,
        )
    )

    if not args.quiet:
        verdict = "FRESH" if fresh else "STALE"
        print(f"verify_atlas_backup: {verdict} — newest snapshot {age_hours:.1f}h old (threshold {args.max_age_hours}h)")

    return 0 if fresh else 1


if __name__ == "__main__":
    sys.exit(main())
