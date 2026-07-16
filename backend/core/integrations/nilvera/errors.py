"""Nilvera integration errors."""

import json
from typing import Any


class NilveraApiError(Exception):
    """Base exception for Nilvera API errors."""

    def __init__(
        self,
        message: str,
        safe_user_message: str | None = None,
        http_status: int | None = None,
        provider_code: str | None = None,
        description: str | None = None,
        detail: str | None = None,
        correlation_id: str | None = None,
        retryable: bool = False,
        raw_response: str | dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.safe_user_message = safe_user_message or "E-Belge entegratörü ile iletişimde bir sorun oluştu."
        self.http_status = http_status
        self.provider_code = provider_code
        self.description = description
        self.detail = detail
        self.correlation_id = correlation_id
        self.retryable = retryable

        self.sanitized_preview: str | None = None
        if raw_response is not None:
            self.sanitized_preview = self._create_sanitized_preview(raw_response)

    def _create_sanitized_preview(self, raw_response: str | dict[str, Any]) -> str:
        """Create a bounded, safe preview of the response."""
        if isinstance(raw_response, dict):
            try:
                # remove sensitive keys if any
                safe_dict = {k: v for k, v in raw_response.items() if k.lower() not in ["authorization", "apikey", "vkn", "tckn", "password"]}
                content = json.dumps(safe_dict)
            except Exception:
                content = str(raw_response)
        else:
            content = str(raw_response)

        import re
        # Hard redaction of common sensitive patterns
        content_lower = content.lower()
        if "authorization" in content_lower or "api_key" in content_lower or "bearer" in content_lower:
            content = "[REDACTED_POTENTIAL_SECRETS]"

        # Redact VKN/TCKN-like values in the string
        content = re.sub(r'(?i)(vkn|tckn)[\"\'\s:=]+([0-9]{10,11})', r'\1: [REDACTED]', content)

        return content[:512]

    def __str__(self) -> str:
        base = super().__str__()
        parts = []
        if self.http_status:
            parts.append(f"HTTP {self.http_status}")
        if self.provider_code:
            parts.append(f"Code {self.provider_code}")
        if self.correlation_id:
            parts.append(f"CorrID {self.correlation_id}")
        ctx = f" [{', '.join(parts)}]" if parts else ""
        return f"{base}{ctx}"

    def __repr__(self) -> str:
        # Prevent any automatic exposure of detail, description, or sanitized_preview
        return f"{self.__class__.__name__}({repr(self.args[0]) if self.args else ''})"


class NilveraValidationError(NilveraApiError):
    """Raised when request payload is invalid (HTTP 400)."""


class NilveraAuthError(NilveraApiError):
    """Raised when authentication fails (HTTP 401/403)."""


class NilveraNotFoundError(NilveraApiError):
    """Raised when a resource is not found (HTTP 404)."""


class NilveraDuplicateError(NilveraApiError):
    """Raised when the UUID or invoice is a duplicate (HTTP 409)."""


class NilveraBusinessRuleError(NilveraApiError):
    """Raised when a business rule is violated (HTTP 422)."""


class NilveraRateLimitError(NilveraApiError):
    """Raised when rate limit is exceeded (HTTP 429)."""


class NilveraServerError(NilveraApiError):
    """Raised when the provider has an internal error (HTTP 5xx)."""


class NilveraTimeoutError(NilveraApiError):
    """Raised when a network timeout occurs."""


class NilveraResponseSizeError(NilveraApiError):
    """Raised when the response size exceeds the allowed limit."""
