"""
PII Registry — Central PII field definitions and masking rules.

This is the SINGLE SOURCE OF TRUTH for:
  - Which fields are PII
  - How each field should be masked
  - Who can see unmasked values (role-based)
  - What appears in logs vs API responses

Masking policy levels:
  FULL     — completely redacted, e.g. "***REDACTED***"
  PARTIAL  — show first/last chars, e.g. "jo***@e***om"
  HASH     — show SHA-256 prefix for correlation, e.g. "sha256:a1b2c3..."
  NONE     — no masking (non-PII or authorized viewer)
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum


class MaskLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    HASH = "hash"
    NONE = "none"


class PIICategory(str, Enum):
    """PII field categories for classification and reporting."""

    IDENTITY = "identity"  # TC kimlik, pasaport, vergi no
    CONTACT = "contact"  # email, telefon, adres
    FINANCIAL = "financial"  # kredi kartı, IBAN, ödeme bilgileri
    AUTHENTICATION = "authentication"  # password, token, API key
    HEALTH = "health"  # sağlık bilgileri
    LOCATION = "location"  # adres, konum
    PERSONAL = "personal"  # isim, doğum tarihi


class SecretType(str, Enum):
    """Secret classification — each type has its own lifecycle."""

    JWT_APP = "jwt_app"  # JWT signing keys, app secrets
    CONNECTOR_CREDENTIAL = "connector"  # Channel manager provider credentials
    WEBHOOK_SECRET = "webhook"  # Webhook signing/verification secrets
    ENCRYPTION_KEY = "encryption"  # Master encryption keys, key material
    THIRD_PARTY_API = "third_party"  # External API keys (Stripe, etc.)
    DATABASE = "database"  # DB connection strings, passwords
    INTERNAL = "internal"  # Internal service-to-service tokens


@dataclass(frozen=True)
class PIIFieldRule:
    """Masking rule for a single PII field."""

    field_name: str
    category: PIICategory
    default_mask: MaskLevel = MaskLevel.FULL
    log_mask: MaskLevel = MaskLevel.FULL
    visible_prefix: int = 0
    visible_suffix: int = 0
    unmask_roles: frozenset[str] = field(default_factory=lambda: frozenset({"super_admin"}))
    description: str = ""


# ── PII Field Registry ─────────────────────────────────────────────

PII_FIELDS: dict[str, PIIFieldRule] = {}


def _register(*rules: PIIFieldRule) -> None:
    for rule in rules:
        PII_FIELDS[rule.field_name] = rule


# Identity
_register(
    PIIFieldRule("tc_kimlik", PIICategory.IDENTITY, description="TC Kimlik No"),
    PIIFieldRule("id_number", PIICategory.IDENTITY, description="National ID"),
    PIIFieldRule("passport_number", PIICategory.IDENTITY, description="Passport number"),
    PIIFieldRule("tax_id", PIICategory.IDENTITY, description="Tax ID"),
    PIIFieldRule("ssn", PIICategory.IDENTITY, description="Social Security Number"),
    PIIFieldRule("national_id", PIICategory.IDENTITY, description="National ID"),
    PIIFieldRule("identity_number", PIICategory.IDENTITY, description="Identity number"),
)

# Contact — partial mask by default
_register(
    PIIFieldRule(
        "email", PIICategory.CONTACT, default_mask=MaskLevel.PARTIAL, visible_prefix=2, visible_suffix=2, unmask_roles=frozenset({"super_admin", "admin", "front_desk"}), description="Email address"
    ),
    PIIFieldRule(
        "phone", PIICategory.CONTACT, default_mask=MaskLevel.PARTIAL, visible_prefix=0, visible_suffix=4, unmask_roles=frozenset({"super_admin", "admin", "front_desk"}), description="Phone number"
    ),
    PIIFieldRule(
        "phone_number",
        PIICategory.CONTACT,
        default_mask=MaskLevel.PARTIAL,
        visible_prefix=0,
        visible_suffix=4,
        unmask_roles=frozenset({"super_admin", "admin", "front_desk"}),
        description="Phone number",
    ),
    PIIFieldRule(
        "mobile", PIICategory.CONTACT, default_mask=MaskLevel.PARTIAL, visible_prefix=0, visible_suffix=4, unmask_roles=frozenset({"super_admin", "admin", "front_desk"}), description="Mobile number"
    ),
    PIIFieldRule("address", PIICategory.CONTACT, default_mask=MaskLevel.FULL, unmask_roles=frozenset({"super_admin", "admin"}), description="Address"),
    PIIFieldRule(
        "guest_email",
        PIICategory.CONTACT,
        default_mask=MaskLevel.PARTIAL,
        visible_prefix=2,
        visible_suffix=2,
        unmask_roles=frozenset({"super_admin", "admin", "front_desk"}),
        description="Guest email",
    ),
    PIIFieldRule(
        "guest_phone",
        PIICategory.CONTACT,
        default_mask=MaskLevel.PARTIAL,
        visible_prefix=0,
        visible_suffix=4,
        unmask_roles=frozenset({"super_admin", "admin", "front_desk"}),
        description="Guest phone",
    ),
)

# Financial — always full mask
_register(
    PIIFieldRule("credit_card", PIICategory.FINANCIAL, description="Credit card number"),
    PIIFieldRule("card_number", PIICategory.FINANCIAL, description="Card number"),
    PIIFieldRule("cvv", PIICategory.FINANCIAL, description="CVV"),
    PIIFieldRule("iban", PIICategory.FINANCIAL, default_mask=MaskLevel.PARTIAL, visible_suffix=4, description="IBAN"),
    PIIFieldRule("account_number", PIICategory.FINANCIAL, description="Bank account"),
    PIIFieldRule("payment_token", PIICategory.FINANCIAL, description="Payment token"),
)

# Authentication — always full mask, never unmask via API
_register(
    PIIFieldRule("password", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Password"),
    PIIFieldRule("hashed_password", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Hashed password"),
    PIIFieldRule("api_key", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="API key"),
    PIIFieldRule("api_secret", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="API secret"),
    PIIFieldRule("secret_key", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Secret key"),
    PIIFieldRule("token", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Auth token"),
    PIIFieldRule("access_token", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Access token"),
    PIIFieldRule("refresh_token", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Refresh token"),
    PIIFieldRule("authorization", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Authorization header"),
    PIIFieldRule("wsse_password", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="WSSE password"),
    PIIFieldRule("webhook_secret", PIICategory.AUTHENTICATION, unmask_roles=frozenset(), description="Webhook secret"),
)


# ── Masking Functions ──────────────────────────────────────────────


def mask_value(value: str, rule: PIIFieldRule, *, user_role: str = "") -> str:
    """Apply masking to a value based on its PII rule and the viewer's role."""
    if not value or not isinstance(value, str):
        return "***"

    # Check if user has unmask permission
    if user_role and user_role in rule.unmask_roles:
        return value

    level = rule.default_mask

    if level == MaskLevel.NONE:
        return value
    if level == MaskLevel.FULL:
        return "***REDACTED***"
    if level == MaskLevel.HASH:
        h = hashlib.sha256(value.encode()).hexdigest()[:12]
        return f"sha256:{h}"
    if level == MaskLevel.PARTIAL:
        return _partial_mask(value, rule.visible_prefix, rule.visible_suffix)

    return "***REDACTED***"


def mask_for_log(value: str, rule: PIIFieldRule) -> str:
    """Mask a value for log output — always use log_mask level, never unmask."""
    if not value or not isinstance(value, str):
        return "***"

    level = rule.log_mask
    if level == MaskLevel.FULL:
        return "***REDACTED***"
    if level == MaskLevel.HASH:
        h = hashlib.sha256(value.encode()).hexdigest()[:12]
        return f"sha256:{h}"
    if level == MaskLevel.PARTIAL:
        return _partial_mask(value, rule.visible_prefix, rule.visible_suffix)
    return "***REDACTED***"


def _partial_mask(value: str, prefix: int, suffix: int) -> str:
    """Show prefix/suffix characters, mask the rest."""
    if len(value) <= (prefix + suffix + 2):
        return "*" * len(value)
    hidden = len(value) - prefix - suffix
    return value[:prefix] + "*" * hidden + value[-suffix:] if suffix > 0 else value[:prefix] + "*" * hidden


def mask_dict(
    data: dict,
    *,
    user_role: str = "",
    context: str = "api",
    depth: int = 0,
) -> dict:
    """Recursively mask PII fields in a dictionary.

    Args:
        data: Dictionary to mask.
        user_role: Role of the requesting user (for role-based unmask).
        context: "api" for API responses, "log" for log output.
        depth: Recursion depth guard.
    """
    if depth > 10:
        return data

    masked = {}
    for key, value in data.items():
        key_lower = key.lower()
        rule = PII_FIELDS.get(key_lower)

        if rule:
            if isinstance(value, str):
                if context == "log":
                    masked[key] = mask_for_log(value, rule)
                else:
                    masked[key] = mask_value(value, rule, user_role=user_role)
            elif value is None:
                masked[key] = None
            else:
                masked[key] = "***REDACTED***"
        elif isinstance(value, dict):
            masked[key] = mask_dict(value, user_role=user_role, context=context, depth=depth + 1)
        elif isinstance(value, list):
            masked[key] = [mask_dict(item, user_role=user_role, context=context, depth=depth + 1) if isinstance(item, dict) else item for item in value]
        else:
            masked[key] = value

    return masked


# ── PII Detection in Free Text ─────────────────────────────────────

_PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "***EMAIL***"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "***CARD***"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "***PHONE***"),
    (re.compile(r"\b\d{11}\b"), "***IDENTITY***"),  # TC Kimlik
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "***JWT***"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "***AWS_KEY***"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "***API_KEY***"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "***GITHUB_PAT***"),
    (re.compile(r"sk_live_[A-Za-z0-9]+"), "***STRIPE_KEY***"),
    (re.compile(r"-----BEGIN (RSA )?PRIVATE KEY-----"), "***PRIVATE_KEY***"),
]


def scrub_text(text: str) -> str:
    """Remove PII patterns from free-form text (for logs, error messages, payloads)."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ── Secret Classification Lifecycle ────────────────────────────────

SECRET_LIFECYCLE: dict[SecretType, dict] = {
    SecretType.JWT_APP: {
        "rotation_max_days": 365,
        "rotation_warning_days": 300,
        "auto_rotation": False,
        "requires_restart": True,
        "backup_required": True,
    },
    SecretType.CONNECTOR_CREDENTIAL: {
        "rotation_max_days": 90,
        "rotation_warning_days": 60,
        "auto_rotation": False,
        "requires_restart": False,
        "backup_required": True,
    },
    SecretType.WEBHOOK_SECRET: {
        "rotation_max_days": 180,
        "rotation_warning_days": 150,
        "auto_rotation": False,
        "requires_restart": False,
        "backup_required": True,
    },
    SecretType.ENCRYPTION_KEY: {
        "rotation_max_days": 365,
        "rotation_warning_days": 300,
        "auto_rotation": False,
        "requires_restart": True,
        "backup_required": True,
    },
    SecretType.THIRD_PARTY_API: {
        "rotation_max_days": 90,
        "rotation_warning_days": 60,
        "auto_rotation": False,
        "requires_restart": False,
        "backup_required": False,
    },
    SecretType.DATABASE: {
        "rotation_max_days": 90,
        "rotation_warning_days": 60,
        "auto_rotation": False,
        "requires_restart": True,
        "backup_required": True,
    },
    SecretType.INTERNAL: {
        "rotation_max_days": 180,
        "rotation_warning_days": 150,
        "auto_rotation": False,
        "requires_restart": False,
        "backup_required": False,
    },
}


def get_pii_policy_summary() -> dict:
    """Return the full PII policy as a structured document."""
    categories = {}
    for rule in PII_FIELDS.values():
        cat = rule.category.value
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(
            {
                "field": rule.field_name,
                "default_mask": rule.default_mask.value,
                "log_mask": rule.log_mask.value,
                "unmask_roles": sorted(rule.unmask_roles),
                "description": rule.description,
            }
        )

    return {
        "total_pii_fields": len(PII_FIELDS),
        "categories": categories,
        "secret_lifecycle": {st.value: lifecycle for st, lifecycle in SECRET_LIFECYCLE.items()},
        "masking_levels": {
            "full": "Completely redacted — ***REDACTED***",
            "partial": "Show first/last chars — jo***@e***om",
            "hash": "SHA-256 prefix for correlation — sha256:a1b2c3...",
            "none": "No masking (authorized viewer only)",
        },
    }
