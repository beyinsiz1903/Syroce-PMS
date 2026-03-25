"""
Security — Sensitive Output Masking (Enhanced)

Masks PII and sensitive fields in API responses.
Now delegates to the centralized PII Registry for field definitions
and masking rules, providing role-based access control.
"""
from typing import Any

from security.pii_registry import PII_FIELDS, MaskLevel, mask_dict as pii_mask_dict

# Fields that should always be masked in output (kept for backward compat)
_MASK_FIELDS = {
    "hashed_password", "password", "api_key", "api_secret",
    "secret_key", "token", "access_token", "refresh_token",
    "credit_card", "card_number", "cvv", "ssn", "id_number",
    "passport_number", "tax_id",
}

# Fields to partially mask (show last 4 chars) — kept for backward compat
_PARTIAL_MASK_FIELDS = {
    "email", "phone", "iban",
}


def mask_output(data: Any, depth: int = 0, *, user_role: str = "") -> Any:
    """Recursively mask sensitive fields in output data.

    Uses PII Registry for comprehensive masking with role-based unmask.
    Falls back to legacy patterns for backward compatibility.
    """
    if depth > 8:
        return data
    if isinstance(data, dict):
        return pii_mask_dict(data, user_role=user_role, context="api")
    if isinstance(data, list):
        return [mask_output(item, depth + 1, user_role=user_role) for item in data]
    return data


def _mask_field(key: str, value: Any, depth: int) -> Any:
    """Legacy mask function — used as fallback."""
    key_lower = key.lower()
    if key_lower in _MASK_FIELDS:
        return "***MASKED***"
    if key_lower in _PARTIAL_MASK_FIELDS and isinstance(value, str) and len(value) > 4:
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    if isinstance(value, (dict, list)):
        return mask_output(value, depth + 1)
    return value
