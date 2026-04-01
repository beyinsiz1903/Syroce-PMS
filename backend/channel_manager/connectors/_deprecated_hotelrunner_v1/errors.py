"""
HotelRunner Connector Errors - Typed exceptions for the connector layer.
Every error maps to a specific recovery strategy.
"""


class ConnectorError(Exception):
    """Base connector error."""
    def __init__(self, message: str, provider: str = "hotelrunner", recoverable: bool = False):
        self.message = message
        self.provider = provider
        self.recoverable = recoverable
        super().__init__(message)


class AuthenticationError(ConnectorError):
    """Invalid or expired credentials. Requires re-auth or credential rotation."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, recoverable=False)


class RateLimitError(ConnectorError):
    """Provider rate limit hit. Must wait before retrying."""
    def __init__(self, retry_after_seconds: int = 60, message: str = "Rate limit exceeded"):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, recoverable=True)


class ProviderUnavailableError(ConnectorError):
    """Provider API is down or unreachable."""
    def __init__(self, message: str = "Provider unavailable"):
        super().__init__(message, recoverable=True)


class ProviderValidationError(ConnectorError):
    """Provider rejected the request due to invalid data in the push payload."""
    def __init__(self, message: str = "Provider validation failed", details: dict = None):
        self.details = details or {}
        super().__init__(message, recoverable=False)


class SchemaMismatchError(ConnectorError):
    """Response schema doesn't match expected format."""
    def __init__(self, message: str = "Schema mismatch", expected: str = "", actual: str = ""):
        self.expected = expected
        self.actual = actual
        super().__init__(message, recoverable=False)


class UnknownResponseFormatError(ConnectorError):
    """Response format is unrecognizable."""
    def __init__(self, message: str = "Unknown response format", raw_response: str = ""):
        self.raw_response = raw_response[:2000]
        super().__init__(message, recoverable=False)


class ValidationError(ConnectorError):
    """Provider rejected the request due to invalid data."""
    def __init__(self, message: str = "Validation failed", details: dict = None):
        self.details = details or {}
        super().__init__(message, recoverable=False)


class MappingError(ConnectorError):
    """Required mapping not found or invalid."""
    def __init__(self, entity_type: str, entity_id: str, message: str = ""):
        self.entity_type = entity_type
        self.entity_id = entity_id
        msg = message or f"No valid mapping for {entity_type}:{entity_id}"
        super().__init__(msg, recoverable=False)


class XmlParseError(ConnectorError):
    """Failed to parse provider XML response."""
    def __init__(self, message: str = "XML parse error", raw_xml: str = ""):
        self.raw_xml = raw_xml[:2000]
        super().__init__(message, recoverable=False)


class DuplicateError(ConnectorError):
    """Duplicate entity detected (idempotency protection)."""
    def __init__(self, entity_type: str, external_id: str):
        self.entity_type = entity_type
        self.external_id = external_id
        super().__init__(f"Duplicate {entity_type}: {external_id}", recoverable=False)


class ResponseParseError(ConnectorError):
    """Failed to parse provider JSON/REST response."""
    def __init__(self, message: str = "Response parse error", raw_response: str = ""):
        self.raw_response = raw_response[:2000]
        super().__init__(message, recoverable=False)


class PaginationExhaustedError(ConnectorError):
    """Pagination safety limit reached to prevent infinite loops."""
    def __init__(self, max_pages: int, fetched_count: int):
        self.max_pages = max_pages
        self.fetched_count = fetched_count
        super().__init__(
            f"Pagination safety limit reached: {max_pages} pages, {fetched_count} items",
            recoverable=False,
        )


class AcknowledgementError(ConnectorError):
    """Failed to confirm delivery of a reservation to provider."""
    def __init__(self, message_uid: str, hr_number: str = "", reason: str = ""):
        self.message_uid = message_uid
        self.hr_number = hr_number
        self.reason = reason
        super().__init__(
            f"Acknowledgement failed for {hr_number} (uid={message_uid}): {reason}",
            recoverable=True,
        )
