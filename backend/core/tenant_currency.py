"""
Tenant currency helper.

Reads the per-tenant currency preference from `hotel_settings.currency`
(falls back to 'TRY'). Cached in-process for 60 seconds to avoid
hammering Mongo on every dashboard request.
"""
from __future__ import annotations

import time
from typing import Tuple

from core.database import db

_CACHE: dict[str, Tuple[float, str, str]] = {}
_TTL = 60.0

_DEFAULT_SYMBOLS = {
    "TRY": "\u20ba",
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
}


def _symbol_for(code: str) -> str:
    return _DEFAULT_SYMBOLS.get((code or "TRY").upper(), code or "")


async def get_tenant_currency(tenant_id: str) -> Tuple[str, str]:
    """Return (currency_code, currency_symbol) for the tenant."""
    if not tenant_id:
        return "TRY", _symbol_for("TRY")

    now = time.monotonic()
    cached = _CACHE.get(tenant_id)
    if cached and (now - cached[0]) < _TTL:
        return cached[1], cached[2]

    code = "TRY"
    symbol = _symbol_for("TRY")
    try:
        settings = await db.hotel_settings.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0, "currency": 1, "currency_symbol": 1},
        )
        if settings:
            code = (settings.get("currency") or "TRY").upper()
            symbol = settings.get("currency_symbol") or _symbol_for(code)
    except Exception:
        pass

    _CACHE[tenant_id] = (now, code, symbol)
    return code, symbol


def invalidate_tenant_currency(tenant_id: str) -> None:
    _CACHE.pop(tenant_id, None)
