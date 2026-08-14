"""Fail-closed, read-only Nilvera production preflight.

This script is intentionally incapable of provider mutation. It validates the
production runtime contract and performs two non-retrying GET requests only.
No provider values, credentials, VKNs, tenant identifiers, or response payloads
are printed.
"""

from __future__ import annotations

import asyncio
import os
import re

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import (
    NilveraEndpoints,
    get_nilvera_config,
)
from core.integrations.nilvera.errors import NilveraApiError


_VKN = re.compile(r"^\d{10,11}$")


class NilveraProductionPreflightError(RuntimeError):
    """Safe, redacted production preflight failure."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise NilveraProductionPreflightError(f"BLOCKED_{name}_MISSING")
    return value


def _require_false(name: str) -> None:
    value = os.environ.get(name, "false").strip().lower()
    if value != "false":
        raise NilveraProductionPreflightError(f"BLOCKED_{name}_MUST_BE_FALSE")


async def run_preflight() -> None:
    tenant_id = _required("NILVERA_PRODUCTION_TENANT_ID")
    api_key = _required("NILVERA_PRODUCTION_API_KEY")
    seller_vkn = _required("NILVERA_PRODUCTION_SELLER_VKN")

    if len(tenant_id) > 128:
        raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_TENANT_ID_INVALID")
    if not _VKN.fullmatch(seller_vkn):
        raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_SELLER_VKN_INVALID")

    _require_false("NILVERA_INCOMING_ANSWER_ENABLED")
    _require_false("NILVERA_CREATE_RETURN_ENABLED")

    config = get_nilvera_config()
    if not config.enabled:
        raise NilveraProductionPreflightError("BLOCKED_NILVERA_GLOBAL_GATE_DISABLED")
    if config.env != "production":
        raise NilveraProductionPreflightError("BLOCKED_NILVERA_ENV_NOT_PRODUCTION")
    if config.base_url != "https://api.nilvera.com":
        raise NilveraProductionPreflightError("BLOCKED_NILVERA_PRODUCTION_HOST_MISMATCH")

    provider_read_count = 0
    async with NilveraHttpClient(api_key=api_key) as client:
        try:
            company = await client.get(
                NilveraEndpoints.GET_COMPANY,
                retryable=False,
                stage="PRODUCTION_PREFLIGHT_COMPANY",
            )
            provider_read_count += 1
            if not isinstance(company, dict):
                raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_COMPANY_RESPONSE_INVALID")

            taxpayer = await client.get(
                NilveraEndpoints.CHECK_TAX_NUMBER.format(tax_number=seller_vkn),
                retryable=False,
                stage="PRODUCTION_PREFLIGHT_TAXPAYER",
            )
            provider_read_count += 1
            if not isinstance(taxpayer, (dict, list, bool)):
                raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_TAXPAYER_RESPONSE_INVALID")
        except NilveraProductionPreflightError:
            raise
        except NilveraApiError as exc:
            raise NilveraProductionPreflightError(
                f"BLOCKED_PRODUCTION_PROVIDER_READ_{exc.classification or 'FAILED'}"
            ) from None
        except Exception as exc:
            raise NilveraProductionPreflightError(
                f"BLOCKED_PRODUCTION_PREFLIGHT_{type(exc).__name__.upper()}"
            ) from None

    if provider_read_count != 2:
        raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_PROVIDER_READ_COUNT")

    print(
        "NILVERA_PRODUCTION_PREFLIGHT "
        "production_host=true, credential_present=true, tenant_context_present=true, "
        "seller_identity_format_valid=true, incoming_answer_enabled=false, "
        "create_return_enabled=false, provider_read_count=2, provider_write_count=0"
    )


def main() -> int:
    try:
        asyncio.run(run_preflight())
    except NilveraProductionPreflightError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
