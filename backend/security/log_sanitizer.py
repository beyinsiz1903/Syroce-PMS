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
    # HotelRunner callback secrets are path segments, not key-value pairs.
    (
        re.compile(
            r"(/api/(?:channel-manager/hotelrunner|integrations/hotelrunner)/(?:callback|webhooks/reservations)/)[^/?\s]+",
            re.IGNORECASE,
        ),
        r"\1***REDACTED***",
    ),
    # Auth/secret key-value pairs
    (re.compile(r"(username|user|password|passwd|pwd|secret|token|api[_-]?key|authorization|bearer)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    # Email
    (re.compile(r"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)"), "***EMAIL***"),
    # Credit card
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "***CARD***"),
    # Phone (international and local formats — avoid matching UUIDs by requiring non-hex context)
    (re.compile(r"(?<![0-9a-fA-F-])\+?\d{1,3}[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{2,4}(?![0-9a-fA-F-])"), "***PHONE***"),
    (re.compile(r"(?<![0-9a-fA-F-])\b\d{3}[-.]?\d{3}[-.]?\d{4}\b(?![0-9a-fA-F-])"), "***PHONE***"),
    # TC Kimlik (11-digit Turkish ID — avoid matching UUIDs)
    (re.compile(r"(?<![0-9a-fA-F-])\b\d{11}\b(?![0-9a-fA-F-])"), "***IDENTITY***"),
    # JWT tokens
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "***JWT***"),
    # AWS access key
    (re.compile(r"AKIA[0-9A-Z]{16}"), "***AWS_KEY***"),
    # OpenAI / API keys
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "***API_KEY***"),
    # GitHub PAT
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "***GITHUB_PAT***"),
    # Stripe keys
    (re.compile(r"sk_live_[A-Za-z0-9]+"), "***STRIPE_KEY***"),
    (re.compile(r"sk_test_[A-Za-z0-9]+"), "***STRIPE_TEST_KEY***"),
    # Private keys
    (re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"), "***PRIVATE_KEY***"),
    # IBAN (must start with 2 uppercase letters + 2 digits, min 15 chars)
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,28}\b"), "***IBAN***"),
    # Passport (common formats — careful to avoid generic matches)
    (re.compile(r"\b[A-Z]{1,2}\d{7,9}\b"), "***PASSPORT***"),
    # OpenAI key
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "***API_KEY***"),
    # MongoDB connection string
    (re.compile(r"mongodb(\+srv)?://[^\s]+"), "***MONGO_URI***"),
    # Generic connection string with password
    (re.compile(r"://[^:]+:[^@]+@"), "://***:***@"),
]

# Field names to fully redact in structured logs
_SENSITIVE_FIELDS: set[str] = set()


def _init_sensitive_fields():
    """Initialize sensitive fields from PII registry."""
    global _SENSITIVE_FIELDS
    # Base set
    _SENSITIVE_FIELDS = {
        "password",
        "username",
        "user",
        "hashed_password",
        "secret",
        "api_key",
        "api_secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "credit_card",
        "card_number",
        "cvv",
        "ssn",
        "id_number",
        "passport_number",
        "tax_id",
        "tc_kimlik",
        "national_id",
        "identity_number",
        "secret_key",
        "webhook_secret",
        "wsse_password",
        "payment_token",
        "account_number",
        "iban",
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
            sanitized[key] = [sanitize_dict(v, depth=depth + 1) if isinstance(v, dict) else sanitize_string(v) if isinstance(v, str) else v for v in value]
        else:
            sanitized[key] = value
    return sanitized


def detect_secret_leakage(text: str) -> bool:
    """Check if a string contains what looks like leaked secrets."""
    indicators = [
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"sk-[a-zA-Z0-9]{48}"),
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
        re.compile(r"sk_live_[A-Za-z0-9]+"),
        re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----"),
        re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
        re.compile(r"mongodb(\+srv)?://[^\s]+"),
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
        # Render before redaction. Sanitizing a %-style format template first
        # can remove placeholders such as ``user=%s`` while leaving the args
        # tuple intact, which makes the logging handler itself raise TypeError.
        # Rendering first also covers non-string arguments such as httpx.URL.
        try:
            rendered = record.getMessage()
        except Exception:
            return True
        sanitized = sanitize_string(rendered)
        if sanitized != rendered:
            record.msg = sanitized
            record.args = ()
        return True


def harden_logging() -> None:
    """Attach the PII/secret sanitizer to every root handler and silence the
    verbose third-party HTTP request logging that echoes full outbound URLs
    (including ``?token=...`` query params) at INFO level.

    Idempotent and safe to call from every process entry point — the FastAPI
    server (uvicorn) AND Celery workers — so scheduled connector calls (e.g.
    HotelRunner pulls) never leak credentials into worker logs either.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, SanitizedLogFilter) for f in handler.filters):
            handler.addFilter(SanitizedLogFilter())
    # httpx/httpcore log "HTTP Request: GET <full-url>" at INFO; our connectors
    # already log method+path without credentials, so drop these to WARNING.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
