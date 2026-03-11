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
