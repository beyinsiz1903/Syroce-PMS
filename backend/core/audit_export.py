"""Cryptographically verifiable exports for the tenant audit timeline.

The export payload is intentionally a JSON evidence package rather than a
spreadsheet with an unprovable footer.  Consumers can recompute the payload
digest and verify the HMAC signature with the tenant's audit-export key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any


SIGNING_KEY_ENV = "AUDIT_EXPORT_SIGNING_KEY"
SIGNATURE_ALGORITHM = "HMAC-SHA256"


def canonical_json(value: Any) -> bytes:
    """Return stable UTF-8 bytes so an export has one unambiguous digest."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def signing_key() -> bytes | None:
    """Read the dedicated audit-export key without ever falling back to JWT."""
    value = os.environ.get(SIGNING_KEY_ENV, "").strip()
    return value.encode("utf-8") if value else None


def public_key_id(key: bytes) -> str:
    """Expose a non-secret key identifier for verification and rotation."""
    return hashlib.sha256(key).hexdigest()[:16]


def build_signed_export(
    *,
    tenant_id: str,
    actor_id: str,
    events: list[dict],
    filters: dict[str, Any],
    chain_status: dict[str, Any] | None = None,
    key: bytes | None = None,
) -> dict[str, Any]:
    """Create a signed, self-contained audit evidence package.

    ``events`` must already have passed timeline redaction.  The signature
    covers the exact payload returned to the caller, including selected
    filters and chain-verification result, so neither can be altered later
    without invalidating the package.
    """
    key = key or signing_key()
    if not key:
        raise RuntimeError(f"{SIGNING_KEY_ENV} is not configured")

    payload = {
        "schema": "syroce.audit-export.v1",
        "tenant_id": tenant_id,
        "exported_by": actor_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "filters": filters,
        "events": events,
        "chain_status": chain_status or {"available": False},
    }
    encoded = canonical_json(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    signature = hmac.new(key, encoded, hashlib.sha256).hexdigest()
    return {
        "payload": payload,
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": public_key_id(key),
            "payload_sha256": digest,
            "value": signature,
        },
    }


def verify_signed_export(package: dict[str, Any], key: bytes) -> bool:
    """Verify an exported package; useful to audit officers and tests."""
    payload = package.get("payload")
    signature = (package.get("signature") or {}).get("value")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return False
    encoded = canonical_json(payload)
    expected = hmac.new(key, encoded, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
