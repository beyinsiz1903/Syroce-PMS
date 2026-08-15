"""Small, dependency-free coercion helpers for historical database rows."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_utc_datetime(value: Any) -> datetime | None:
    """Return a UTC-aware datetime for supported values, otherwise ``None``."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def safe_decimal(value: Any) -> Decimal:
    """Coerce stored numeric values without allowing malformed data to crash reads."""
    if isinstance(value, bool) or value is None:
        return Decimal("0")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    return amount if amount.is_finite() else Decimal("0")


def normalize_dimension_label(value: Any, *, default: str = "direct") -> str:
    """Return a bounded scalar label for legacy analytics dimensions."""
    if isinstance(value, str):
        label = value.strip()
        return label[:100] if label else default
    if isinstance(value, dict):
        for key in ("name", "code", "value", "channel", "source", "provider"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()[:100]
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                return str(candidate)[:100]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)[:100]
    return default
