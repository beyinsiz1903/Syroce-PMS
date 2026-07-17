class IntegrationError(Exception):
    def __init__(
        self,
        safe_user_message: str,
        category: str,
        safe_code: str,
        retryable: bool,
        http_status: int | None = None,
        provider: str | None = None,
        provider_code: str | None = None,
        correlation_id: str | None = None,
        sanitized_context: dict | None = None,
    ):
        super().__init__(safe_user_message)
        self.safe_user_message = safe_user_message
        self.category = category
        self.safe_code = safe_code
        self.retryable = retryable
        self.http_status = http_status
        self.provider = provider
        self.provider_code = provider_code
        self.correlation_id = correlation_id
        self.sanitized_context = sanitized_context or {}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} code={self.safe_code} retryable={self.retryable}>"


class IntegrationValidationError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="VALIDATION", safe_code="VALIDATION_FAILED", retryable=False, **kwargs)


class IntegrationAuthenticationError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="AUTHENTICATION", safe_code="AUTH_FAILED", retryable=False, **kwargs)


class IntegrationAuthorizationError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="AUTHORIZATION", safe_code="AUTHORIZATION_FAILED", retryable=False, **kwargs)


class IntegrationNotFoundError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="NOT_FOUND", safe_code="NOT_FOUND", retryable=False, **kwargs)


class IntegrationConflictError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="CONFLICT", safe_code="CONFLICT", retryable=False, **kwargs)


class IntegrationRateLimitError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="RATE_LIMIT", safe_code="RATE_LIMIT_EXCEEDED", retryable=True, **kwargs)


class IntegrationTimeoutError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="TIMEOUT", safe_code="TIMEOUT", retryable=True, **kwargs)


class IntegrationTransportError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="TRANSPORT", safe_code="TRANSPORT_ERROR", retryable=True, **kwargs)


class IntegrationProviderUnavailableError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="PROVIDER_UNAVAILABLE", safe_code="PROVIDER_UNAVAILABLE", retryable=True, **kwargs)


class IntegrationBusinessRuleError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="BUSINESS_RULE", safe_code="BUSINESS_RULE_VIOLATION", retryable=False, **kwargs)


class IntegrationUnknownError(IntegrationError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="UNKNOWN", safe_code="UNKNOWN_ERROR", retryable=False, **kwargs)
