"""
Security — Log Sanitizer (Enhanced)

Filters sensitive data from ALL log output:
  - Application logs
  - Error payloads / stack traces
  - Timeline events
  - Failure tracker entries
  - Webhook raw payloads
  - Sandbox dashboard data
  - Incident payloads
  - Reconciliation diff screens

Uses the PII Registry as the source of truth for field detection,
plus regex patterns for free-text PII scrubbing.
"""
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Regex patterns for free-text PII detection ──────────────────────

_SENSITIVE_PATTERNS = [
    # Auth/secret key-value pairs
    (re.compile(r'(password|passwd|pwd|secret|token|api[_-]?key|authorization|bearer)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=***REDACTED***'),
    # Email
    (re.compile(r'(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)'), '***EMAIL***'),
    # Credit card
    (re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'), '***CARD***'),
    # Phone (international and local formats — avoid matching UUIDs by requiring non-hex context)
    (re.compile(r'(?<![0-9a-fA-F-])\+?\d{1,3}[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{2,4}(?![0-9a-fA-F-])'), '***PHONE***'),
    (re.compile(r'(?<![0-9a-fA-F-])\b\d{3}[-.]?\d{3}[-.]?\d{4}\b(?![0-9a-fA-F-])'), '***PHONE***'),
    # TC Kimlik (11-digit Turkish ID — avoid matching UUIDs)
    (re.compile(r'(?<![0-9a-fA-F-])\b\d{11}\b(?![0-9a-fA-F-])'), '***IDENTITY***'),
    # JWT tokens
    (re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'), '***JWT***'),
    # AWS access key
    (re.compile(r'AKIA[0-9A-Z]{16}'), '***AWS_KEY***'),
    # OpenAI / API keys
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), '***API_KEY***'),
    # GitHub PAT
    (re.compile(r'ghp_[A-Za-z0-9]{36}'), '***GITHUB_PAT***'),
    # Stripe keys
    (re.compile(r'sk_live_[A-Za-z0-9]+'), '***STRIPE_KEY***'),
    (re.compile(r'sk_test_[A-Za-z0-9]+'), '***STRIPE_TEST_KEY***'),
    # Private keys
    (re.compile(r'-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----'), '***PRIVATE_KEY***'),
    # IBAN (must start with 2 uppercase letters + 2 digits, min 15 chars)
    (re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,28}\b'), '***IBAN***'),
    # Passport (common formats — careful to avoid generic matches)
    (re.compile(r'\b[A-Z]{1,2}\d{7,9}\b'), '***PASSPORT***'),
    # Emergent key
    (re.compile(r'sk-emergent-[a-zA-Z0-9]+'), '***EMERGENT_KEY***'),
    # MongoDB connection string
    (re.compile(r'mongodb(\+srv)?://[^\s]+'), '***MONGO_URI***'),
    # Generic connection string with password
    (re.compile(r'://[^:]+:[^@]+@'), '://***:***@'),
]

# Field names to fully redact in structured logs
_SENSITIVE_FIELDS: set[str] = set()


def _init_sensitive_fields():
    """Initialize sensitive fields from PII registry."""
    global _SENSITIVE_FIELDS
    # Base set
    _SENSITIVE_FIELDS = {
        "password", "hashed_password", "secret", "api_key", "api_secret",
        "token", "access_token", "refresh_token", "authorization",
        "credit_card", "card_number", "cvv", "ssn", "id_number",
        "passport_number", "tax_id", "tc_kimlik", "national_id",
        "identity_number", "secret_key", "webhook_secret", "wsse_password",
        "payment_token", "account_number", "iban",
    }
    # Merge from PII registry
    try:
        from security.pii_registry import PII_FIELDS
        _SENSITIVE_FIELDS.update(PII_FIELDS.keys())
    except ImportError:
        pass


_init_sensitive_fields()


def sanitize_string(text: str) -> str:
    """Redact sensitive data patterns from a string."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_dict(data: dict[str, Any], *, depth: int = 0) -> dict[str, Any]:
    """Redact sensitive fields from a dictionary (for structured logging)."""
    if depth > 8:
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
                sanitize_dict(v, depth=depth + 1) if isinstance(v, dict)
                else sanitize_string(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


def detect_secret_leakage(text: str) -> bool:
    """Check if a string contains what looks like leaked secrets."""
    indicators = [
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'sk-[a-zA-Z0-9]{48}'),
        re.compile(r'ghp_[A-Za-z0-9]{36}'),
        re.compile(r'sk_live_[A-Za-z0-9]+'),
        re.compile(r'-----BEGIN (RSA )?PRIVATE KEY-----'),
        re.compile(r'sk-emergent-[a-zA-Z0-9]+'),
        re.compile(r'mongodb(\+srv)?://[^\s]+'),
    ]
    for pattern in indicators:
        if pattern.search(text):
            return True
    return False


class SanitizedLogFilter(logging.Filter):
    """Logging filter that automatically sanitizes log messages.

    Attach this to any logger/handler to strip PII from all output:
        handler.addFilter(SanitizedLogFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize_string(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True
