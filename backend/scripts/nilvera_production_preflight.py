"""Fail-closed, read-only Nilvera production preflight.

The platform-level preflight validates the central production API credential with
one non-retrying GET. When a target tenant is supplied by the production runtime,
its Nilvera enablement and seller identity are loaded from Syroce tenant settings
and a second non-retrying GET verifies that seller identity.

No provider values, credentials, VKNs, tenant identifiers, or response payloads
are printed. This script is intentionally incapable of provider mutation.
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
from core.integrations.nilvera.provisioner import get_nilvera_tenant_config

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


def _target_tenant_id() -> str | None:
    value = os.environ.get("NILVERA_PRODUCTION_TARGET_TENANT_ID", "").strip()
    if not value:
        return None
    if len(value) > 128:
        raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_TENANT_ID_INVALID")
    return value


async def _load_tenant_seller_vkn(tenant_id: str) -> str:
    tenant_cfg = await get_nilvera_tenant_config(tenant_id, decrypt_api_key=False)
    if not tenant_cfg.get("enabled"):
        raise NilveraProductionPreflightError("BLOCKED_TENANT_NILVERA_NOT_ENABLED")

    seller = tenant_cfg.get("seller") or {}
    seller_vkn = str(seller.get("vkn") or "").strip()
    if not _VKN.fullmatch(seller_vkn):
        raise NilveraProductionPreflightError("BLOCKED_TENANT_SELLER_VKN_INVALID")
    return seller_vkn


async def run_preflight() -> None:
    api_key = _required("NILVERA_PRODUCTION_API_KEY")
    tenant_id = _target_tenant_id()

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
    tenant_context_present = False
    seller_identity_format_valid = False

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

            if tenant_id is not None:
                seller_vkn = await _load_tenant_seller_vkn(tenant_id)
                tenant_context_present = True
                seller_identity_format_valid = True
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

    expected_read_count = 2 if tenant_id is not None else 1
    if provider_read_count != expected_read_count:
        raise NilveraProductionPreflightError("BLOCKED_PRODUCTION_PROVIDER_READ_COUNT")

    print(
        "NILVERA_PRODUCTION_PREFLIGHT "
        "production_host=true, credential_present=true, "
        f"tenant_context_present={str(tenant_context_present).lower()}, "
        f"seller_identity_format_valid={str(seller_identity_format_valid).lower()}, "
        "incoming_answer_enabled=false, create_return_enabled=false, "
        f"provider_read_count={provider_read_count}, provider_write_count=0"
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
