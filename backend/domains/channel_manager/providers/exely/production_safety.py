"""Fail-closed runtime gates for Exely production provider I/O."""

from __future__ import annotations

from infra.feature_flags import is_disabled, is_enabled

from .security import is_exely_production

ENABLE_EXELY_PRODUCTION = "ENABLE_EXELY_PRODUCTION"
DISABLE_EXELY_RESERVATION_SYNC = "DISABLE_EXELY_RESERVATION_SYNC"
DISABLE_EXELY_ARI_WRITE = "DISABLE_EXELY_ARI_WRITE"

EXELY_PRODUCTION_DISABLED = "EXELY_PRODUCTION_DISABLED"
EXELY_RESERVATION_SYNC_DISABLED = "EXELY_RESERVATION_SYNC_DISABLED"
EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE = "EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE"


def provider_io_block_reason() -> str:
    """Return a safe reason when production provider access is not enabled."""
    if is_exely_production() and not is_enabled(ENABLE_EXELY_PRODUCTION):
        return EXELY_PRODUCTION_DISABLED
    return ""


def reservation_sync_block_reason() -> str:
    """Gate reservation reads and delivery acknowledgements together."""
    reason = provider_io_block_reason()
    if reason:
        return reason
    if is_disabled(DISABLE_EXELY_RESERVATION_SYNC):
        return EXELY_RESERVATION_SYNC_DISABLED
    return ""


def ari_write_block_reason() -> str:
    """Gate every Exely ARI mutation immediately before durable delivery."""
    reason = provider_io_block_reason()
    if reason:
        return reason
    if is_disabled(DISABLE_EXELY_ARI_WRITE):
        return EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE
    return ""


def safe_runtime_state() -> dict[str, bool]:
    """Expose booleans only; never return raw environment values."""
    production_environment = is_exely_production()
    production_enabled = not production_environment or not provider_io_block_reason()
    return {
        "production_environment": production_environment,
        "production_activation_enabled": production_enabled,
        "reservation_sync_allowed": not reservation_sync_block_reason(),
        "ari_write_allowed": not ari_write_block_reason(),
    }
