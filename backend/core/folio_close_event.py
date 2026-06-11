"""folio.closed.v1 e-Fatura readiness event — pure, Mongo-free helpers.

The PMS is the *authoritative data provider* for Turkish e-Fatura. When a folio
is closed we publish a REFERENCE-BASED event on the SXI bus: the envelope carries
ONLY identifiers, a light monetary summary and a signed, time-limited fetch URL.
NO guest PII ever crosses the bus — the ``generic_webhook`` adapter logs a request
excerpt into delivery records, so any PII in the envelope would leak there. The
middleware pulls the authoritative, decrypted invoice data from the signed fetch
endpoint instead.

Every function here is deterministic and free of database / event-loop
dependencies so it unit-tests without Mongo.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

EVENT_NAME = "folio.closed.v1"

# Default signed-URL lifetime: 72h. Override with FOLIO_FETCH_TTL_SECONDS.
_DEFAULT_TTL_SECONDS = 72 * 3600


class FetchSecretMissing(RuntimeError):
    """Raised (fail-closed) when no signing secret is configured."""


def _fetch_secret() -> bytes:
    """Resolve the HMAC signing secret. Fail-closed if none is configured."""
    secret = os.environ.get("FOLIO_FETCH_SECRET") or os.environ.get("JWT_SECRET")
    if not secret:
        raise FetchSecretMissing(
            "FOLIO_FETCH_SECRET/JWT_SECRET unset; refusing to sign folio fetch token"
        )
    return secret.encode("utf-8")


def fetch_ttl_seconds() -> int:
    """Signed-URL lifetime in seconds (env-overridable, positive only)."""
    raw = os.environ.get("FOLIO_FETCH_TTL_SECONDS")
    if not raw:
        return _DEFAULT_TTL_SECONDS
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SECONDS
    return val if val > 0 else _DEFAULT_TTL_SECONDS


def normalize_closed_at(value: Any) -> str:
    """Canonical string for a folio's ``closed_at`` across mixed storage types.

    Most close paths persist an ISO string; the mobile payment auto-close path
    persists a BSON ``datetime``. Normalizing keeps the ``message_id`` and the
    signed token stable regardless of how the value was stored.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_message_id(folio_id: str, closed_at_norm: str) -> str:
    """Stable idempotency key: a reopen/reclose yields a new closed_at => new id."""
    return f"{EVENT_NAME}:{folio_id}:{closed_at_norm}"


def _signing_payload(tenant_id: str, folio_id: str, closed_at_norm: str, exp_epoch: int) -> str:
    return f"{tenant_id}|{folio_id}|{closed_at_norm}|{exp_epoch}"


def sign_fetch_token(tenant_id: str, folio_id: str, closed_at_norm: str, exp_epoch: int) -> str:
    """Full 64-char HMAC-SHA256 hexdigest over the bound fetch parameters."""
    raw = _signing_payload(tenant_id, folio_id, closed_at_norm, exp_epoch)
    return hmac.new(_fetch_secret(), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def make_fetch_token(
    tenant_id: str,
    folio_id: str,
    closed_at_norm: str,
    *,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Return ``(token, exp_epoch)`` for a signed, time-limited fetch URL."""
    now_dt = now or datetime.now(UTC)
    ttl = ttl_seconds if (ttl_seconds and ttl_seconds > 0) else fetch_ttl_seconds()
    exp_epoch = int(now_dt.timestamp()) + ttl
    token = sign_fetch_token(tenant_id, folio_id, closed_at_norm, exp_epoch)
    return token, exp_epoch


def verify_fetch_token(
    token: str,
    *,
    tenant_id: str,
    folio_id: str,
    closed_at_norm: str,
    exp_epoch: Any,
    now: datetime | None = None,
) -> str:
    """Verify a fetch token. Returns ``'ok'`` | ``'expired'`` | ``'invalid'``.

    Signature is checked first (constant-time) so an attacker who tampers with
    ``exp`` or any bound field can never learn anything beyond ``'invalid'``.
    """
    now_dt = now or datetime.now(UTC)
    try:
        exp = int(exp_epoch)
    except (TypeError, ValueError):
        return "invalid"
    expected = sign_fetch_token(tenant_id, folio_id, closed_at_norm, exp)
    if not hmac.compare_digest(expected, token or ""):
        return "invalid"
    if int(now_dt.timestamp()) > exp:
        return "expired"
    return "ok"


def build_fetch_url(base_url: str, folio_id: str, tenant_id: str, exp_epoch: int, token: str) -> str:
    """Absolute signed URL the middleware calls to pull authoritative data."""
    base = (base_url or "").rstrip("/")
    qs = urlencode({"tenant_id": tenant_id, "exp": exp_epoch, "token": token})
    return f"{base}/api/public/finance/folio/{folio_id}/einvoice-data?{qs}"


def build_event_payload(
    folio: dict[str, Any],
    *,
    base_url: str,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the reference-based, PII-free SXI envelope payload for a closed folio."""
    folio_id = folio.get("id")
    tenant_id = folio.get("tenant_id")
    closed_at_norm = normalize_closed_at(folio.get("closed_at"))
    token, exp_epoch = make_fetch_token(
        tenant_id, folio_id, closed_at_norm, ttl_seconds=ttl_seconds, now=now
    )
    fetch_url = build_fetch_url(base_url, folio_id, tenant_id, exp_epoch, token)
    return {
        "event": EVENT_NAME,
        "folio_id": folio_id,
        "folio_number": folio.get("folio_number"),
        "booking_id": folio.get("booking_id"),
        "tenant_id": tenant_id,
        "folio_type": folio.get("folio_type"),
        "closed_at": closed_at_norm,
        "currency": folio.get("currency") or "TRY",
        "balance_at_close": folio.get("balance", 0.0),
        "fetch_url": fetch_url,
        "fetch_expires_at": datetime.fromtimestamp(exp_epoch, UTC).isoformat(),
    }
