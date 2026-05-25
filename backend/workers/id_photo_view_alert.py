"""KVKK ID photo view alert worker (Task #105).

Periodically scans `audit_logs` for `view_online_checkin_id_photo`
events grouped by tenant + actor. When a single actor exceeds a
configurable threshold within a sliding window, the worker:

  1. Writes a high-severity (`critical`) audit event with
     ``operation_name = "id_photo_view_burst_alert"`` so the new
     KVKK report and audit timeline UIs surface it immediately.
  2. Inserts a tenant-broadcast notification (priority=``high``) into
     ``notifications`` so the existing admin notification bell picks it
     up in near real time.

Per-tenant overrides live in the ``kvkk_id_photo_alert_config``
collection (one document per tenant):

    {
      "tenant_id":        "<tid>",
      "enabled":          true,    # toggle off without removing config
      "threshold":        20,      # views per actor per window
      "window_minutes":   60,      # sliding window length
      "cooldown_minutes": 60       # suppress repeat alerts for same actor
    }

Defaults (applied when no config doc exists):

    enabled=True, threshold=20, window_minutes=60, cooldown_minutes=60

A separate ``kvkk_id_photo_alert_state`` collection holds the last alert
timestamp per (tenant, actor) so the worker doesn't re-fire every cycle
while an ongoing burst is still inside the window.

Tick interval is env-overridable via
``KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`` (default 600s).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from core.transient_db_guard import TransientFailureTracker

logger = logging.getLogger(__name__)

# Streak tracker so an Atlas blip on the system DB during a tick does not
# emit an ERROR-level "tick crashed" on every run. After a sustained
# streak the log is escalated back to ERROR so Sentry still surfaces a
# real outage. See `core.transient_db_guard`.
_transient_tracker = TransientFailureTracker("kvkk-id-photo-alert")

DEFAULT_THRESHOLD = 20
DEFAULT_WINDOW_MINUTES = 60
DEFAULT_COOLDOWN_MINUTES = 60

DEFAULT_INTERVAL_SECONDS = int(
    os.environ.get("KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS", "600")
)

CONFIG_COLLECTION = "kvkk_id_photo_alert_config"
STATE_COLLECTION = "kvkk_id_photo_alert_state"
VIEW_ACTION = "view_online_checkin_id_photo"
ALERT_ACTION = "id_photo_view_burst_alert"

# Manager / admin roles allowed to see this alert in the bell. The
# notifications router filters by `target_roles` (added below), so even
# though the notification is broadcast (`user_id=None`), only managers
# see it. Using string values (not the enum) keeps the worker decoupled
# from the User model import cycle.
DEFAULT_ALERT_ROLES: tuple[str, ...] = (
    "super_admin",
    "admin",
    "supervisor",
)


def _system_db():
    """Bypass the tenant-aware proxy: this worker spans every tenant."""
    from core.tenant_db import get_system_db
    return get_system_db()


def _safe_int(value, default: int) -> int:
    """Best-effort int coercion.

    Returns ``default`` for ``None``, missing, blank, or non-numeric
    values. A single bad config doc must never crash the worker — this
    is critical for a compliance/safety alarm where silent total
    failure is worse than per-field defaulting.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        # bool is a subclass of int but never a meaningful threshold.
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_config(raw: dict | None, tenant_id: str) -> dict:
    """Apply defaults and clamp values to safe operational bounds.

    A misconfigured tenant document must never DOS the worker (e.g.
    ``window_minutes="abc"`` or ``threshold=-1``), so every numeric
    field is coerced via ``_safe_int`` and clamped to a defensible
    range before use.
    """
    raw = raw or {}
    threshold = _safe_int(raw.get("threshold"), DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD
    window = _safe_int(raw.get("window_minutes"), DEFAULT_WINDOW_MINUTES) or DEFAULT_WINDOW_MINUTES
    cooldown = _safe_int(raw.get("cooldown_minutes"), DEFAULT_COOLDOWN_MINUTES) or DEFAULT_COOLDOWN_MINUTES
    threshold = max(1, min(threshold, 10_000))
    window = max(1, min(window, 24 * 60))
    cooldown = max(1, min(cooldown, 7 * 24 * 60))

    raw_roles = raw.get("alert_roles")
    if isinstance(raw_roles, list) and raw_roles:
        roles = tuple(str(r) for r in raw_roles if isinstance(r, str) and r.strip())
        if not roles:
            roles = DEFAULT_ALERT_ROLES
    else:
        roles = DEFAULT_ALERT_ROLES

    return {
        "tenant_id": tenant_id,
        "enabled": raw.get("enabled", True) is not False,
        "threshold": threshold,
        "window_minutes": window,
        "cooldown_minutes": cooldown,
        "alert_roles": roles,
    }


async def _load_configs(db) -> dict[str, dict]:
    """Return ``{tenant_id: resolved_config}`` for explicit per-tenant overrides.

    Each document is parsed in isolation: a malformed config for one
    tenant must NOT prevent the worker from processing the others.
    """
    out: dict[str, dict] = {}
    try:
        cur = db[CONFIG_COLLECTION].find({}, {"_id": 0})
    except Exception:
        logger.exception("[kvkk-id-photo-alert] failed to open config cursor")
        return out
    try:
        async for doc in cur:
            try:
                tid = doc.get("tenant_id") if isinstance(doc, dict) else None
                if not tid:
                    continue
                out[tid] = _resolve_config(doc, tid)
            except Exception:
                logger.exception(
                    "[kvkk-id-photo-alert] skipping malformed config doc: %r", doc
                )
    except Exception:
        logger.exception("[kvkk-id-photo-alert] config cursor iteration failed")
    return out


def _max_window_minutes(configs: dict[str, dict]) -> int:
    """Largest window across all tenants — one audit_logs scan covers them all."""
    explicit_max = max(
        (c["window_minutes"] for c in configs.values()),
        default=DEFAULT_WINDOW_MINUTES,
    )
    return max(explicit_max, DEFAULT_WINDOW_MINUTES)


async def _scan_actor_view_counts(db, since_iso: str) -> list[dict]:
    """Aggregate view counts grouped by tenant + actor since ``since_iso``."""
    pipeline = [
        {
            "$match": {
                "operation_name": VIEW_ACTION,
                "timestamp": {"$gte": since_iso},
            },
        },
        {
            "$group": {
                "_id": {"tenant_id": "$tenant_id", "actor_id": "$actor_id"},
                "count": {"$sum": 1},
                "last_view_at": {"$max": "$timestamp"},
            },
        },
    ]
    rows: list[dict] = []
    async for doc in db.audit_logs.aggregate(pipeline):
        key = doc.get("_id") or {}
        tenant_id = key.get("tenant_id")
        actor_id = key.get("actor_id")
        if not tenant_id or not actor_id:
            continue
        rows.append({
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "count": int(doc.get("count") or 0),
            "last_view_at": doc.get("last_view_at"),
        })
    return rows


async def _should_fire(
    db, tenant_id: str, actor_id: str, cooldown_minutes: int
) -> bool:
    """Cooldown gate — avoids spamming admins every tick during an ongoing burst."""
    state = await db[STATE_COLLECTION].find_one(
        {"tenant_id": tenant_id, "actor_id": actor_id},
        {"_id": 0, "last_alerted_at": 1},
    )
    if not state:
        return True
    last = state.get("last_alerted_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except Exception:
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    return datetime.now(UTC) - last_dt >= timedelta(minutes=cooldown_minutes)


async def _record_alert_state(db, tenant_id: str, actor_id: str) -> None:
    await db[STATE_COLLECTION].update_one(
        {"tenant_id": tenant_id, "actor_id": actor_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "last_alerted_at": datetime.now(UTC).isoformat(),
            },
        },
        upsert=True,
    )


async def _write_high_severity_audit(
    db,
    tenant_id: str,
    actor_id: str,
    count: int,
    window_minutes: int,
    threshold: int,
) -> None:
    from core.audit import log_audit_event
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=actor_id,
        action=ALERT_ACTION,
        entity_type="audit_alert",
        entity_id=actor_id,
        details=(
            f"KVKK kimlik fotoğrafı görüntüleme uyarısı: "
            f"actor={actor_id} son {window_minutes} dk içinde {count} "
            f"görüntüleme yaptı (eşik={threshold})."
        ),
        after_value={
            "actor_id": actor_id,
            "view_count": count,
            "threshold": threshold,
            "window_minutes": window_minutes,
        },
        db=db,
        severity="critical",
    )


async def _dispatch_admin_notification(
    db,
    tenant_id: str,
    actor_id: str,
    count: int,
    window_minutes: int,
    threshold: int,
    alert_roles: tuple[str, ...] = DEFAULT_ALERT_ROLES,
) -> None:
    """Insert a manager-only notification.

    Notifications use ``user_id=None`` (tenant-broadcast within the
    tenant) plus a ``target_roles`` array. The notifications router
    filters by role, so only users whose role is in ``alert_roles``
    actually see this entry — clerks and front-desk staff do not.
    """
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "user_id": None,
        "target_roles": list(alert_roles),
        "type": "kvkk_id_photo_alert",
        "title": "KVKK: Olağandışı kimlik fotoğrafı görüntüleme",
        "message": (
            f"{actor_id} kullanıcısı son {window_minutes} dakikada "
            f"{count} kimlik fotoğrafı açtı (eşik {threshold})."
        ),
        "priority": "high",
        "read": False,
        "action_url": "/audit-timeline?report=id-photo-views",
        "context": {
            "actor_id": actor_id,
            "view_count": count,
            "threshold": threshold,
            "window_minutes": window_minutes,
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.notifications.insert_one(doc)


async def _recount_for_tenant_window(
    db, tenant_id: str, actor_id: str, window_minutes: int
) -> int:
    """Recount within the tenant's (smaller) window when the global scan
    used a wider one. Without this the worker would over-trigger for
    tenants whose window is shorter than the global max.
    """
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    return await db.audit_logs.count_documents({
        "tenant_id": tenant_id,
        "operation_name": VIEW_ACTION,
        "actor_id": actor_id,
        "timestamp": {"$gte": since.isoformat()},
    })


async def _evaluate_row(db, row: dict, configs: dict[str, dict]) -> bool:
    tenant_id = row["tenant_id"]
    actor_id = row["actor_id"]
    cfg = configs.get(tenant_id) or _resolve_config(None, tenant_id)
    if not cfg["enabled"]:
        return False
    if row["count"] < cfg["threshold"]:
        return False
    if not await _should_fire(db, tenant_id, actor_id, cfg["cooldown_minutes"]):
        return False

    await _write_high_severity_audit(
        db, tenant_id, actor_id, row["count"], cfg["window_minutes"], cfg["threshold"]
    )
    await _dispatch_admin_notification(
        db,
        tenant_id,
        actor_id,
        row["count"],
        cfg["window_minutes"],
        cfg["threshold"],
        alert_roles=cfg.get("alert_roles", DEFAULT_ALERT_ROLES),
    )
    await _record_alert_state(db, tenant_id, actor_id)
    logger.warning(
        "[kvkk-id-photo-alert] FIRED tenant=%s actor=%s count=%d "
        "threshold=%d window=%dm",
        tenant_id, actor_id, row["count"], cfg["threshold"], cfg["window_minutes"],
    )
    return True


async def _run_once() -> dict:
    db = _system_db()
    configs = await _load_configs(db)
    scan_window = _max_window_minutes(configs)
    since = datetime.now(UTC) - timedelta(minutes=scan_window)
    rows = await _scan_actor_view_counts(db, since.isoformat())

    fired = 0
    for row in rows:
        cfg = configs.get(row["tenant_id"]) or _resolve_config(None, row["tenant_id"])
        if cfg["window_minutes"] < scan_window:
            try:
                row = {
                    **row,
                    "count": await _recount_for_tenant_window(
                        db, row["tenant_id"], row["actor_id"], cfg["window_minutes"]
                    ),
                }
            except Exception:
                logger.exception(
                    "[kvkk-id-photo-alert] recount failed tenant=%s actor=%s",
                    row["tenant_id"], row["actor_id"],
                )
                continue
        try:
            if await _evaluate_row(db, row, configs):
                fired += 1
        except Exception:
            logger.exception(
                "[kvkk-id-photo-alert] evaluate failed tenant=%s actor=%s",
                row["tenant_id"], row["actor_id"],
            )

    summary = {"rows_scanned": len(rows), "alerts_fired": fired}
    if fired:
        logger.info("[kvkk-id-photo-alert] cycle complete: %s", summary)
    return summary


async def _ensure_indexes(db) -> None:
    """Best-effort index creation; failures are non-fatal."""
    try:
        await db[STATE_COLLECTION].create_index(
            [("tenant_id", 1), ("actor_id", 1)], unique=True
        )
        await db[CONFIG_COLLECTION].create_index("tenant_id", unique=True)
    except Exception as e:
        logger.warning("[kvkk-id-photo-alert] index ensure failed: %s", e)


async def run_loop(interval_seconds: int | None = None) -> None:
    interval = int(interval_seconds or DEFAULT_INTERVAL_SECONDS)
    logger.info("[kvkk-id-photo-alert] worker started (interval=%ss)", interval)
    try:
        await _ensure_indexes(_system_db())
    except Exception as e:
        logger.warning("[kvkk-id-photo-alert] index ensure error: %s", e)

    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _transient_tracker.log_exception(
                logger, exc, TransientFailureTracker.OUTER_LOOP_KEY,
                context="tick",
                non_transient_msg="%s tick crashed: %s",
            )
        else:
            _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
