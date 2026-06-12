
import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status

IDEMPOTENCY_HEADER = "Idempotency-Key"

# Task #81 — TTL retention windows for the `idempotency_keys` collection.
# A single TTL index on `expires_at` (created in
# bootstrap/phases/perf_indexes.py as `idx_idempotency_expires_at_ttl` with
# expireAfterSeconds=0) sweeps rows once `expires_at` is reached.
#
#   - PROCESSING grace: a crashed worker that never calls complete/release
#     leaves the slot in "processing". After 5 minutes the row expires so a
#     legitimate retry is no longer blocked by a ghost lock.
#   - COMPLETED / FAILED retention: completed and failed rows act as the
#     replay cache for client retries. 24h matches the longest window in
#     which a client (mobile app, OTA, internal worker) might sensibly
#     retry the same Idempotency-Key.
IDEMPOTENCY_PROCESSING_GRACE_SECONDS = 300
IDEMPOTENCY_RETENTION_SECONDS = 24 * 60 * 60
# Some clients (and our own stress harness) send the RFC-style `X-` prefixed
# variant. Accept both so a retry from either client kind hits the same lock.
IDEMPOTENCY_HEADER_ALIASES = ("Idempotency-Key", "X-Idempotency-Key")


def normalize_idempotency_key(key: str | None) -> str | None:
    if not key:
        return None
    normalized = key.strip()
    return normalized or None


def get_idempotency_key(request: Request) -> str | None:
    for header in IDEMPOTENCY_HEADER_ALIASES:
        value = request.headers.get(header)
        normalized = normalize_idempotency_key(value)
        if normalized:
            return normalized
    return None


def ensure_idempotent_request(request: Request, required: bool = True) -> str | None:
    key = get_idempotency_key(request)
    if required and not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing {IDEMPOTENCY_HEADER} header",
        )
    return key


def _lock_id(tenant_id: str, scope: str, key: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{scope}:{key}".encode()).hexdigest()


async def claim_idempotency(
    db_handle,
    *,
    tenant_id: str,
    scope: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Atomically claim an idempotency slot.

    Returns either:
      - {"status": "acquired", "lock_id": ...} on first claim
      - {"status": "replay", "response": {...}} if the same key already
        completed (caller should return the cached response verbatim)
      - {"status": "in_flight"} if another request is still processing the key

    Uses MongoDB unique-on-_id semantics on `idempotency_keys` to serialize
    concurrent claims without a transaction. Callers MUST follow up with
    `complete_idempotency` (success) or `release_idempotency` (failure) so
    the slot doesn't stay stuck in 'processing' forever.
    """
    from pymongo.errors import DuplicateKeyError  # type: ignore

    lock_id = _lock_id(tenant_id, scope, idempotency_key)
    now = datetime.now(UTC)
    doc = {
        "_id": lock_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "idempotency_key": idempotency_key,
        "status": "processing",
        "created_at": now.isoformat(),
        # BSON Date powers the TTL sweep — a crashed worker's "processing"
        # slot expires after the short grace window so retries aren't blocked.
        "expires_at": now + timedelta(seconds=IDEMPOTENCY_PROCESSING_GRACE_SECONDS),
    }
    try:
        await db_handle.idempotency_keys.insert_one(doc)
        return {"status": "acquired", "lock_id": lock_id}
    except DuplicateKeyError:
        existing = await db_handle.idempotency_keys.find_one({"_id": lock_id}, {"_id": 0})
        if existing and existing.get("status") == "completed":
            return {"status": "replay", "response": existing.get("response_body") or {}}
        return {"status": "in_flight"}


async def complete_idempotency(
    db_handle,
    *,
    lock_id: str,
    response_body: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    await db_handle.idempotency_keys.update_one(
        {"_id": lock_id},
        {"$set": {
            "status": "completed",
            "response_body": response_body,
            "completed_at": now.isoformat(),
            # Push expiry out to the replay-retention window so the cached
            # response survives client retries but still gets swept eventually.
            "expires_at": now + timedelta(seconds=IDEMPOTENCY_RETENTION_SECONDS),
        }},
    )


async def release_idempotency(db_handle, *, lock_id: str, error: str | None = None) -> None:
    """Drop a processing lock so the caller can retry.

    Used when the protected operation raised before producing a stable result.
    We delete (not mark failed) because the caller's intent is "let me try
    again with the same key"; keeping a 'failed' marker would block retries.
    """
    await db_handle.idempotency_keys.delete_one({"_id": lock_id})


# ── Short-window auto-dedup (server-side anti-double-submit) ──────────────────
#
# claim_idempotency above protects requests that carry an EXPLICIT client key
# (Idempotency-Key header / payment reference) with a 24h replay cache. That
# does nothing for a cashier double-click that ships NO key. The guard below
# fills that gap: it derives a fingerprint from the payment itself and rejects a
# second identical payment that arrives within a short window. We REJECT (409)
# rather than replay, because without an explicit client key there is no
# verifiable intent — silently returning the prior payment would mask a possibly
# legitimate second charge, while a 409 is trivially recoverable.
PAYMENT_DEDUP_DEFAULT_WINDOW_SECONDS = 10


def payment_dedup_window_seconds() -> int:
    """Window (seconds) within which an unkeyed identical payment is a dup.

    Env-tunable via ``PAYMENT_DEDUP_WINDOW_SECONDS``; floored at 1s. Kept short
    so genuine, deliberately-repeated identical payments are only briefly
    blocked, while double-clicks/network replays (sub-second) are caught.
    """
    raw = os.getenv("PAYMENT_DEDUP_WINDOW_SECONDS")
    try:
        value = int(raw) if raw is not None else PAYMENT_DEDUP_DEFAULT_WINDOW_SECONDS
    except (TypeError, ValueError):
        value = PAYMENT_DEDUP_DEFAULT_WINDOW_SECONDS
    return max(1, value)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def claim_short_window_dedup(
    db_handle,
    *,
    tenant_id: str,
    scope: str,
    fingerprint: str,
    window_seconds: int | None = None,
) -> dict[str, Any]:
    """Atomically claim a short-window dedup slot for an unkeyed payment.

    Returns either:
      - ``{"status": "acquired", "lock_id": ...}`` when this is the first
        identical payment in the window (caller proceeds, then leaves the slot
        on success so the window keeps catching repeats, or releases it on
        failure so a real retry isn't blocked), or
      - ``{"status": "duplicate"}`` when an identical payment is still inside
        the window (caller returns 409).

    Window precision comes from a ``created_at`` comparison plus a CONDITIONAL
    (CAS) delete on stale reclaim — so two concurrent double-clicks can never
    BOTH acquire. The TTL index on ``expires_at`` is only a backstop sweep
    (Mongo's TTL monitor runs ~every 60s, too coarse to define the window).
    """
    from pymongo.errors import DuplicateKeyError  # type: ignore

    window = (
        window_seconds if window_seconds is not None
        else payment_dedup_window_seconds()
    )
    lock_id = _lock_id(tenant_id, scope, fingerprint)
    now = datetime.now(UTC)

    def _fresh_doc() -> dict[str, Any]:
        return {
            "_id": lock_id,
            "tenant_id": tenant_id,
            "scope": scope,
            "idempotency_key": fingerprint,
            "status": "processing",
            "auto": True,
            "created_at": now.isoformat(),
            # Backstop TTL well past the logical window; window precision is
            # enforced by the created_at comparison below.
            "expires_at": now + timedelta(
                seconds=max(window, IDEMPOTENCY_PROCESSING_GRACE_SECONDS)
            ),
        }

    try:
        await db_handle.idempotency_keys.insert_one(_fresh_doc())
        return {"status": "acquired", "lock_id": lock_id}
    except DuplicateKeyError:
        pass

    existing = await db_handle.idempotency_keys.find_one({"_id": lock_id})
    if not existing:
        # Raced with an expiry/delete between our insert and read — one retry.
        try:
            await db_handle.idempotency_keys.insert_one(_fresh_doc())
            return {"status": "acquired", "lock_id": lock_id}
        except DuplicateKeyError:
            return {"status": "duplicate"}

    observed_created = existing.get("created_at")
    created_dt = _parse_iso(observed_created)
    if created_dt is None or (now - created_dt).total_seconds() <= window:
        # Inside the window (or an unparseable timestamp -> fail-safe reject):
        # this is the suspected double submit.
        return {"status": "duplicate"}

    # Stale lock from an earlier, distinct payment OUTSIDE the window. Reclaim
    # with a CAS delete keyed on the OBSERVED created_at, so only one of several
    # concurrent racers wins; the losers fall through to "duplicate".
    deleted = await db_handle.idempotency_keys.delete_one(
        {"_id": lock_id, "created_at": observed_created}
    )
    if deleted.deleted_count != 1:
        return {"status": "duplicate"}
    try:
        await db_handle.idempotency_keys.insert_one(_fresh_doc())
        return {"status": "acquired", "lock_id": lock_id}
    except DuplicateKeyError:
        return {"status": "duplicate"}
