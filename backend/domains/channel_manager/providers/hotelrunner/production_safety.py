"""Fail-closed runtime gates for HotelRunner production provider I/O."""

from __future__ import annotations

import os

from infra.feature_flags import is_disabled, is_enabled
from infra.production_config import is_production_env

ENABLE_HOTELRUNNER_PRODUCTION = "ENABLE_HOTELRUNNER_PRODUCTION"
DISABLE_HOTELRUNNER_RESERVATION_SYNC = "DISABLE_HOTELRUNNER_RESERVATION_SYNC"
DISABLE_HOTELRUNNER_ARI_WRITE = "DISABLE_HOTELRUNNER_ARI_WRITE"

HOTELRUNNER_PRODUCTION_DISABLED = "HOTELRUNNER_PRODUCTION_DISABLED"
HOTELRUNNER_RESERVATION_SYNC_DISABLED = "HOTELRUNNER_RESERVATION_SYNC_DISABLED"
HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE = "HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE"


def is_hotelrunner_production() -> bool:
    if is_production_env():
        return True
    return any(os.getenv(key, "").strip().lower() in {"prod", "live"} for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"))


def provider_io_block_reason() -> str:
    if is_hotelrunner_production() and not is_enabled(ENABLE_HOTELRUNNER_PRODUCTION):
        return HOTELRUNNER_PRODUCTION_DISABLED
    return ""


def reservation_sync_block_reason() -> str:
    reason = provider_io_block_reason()
    if reason:
        return reason
    if is_disabled(DISABLE_HOTELRUNNER_RESERVATION_SYNC):
        return HOTELRUNNER_RESERVATION_SYNC_DISABLED
    return ""


def ari_write_block_reason() -> str:
    reason = provider_io_block_reason()
    if reason:
        return reason
    if is_disabled(DISABLE_HOTELRUNNER_ARI_WRITE):
        return HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE
    return ""


def provider_operation_block_reason(method: str, path: str) -> str:
    """Classify every HotelRunner HTTP operation before credentials or network I/O."""
    normalized_method = method.strip().upper()
    normalized_path = path.strip().lower()
    if "reservations" in normalized_path:
        return reservation_sync_block_reason()
    if normalized_method == "GET":
        return provider_io_block_reason()
    return ari_write_block_reason()


def safe_runtime_state() -> dict[str, bool]:
    production_environment = is_hotelrunner_production()
    production_enabled = not production_environment or not provider_io_block_reason()
    return {
        "production_environment": production_environment,
        "production_activation_enabled": production_enabled,
        "reservation_sync_allowed": not reservation_sync_block_reason(),
        "ari_write_allowed": not ari_write_block_reason(),
    }
