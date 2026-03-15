"""
HotelRunner Provider — Production-Grade Adapter
=================================================

Single source of truth for all HotelRunner API operations.

Public API:
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

All existing imports continue to work via this re-export.
"""

from .provider import HotelRunnerProvider
from .schemas import ProviderResult
from .errors import (
    HotelRunnerError,
    HotelRunnerAuthError,
    HotelRunnerRateLimitError,
    HotelRunnerTemporaryError,
    HotelRunnerPayloadError,
    HotelRunnerParseError,
    HotelRunnerMappingError,
    HotelRunnerPaginationError,
    HotelRunnerValidationError,
)

__all__ = [
    "HotelRunnerProvider",
    "ProviderResult",
    "HotelRunnerError",
    "HotelRunnerAuthError",
    "HotelRunnerRateLimitError",
    "HotelRunnerTemporaryError",
    "HotelRunnerPayloadError",
    "HotelRunnerParseError",
    "HotelRunnerMappingError",
    "HotelRunnerPaginationError",
    "HotelRunnerValidationError",
]
