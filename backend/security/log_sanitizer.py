"""
Security — Log Sanitizer
Filters sensitive data from logs before output.
"""
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Patterns to redact from logs
_SENSITIVE_PATTERNS = [
    (re.compile(r'(password|passwd|pwd|secret|token|api[_-]?key|authorization|bearer)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=***REDACTED***'),
    (re.compile(r'(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)'), '***EMAIL***'),
    (re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'), '***CARD***'),
    (re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'), '***PHONE***'),
    (re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'), '***JWT***'),
]

# Field names to redact in dict logs
_SENSITIVE_FIELDS = {
    "password", "hashed_password", "secret", "api_key", "token",
    "access_token", "refresh_token", "authorization", "credit_card",
    "card_number", "cvv", "ssn", "id_number",
}


def sanitize_string(text: str) -> str:
    """Redact sensitive data patterns from a string."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_dict(data: Dict[str, Any], *, depth: int = 0) -> Dict[str, Any]:
    """Redact sensitive fields from a dictionary (for structured logging)."""
    if depth > 5:
        return data

    sanitized = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_FIELDS:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, depth=depth + 1)
        elif isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(v, depth=depth + 1) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


def detect_secret_leakage(text: str) -> bool:
    """Check if a string contains what looks like leaked secrets."""
    indicators = [
        re.compile(r'AKIA[0-9A-Z]{16}'),             # AWS access key
        re.compile(r'sk-[a-zA-Z0-9]{48}'),            # OpenAI key
        re.compile(r'ghp_[A-Za-z0-9]{36}'),           # GitHub PAT
        re.compile(r'sk_live_[A-Za-z0-9]+'),          # Stripe live key
        re.compile(r'-----BEGIN (RSA )?PRIVATE KEY-----'),  # Private key
    ]
    for pattern in indicators:
        if pattern.search(text):
            return True
    return False
