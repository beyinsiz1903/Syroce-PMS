"""
Data Masking - Sensitive data masking for API responses and logs.
"""
import logging
import re
from typing import Any

logger = logging.getLogger("security.masking")

# Fields that should always be masked in API responses
SENSITIVE_FIELDS = {
    "credit_card", "credit_card_number", "card_number", "cvv", "cvc",
    "password", "password_hash", "secret", "api_key", "api_secret",
    "credential_value", "credential_value_encoded", "token",
    "id_number", "passport_number", "tax_id", "ssn",
    "bank_account", "iban", "routing_number",
}

# Partial masking fields (show first/last chars)
PARTIAL_MASK_FIELDS = {
    "email", "phone", "mobile",
}

# Patterns for auto-detection
PATTERNS = {
    "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\+?\d{10,15}"),
}


class DataMaskingService:
    """Masks sensitive data in API responses and audit logs."""

    def mask_dict(self, data: dict, depth: int = 0) -> dict:
        """Recursively mask sensitive fields in a dictionary."""
        if depth > 10:
            return data

        masked = {}
        for key, value in data.items():
            lower_key = key.lower()

            if lower_key in SENSITIVE_FIELDS:
                masked[key] = self._full_mask(value)
            elif lower_key in PARTIAL_MASK_FIELDS:
                masked[key] = self._partial_mask(value)
            elif isinstance(value, dict):
                masked[key] = self.mask_dict(value, depth + 1)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_dict(item, depth + 1) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def mask_string(self, text: str) -> str:
        """Mask sensitive patterns in a string."""
        for pattern_name, pattern in PATTERNS.items():
            if pattern_name == "credit_card":
                text = pattern.sub(lambda m: m.group()[:4] + " **** **** " + m.group()[-4:], text)
            elif pattern_name == "email":
                text = pattern.sub(lambda m: m.group()[:2] + "***@***" + m.group().split("@")[1][-4:], text)
        return text

    def _full_mask(self, value: Any) -> str:
        if value is None:
            return "****"
        s = str(value)
        if len(s) <= 4:
            return "****"
        return "****" + s[-4:] if len(s) > 8 else "****"

    def _partial_mask(self, value: Any) -> str:
        if value is None:
            return "****"
        s = str(value)
        if len(s) <= 4:
            return s[0] + "***"
        return s[:2] + "*" * (len(s) - 4) + s[-2:]

    def get_masking_coverage(self, data: dict) -> dict[str, Any]:
        """Analyze masking coverage for a data structure."""
        total_fields = 0
        sensitive_found = 0
        masked_fields = []

        def scan(d: dict, path: str = ""):
            nonlocal total_fields, sensitive_found
            for key, value in d.items():
                total_fields += 1
                lower_key = key.lower()
                full_path = f"{path}.{key}" if path else key

                if lower_key in SENSITIVE_FIELDS or lower_key in PARTIAL_MASK_FIELDS:
                    sensitive_found += 1
                    masked_fields.append(full_path)

                if isinstance(value, dict):
                    scan(value, full_path)

        scan(data)
        return {
            "total_fields": total_fields,
            "sensitive_fields": sensitive_found,
            "masked_fields": masked_fields,
            "coverage": round(sensitive_found / max(total_fields, 1), 4) if sensitive_found > 0 else 1.0,
        }

    def preview_masking(self, sample_data: dict) -> dict[str, Any]:
        """Preview how data would be masked."""
        original_fields = list(sample_data.keys())
        masked = self.mask_dict(sample_data)
        changed_fields = [
            k for k in original_fields
            if str(sample_data.get(k)) != str(masked.get(k))
        ]
        return {
            "original_field_count": len(original_fields),
            "masked_field_count": len(changed_fields),
            "changed_fields": changed_fields,
            "masked_output": masked,
        }


data_masking = DataMaskingService()
