"""Shared JSON-safe coercion helpers for list/detail API responses.

FastAPI serializes a handler's return value OUTSIDE the handler body, so a
single non-JSON-native field (BSON ``Decimal128``, ``ObjectId``, encrypted-field
``bytes``, naive ``datetime``, or a legacy ``str`` timestamp mixed with new
``datetime`` ones) on any returned row surfaces as an unhandled 500 at the
encode step — which a handler-local ``try/except`` cannot catch.

These helpers coerce a payload into JSON-native types so the response is
total-serializable. Binary/encrypted blobs are REDACTED (never base64-exposed),
so this is not a PII-disclosure path.

The pattern was first proven inline in ``routers/audit_timeline.py`` (Audit
Timeline P1 fix); this module is the shared, reusable form applied to the other
audit/list surfaces (``/security/audit-logs``, ``/hr/staff``) that returned raw
Mongo documents.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from bson import ObjectId
from bson.decimal128 import Decimal128


def ts_to_iso(ts) -> str:
    """Normalize a mixed-type timestamp (str | datetime | None | other) to a
    safe ISO string. Legacy rows store ``timestamp`` as an ISO string; newer
    rows store a BSON ``datetime``. Returns "" for None and a defensive
    ``str(...)`` fallback for unexpected types (dict cursor leaks, numbers)."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, datetime):
        try:
            return ts.isoformat()
        except Exception:
            return str(ts)
    return str(ts)


def json_safe(value):
    """Recursively coerce a Mongo document into JSON-native types.

    datetime/date -> ISO string; Decimal128 -> str; Decimal -> float;
    bytes/bytearray -> "<binary>" (redacted, never base64-exposed);
    ObjectId -> str; dict/list recurse; anything else -> str().
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, Decimal128):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return "<binary>"
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return str(value)
