"""
Atlas Backup Check — MongoDB Atlas managed-backup awareness layer.

MongoDB Atlas can manage cloud snapshots and point-in-time restore for
dedicated clusters, but the cluster tier alone is not proof that either
feature is enabled. Production readiness therefore requires both explicit
configuration and a recent snapshot verification.

This module exposes a helper used by `readiness_validator.py` to detect
Atlas from the connection URI. When Atlas Admin API credentials are present,
it also verifies the cluster backup flags and newest snapshot through a
short-lived cache. The same check can be run manually with
`backend/scripts/verify_atlas_backup.py`.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

_LIVE_CACHE: dict[str, Any] = {}


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


def _env_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _live_snapshot_verification() -> tuple[dict[str, Any] | None, str | None]:
    """Fetch a current Atlas snapshot with a short in-process cache.

    The readiness endpoint is operator-facing but may refresh repeatedly. The
    cache avoids hitting the Atlas Admin API on every refresh. Errors expose
    only their class name; credentials and request URLs are never returned.
    """
    required = (
        "ATLAS_API_PUBLIC_KEY",
        "ATLAS_API_PRIVATE_KEY",
        "ATLAS_PROJECT_ID",
        "ATLAS_CLUSTER_NAME",
    )
    if not all(os.environ.get(key) for key in required):
        return None, "api_keys_unset"

    ttl = float(os.environ.get("ATLAS_BACKUP_LIVE_CACHE_SECONDS", "900"))
    now_mono = time.monotonic()
    cached_at = _LIVE_CACHE.get("cached_at")
    if isinstance(cached_at, (int, float)) and now_mono - cached_at <= ttl:
        return _LIVE_CACHE.get("verification"), _LIVE_CACHE.get("error")

    try:
        from scripts.verify_atlas_backup import _fetch_latest_snapshot

        snapshot = _fetch_latest_snapshot()
        created = _parse_iso(snapshot.get("created_at")) if snapshot else None
        if created is None:
            verification = None
            error = "no_snapshot_found"
        else:
            age = max(0.0, (datetime.now(UTC) - created).total_seconds() / 3600.0)
            verification = {
                "verified_at": datetime.now(UTC).isoformat(),
                "snapshot_age_hours": age,
                "fresh": age <= float(os.environ.get("ATLAS_BACKUP_MAX_AGE_HOURS", "26")),
                "cloud_backup_enabled": snapshot.get("cloud_backup_enabled"),
                "pitr_enabled": snapshot.get("pitr_enabled"),
            }
            error = None
    except Exception as exc:  # noqa: BLE001 - readiness must report, not crash
        verification = None
        error = type(exc).__name__

    _LIVE_CACHE.clear()
    _LIVE_CACHE.update(
        {"cached_at": now_mono, "verification": verification, "error": error}
    )
    return verification, error


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
         ``backend/scripts/verify_atlas_backup.py``.
      2. Live Atlas Admin API query when all four API identifiers/credentials
         are configured (cached for 15 minutes by default).
      3. ``ATLAS_BACKUP_VERIFIED_AT`` is retained for diagnostics only; it
         cannot produce a fresh verdict without snapshot evidence.
      4. ``None`` — fail closed in production.
    """
    uri = _get_mongo_uri()
    atlas = is_atlas_uri(uri)

    tier = (os.environ.get("ATLAS_TIER") or "").strip().upper() or "unknown"

    sidecar = _read_verification_sidecar()
    verification_source = "sidecar" if sidecar else None
    verification_error: str | None = None
    if not sidecar:
        sidecar, verification_error = _live_snapshot_verification()
        if sidecar:
            verification_source = "atlas_admin_api"
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

    # A compatible tier only means the feature *can* be enabled. Atlas allows
    # operators to turn Cloud Backup / Continuous Cloud Backup off, so tier
    # inference must never become a production-green signal by itself.
    _M10_PLUS_BASES = {"M10", "M20", "M30", "M40", "M50", "M60", "M80", "M140", "M200", "M300", "M400", "M700"}
    supports_continuous_backup = tier in _M10_PLUS_BASES or any(
        tier.startswith(b) for b in _M10_PLUS_BASES
    )
    api_cloud_backup = sidecar.get("cloud_backup_enabled") if sidecar else None
    api_pitr = sidecar.get("pitr_enabled") if sidecar else None
    cloud_backup_enabled = (
        api_cloud_backup
        if isinstance(api_cloud_backup, bool)
        else _env_true("ATLAS_CLOUD_BACKUP_ENABLED")
    )
    pitr_enabled = api_pitr if isinstance(api_pitr, bool) else _env_true("ATLAS_PITR_ENABLED")
    has_continuous_backup = supports_continuous_backup and cloud_backup_enabled and pitr_enabled
    has_snapshot_only = cloud_backup_enabled and not pitr_enabled

    max_snapshot_age = float(os.environ.get("ATLAS_BACKUP_MAX_AGE_HOURS", "26"))
    max_verification_age = float(
        os.environ.get("ATLAS_BACKUP_VERIFICATION_MAX_AGE_HOURS", "26")
    )
    verified_time = _parse_iso(verified_at)
    verification_age_hours: float | None = None
    effective_snapshot_age_hours: float | None = None
    if verified_time is not None:
        verification_age_hours = max(
            0.0, (datetime.now(UTC) - verified_time).total_seconds() / 3600.0
        )
    if snapshot_age_hours is not None and verification_age_hours is not None:
        effective_snapshot_age_hours = snapshot_age_hours + verification_age_hours

    # Do not trust a historical `fresh: true` forever. Both the verification
    # event and the snapshot it observed must still be inside their windows.
    verification_fresh = bool(
        sidecar
        and sidecar.get("fresh") is True
        and verification_age_hours is not None
        and verification_age_hours <= max_verification_age
        and effective_snapshot_age_hours is not None
        and effective_snapshot_age_hours <= max_snapshot_age
    )

    return {
        "atlas_managed": atlas,
        "tier": tier,
        "supports_continuous_backup": supports_continuous_backup,
        "cloud_backup_enabled": cloud_backup_enabled,
        "pitr_enabled": pitr_enabled,
        "has_continuous_backup": has_continuous_backup,
        "has_snapshot_only": has_snapshot_only,
        "verified_at": verified_at,
        "snapshot_age_hours": snapshot_age_hours,
        "effective_snapshot_age_hours": effective_snapshot_age_hours,
        "verification_age_hours": verification_age_hours,
        "verification_fresh": verification_fresh,
        "verification_source": verification_source,
        "verification_error": verification_error,
        "max_snapshot_age_hours": max_snapshot_age,
        "max_verification_age_hours": max_verification_age,
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
      * Atlas with declared backup + fresh verification: healthy.
      * Compatible tier without explicit enablement or fresh evidence:
        fail-closed in production.
      * Atlas M0: ``status="atlas_no_backup"``, score 0.3 in dev,
        0.0 in prod.
      * Non-Atlas: fall back to legacy local-backup-manager behaviour.
    """
    atlas = get_atlas_backup_status()
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "development").strip().lower()
    is_prod = env in ("production", "prod", "live")

    if atlas["atlas_managed"]:
        if atlas["has_continuous_backup"] and atlas["verification_fresh"]:
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
        if atlas["has_snapshot_only"] and atlas["verification_fresh"]:
            return (
                {
                    "status": "atlas_snapshots_only",
                    "atlas": atlas,
                    "warning": "Cloud snapshots are verified, but PITR is not enabled.",
                    "rpo_target": "24 hours",
                    "rto_target": "minutes (Atlas restore)",
                },
                0.7,
            )
        if atlas["cloud_backup_enabled"] and not atlas["verification_fresh"]:
            return (
                {
                    "status": "atlas_backup_unverified",
                    "atlas": atlas,
                    "warning": (
                        "Atlas backup is declared, but no fresh snapshot verification exists. "
                        "Run backend/scripts/verify_atlas_backup.py with Atlas API credentials."
                    ),
                },
                0.0 if is_prod else 0.5,
            )

        # M0, unknown tier, or a compatible tier with backup toggles not
        # explicitly declared — no managed-backup guarantee.
        is_m0 = atlas["tier"] == "M0"
        return (
            {
                "status": "atlas_no_backup" if is_m0 else "atlas_backup_not_declared",
                "atlas": atlas,
                "warning": (
                    "M0 free-tier has no managed backup; use a dedicated tier with Cloud Backup or durable offsite backups."
                    if is_m0
                    else "Set ATLAS_TIER, ATLAS_CLOUD_BACKUP_ENABLED and ATLAS_PITR_ENABLED to match the Atlas console, then verify a current snapshot."
                ),
            },
            0.0 if is_prod else 0.3,
        )

    # Non-Atlas: a flag alone is not evidence. Require a recent real backup and
    # an explicitly durable destination (or a path outside known ephemeral
    # roots). In-memory `last_successful` is conservative: after a restart the
    # deployment must re-establish backup evidence.
    enabled = local_backup_status.get("enabled", False)
    last = local_backup_status.get("last_successful") or {}
    completed = _parse_iso(last.get("completed_at"))
    age_hours = (
        max(0.0, (datetime.now(UTC) - completed).total_seconds() / 3600.0)
        if completed
        else None
    )
    max_age = float(os.environ.get("BACKUP_MAX_AGE_HOURS", "26"))
    backup_path = str(local_backup_status.get("backup_path") or "")
    durable = _env_true("BACKUP_DURABLE") or bool(
        backup_path and not backup_path.startswith(("/tmp", "/var/tmp"))
    )
    fresh = bool(
        enabled
        and last.get("status") == "completed"
        and age_hours is not None
        and age_hours <= max_age
        and durable
    )
    if fresh:
        status = "enabled_verified"
        score = 1.0
        warning = None
    elif enabled:
        status = "enabled_unverified"
        score = 0.0 if is_prod else 0.5
        warning = "Backup is enabled but no recent real backup on durable storage is verified."
    else:
        status = "disabled"
        score = 0.0 if is_prod else 0.3
        warning = "Backup is disabled."
    return (
        {
            "status": status,
            "atlas": atlas,
            "details": local_backup_status,
            "last_backup_age_hours": age_hours,
            "max_backup_age_hours": max_age,
            "durable_destination": durable,
            "warning": warning,
        },
        score,
    )
