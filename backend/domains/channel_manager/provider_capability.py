"""
Provider Capability Matrix
==========================

Defines the behavioral contract for each provider.
Not just config — this is the system's understanding of what each
provider does and does not guarantee.

Every provider difference should be encoded here, not scattered
across ad-hoc if-else branches.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from .data_model import ConnectorProvider, ErrorClass


class ReservationIngestType(str, Enum):
    PUSH_WEBHOOK = "push_webhook"
    PULL_POLL = "pull_poll"
    HYBRID = "hybrid"


class CancellationBehavior(str, Enum):
    EXPLICIT_CANCEL_EVENT = "explicit_cancel_event"
    STATUS_CHANGE = "status_change"
    DELETE = "delete"


class ModificationBehavior(str, Enum):
    FULL_REPLACE = "full_replace"
    PARTIAL_DELTA = "partial_delta"
    CANCEL_AND_REBOOK = "cancel_and_rebook"


class ARIPushBehavior(str, Enum):
    SINGLE_MESSAGE = "single_message"       # rates + avail in one call
    SPLIT_MESSAGES = "split_messages"       # rates and avail must be separate
    BATCH_ONLY = "batch_only"


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 60.0
    exponential_factor: float = 2.0
    retryable_http_codes: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    retryable_error_patterns: List[str] = field(default_factory=list)


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10
    cooldown_seconds: float = 1.0


@dataclass
class ProviderCapability:
    """Complete behavioral contract for a provider."""

    provider: ConnectorProvider
    display_name: str

    # Reservation handling
    reservation_ingest_type: ReservationIngestType
    cancellation_behavior: CancellationBehavior
    modification_behavior: ModificationBehavior

    # ARI push
    ari_push_behavior: ARIPushBehavior
    supports_delta_push: bool = False
    supports_restriction_push: bool = True
    max_date_range_days: int = 365

    # Timing & consistency
    eventual_consistency_window_seconds: int = 30
    typical_ack_latency_ms: int = 2000

    # Duplicate handling
    provider_guarantees_unique_event_id: bool = False
    provider_sends_last_modified: bool = True

    # Delivery semantics
    ack_means_applied: bool = False  # HTTP 200 != inventory applied

    # Rate limits
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)

    # Retry
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

    # Error taxonomy: maps error patterns to error classes
    error_classification: Dict[str, ErrorClass] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════
# PROVIDER REGISTRY
# ══════════════════════════════════════════════════════════════════════

PROVIDER_CAPABILITIES: Dict[str, ProviderCapability] = {
    "exely": ProviderCapability(
        provider=ConnectorProvider.EXELY,
        display_name="Exely",
        reservation_ingest_type=ReservationIngestType.PULL_POLL,
        cancellation_behavior=CancellationBehavior.STATUS_CHANGE,
        modification_behavior=ModificationBehavior.FULL_REPLACE,
        ari_push_behavior=ARIPushBehavior.SPLIT_MESSAGES,
        supports_delta_push=False,
        supports_restriction_push=True,
        max_date_range_days=365,
        eventual_consistency_window_seconds=60,
        typical_ack_latency_ms=3000,
        provider_guarantees_unique_event_id=False,
        provider_sends_last_modified=True,
        ack_means_applied=False,
        rate_limits=RateLimitConfig(
            requests_per_minute=30,
            requests_per_hour=500,
            burst_limit=5,
            cooldown_seconds=2.0,
        ),
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_delay_seconds=5.0,
            max_delay_seconds=120.0,
            exponential_factor=2.0,
            retryable_http_codes=[429, 500, 502, 503, 504],
            retryable_error_patterns=["timeout", "connection reset", "SOAP fault"],
        ),
        error_classification={
            "timeout": ErrorClass.RETRYABLE,
            "connection reset": ErrorClass.RETRYABLE,
            "429": ErrorClass.RETRYABLE,
            "500": ErrorClass.RETRYABLE,
            "502": ErrorClass.RETRYABLE,
            "503": ErrorClass.RETRYABLE,
            "invalid credentials": ErrorClass.CONFIGURATION,
            "authentication failed": ErrorClass.CONFIGURATION,
            "invalid hotel id": ErrorClass.CONFIGURATION,
            "unmapped room": ErrorClass.CONFIGURATION,
            "closed date range": ErrorClass.BUSINESS_REJECTION,
            "rate plan not available": ErrorClass.BUSINESS_REJECTION,
            "minimum stay violation": ErrorClass.BUSINESS_REJECTION,
        },
    ),
    "hotelrunner": ProviderCapability(
        provider=ConnectorProvider.HOTELRUNNER,
        display_name="HotelRunner",
        reservation_ingest_type=ReservationIngestType.PUSH_WEBHOOK,
        cancellation_behavior=CancellationBehavior.EXPLICIT_CANCEL_EVENT,
        modification_behavior=ModificationBehavior.FULL_REPLACE,
        ari_push_behavior=ARIPushBehavior.SINGLE_MESSAGE,
        supports_delta_push=True,
        supports_restriction_push=True,
        max_date_range_days=730,
        eventual_consistency_window_seconds=15,
        typical_ack_latency_ms=1000,
        provider_guarantees_unique_event_id=True,
        provider_sends_last_modified=True,
        ack_means_applied=False,
        rate_limits=RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_limit=10,
            cooldown_seconds=1.0,
        ),
        retry_policy=RetryPolicy(
            max_attempts=5,
            base_delay_seconds=2.0,
            max_delay_seconds=60.0,
            exponential_factor=2.0,
            retryable_http_codes=[429, 500, 502, 503, 504],
            retryable_error_patterns=["timeout", "rate limit"],
        ),
        error_classification={
            "timeout": ErrorClass.RETRYABLE,
            "rate limit": ErrorClass.RETRYABLE,
            "429": ErrorClass.RETRYABLE,
            "500": ErrorClass.RETRYABLE,
            "invalid api key": ErrorClass.CONFIGURATION,
            "property not found": ErrorClass.CONFIGURATION,
            "room type inactive": ErrorClass.BUSINESS_REJECTION,
            "date range closed": ErrorClass.BUSINESS_REJECTION,
        },
    ),
}


def get_capability(provider: str) -> ProviderCapability:
    cap = PROVIDER_CAPABILITIES.get(provider)
    if not cap:
        raise ValueError(f"Unknown provider: {provider}")
    return cap


def classify_error(provider: str, error_message: str) -> ErrorClass:
    """Classify an error from a provider into retryable/config/business."""
    cap = PROVIDER_CAPABILITIES.get(provider)
    if not cap:
        return ErrorClass.RETRYABLE

    error_lower = error_message.lower()
    for pattern, cls in cap.error_classification.items():
        if pattern.lower() in error_lower:
            return cls

    return ErrorClass.RETRYABLE


def should_retry(provider: str, error_message: str, attempt: int) -> bool:
    """Determine if an operation should be retried based on provider policy."""
    cap = get_capability(provider)
    cls = classify_error(provider, error_message)

    if cls != ErrorClass.RETRYABLE:
        return False

    return attempt < cap.retry_policy.max_attempts


def get_retry_delay(provider: str, attempt: int) -> float:
    """Calculate retry delay with exponential backoff."""
    cap = get_capability(provider)
    policy = cap.retry_policy
    delay = policy.base_delay_seconds * (policy.exponential_factor ** attempt)
    return min(delay, policy.max_delay_seconds)
