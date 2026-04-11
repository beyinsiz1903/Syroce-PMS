"""Compatibility alias — use hr_client instead."""
from .hr_client import (  # noqa: F401
    AUDIT_TRUNCATE_LEN,
    DEFAULT_PER_PAGE,
    HOTELRUNNER_API_BASE,
    HOTELRUNNER_MOCK_BASE,
    HOTELRUNNER_SANDBOX_BASE,
    HotelRunnerClient,
    MASK_KEYS,
    MAX_PAGINATION_PAGES,
    VALID_ENVIRONMENTS,
    _mask_params,
    _truncate,
)

__all__ = [
    "HotelRunnerClient",
    "HOTELRUNNER_API_BASE",
    "HOTELRUNNER_SANDBOX_BASE",
    "HOTELRUNNER_MOCK_BASE",
    "MAX_PAGINATION_PAGES",
    "DEFAULT_PER_PAGE",
    "AUDIT_TRUNCATE_LEN",
    "MASK_KEYS",
    "VALID_ENVIRONMENTS",
    "_mask_params",
    "_truncate",
]
