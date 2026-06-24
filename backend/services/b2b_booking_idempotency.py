"""
B2B booking idempotency — `Idempotency-Key` support for the B2B/agency reservation
create endpoint.

Additive and scoped to the B2B path: when a caller supplies an `Idempotency-Key`
header (UUID), a retry of the SAME request (e.g. after a network timeout) returns
the ORIGINAL result instead of creating a second booking. Callers that omit the
header keep the legacy behaviour (back-compatible, pilot_drift=0).

Storage: sysdb.b2b_idempotency_keys (alongside agency_api_keys / agency_contracts).
  - Unique index (tenant_id, agency_id, key) -> at-most-one record per logical request.
  - TTL index on `expires_at` auto-expires records after IDEMPOTENCY_TTL_SECONDS.

Doctrine: fail-closed on duplicate/conflict, never double-create, never weaken auth.
Business 4xx results are cached as `failed_final` (a same-key retry replays the same
deterministic error); unexpected 5xx drops the sentinel so a retry can re-attempt.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_system_db
from shared_kernel.idempotency import seal_response_body, unseal_response_body

logger = logging.getLogger(__name__)

COLLECTION = "b2b_idempotency_keys"
IDEMPOTENCY_TTL_SECONDS = 24 * 3600
# A "processing" sentinel older than this is treated as abandoned (the owning
# request crashed mid-flight) and may be taken over by a retry.
_PROCESSING_LOCK_SECONDS = 90
# In-flight collision: poll briefly for the owning request to reach a terminal
# state before giving up with 429.
_INFLIGHT_POLL_ATTEMPTS = 10
_INFLIGHT_POLL_INTERVAL = 0.4

_TERMINAL = ("succeeded", "failed_final")

_indexes_ready = False


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(dt: datetime | None) -> datetime | None:
    """Coerce a Mongo-read datetime to tz-aware UTC.

    Motor/pymongo return naive (UTC) datetimes by default, so a stored value read
    back cannot be compared directly against an aware ``_now()`` without raising
    ``TypeError: can't compare offset-naive and offset-aware datetimes``.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def compute_request_hash(tenant_id: str, agency_id: str, payload: dict) -> str:
    """Deterministic fingerprint of the logical request (tenant + agency + body)."""
    blob = json.dumps(
        {"t": tenant_id, "a": agency_id, "p": payload},
        sort_keys=True, default=str, separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).hexdigest()


async def _ensure_indexes(sysdb) -> None:
    """Init-once index guard (no per-request rebuild). Retried until it succeeds."""
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await sysdb[COLLECTION].create_index(
            [("tenant_id", 1), ("agency_id", 1), ("key", 1)],
            unique=True, name="uniq_b2b_idem_key",
        )
        await sysdb[COLLECTION].create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_b2b_idem",
        )
        # Durable double-create backstop on the bookings collection itself: the
        # sentinel above only serializes requests that observe each other. If a
        # slow original owner exceeds the _PROCESSING_LOCK_SECONDS lock, a retry
        # may take over (action="recover"), find no booking yet, and create one
        # while the original ALSO creates one. A unique constraint on the booking
        # row physically rejects the second insert (-> DuplicateKeyError ->
        # recover/replay). PARTIAL so it ONLY constrains B2B bookings carrying a
        # string key; non-B2B / keyless bookings are completely unaffected
        # (additive, pilot_drift=0 — the field is new in T001 so no existing row
        # collides at build time).
        await sysdb["bookings"].create_index(
            [("tenant_id", 1), ("agency_id", 1), ("b2b_idempotency_key", 1)],
            unique=True,
            name="uniq_b2b_booking_idem_key",
            partialFilterExpression={"b2b_idempotency_key": {"$type": "string"}},
        )
        _indexes_ready = True
    except Exception as exc:  # pragma: no cover - best effort, retried next call
        logger.warning("b2b idempotency index ensure deferred: %s", exc)


def _filter(tenant_id: str, agency_id: str, key: str) -> dict:
    return {"tenant_id": tenant_id, "agency_id": agency_id, "key": key}


async def _insert_sentinel(sysdb, tenant_id, agency_id, key, request_hash, now) -> bool:
    """Insert the processing sentinel. Returns True if we now own the key."""
    try:
        await sysdb[COLLECTION].insert_one({
            **_filter(tenant_id, agency_id, key),
            "request_hash": request_hash,
            "status": "processing",
            "response_body": None,
            "status_code": None,
            "booking_id": None,
            "created_at": now,
            "updated_at": now,
            "locked_until": now + timedelta(seconds=_PROCESSING_LOCK_SECONDS),
            "expires_at": now + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS),
        })
        return True
    except DuplicateKeyError:
        return False


async def begin(tenant_id: str, agency_id: str, key: str, payload: dict) -> dict:
    """Claim an idempotency key.

    Returns one of:
      {"action": "proceed"}                       -> caller owns a FRESH key, run the request
      {"action": "recover"}                       -> caller took over an ABANDONED
                                                     sentinel; a prior attempt may have
                                                     already created the booking, so the
                                                     caller MUST check for it before
                                                     creating a new one (no double-create)
      {"action": "replay", "status_code", "body"} -> return the stored result
      {"action": "conflict"}                      -> same key, different payload (409)
      {"action": "in_flight"}                     -> another request still processing (429)
    """
    sysdb = get_system_db()
    await _ensure_indexes(sysdb)
    request_hash = compute_request_hash(tenant_id, agency_id, payload)
    now = _now()

    if await _insert_sentinel(sysdb, tenant_id, agency_id, key, request_hash, now):
        return {"action": "proceed"}

    # Key already exists — inspect it (with brief polling for an in-flight owner).
    for attempt in range(_INFLIGHT_POLL_ATTEMPTS + 1):
        existing = await sysdb[COLLECTION].find_one(
            _filter(tenant_id, agency_id, key), {"_id": 0}
        )
        if existing is None:
            # Expired/cleaned between calls — try to take over with a fresh sentinel.
            now = _now()
            if await _insert_sentinel(sysdb, tenant_id, agency_id, key, request_hash, now):
                return {"action": "proceed"}
            continue
        if existing.get("request_hash") != request_hash:
            return {"action": "conflict"}
        status = existing.get("status")
        if status in _TERMINAL:
            return {
                "action": "replay",
                "status_code": existing.get("status_code") or 200,
                "body": unseal_response_body(existing),
            }
        # status == "processing": maybe stale (owner crashed) -> take over.
        now = _now()
        locked_until = _as_aware(existing.get("locked_until"))
        if locked_until is not None and locked_until < now:
            took_over = await sysdb[COLLECTION].find_one_and_update(
                {**_filter(tenant_id, agency_id, key), "status": "processing",
                 "locked_until": {"$lt": now}},
                {"$set": {"locked_until": now + timedelta(seconds=_PROCESSING_LOCK_SECONDS),
                          "updated_at": now}},
            )
            if took_over is not None:
                # We took over an ABANDONED processing sentinel (the previous owner
                # crashed). It may have created the booking before dying, so signal
                # the caller to look for an existing booking under this key BEFORE
                # creating a new one (no double-create). A fresh claim still returns
                # "proceed" above; only this takeover path returns "recover".
                return {"action": "recover"}
        if attempt < _INFLIGHT_POLL_ATTEMPTS:
            await asyncio.sleep(_INFLIGHT_POLL_INTERVAL)
    return {"action": "in_flight"}


async def finalize_success(tenant_id, agency_id, key, status_code, body, booking_id=None) -> None:
    sysdb = get_system_db()
    now = _now()
    try:
        await sysdb[COLLECTION].update_one(
            _filter(tenant_id, agency_id, key),
            {"$set": {
                "status": "succeeded",
                "status_code": status_code,
                # PII-at-rest: encrypted envelope only, never plaintext.
                **seal_response_body(body),
                "booking_id": booking_id,
                "updated_at": now,
                "expires_at": now + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS),
            }},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("b2b idempotency finalize_success failed (%s): %s", key, exc)


async def finalize_failure(tenant_id, agency_id, key, status_code, body, terminal: bool) -> None:
    sysdb = get_system_db()
    now = _now()
    try:
        if terminal:
            await sysdb[COLLECTION].update_one(
                _filter(tenant_id, agency_id, key),
                {"$set": {
                    "status": "failed_final",
                    "status_code": status_code,
                    # PII-at-rest: encrypted envelope only, never plaintext.
                    **seal_response_body(body),
                    "updated_at": now,
                    "expires_at": now + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS),
                }},
            )
        else:
            # Retryable (5xx/unexpected): drop the sentinel so a retry with the same
            # key can re-attempt cleanly.
            await sysdb[COLLECTION].delete_one(_filter(tenant_id, agency_id, key))
    except Exception as exc:  # pragma: no cover
        logger.warning("b2b idempotency finalize_failure failed (%s): %s", key, exc)
