"""Shared tenant-level pull settings; never control the process-wide worker here."""

MIN_PULL_INTERVAL_SECONDS = 180
MAX_PULL_INTERVAL_SECONDS = 3600
DEFAULT_PULL_INTERVAL_SECONDS = 900


def connection_pull_interval_seconds(connection: dict) -> int:
    """Prefer the saved UI setting, with bounded support for legacy seconds."""
    try:
        minutes = connection.get("sync_interval_minutes")
        raw = minutes if minutes is not None else connection.get("sync_interval_seconds", DEFAULT_PULL_INTERVAL_SECONDS)
        if isinstance(raw, bool):
            raise ValueError("Boolean interval")
        seconds = int(raw) * 60 if minutes is not None else int(raw)
    except (TypeError, ValueError, OverflowError):
        seconds = DEFAULT_PULL_INTERVAL_SECONDS
    return max(MIN_PULL_INTERVAL_SECONDS, min(seconds, MAX_PULL_INTERVAL_SECONDS))
