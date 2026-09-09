"""
Verify Atlas Backup — Atlas Admin API snapshot recency check (optional).

Run from CI / cron when ``ATLAS_API_PUBLIC_KEY`` / ``ATLAS_API_PRIVATE_KEY``
/ ``ATLAS_PROJECT_ID`` / ``ATLAS_CLUSTER_NAME`` are configured. Lists
the most recent cloud snapshot and exports ``ATLAS_BACKUP_VERIFIED_AT``
to a small JSON sidecar (``.local/atlas_backup_verified.json``) which
the readiness validator can surface.

Without API keys the script is only a no-op in development. Production and
``--require-keys`` runs fail closed because a declared tier is not proof that
Cloud Backup is enabled or that a usable snapshot exists.

Exit codes:
  0  → Cloud Backup + PITR enabled and snapshot fresh, or development
       api_keys_unset (no-op)
  1  → backup/PITR disabled or snapshot older than --max-age-hours
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
    base_url = f"https://cloud.mongodb.com/api/atlas/v2/groups/{project_id}/clusters/{cluster}"
    auth = HTTPDigestAuth(
        os.environ["ATLAS_API_PUBLIC_KEY"],
        os.environ["ATLAS_API_PRIVATE_KEY"],
    )
    headers = {"Accept": "application/vnd.atlas.2024-11-13+json"}
    cluster_resp = requests.get(base_url, auth=auth, headers=headers, timeout=5)
    cluster_resp.raise_for_status()
    cluster_data = cluster_resp.json()

    resp = requests.get(f"{base_url}/backup/snapshots", auth=auth, headers=headers, timeout=5)
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
        "cloud_backup_enabled": bool(
            cluster_data.get("backupEnabled") or cluster_data.get("providerBackupEnabled")
        ),
        "pitr_enabled": bool(cluster_data.get("pitEnabled")),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-age-hours", type=int, default=26, help="Fail if newest snapshot older than this (default 26)")
    p.add_argument("--sidecar", default=".local/atlas_backup_verified.json")
    p.add_argument("--require-keys", action="store_true", help="Fail when Atlas API credentials are missing")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if not _has_atlas_keys():
        env = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").strip().lower()
        if args.require_keys or env in {"production", "prod", "live"}:
            print("verify_atlas_backup: Atlas API keys are required", file=sys.stderr)
            return 2
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
    configured = bool(snap.get("cloud_backup_enabled") and snap.get("pitr_enabled"))
    fresh = configured and age_hours <= args.max_age_hours

    sidecar_path = Path(args.sidecar)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(
        json.dumps(
            {
                "verified_at": datetime.now(UTC).isoformat(),
                "snapshot_id": snap["snapshot_id"],
                "snapshot_age_hours": round(age_hours, 2),
                "snapshot_type": snap.get("type"),
                "cloud_backup_enabled": snap.get("cloud_backup_enabled", False),
                "pitr_enabled": snap.get("pitr_enabled", False),
                "fresh": fresh,
                "max_age_hours": args.max_age_hours,
            },
            indent=2,
        )
    )

    if not args.quiet:
        if not configured:
            verdict = "DISABLED"
        else:
            verdict = "FRESH" if fresh else "STALE"
        print(
            f"verify_atlas_backup: {verdict} — newest snapshot {age_hours:.1f}h old "
            f"(threshold {args.max_age_hours}h)"
        )

    return 0 if fresh else 1


if __name__ == "__main__":
    sys.exit(main())
