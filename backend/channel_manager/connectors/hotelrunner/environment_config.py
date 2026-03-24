"""
Environment Configuration for HotelRunner Connector.

Supports: sandbox, mock, production environments.
Each environment defines its own base URLs, timeouts, and feature flags.
"""
from typing import Any, Dict

from pydantic import BaseModel


class EnvironmentConfig(BaseModel):
    """Configuration for a specific runtime environment."""
    name: str
    api_base_url: str
    sandbox: bool = True
    timeout_connect: float = 10.0
    timeout_read: float = 30.0
    retry_max: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    rate_limit_rps: int = 10
    enable_audit_payloads: bool = True
    enable_raw_logging: bool = False
    credential_encryption_required: bool = True
    sync_polling_interval_seconds: int = 300
    reservation_polling_interval_seconds: int = 300
    description: str = ""


ENVIRONMENTS: Dict[str, EnvironmentConfig] = {
    "mock": EnvironmentConfig(
        name="mock",
        api_base_url="http://localhost:9999/api/v2",
        sandbox=True,
        timeout_connect=5.0,
        timeout_read=10.0,
        retry_max=1,
        retry_base_delay=0.1,
        retry_max_delay=1.0,
        rate_limit_rps=100,
        enable_audit_payloads=True,
        enable_raw_logging=True,
        credential_encryption_required=False,
        sync_polling_interval_seconds=60,
        reservation_polling_interval_seconds=60,
        description="Local mock server for development and testing",
    ),
    "sandbox": EnvironmentConfig(
        name="sandbox",
        api_base_url="https://sandbox.hotelrunner.com/api/v2",
        sandbox=True,
        timeout_connect=10.0,
        timeout_read=30.0,
        retry_max=3,
        retry_base_delay=1.0,
        retry_max_delay=30.0,
        rate_limit_rps=10,
        enable_audit_payloads=True,
        enable_raw_logging=True,
        credential_encryption_required=True,
        sync_polling_interval_seconds=300,
        reservation_polling_interval_seconds=300,
        description="HotelRunner sandbox for integration testing",
    ),
    "production": EnvironmentConfig(
        name="production",
        api_base_url="https://app.hotelrunner.com/api/v2",
        sandbox=False,
        timeout_connect=10.0,
        timeout_read=30.0,
        retry_max=5,
        retry_base_delay=2.0,
        retry_max_delay=60.0,
        rate_limit_rps=5,
        enable_audit_payloads=True,
        enable_raw_logging=False,
        credential_encryption_required=True,
        sync_polling_interval_seconds=300,
        reservation_polling_interval_seconds=300,
        description="HotelRunner production API",
    ),
}


def get_environment_config(env_name: str) -> EnvironmentConfig:
    """Get config for a named environment. Defaults to sandbox."""
    return ENVIRONMENTS.get(env_name, ENVIRONMENTS["sandbox"])


def get_all_environments() -> Dict[str, Dict[str, Any]]:
    """Return all environment configs as dicts."""
    return {k: v.model_dump() for k, v in ENVIRONMENTS.items()}
