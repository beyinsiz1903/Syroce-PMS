"""
Security — Sensitive Output Masking
Masks PII and sensitive fields in API responses.
"""
import re
from typing import Dict, Any, List

# Fields that should always be masked in output
_MASK_FIELDS = {
    "hashed_password", "password", "api_key", "api_secret",
    "secret_key", "token", "access_token", "refresh_token",
    "credit_card", "card_number", "cvv", "ssn", "id_number",
    "passport_number", "tax_id",
}

# Fields to partially mask (show last 4 chars)
_PARTIAL_MASK_FIELDS = {
    "email", "phone", "iban",
}


def mask_output(data: Any, depth: int = 0) -> Any:
    """Recursively mask sensitive fields in output data."""
    if depth > 8:
        return data
    if isinstance(data, dict):
        return {k: _mask_field(k, v, depth) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_output(item, depth + 1) for item in data]
    return data


def _mask_field(key: str, value: Any, depth: int) -> Any:
    key_lower = key.lower()
    if key_lower in _MASK_FIELDS:
        return "***MASKED***"
    if key_lower in _PARTIAL_MASK_FIELDS and isinstance(value, str) and len(value) > 4:
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    if isinstance(value, (dict, list)):
        return mask_output(value, depth + 1)
    return value
