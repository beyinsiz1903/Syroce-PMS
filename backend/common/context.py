"""
Common — Operation Context
Carries tenant, property, actor, and audit info through service calls.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class OperationContext:
    """Immutable context passed from router to service to repository."""

    tenant_id: str
    actor_id: str
    actor_email: str = ""
    actor_role: str = ""
    actor_is_super_admin: bool = False
    property_id: str | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_user(cls, user, **overrides) -> "OperationContext":
        """Build context from the authenticated user (FastAPI dependency)."""
        # Honor both `role` and `roles[]` representations of super_admin.
        try:
            from core.security import _is_super_admin
            is_sa = _is_super_admin(user)
        except Exception:
            is_sa = False
        return cls(
            tenant_id=getattr(user, "tenant_id", ""),
            actor_id=getattr(user, "id", ""),
            actor_email=getattr(user, "email", ""),
            actor_role=getattr(user, "role", ""),
            actor_is_super_admin=is_sa,
            property_id=getattr(user, "property_id", None),
            **overrides,
        )
