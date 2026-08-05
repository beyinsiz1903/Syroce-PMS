"""Nilvera Integration package."""

from .alias import resolve_receiver_alias
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
from .document_service import NilveraDocumentService
from .series import NilveraSeriesDetail, NilveraSeriesItem, NilveraSeriesPage, NilveraSeriesService

__all__ = [
    "resolve_receiver_alias",
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
    "NilveraSeriesDetail",
    "NilveraSeriesItem",
    "NilveraSeriesPage",
    "NilveraSeriesService",
    "NilveraDocumentService",
]
