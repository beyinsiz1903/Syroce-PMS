"""
PII Masking — Application-layer response masking.

Instead of middleware (which conflicts with GZip compression),
provides FastAPI dependencies and utility functions for:
  1. Masking API responses at the endpoint level
  2. Role-based unmask via dependency injection
  3. Automatic masking for ops/timeline/failure endpoints

Usage:
    from security.pii_masking_middleware import PIIMaskingContext, get_pii_context

    @router.get("/guests")
    async def list_guests(pii: PIIMaskingContext = Depends(get_pii_context)):
        data = await fetch_guests()
        return pii.mask(data)
"""
import logging
from dataclasses import dataclass

from fastapi import Depends, Request

from security.pii_registry import mask_dict

logger = logging.getLogger("security.pii_masking")


@dataclass
class PIIMaskingContext:
    """Context for PII masking in a single request."""
    user_role: str = ""
    force_mask: bool = False

    def mask(self, data):
        """Apply PII masking to response data."""
        effective_role = "" if self.force_mask else self.user_role
        if isinstance(data, dict):
            return mask_dict(data, user_role=effective_role, context="api")
        if isinstance(data, list):
            return [
                mask_dict(item, user_role=effective_role, context="api")
                if isinstance(item, dict) else item
                for item in data
            ]
        return data


def get_pii_context(request: Request) -> PIIMaskingContext:
    """FastAPI dependency that creates a PII masking context from the request."""
    user_role = ""
    try:
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "role"):
            user_role = user.role
        elif user and isinstance(user, dict):
            user_role = user.get("role", "")
    except Exception:
        pass

    # Check if this is a sensitive ops endpoint
    path = request.url.path
    force_mask = any(path.startswith(p) for p in (
        "/api/ops/",
        "/api/timeline/",
        "/api/failures/",
        "/api/webhooks/raw",
    ))

    return PIIMaskingContext(user_role=user_role, force_mask=force_mask)
