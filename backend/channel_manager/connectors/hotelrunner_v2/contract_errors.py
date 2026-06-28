"""
Provider Contract Error Classes — Typed error hierarchy for XML builder/parser failures.

Covers: invalid_xml, missing_required_field, schema_mismatch,
        provider_error_response, unknown_response_format.
"""

from typing import Any


class ProviderContractError(Exception):
    """Base class for all provider contract violations."""

    error_type: str = "provider_contract_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": str(self),
            "details": self.details,
        }


class InvalidXmlError(ProviderContractError):
    """Raised when XML payload is malformed or unparseable."""

    error_type = "invalid_xml"

    def __init__(self, message: str, raw_xml: str = "", parse_error: str = ""):
        super().__init__(
            message,
            {
                "raw_xml_snippet": raw_xml[:500] if raw_xml else "",
                "parse_error": parse_error,
            },
        )


class MissingRequiredFieldError(ProviderContractError):
    """Raised when a required field is absent from provider payload."""

    error_type = "missing_required_field"

    def __init__(self, field_name: str, entity_type: str = "", entity_id: str = ""):
        super().__init__(
            f"Missing required field '{field_name}' in {entity_type} {entity_id}",
            {
                "field_name": field_name,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )


class SchemaMismatchError(ProviderContractError):
    """Raised when provider response doesn't match the expected schema."""

    error_type = "schema_mismatch"

    def __init__(self, message: str, expected: str = "", actual: str = ""):
        super().__init__(
            message,
            {
                "expected_schema": expected,
                "actual_schema": actual,
            },
        )


class ProviderErrorResponseError(ProviderContractError):
    """Raised when provider returns a structured error response (OTA Error, etc)."""

    error_type = "provider_error_response"

    def __init__(self, provider: str, error_code: str, error_message: str, raw_response: str = ""):
        super().__init__(
            f"{provider} error [{error_code}]: {error_message}",
            {
                "provider": provider,
                "error_code": error_code,
                "error_message": error_message,
                "raw_response_snippet": raw_response[:500] if raw_response else "",
            },
        )


class UnknownResponseFormatError(ProviderContractError):
    """Raised when provider response format is completely unrecognized."""

    error_type = "unknown_response_format"

    def __init__(self, content_type: str = "", raw_response: str = ""):
        super().__init__(
            f"Unknown response format: {content_type}",
            {
                "content_type": content_type,
                "raw_response_snippet": raw_response[:500] if raw_response else "",
            },
        )
