
import hashlib
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
