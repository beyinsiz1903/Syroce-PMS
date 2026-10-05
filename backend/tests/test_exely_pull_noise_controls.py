import logging
import time

from domains.channel_manager.providers.exely import observability
from domains.channel_manager.providers.exely.errors import ExelyRateLimitError
from domains.channel_manager.providers.exely.provider import ExelyProvider


def test_local_quota_backpressure_is_not_counted_as_provider_failure(caplog):
    observability.reset_metrics()
    caplog.set_level(logging.INFO, logger="exely.provider")
    provider = ExelyProvider(username="u", password="p", hotel_code="H")

    provider._handle_error(
        ExelyRateLimitError(retry_after_seconds=45, source="local_quota"),
        time.time(),
        "OTA_ReadRQ",
    )

    health = observability.get_provider_health()
    assert health["error_count"] == 0
    assert "local_quota_blocked action=OTA_ReadRQ retry_after_seconds=45" in caplog.text
