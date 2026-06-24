"""
B2B agency auto-provisioning — shared logic (Seçenek B / approval model).

Single source of truth for:
  - Hotel-level "connect code" crypto + storage (sys_db.b2b_connect_codes).
    The connect code is a LOW-PRIVILEGE bootstrap secret: it can only file a
    connection request and poll its status — it can NEVER mint an API key.
  - One-time encrypted delivery of an issued API key on the connection-request
    document (sys_db.b2b_connection_requests).
  - The shared `mint_agency_api_key` helper reused by both the manual
    api_keys.py issuance endpoints and the connect-request approval flow, so a
    minted key has a single, audited shape.

Security invariants (see threat_model.md):
  - Raw connect code / raw API key are returned to the caller ONCE and never
    persisted in plaintext. The connect code is stored only as an HMAC; the
    delivered key is stored Fernet-encrypted and atomically read-once.
  - Tenant is ALWAYS resolved server-side (from the code hash or the JWT),
    never trusted from the request body.
  - Fail-closed: a missing JWT_SECRET raises rather than falling back to a
    hard-coded pepper.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from ._scope import _hash_api_key

logger = logging.getLogger(__name__)

CONNECT_CODE_PREFIX = "syroce_connect_"
# Default least-privilege scope for auto-provisioned agency keys. The hotel can
# widen/narrow this at approval time. Never default to unrestricted (None).
DEFAULT_AUTO_SCOPES = ["booking_engine", "webhooks"]

REQUEST_TTL_DAYS = 30          # full request record retention (TTL sweep)
KEY_DELIVERY_TTL_HOURS = 72    # window the agency app has to retrieve the key


# ── Crypto (derived from JWT_SECRET with domain separation, fail-closed) ──

def _secret_base() -> str:
    base = os.environ.get("JWT_SECRET", "")
    if not base:
        try:
            from core.security import JWT_SECRET as _RUNTIME_JWT_SECRET
            base = _RUNTIME_JWT_SECRET or ""
        except Exception:
            base = ""
    if not base:
        raise RuntimeError(
            "JWT_SECRET must be set for B2B connect-code provisioning"
        )
    return base


def _code_pepper() -> bytes:
    return hashlib.sha256(b"b2b-connect-code-v1|" + _secret_base().encode()).digest()


def hash_connect_code(raw_code: str) -> str:
    """Deterministic HMAC-SHA256 token for fast unique-index lookup."""
    return hmac.new(_code_pepper(), raw_code.encode(), hashlib.sha256).hexdigest()


def _key_fernet() -> Fernet:
    digest = hashlib.sha256(b"b2b-connect-key-v1|" + _secret_base().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_delivery_key(raw_key: str) -> str:
    return _key_fernet().encrypt(raw_key.encode()).decode()


def decrypt_delivery_key(token: str) -> str:
    try:
        return _key_fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("delivery key could not be decrypted (key mismatch)") from e


# ── Per-request delivery token (binds key retrieval to the creator) ──
#
# The connect code is a HOTEL-level shared bootstrap secret, so it must NOT be
# sufficient on its own to read a minted key. Each connection request also gets
# a high-entropy delivery token, returned to the creating agency app exactly
# once at create time; only its HMAC is persisted. Polling for status / key
# delivery requires this token, so a party that only knows the shared hotel
# connect code can never read (or race for) another agency's API key.

def _delivery_pepper() -> bytes:
    return hashlib.sha256(b"b2b-delivery-token-v1|" + _secret_base().encode()).digest()


def generate_delivery_token() -> str:
    """High-entropy per-request token. Returned to the caller ONCE."""
    return secrets.token_urlsafe(32)


def hash_delivery_token(raw_token: str) -> str:
    """Deterministic HMAC-SHA256 token for constant-time per-request matching."""
    return hmac.new(_delivery_pepper(), raw_token.encode(), hashlib.sha256).hexdigest()


# ── Small helpers ────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def normalize_agency_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _code_prefix(raw_code: str) -> str:
    return raw_code[:20] + "..."


# ── Connect code storage (sys_db.b2b_connect_codes) ──────────────

async def generate_connect_code(sysdb, tenant_id: str) -> dict:
    """Rotate (deactivate old + create new) the active connect code for a tenant.

    Returns the RAW code exactly once. Only the HMAC is persisted.
    """
    raw = CONNECT_CODE_PREFIX + secrets.token_urlsafe(32)
    now = _now_iso()
    await sysdb.b2b_connect_codes.update_many(
        {"tenant_id": tenant_id, "is_active": True},
        {"$set": {"is_active": False, "rotated_at": now}},
    )
    doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "code_hmac": hash_connect_code(raw),
        "code_prefix": _code_prefix(raw),
        "is_active": True,
        "created_at": now,
        "rotated_at": None,
    }
    await sysdb.b2b_connect_codes.insert_one(doc)
    return {"connect_code": raw, "code_prefix": doc["code_prefix"], "created_at": now}


async def ensure_connect_code_for_tenant(sysdb, tenant_id: str) -> dict | None:
    """Create a connect code for a tenant that has none. Returns raw code (once)
    or None when one already exists. Used by the tenant-creation hook only —
    NEVER call this from a GET handler (would mutate on read)."""
    existing = await sysdb.b2b_connect_codes.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 1}
    )
    if existing:
        return None
    return await generate_connect_code(sysdb, tenant_id)


async def resolve_tenant_from_code(sysdb, raw_code: str | None) -> str | None:
    """Resolve the owning tenant_id from a raw connect code, or None.

    Tenant identity comes ONLY from this lookup, never from the request body.
    """
    if not raw_code or not raw_code.strip():
        return None
    doc = await sysdb.b2b_connect_codes.find_one(
        {"code_hmac": hash_connect_code(raw_code.strip()), "is_active": True},
        {"_id": 0, "tenant_id": 1},
    )
    return doc["tenant_id"] if doc else None


async def get_connect_info(sysdb, tenant_id: str) -> dict:
    """Read-only status of a tenant's connect code (no raw value, no mutation)."""
    doc = await sysdb.b2b_connect_codes.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not doc:
        return {"has_active_code": False, "code_prefix": None, "created_at": None}
    return {
        "has_active_code": True,
        "code_prefix": doc.get("code_prefix"),
        "created_at": doc.get("created_at"),
    }


# ── Shared API-key issuance (single source of truth) ─────────────

async def mint_agency_api_key(
    db_handle, tenant_id: str, agency: dict, scopes, created_by: str | None
) -> tuple[str, dict]:
    """Generate + persist an agency API key. Returns (raw_key, stored_doc).

    `db_handle` is the collection owner (scoped `db` under a JWT request, or
    `get_system_db()` under code-auth) — both resolve to the same physical
    agency_api_keys collection. Caller owns the 409/agency-lookup checks.
    """
    raw_key = f"syroce_b2b_{secrets.token_urlsafe(32)}"
    key_doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "agency_id": agency["id"],
        "agency_name": agency.get("name", ""),
        "key_hash": _hash_api_key(raw_key),
        "key_prefix": raw_key[:16] + "...",
        "scopes": scopes,
        "is_active": True,
        "usage_count": 0,
        "created_at": _now_iso(),
        "created_by": created_by,
        "last_used_at": None,
    }
    await db_handle.agency_api_keys.insert_one(key_doc)
    key_doc.pop("_id", None)
    return raw_key, key_doc
