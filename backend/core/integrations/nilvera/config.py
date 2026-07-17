"""Nilvera integration configuration."""

import os
from typing import Literal

from pydantic import BaseModel, Field


class NilveraSettings(BaseModel):
    """Configuration for Nilvera integration."""

    env: Literal["test", "production"] = Field(default="test")
    timeout_ms: int = Field(default=30000, gt=0, le=120000)
    retry_max: int = Field(default=3, ge=0, le=5, description="Number of retries after the initial attempt. 3 means 4 total attempts.")
    retry_base_delay_ms: int = Field(default=1000, gt=0)
    max_response_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)  # 10MB default

    @property
    def base_url(self) -> str:
        """Get the effective base URL."""
        if self.env == "production":
            return "https://api.nilvera.com"
        return "https://apitest.nilvera.com"


class NilveraEndpoints:
    """Official Nilvera API endpoints (V1)."""
    # Company / Taxpayer lookups
    CHECK_TAX_NUMBER = "/general/GlobalCompany/Check/TaxNumber/{tax_number}"
    GET_CUSTOMER_INFO = "/general/GlobalCompany/GetGlobalCustomerInfo/{tax_number}"

    # E-Invoice
    SEND_INVOICE_MODEL = "/einvoice/Send/Model"


_config: NilveraSettings | None = None


def get_nilvera_config() -> NilveraSettings:
    """Lazy loader for config."""
    global _config
    if _config is None:
        raw_env = os.environ.get("NILVERA_ENV")
        if raw_env is None:
            env_val = "test"
        else:
            env_val = raw_env.strip().lower()

        _config = NilveraSettings(
            env=env_val,
            timeout_ms=int(os.environ.get("NILVERA_TIMEOUT_MS", "30000")),
            retry_max=int(os.environ.get("NILVERA_RETRY_MAX", "3")),
            retry_base_delay_ms=int(os.environ.get("NILVERA_RETRY_BASE_DELAY_MS", "1000")),
            max_response_size_bytes=int(os.environ.get("NILVERA_MAX_RESPONSE_SIZE_BYTES", str(10 * 1024 * 1024))),
        )
    return _config
