"""User-specific guest data visibility and masking.

The policy is deliberately independent from the user's role.  A hotel
administrator stores an explicit mode for each guest-data group on the user
document.  API/report serializers call this module after decrypting data, so
HTML, print, CSV and PDF consumers all receive the same protected value.

Accounts created before this feature may not have an explicit policy.  Those
accounts retain the previous PII permission behaviour until an administrator
saves their data profile; newly provisioned accounts always receive an
explicit secure policy.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

ALLOWED_VISIBILITY_MODES = frozenset({"full", "masked", "hidden"})

GUEST_DATA_FIELDS: dict[str, dict[str, Any]] = {
    "name": {
        "label": "Ad ve soyad",
        "description": "Misafirin adı, soyadı ve rezervasyon üzerindeki adı",
        "aliases": {"name", "full_name", "guest_name", "primary_guest_name", "first_name", "last_name"},
        "default": "full",
    },
    "email": {
        "label": "E-posta",
        "description": "Misafir e-posta adresleri",
        "aliases": {"email", "guest_email"},
        "default": "masked",
    },
    "phone": {
        "label": "Telefon",
        "description": "Telefon ve cep telefonu numaraları",
        "aliases": {"phone", "phone_number", "mobile", "guest_phone"},
        "default": "masked",
    },
    "identity": {
        "label": "Kimlik ve pasaport numarası",
        "description": "TCKN, ulusal kimlik ve pasaport numaraları",
        "aliases": {
            "tc_kimlik", "tc_identity_number", "id_number", "national_id",
            "identity_number", "passport_number", "tax_id", "billing_tax_number",
        },
        "default": "hidden",
    },
    "birth_date": {
        "label": "Doğum tarihi",
        "description": "Doğum tarihi ve yaş bilgisi",
        "aliases": {"birth_date", "date_of_birth", "dob"},
        "default": "hidden",
    },
    "address": {
        "label": "Adres ve konum",
        "description": "Adres, şehir ve fatura adresi",
        "aliases": {"address", "billing_address", "street", "city", "district", "postal_code"},
        "default": "hidden",
    },
    "nationality": {
        "label": "Uyruk ve ülke",
        "description": "Uyruk, ülke ve vatandaşlık bilgisi",
        "aliases": {"nationality", "country", "citizenship"},
        "default": "full",
    },
    "notes": {
        "label": "Misafir notları",
        "description": "Serbest metin notlar, tercihler ve özel istekler",
        "aliases": {
            "notes", "guest_notes", "special_requests", "preferences",
            "pillow_preference", "spa_preference", "minibar_preference",
        },
        "default": "hidden",
    },
    "financial": {
        "label": "Finansal bilgiler",
        "description": "Konaklama tutarı, bakiye ve misafire bağlı finansal değerler",
        "aliases": {
            "total_amount", "balance", "total_revenue", "lifetime_value",
            "billing_tax_number", "company_id", "iban", "account_number",
        },
        "default": "hidden",
    },
    "identity_photo": {
        "label": "Kimlik fotoğrafı",
        "description": "Kimlik/pasaport görseli ve belge bağlantıları",
        "aliases": {"identity_photo", "id_photo", "document_image", "document_url", "photo_url"},
        "default": "hidden",
    },
}

DEFAULT_GUEST_DATA_VISIBILITY = {
    key: str(definition["default"])
    for key, definition in GUEST_DATA_FIELDS.items()
}

_ALIAS_TO_FIELD = {
    alias: field_key
    for field_key, definition in GUEST_DATA_FIELDS.items()
    for alias in definition["aliases"]
}


def guest_data_visibility_catalog() -> dict[str, Any]:
    return {
        "modes": [
            {"value": "full", "label": "Tam göster"},
            {"value": "masked", "label": "Maskeli göster"},
            {"value": "hidden", "label": "Tamamen gizle"},
        ],
        "fields": [
            {
                "key": key,
                "label": definition["label"],
                "description": definition["description"],
                "default": definition["default"],
            }
            for key, definition in GUEST_DATA_FIELDS.items()
        ],
        "default_policy": dict(DEFAULT_GUEST_DATA_VISIBILITY),
    }


def normalize_guest_data_visibility(policy: Mapping[str, Any] | None) -> dict[str, str]:
    normalized = dict(DEFAULT_GUEST_DATA_VISIBILITY)
    if not isinstance(policy, Mapping):
        return normalized
    unknown = set(policy) - set(GUEST_DATA_FIELDS)
    if unknown:
        raise ValueError(f"Unknown guest data fields: {', '.join(sorted(unknown))}")
    for key, raw_mode in policy.items():
        mode = str(raw_mode or "").strip().lower()
        if mode not in ALLOWED_VISIBILITY_MODES:
            raise ValueError(f"Invalid visibility mode for {key}: {raw_mode}")
        normalized[key] = mode
    return normalized


def user_guest_data_visibility(user: Any) -> tuple[dict[str, str], str]:
    explicit = getattr(user, "guest_data_visibility", None)
    if isinstance(explicit, Mapping) and explicit:
        return normalize_guest_data_visibility(explicit), "user"

    # Backwards-compatible bridge for accounts created before explicit
    # per-user profiles existed.  It is surfaced as "legacy" in the audit
    # report so the hotel can find and replace every remaining legacy profile.
    role = getattr(getattr(user, "role", None), "value", None) or str(getattr(user, "role", "") or "")
    grants = set(getattr(user, "granted_permissions", None) or [])
    legacy_full = role in {"admin", "super_admin", "manager", "general_manager"} or "view_guest_pii" in grants
    if legacy_full:
        return dict.fromkeys(GUEST_DATA_FIELDS, "full"), "legacy"
    return normalize_guest_data_visibility(None), "legacy"


def visibility_mode_for_field(policy: Mapping[str, str], field_name: str) -> tuple[str | None, str]:
    field_key = _ALIAS_TO_FIELD.get(str(field_name or "").lower())
    return field_key, policy.get(field_key, "full") if field_key else "full"


def _mask_name(value: str) -> str:
    words = value.split()
    return " ".join((word[:1] + "*" * max(len(word) - 1, 2)) if word else "" for word in words)


def _mask_email(value: str) -> str:
    if "@" not in value:
        return _mask_generic(value)
    local, domain = value.split("@", 1)
    return f"{local[:1] or '*'}***@{domain}"


def _mask_phone(value: str) -> str:
    compact = str(value)
    return "*" * max(len(compact) - 4, 4) + compact[-4:]


def _mask_generic(value: str) -> str:
    if len(value) <= 4:
        return "*" * max(len(value), 3)
    return value[:1] + "*" * (len(value) - 3) + value[-2:]


def mask_guest_value(value: Any, field_key: str, mode: str) -> Any:
    if value is None or value == "" or mode == "full":
        return value
    if mode == "hidden":
        return None
    text = str(value)
    if field_key == "name":
        return _mask_name(text)
    if field_key == "email":
        return _mask_email(text)
    if field_key == "phone":
        return _mask_phone(text)
    if field_key == "birth_date":
        return f"{text[:4]}-**-**" if len(text) >= 4 else "****"
    return _mask_generic(text)


def protect_guest_row(row: Mapping[str, Any], user: Any) -> dict[str, Any]:
    policy, _source = user_guest_data_visibility(user)
    protected: dict[str, Any] = {}
    for key, value in row.items():
        field_key, mode = visibility_mode_for_field(policy, key)
        if field_key:
            protected[key] = mask_guest_value(value, field_key, mode)
        elif isinstance(value, Mapping):
            protected[key] = protect_guest_row(value, user)
        elif isinstance(value, list):
            protected[key] = [protect_guest_row(item, user) if isinstance(item, Mapping) else item for item in value]
        else:
            protected[key] = value
    return protected


def guest_visibility_summary(user: Any) -> dict[str, Any]:
    policy, source = user_guest_data_visibility(user)
    return {
        "policy_source": source,
        "server_side_enforced": True,
        "policy": deepcopy(policy),
        "full_fields": sorted(key for key, mode in policy.items() if mode == "full"),
        "masked_fields": sorted(key for key, mode in policy.items() if mode == "masked"),
        "hidden_fields": sorted(key for key, mode in policy.items() if mode == "hidden"),
    }
