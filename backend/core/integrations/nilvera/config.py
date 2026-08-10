"""Nilvera integration configuration."""

import os
from typing import Literal

from pydantic import BaseModel, Field


class NilveraSettings(BaseModel):
    """Configuration for Nilvera integration."""

    enabled: bool = Field(..., description="Strict global kill switch for Nilvera integration")
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
    GET_COMPANY = "/general/Company"
    CHECK_TAX_NUMBER = "/general/GlobalCompany/Check/TaxNumber/{tax_number}"
    GET_CUSTOMER_INFO = "/general/GlobalCompany/GetGlobalCustomerInfo/{tax_number}"

    # E-Invoice
    SEND_INVOICE_MODEL = "/einvoice/Send/Model"
    LIST_SALE_INVOICES = "/einvoice/Sale"
    GET_SALE_INVOICE_STATUS = "/einvoice/Sale/{uuid}/Status"
    GET_SALE_INVOICE_DETAIL = "/einvoice/Sale/{uuid}/Details"
    GET_SALE_INVOICE_ENVELOPE_INFO = "/einvoice/Sale/{uuid}/EnvelopeInfo"

    # E-Invoice Purchase (Incoming)
    LIST_PURCHASE_INVOICES = "/einvoice/Purchase"
    GET_PURCHASE_INVOICE_DETAIL = "/einvoice/Purchase/{uuid}/Details"
    GET_PURCHASE_INVOICE_STATUS = "/einvoice/Purchase/{uuid}/Status"
    GET_PURCHASE_INVOICE_HISTORIES = "/einvoice/Purchase/{uuid}/Histories"
    SEND_ANSWER = "/einvoice/Purchase/SendAnswer"


_config: NilveraSettings | None = None


def _parse_required_bool(name: str) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        raise ValueError(f"{name}_MISSING")

    value = raw.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False

    raise ValueError(f"{name}_INVALID")


def is_nilvera_incoming_answer_enabled() -> bool:
    """Return the fail-closed incoming answer feature state."""
    return os.environ.get("NILVERA_INCOMING_ANSWER_ENABLED", "false").strip().lower() == "true"


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
            enabled=_parse_required_bool("NILVERA_ENABLED"),
            env=env_val,
            timeout_ms=int(os.environ.get("NILVERA_TIMEOUT_MS", "30000")),
            retry_max=int(os.environ.get("NILVERA_RETRY_MAX", "3")),
            retry_base_delay_ms=int(os.environ.get("NILVERA_RETRY_BASE_DELAY_MS", "1000")),
            max_response_size_bytes=int(os.environ.get("NILVERA_MAX_RESPONSE_SIZE_BYTES", str(10 * 1024 * 1024))),
        )
    return _config
