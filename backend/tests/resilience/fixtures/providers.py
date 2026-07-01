"""
Mock provider adapters for chaos injection.

These simulate real-world OTA failure modes:
- Timeout
- Rate limiting (429)
- Auth failure (401/403)
- Malformed responses
- Partial responses
- Slow responses
"""
import asyncio


async def mock_provider_timeout(*args, **kwargs):
    """Simulate provider connection timeout."""
    raise TimeoutError("Connection timed out after 30s")


async def mock_provider_rate_limit(*args, **kwargs):
    """Simulate 429 rate limiting."""
    raise Exception("Provider returned 429: rate limit exceeded — try again later")


async def mock_provider_auth_failure(*args, **kwargs):
    """Simulate 401 authentication failure."""
    raise Exception("authentication failed: 401 Unauthorized — API key expired")


async def mock_provider_500(*args, **kwargs):
    """Simulate provider internal server error."""
    raise Exception("Provider returned 502 Bad Gateway")


async def mock_provider_malformed_response(*args, **kwargs):
    """Return structurally valid but semantically incomplete response."""
    return {"status": "ok", "reservations": None, "error": ""}


async def mock_provider_partial_response(*args, **kwargs):
    """Return response with missing required fields."""
    return {
        "reservation_id": "RES-001",
        # Missing: guest_name, dates, room_type
    }


async def mock_provider_slow_response(*args, **kwargs):
    """Simulate 15-second latency spike."""
    await asyncio.sleep(0.5)  # Shortened for tests, represents concept
    return {"status": "ok"}


async def mock_provider_success(*args, **kwargs):
    """Normal successful response."""
    return {"status": "ok", "reservation_id": "RES-001"}


# ── Dispatch Mocks (for outbox dispatcher) ─────────────────────────

async def mock_dispatch_timeout(event):
    """Outbox dispatch that times out."""
    raise TimeoutError("Dispatch timeout to provider")


async def mock_dispatch_429(event):
    """Outbox dispatch that gets rate-limited."""
    raise Exception("Provider returned 429: rate limit exceeded")


async def mock_dispatch_permanent(event):
    """Outbox dispatch with permanent failure."""
    return (False, "permanent: unsupported event_type 'invalid.type.v1'")


async def mock_dispatch_retryable(event):
    """Outbox dispatch with retryable failure."""
    return (False, "retryable: 503 Service Unavailable")


async def mock_dispatch_success(event):
    """Successful outbox dispatch."""
    return (True, "Dispatched: 1 sync jobs created")
