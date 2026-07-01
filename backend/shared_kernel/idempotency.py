import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)

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


# ── Response-body PII-at-rest sealing ────────────────────────────────────────
#
# The replay cache persists a completed request's response body so a retry with
# the same Idempotency-Key gets the identical answer. Those bodies can carry
# guest PII (booking dicts: name/e-mail/phone) and financial detail, so we never
# store them as plaintext. `seal_response_body` encrypts the WHOLE body as one
# opaque envelope (whole-blob, NOT field redaction, so replay is byte-faithful);
# `unseal_response_body` reverses it and dual-reads any legacy plaintext rows
# written before at-rest sealing existed (those age out via the 24h TTL).
#
# These two helpers are the single source of truth and are reused by every
# writer/reader of an idempotency response body (this module's central
# complete/claim, the per-domain repositories under modules/*, and the B2B
# idempotency store) so the guarantee holds everywhere, not just here.
RESPONSE_BODY_ENC_FIELD = "response_body_enc"
RESPONSE_BODY_PLAINTEXT_FIELD = "response_body"
_CRYPTO_ENVELOPE_PREFIXES = ("SYR1:", "aes256gcm:")


def _get_crypto_service():
    try:
        from core.crypto.service import get_crypto_service

        return get_crypto_service()
    except Exception:  # pragma: no cover - crypto subsystem import/init failure
        return None


def seal_response_body(response_body: Any) -> dict[str, Any]:
    """Return the persisted ``$set`` fragment for a response body, PII-encrypted.

    Serialises the body with ``jsonable_encoder`` first (so datetimes/enums/
    Decimals match the wire shape FastAPI produces on the fresh path, keeping
    replay faithful), then encrypts the JSON as a single envelope. On success
    returns ``{RESPONSE_BODY_ENC_FIELD: <envelope>}``.

    Fail-closed: if crypto is unavailable, raises, or hands back a NON-envelope
    value (the ``CRYPTO_BYPASS_ALLOWED`` break-glass mode returns *plaintext*
    without raising), we return ``{}`` so plaintext PII is NEVER written. The
    cost is a degraded replay (an empty body / 409 on a later retry), never a
    leak. Never raises — some callers run this AFTER the durable write (outside
    their try/except), so a raise here would 500 an operation that succeeded.
    """
    try:
        crypto = _get_crypto_service()
        if crypto is None:
            logger.warning("idempotency: crypto unavailable; response body not cached")
            return {}
        blob = json.dumps(
            jsonable_encoder(response_body),
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
        cipher = crypto.encrypt(blob)
    except Exception:
        logger.warning("idempotency: response body seal failed; not cached")
        return {}
    if not isinstance(cipher, str) or not cipher.startswith(_CRYPTO_ENVELOPE_PREFIXES):
        # Break-glass bypass / misconfig returned plaintext -> refuse to persist.
        logger.warning("idempotency: crypto returned non-envelope; body not cached")
        return {}
    return {RESPONSE_BODY_ENC_FIELD: cipher}


def unseal_response_body(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Recover a replay response body from a stored idempotency row.

    Dual-read: prefers the encrypted envelope; falls back to any legacy
    plaintext ``response_body`` (rows written before sealing existed); returns
    ``{}`` when neither is usable (incl. a row completed while crypto was down).
    Never raises.
    """
    if not doc:
        return {}
    enc = doc.get(RESPONSE_BODY_ENC_FIELD)
    if isinstance(enc, str) and enc:
        try:
            crypto = _get_crypto_service()
            if crypto is None:
                logger.warning("idempotency: crypto unavailable; cannot unseal replay body")
                return {}
            return json.loads(crypto.decrypt(enc))
        except Exception:
            logger.warning("idempotency: response body unseal failed")
            return {}
    legacy = doc.get(RESPONSE_BODY_PLAINTEXT_FIELD)
    return legacy if isinstance(legacy, dict) else {}


async def claim_idempotency(
    db_handle,
    *,
    tenant_id: str,
    scope: str,
    idempotency_key: str,
    request_hash: str | None = None,
) -> dict[str, Any]:
    """Atomically claim an idempotency slot.

    Returns either:
      - {"status": "acquired", "lock_id": ...} on first claim
      - {"status": "replay", "response": {...}} if the same key already
        completed (caller should return the cached response verbatim)
      - {"status": "in_flight"} if another request is still processing the key
      - {"status": "mismatch"} if the SAME key was already claimed with a
        DIFFERENT ``request_hash`` (caller should reject with 409). Only ever
        returned when the caller supplies ``request_hash``; legacy callers that
        omit it (e.g. folio mutations) never see this branch, so their
        behaviour is byte-identical to before this parameter existed.

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
    if request_hash is not None:
        doc["request_hash"] = request_hash
    try:
        await db_handle.idempotency_keys.insert_one(doc)
        return {"status": "acquired", "lock_id": lock_id}
    except DuplicateKeyError:
        existing = await db_handle.idempotency_keys.find_one({"_id": lock_id}, {"_id": 0})
        # Payload-mismatch guard: only when THIS caller supplied a hash AND the
        # stored slot carries a (different) hash. Never trips for legacy callers
        # that pass no hash, and never trips against a legacy slot with no stored
        # hash — keeping older scopes backward compatible.
        if existing and request_hash is not None:
            existing_hash = existing.get("request_hash")
            if existing_hash is not None and existing_hash != request_hash:
                return {"status": "mismatch"}
        if existing and existing.get("status") == "completed":
            return {"status": "replay", "response": unseal_response_body(existing)}
        return {"status": "in_flight"}


async def complete_idempotency(
    db_handle,
    *,
    lock_id: str,
    response_body: dict[str, Any],
    session=None,
) -> None:
    now = datetime.now(UTC)
    set_fields = {
        "status": "completed",
        "completed_at": now.isoformat(),
        # Push expiry out to the replay-retention window so the cached
        # response survives client retries but still gets swept eventually.
        "expires_at": now + timedelta(seconds=IDEMPOTENCY_RETENTION_SECONDS),
    }
    # PII-at-rest: store the body only as an encrypted envelope. On crypto
    # failure `seal_response_body` returns {} (no plaintext written) and the
    # replay degrades to an empty body rather than leaking.
    set_fields.update(seal_response_body(response_body))
    # session verilirse completion, çağıranın transaction'ına dahil edilir;
    # böylece "yazımlar commit" ⟺ "key completed" atomik olur (çifte-charge
    # penceresi yapısal olarak kapanır). Verilmezse mevcut davranış (best-effort).
    await db_handle.idempotency_keys.update_one(
        {"_id": lock_id},
        {"$set": set_fields},
        session=session,
    )


async def release_idempotency(db_handle, *, lock_id: str, error: str | None = None) -> None:
    """Drop a processing lock so the caller can retry.

    Used when the protected operation raised before producing a stable result.
    We delete (not mark failed) because the caller's intent is "let me try
    again with the same key"; keeping a 'failed' marker would block retries.
    """
    await db_handle.idempotency_keys.delete_one({"_id": lock_id})


# ── High-level request-replay guard (header-gated, additive) ─────────────────
#
# claim/complete/release above are the low-level primitives (used inline by the
# folio mutation endpoints). `begin_idempotency` packages them into the canonical
# request-replay flow so reservation-creation endpoints can adopt it uniformly:
#
#   guard, replay = await begin_idempotency(db, request, tenant_id=..., scope=...,
#                                           payload=body.model_dump())
#   if replay is not None:
#       return replay
#   try:
#       result = ...                      # do the work
#       await guard.complete(result)
#       return result
#   except HTTPException:
#       await guard.release()             # ONLY safe before the first durable write
#       raise
#
# The whole thing is a NO-OP when the request carries no Idempotency-Key header:
# `guard.active` is False, `complete`/`release` do nothing, and `replay` is None,
# so the caller falls through to its existing, byte-identical behaviour.


def build_request_hash(payload: Any) -> str:
    """Stable SHA-256 of a request payload for the payload-mismatch guard.

    Canonicalises via sorted-key JSON (``default=str`` so dates/Decimals/enums
    serialise) so semantically-equal bodies hash equal and a reused key with a
    different body is detected. Returns the empty-dict hash for ``None``.
    """
    canonical = json.dumps(payload if payload is not None else {}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _IdempotencyGuard:
    """Handle returned by `begin_idempotency`.

    When inactive (no header) `lock_id` is None and complete/release are no-ops.
    """

    __slots__ = ("_db", "lock_id", "_closed")

    def __init__(self, db_handle, lock_id: str | None):
        self._db = db_handle
        self.lock_id = lock_id
        self._closed = False

    @property
    def active(self) -> bool:
        return self.lock_id is not None

    async def complete(self, response_body: Any) -> None:
        # Only cache dict responses (BSON-storable, replayable verbatim).
        if self.lock_id and not self._closed and isinstance(response_body, dict):
            await complete_idempotency(self._db, lock_id=self.lock_id, response_body=response_body)
            self._closed = True

    async def release(self, error: str | None = None) -> None:
        if self.lock_id and not self._closed:
            await release_idempotency(self._db, lock_id=self.lock_id, error=error)
            self._closed = True


async def begin_idempotency(
    db_handle,
    request: Request,
    *,
    tenant_id: str,
    scope: str,
    payload: Any = None,
) -> tuple[_IdempotencyGuard, dict[str, Any] | None]:
    """Begin a header-gated request-replay flow.

    Returns ``(guard, replay)``:
      - No Idempotency-Key header  -> (inactive guard, None): caller proceeds normally.
      - Key seen, first time       -> (active guard, None): caller does the work then
                                       calls ``guard.complete(result)``.
      - Key seen, already completed-> (inactive guard, cached_response): caller returns it.

    Raises 409 when another request with the same key is still in flight, or when
    the same key was already used with a different ``payload`` (mismatch).
    """
    key = get_idempotency_key(request)
    if not key:
        return _IdempotencyGuard(db_handle, None), None

    request_hash = build_request_hash(payload) if payload is not None else None
    claim = await claim_idempotency(
        db_handle,
        tenant_id=tenant_id,
        scope=scope,
        idempotency_key=key,
        request_hash=request_hash,
    )
    claim_status = claim.get("status")
    if claim_status == "replay":
        return _IdempotencyGuard(db_handle, None), claim.get("response") or {}
    if claim_status == "in_flight":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
        )
    if claim_status == "mismatch":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key already used with a different payload",
        )
    return _IdempotencyGuard(db_handle, claim["lock_id"]), None


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

    window = window_seconds if window_seconds is not None else payment_dedup_window_seconds()
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
            "expires_at": now + timedelta(seconds=max(window, IDEMPOTENCY_PROCESSING_GRACE_SECONDS)),
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
    deleted = await db_handle.idempotency_keys.delete_one({"_id": lock_id, "created_at": observed_created})
    if deleted.deleted_count != 1:
        return {"status": "duplicate"}
    try:
        await db_handle.idempotency_keys.insert_one(_fresh_doc())
        return {"status": "acquired", "lock_id": lock_id}
    except DuplicateKeyError:
        return {"status": "duplicate"}
