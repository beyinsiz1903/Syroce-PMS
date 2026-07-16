"""Nilvera Integration package."""

from .client import NilveraHttpClient
from .config import NilveraSettings, get_nilvera_config
from .errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraBusinessRuleError,
    NilveraDuplicateError,
    NilveraNotFoundError,
    NilveraRateLimitError,
    NilveraResponseSizeError,
    NilveraServerError,
    NilveraTimeoutError,
    NilveraValidationError,
)
from .series import NilveraSeriesDetail, NilveraSeriesItem, NilveraSeriesPage, NilveraSeriesService

__all__ = [
    "NilveraSettings",
    "get_nilvera_config",
    "NilveraApiError",
    "NilveraAuthError",
    "NilveraBusinessRuleError",
    "NilveraDuplicateError",
    "NilveraNotFoundError",
    "NilveraRateLimitError",
    "NilveraResponseSizeError",
    "NilveraServerError",
    "NilveraTimeoutError",
    "NilveraValidationError",
    "NilveraHttpClient",
    "NilveraSeriesService",
    "NilveraSeriesPage",
    "NilveraSeriesItem",
    "NilveraSeriesDetail",
]
