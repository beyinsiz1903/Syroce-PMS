
import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

IDEMPOTENCY_HEADER = "Idempotency-Key"


def normalize_idempotency_key(key: str | None) -> str | None:
    if not key:
        return None
    normalized = key.strip()
    return normalized or None


def get_idempotency_key(request: Request) -> str | None:
    return normalize_idempotency_key(request.headers.get(IDEMPOTENCY_HEADER))


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
    doc = {
        "_id": lock_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "idempotency_key": idempotency_key,
        "status": "processing",
        "created_at": datetime.now(UTC).isoformat(),
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
    await db_handle.idempotency_keys.update_one(
        {"_id": lock_id},
        {"$set": {
            "status": "completed",
            "response_body": response_body,
            "completed_at": datetime.now(UTC).isoformat(),
        }},
    )


async def release_idempotency(db_handle, *, lock_id: str, error: str | None = None) -> None:
    """Drop a processing lock so the caller can retry.

    Used when the protected operation raised before producing a stable result.
    We delete (not mark failed) because the caller's intent is "let me try
    again with the same key"; keeping a 'failed' marker would block retries.
    """
    await db_handle.idempotency_keys.delete_one({"_id": lock_id})
