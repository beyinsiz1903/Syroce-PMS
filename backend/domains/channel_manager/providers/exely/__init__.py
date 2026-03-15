"""
Exely Provider — Production-Grade SOAP Adapter
=================================================

Single source of truth for all Exely SOAP API operations.

Public API:
    from domains.channel_manager.providers.exely import ExelyProvider

All existing imports continue to work via this re-export.
"""

from .provider import ExelyProvider
from .errors import (
    ExelyError,
    ExelyAuthError,
    ExelySOAPFaultError,
    ExelyTemporaryError,
    ExelyRateLimitError,
    ExelyPayloadError,
    ExelyParseError,
    ExelyMappingError,
    ExelyValidationError,
)

# Re-export ProviderResult for callers that import from exely
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult

__all__ = [
    "ExelyProvider",
    "ProviderResult",
    "ExelyError",
    "ExelyAuthError",
    "ExelySOAPFaultError",
    "ExelyTemporaryError",
    "ExelyRateLimitError",
    "ExelyPayloadError",
    "ExelyParseError",
    "ExelyMappingError",
    "ExelyValidationError",
]
