"""
Common — Operation Context
Carries tenant, property, actor, and audit info through service calls.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass(frozen=True)
class OperationContext:
    """Immutable context passed from router to service to repository."""

    tenant_id: str
    actor_id: str
    actor_email: str = ""
    actor_role: str = ""
    property_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_user(cls, user, **overrides) -> "OperationContext":
        """Build context from the authenticated user (FastAPI dependency)."""
        return cls(
            tenant_id=getattr(user, "tenant_id", ""),
            actor_id=getattr(user, "id", ""),
            actor_email=getattr(user, "email", ""),
            actor_role=getattr(user, "role", ""),
            property_id=getattr(user, "property_id", None),
            **overrides,
        )
