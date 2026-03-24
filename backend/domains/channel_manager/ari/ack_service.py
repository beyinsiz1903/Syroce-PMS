"""
ARI Ack Service.

Processes provider push results: success → ack, failure → retry or dead-letter.
"""
import logging

from . import repositories as repo
from .events import ProviderResult
from .models import STATUS_ACKED, STATUS_FAILED_PERMANENT, STATUS_FAILED_RETRYABLE
from .retry_policy import classify_error, should_retry

logger = logging.getLogger(__name__)


async def process_ack(
    change_set: dict,
    result: ProviderResult,
    outbound_change_id: str,
) -> str:
    """
    Process a provider push result.
    Returns the final status: 'acked', 'failed_retryable', 'manual_review'.
    """
    provider = change_set["provider"]
    cs_id = change_set["id"]
    attempt = change_set.get("outbound_attempt_count", 0)

    # Log the outbound attempt
    await repo.insert_outbound_log({
        "tenant_id": change_set["tenant_id"],
        "property_id": change_set["property_id"],
        "provider": provider,
        "outbound_change_id": outbound_change_id,
        "provider_delta_hash": change_set.get("provider_delta_hash", ""),
        "endpoint_or_action": f"{result.provider}:{change_set['change_scope']}",
        "request_payload": change_set.get("compacted_payload"),
        "response_payload": result.response_payload,
        "status_code": result.status_code,
        "success": result.success,
        "duration_ms": result.duration_ms,
    })

    if result.success:
        await repo.update_change_set_status(cs_id, STATUS_ACKED)
        logger.info(f"ARI push acked: {provider} cs={cs_id}")
        return STATUS_ACKED

    # Failure path
    error_class = classify_error(result.status_code or 0, result.error or "")

    if error_class == "rate_limited":
        # Rate limited — always retry
        await repo.update_change_set_status(
            cs_id, STATUS_FAILED_RETRYABLE,
            error=f"429 Rate Limited: {result.error}",
            inc_attempt=True,
        )
        logger.warning(f"ARI push rate-limited: {provider} cs={cs_id}")
        return STATUS_FAILED_RETRYABLE

    if error_class == "retryable" and should_retry(attempt + 1):
        await repo.update_change_set_status(
            cs_id, STATUS_FAILED_RETRYABLE,
            error=result.error,
            inc_attempt=True,
        )
        logger.warning(f"ARI push failed (retryable): {provider} cs={cs_id} attempt={attempt + 1}")
        return STATUS_FAILED_RETRYABLE

    # Permanent failure or max retries exhausted
    await repo.update_change_set_status(
        cs_id, STATUS_FAILED_PERMANENT,
        error=result.error or f"Permanent failure after {attempt + 1} attempts",
        inc_attempt=True,
    )
    logger.error(f"ARI push failed (permanent): {provider} cs={cs_id}")
    return STATUS_FAILED_PERMANENT
