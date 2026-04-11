"""
Common — Domain Error Types
Typed exceptions for service-layer error handling.
"""


class DomainError(Exception):
    """Base error for all domain/service layer exceptions."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(DomainError):
    def __init__(self, entity: str, identifier: str):
        super().__init__(f"{entity} not found: {identifier}", "NOT_FOUND")


class ValidationError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class ConflictError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "CONFLICT")


class ForbiddenError(DomainError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "FORBIDDEN")


class TenantViolationError(DomainError):
    def __init__(self, message: str = "Tenant isolation violated"):
        super().__init__(message, "TENANT_VIOLATION")
