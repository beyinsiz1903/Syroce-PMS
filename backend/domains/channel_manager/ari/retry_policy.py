"""
ARI Retry Policy.

Exponential backoff with configurable delays per attempt.
"""
import logging
from .models import RETRY_DELAYS, MAX_RETRY_ATTEMPTS

logger = logging.getLogger(__name__)


def get_retry_delay(attempt: int) -> int:
    """Get retry delay in seconds for a given attempt number (0-indexed)."""
    if attempt >= len(RETRY_DELAYS):
        return RETRY_DELAYS[-1]
    return RETRY_DELAYS[attempt]


def should_retry(attempt: int) -> bool:
    """Check if we should retry based on attempt count."""
    return attempt < MAX_RETRY_ATTEMPTS


def classify_error(status_code: int = 0, error: str = "") -> str:
    """Classify an error as retryable or permanent.

    Returns: 'retryable', 'permanent', or 'rate_limited'
    """
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "retryable"
    if status_code in (400, 401, 403, 404, 422):
        return "permanent"
    if "timeout" in error.lower():
        return "retryable"
    if "connection" in error.lower():
        return "retryable"
    if status_code == 0 and error:
        return "retryable"
    return "permanent"
