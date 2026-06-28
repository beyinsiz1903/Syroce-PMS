"""Compatibility alias — use connector_errors instead."""

from .connector_errors import (  # noqa: F401
    AcknowledgementError,
    AuthenticationError,
    ConnectorError,
    DuplicateError,
    MappingError,
    PaginationExhaustedError,
    ProviderUnavailableError,
    ProviderValidationError,
    RateLimitError,
    ResponseParseError,
    SchemaMismatchError,
    UnknownResponseFormatError,
    ValidationError,
    XmlParseError,
)

__all__ = [
    "ConnectorError",
    "AuthenticationError",
    "RateLimitError",
    "ProviderUnavailableError",
    "ProviderValidationError",
    "SchemaMismatchError",
    "UnknownResponseFormatError",
    "ValidationError",
    "MappingError",
    "XmlParseError",
    "DuplicateError",
    "ResponseParseError",
    "PaginationExhaustedError",
    "AcknowledgementError",
]
