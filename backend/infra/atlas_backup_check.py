"""
Atlas Backup Check — MongoDB Atlas managed-backup awareness layer.

When the production cluster is hosted on MongoDB Atlas (M10+ tier),
continuous cloud backup + point-in-time restore are managed by Atlas
itself (snapshots stored on Atlas-controlled S3, retention configurable
in the Atlas console). The local `infra.backup_manager.BackupManager`
mongodump path becomes a *secondary* defense layer (or unused), and a
disabled `BACKUP_ENABLED=false` is no longer a readiness blocker.

This module exposes a single helper used by `readiness_validator.py`
to detect that arrangement from the connection URI alone — no Atlas
Admin API call, no credentials. Operators can additionally run
`backend/scripts/verify_atlas_backup.py` to validate the actual
snapshot recency via the Atlas Admin API when keys are configured.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse


def _get_mongo_uri() -> str:
    """Return whichever URI the backend is actually using.

    Resolution mirrors `backend/core/database.py:19` (`MONGO_URL` first)
    and falls back to `MONGO_ATLAS_URI` for environments where the
    Atlas string is the only one stored in DigitalOcean Secrets.
    """
    return os.environ.get("MONGO_URL") or os.environ.get("MONGO_ATLAS_URI") or ""


def is_atlas_uri(uri: str) -> bool:
    """True if the URI points at a MongoDB Atlas-hosted cluster.

    Atlas SRV hostnames always end in ``.mongodb.net``. We accept both
    ``mongodb+srv://`` and ``mongodb://`` schemes; the host suffix is
    the reliable signal.
    """
    if not uri:
        return False
    try:
        parsed = urlparse(uri)
        host = (parsed.hostname or "").lower()
        return host.endswith(".mongodb.net")
    except Exception:
        return False


def _read_verification_sidecar() -> dict[str, Any] | None:
    """Read the JSON sidecar dropped by ``verify_atlas_backup.py``.

    The sidecar lives at ``.local/atlas_backup_verified.json`` (or wherever
    ``ATLAS_BACKUP_SIDECAR`` env-var points). Returns the parsed dict or
    ``None`` on any error — readiness must NEVER crash because of an
    unreadable sidecar.
    """
    import json
    from pathlib import Path

    path = Path(os.environ.get("ATLAS_BACKUP_SIDECAR") or ".local/atlas_backup_verified.json")
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text())
    except Exception:
        return None


def get_atlas_backup_status() -> dict[str, Any]:
    """Resolve the Atlas-managed backup posture for readiness reporting.

    Returns a dict suitable for embedding under the readiness ``backup``
    check. NEVER includes credentials, raw URIs, or hostnames — only
    boolean signals + the user-declared tier so operators can verify
    against the Atlas console.

    Tier resolution:
      * ``ATLAS_TIER`` env-var if set (e.g. ``M10``, ``M30``).
      * Otherwise ``"unknown"`` — fail-closed in production
        (see ``resolve_backup_check``).

    Verification posture (in priority order):
      1. ``ATLAS_BACKUP_SIDECAR`` JSON written by
         ``backend/scripts/verify_atlas_backup.py`` (preferred —
         contains snapshot id + age + freshness verdict).
      2. ``ATLAS_BACKUP_VERIFIED_AT`` env-var ISO timestamp
         (legacy/manual operator override).
      3. ``None`` — declared trust only.
    """
    uri = _get_mongo_uri()
    atlas = is_atlas_uri(uri)

    tier = (os.environ.get("ATLAS_TIER") or "").strip().upper() or "unknown"

    sidecar = _read_verification_sidecar()
    verified_at: str | None = None
    snapshot_age_hours: float | None = None
    verification_fresh: bool | None = None
    if sidecar:
        verified_at = sidecar.get("verified_at")
        age = sidecar.get("snapshot_age_hours")
        snapshot_age_hours = float(age) if isinstance(age, (int, float)) else None
        verification_fresh = bool(sidecar.get("fresh", False))
    if not verified_at:
        verified_at = os.environ.get("ATLAS_BACKUP_VERIFIED_AT") or None

    # M10 and above include continuous cloud backup + PITR by default.
    # Coverage extends to L (low-CPU) and R (NVMe) variants of those tiers.
    # M2/M5 include daily snapshots only. M0 has no backup.
    _M10_PLUS_BASES = {"M10", "M20", "M30", "M40", "M50", "M60", "M80", "M140", "M200", "M300", "M400", "M700"}
    has_continuous_backup = (
        tier in _M10_PLUS_BASES or any(tier.startswith(b) for b in _M10_PLUS_BASES)  # M30L, M40R, etc.
    )
    has_snapshot_only = tier in {"M2", "M5"}

    return {
        "atlas_managed": atlas,
        "tier": tier,
        "has_continuous_backup": has_continuous_backup,
        "has_snapshot_only": has_snapshot_only,
        "verified_at": verified_at,
        "snapshot_age_hours": snapshot_age_hours,
        "verification_fresh": verification_fresh,
    }


def resolve_backup_check(local_backup_status: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Compose the readiness backup check + score, Atlas-aware.

    Args:
        local_backup_status: payload from
            ``infra.backup_manager.backup_manager.get_status()``.

    Returns:
        ``(check_payload, score)`` where ``check_payload`` is the dict
        embedded under ``checks["backup"]`` and ``score`` is in
        ``[0.0, 1.0]`` (1.0 = healthy, 0.0 = blocker).

    Logic:
      * Atlas M10+: ``status="atlas_managed"``, score 1.0.
        Local backup_manager is informational only.
      * Atlas M2/M5: ``status="atlas_snapshots_only"``, score 0.7
        (degraded — only daily snapshots, no PITR).
      * Atlas M0: ``status="atlas_no_backup"``, score 0.3 in dev,
        0.0 in prod.
      * Non-Atlas: fall back to legacy local-backup-manager behaviour.
    """
    atlas = get_atlas_backup_status()
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").strip().lower()
    is_prod = env in ("production", "prod", "live")

    if atlas["atlas_managed"]:
        if atlas["has_continuous_backup"]:
            return (
                {
                    "status": "atlas_managed",
                    "atlas": atlas,
                    "local_backup_enabled": local_backup_status.get("enabled", False),
                    "rpo_target": "continuous (PITR)",
                    "rto_target": "minutes (Atlas restore)",
                },
                1.0,
            )
        if atlas["has_snapshot_only"]:
            return (
                {
                    "status": "atlas_snapshots_only",
                    "atlas": atlas,
                    "warning": "M2/M5 plans provide daily snapshots only — no PITR",
                    "rpo_target": "24 hours",
                    "rto_target": "minutes (Atlas restore)",
                },
                0.7,
            )
        # M0 or unknown tier on Atlas — no managed backup guarantee.
        # Fail-closed in production for either case (architect review,
        # 12 May 2026): unknown tier in prod is treated as a blocker
        # because the operator hasn't declared the plan and we can't
        # assume continuous backup.
        is_m0 = atlas["tier"] == "M0"
        return (
            {
                "status": "atlas_no_backup" if is_m0 else "atlas_unknown_tier",
                "atlas": atlas,
                "warning": (
                    "M0 free-tier has NO managed backup — upgrade to M10+ or enable BACKUP_ENABLED=true with durable upload" if is_m0 else "ATLAS_TIER env-var unset — set it to declare your plan"
                ),
            },
            0.0 if is_prod else 0.3,
        )

    # Non-Atlas: legacy local backup_manager path
    enabled = local_backup_status.get("enabled", False)
    return (
        {
            "status": "enabled" if enabled else "disabled",
            "atlas": atlas,
            "details": local_backup_status,
        },
        1.0 if enabled else (0.0 if is_prod else 0.3),
    )
