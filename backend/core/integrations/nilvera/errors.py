"""Nilvera integration errors."""

import json
from typing import Any

from core.integrations.errors import IntegrationError


class NilveraApiError(IntegrationError):
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
        category: str = "UNKNOWN",
        safe_code: str = "NILVERA_UNKNOWN_ERROR",
    ):
        safe_msg = safe_user_message or "E-Belge entegratörü ile iletişimde bir sorun oluştu."
        super().__init__(
            safe_user_message=safe_msg,
            category=category,
            safe_code=safe_code,
            retryable=retryable,
            http_status=http_status,
            provider="NILVERA",
            provider_code=provider_code,
            correlation_id=correlation_id,
        )
        self.message = message

        self.sanitized_description: str | None = None
        if description:
            self.sanitized_description = self._create_sanitized_preview(description)

        self.sanitized_detail: str | None = None
        if detail:
            self.sanitized_detail = self._create_sanitized_preview(detail)

        self.sanitized_preview: str | None = None
        if raw_response is not None:
            self.sanitized_preview = self._create_sanitized_preview(raw_response)
            self.sanitized_context["preview"] = self.sanitized_preview

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
        if "authorization" in content_lower or "api_key" in content_lower or "bearer" in content_lower or "password" in content_lower:
            content = "[REDACTED_POTENTIAL_SECRETS]"

        # Redact VKN/TCKN-like values or any 10+ digit number in the string
        content = re.sub(r'(?i)(vkn|tckn)[\"\'\s:=]+([0-9]{10,11})', r'\1: [REDACTED]', content)
        content = re.sub(r'\b\d{10,}\b', '[REDACTED_NUM]', content)

        # Redact emails
        content = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]', content)

        return content[:512]

    def __str__(self) -> str:
        parts = []
        if self.http_status:
            parts.append(f"HTTP {self.http_status}")
        if self.provider_code:
            parts.append(f"Code {self.provider_code}")
        if self.correlation_id:
            parts.append(f"CorrID {self.correlation_id}")
        ctx = f" [{', '.join(parts)}]" if parts else ""
        return f"{self.message}{ctx}"

    def __repr__(self) -> str:
        # Prevent any automatic exposure of detail, description, or sanitized_preview
        return f"{self.__class__.__name__}('{self.message}')"


class NilveraValidationError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "VALIDATION")
        kwargs.setdefault("safe_code", "NILVERA_VALIDATION_FAILED")
        super().__init__(message, **kwargs)


class NilveraAuthError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "AUTHENTICATION")
        kwargs.setdefault("safe_code", "NILVERA_AUTH_FAILED")
        super().__init__(message, **kwargs)


class NilveraNotFoundError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "NOT_FOUND")
        kwargs.setdefault("safe_code", "NILVERA_NOT_FOUND")
        super().__init__(message, **kwargs)


class NilveraDuplicateError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "DUPLICATE")
        kwargs.setdefault("safe_code", "NILVERA_DUPLICATE")
        super().__init__(message, **kwargs)


class NilveraBusinessRuleError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "BUSINESS_RULE")
        kwargs.setdefault("safe_code", "NILVERA_BUSINESS_RULE")
        super().__init__(message, **kwargs)


class NilveraRateLimitError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "RATE_LIMIT")
        kwargs.setdefault("safe_code", "NILVERA_RATE_LIMIT")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NilveraServerError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "PROVIDER_UNAVAILABLE")
        kwargs.setdefault("safe_code", "NILVERA_SERVER_ERROR")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NilveraTimeoutError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "TIMEOUT")
        kwargs.setdefault("safe_code", "NILVERA_TIMEOUT")
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NilveraResponseSizeError(NilveraApiError):
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", "INVALID_PROVIDER_RESPONSE")
        kwargs.setdefault("safe_code", "NILVERA_RESPONSE_TOO_LARGE")
        super().__init__(message, **kwargs)
