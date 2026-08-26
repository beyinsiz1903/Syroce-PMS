"""Deterministic occupancy-based room pricing.

The channel manager receives only the base nightly rate.  These rules are the
PMS-side commercial policy used for direct/manual reservations and for an
operator preview before a base rate is sent to the provider.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MONEY = Decimal("0.01")
PRICING_RULE_VERSION = "occupancy-v1"


class OccupancyPricingError(ValueError):
    """Raised when an occupancy quote cannot be calculated safely."""


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OccupancyPricingError(f"{field} sayisal olmali") from exc
    if not result.is_finite() or result < 0:
        raise OccupancyPricingError(f"{field} negatif veya gecersiz olamaz")
    return result.quantize(MONEY, rounding=ROUND_HALF_UP)


def normalize_occupancy_rule(rule: dict[str, Any] | None) -> dict[str, Any]:
    raw = rule or {}
    pricing_type = str(raw.get("pricing_type") or "per_room")
    if pricing_type not in {"per_person", "per_room"}:
        raise OccupancyPricingError("Gecersiz fiyatlandirma tipi")

    base_occupancy = int(raw.get("base_occupancy") or 2)
    max_occupancy_raw = raw.get("max_occupancy")
    max_occupancy = int(max_occupancy_raw) if max_occupancy_raw not in (None, "") else None
    child_free_age_max = int(raw.get("child_free_age_max") or 0)
    if not 1 <= base_occupancy <= 20:
        raise OccupancyPricingError("Fiyata dahil yetiskin sayisi 1-20 arasinda olmali")
    if max_occupancy is not None and not base_occupancy <= max_occupancy <= 50:
        raise OccupancyPricingError("Maksimum kisi sayisi dahil kisi sayisindan az olamaz")
    if not 0 <= child_free_age_max <= 17:
        raise OccupancyPricingError("Ucretsiz cocuk yas siniri 0-17 arasinda olmali")

    return {
        "pricing_type": pricing_type,
        "base_occupancy": base_occupancy,
        "extra_adult_rate": float(_decimal(raw.get("extra_adult_rate", 0), field="Ek yetiskin ucreti")),
        "extra_child_rate": float(_decimal(raw.get("extra_child_rate", 0), field="Ek cocuk ucreti")),
        "child_free_age_max": child_free_age_max,
        "max_occupancy": max_occupancy,
        "pricing_version": str(raw.get("pricing_version") or PRICING_RULE_VERSION),
    }


def calculate_occupancy_quote(
    *,
    base_nightly_rate: Any,
    nights: int,
    adults: int,
    children_ages: list[int] | None,
    rule: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return an auditable nightly and stay-total quote."""

    normalized = normalize_occupancy_rule(rule)
    base_rate = _decimal(base_nightly_rate, field="Taban gecelik fiyat")
    nights = int(nights)
    adults = int(adults)
    ages = [int(age) for age in (children_ages or [])]
    if nights < 1:
        raise OccupancyPricingError("Konaklama en az bir gece olmali")
    if adults < 1:
        raise OccupancyPricingError("En az bir yetiskin olmali")
    if any(age < 0 or age > 17 for age in ages):
        raise OccupancyPricingError("Cocuk yaslari 0-17 arasinda olmali")

    guests = adults + len(ages)
    max_occupancy = normalized["max_occupancy"]
    if max_occupancy is not None and guests > max_occupancy:
        raise OccupancyPricingError(f"Toplam kisi sayisi oda kapasitesini asiyor (maksimum {max_occupancy})")

    extra_adults = 0
    chargeable_children = 0
    if normalized["pricing_type"] == "per_person":
        extra_adults = max(0, adults - normalized["base_occupancy"])
        chargeable_children = sum(age > normalized["child_free_age_max"] for age in ages)

    adult_supplement = _decimal(normalized["extra_adult_rate"], field="Ek yetiskin ucreti") * extra_adults
    child_supplement = _decimal(normalized["extra_child_rate"], field="Ek cocuk ucreti") * chargeable_children
    nightly_total = (base_rate + adult_supplement + child_supplement).quantize(MONEY, rounding=ROUND_HALF_UP)
    stay_total = (nightly_total * nights).quantize(MONEY, rounding=ROUND_HALF_UP)

    return {
        "pricing_version": normalized["pricing_version"],
        "pricing_type": normalized["pricing_type"],
        "base_occupancy": normalized["base_occupancy"],
        "base_nightly_rate": float(base_rate),
        "nights": nights,
        "adults": adults,
        "children_ages": ages,
        "extra_adults": extra_adults,
        "chargeable_children": chargeable_children,
        "extra_adult_rate": normalized["extra_adult_rate"],
        "extra_child_rate": normalized["extra_child_rate"],
        "adult_supplement_nightly": float(adult_supplement),
        "child_supplement_nightly": float(child_supplement),
        "nightly_total": float(nightly_total),
        "total_amount": float(stay_total),
    }


def _room_type_candidates(room: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for field in ("room_type_code", "room_type", "type", "room_type_name"):
        value = str(room.get(field) or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    return candidates


async def find_occupancy_rule(db: Any, tenant_id: str, room: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a saved rule without depending on an active provider session.

    HotelRunner and Exely store the same PMS-side policy in separate legacy
    collections.  Manual reservations must keep working even when the provider
    is temporarily unavailable, so resolution is local and fail-closed.
    """

    candidates = _room_type_candidates(room)
    if not candidates:
        return None

    # Saved rules use provider inventory codes, whereas physical PMS rooms use
    # local room type names. Expand both supported mapping schemas first.
    for collection_name, local_field, remote_field in (
        ("hotelrunner_room_mappings", "pms_room_type", "hr_inv_code"),
        ("exely_room_mappings", "pms_room_type", "exely_room_code"),
    ):
        collection = getattr(db, collection_name)
        for candidate in list(candidates):
            mapping = await collection.find_one(
                {"tenant_id": tenant_id, local_field: candidate},
                {"_id": 0, remote_field: 1},
            )
            remote_code = str((mapping or {}).get(remote_field) or "").strip()
            if remote_code and remote_code not in candidates:
                candidates.append(remote_code)

    for collection_name in ("hr_pricing_settings", "pricing_settings"):
        collection = getattr(db, collection_name)
        for candidate in candidates:
            document = await collection.find_one(
                {"tenant_id": tenant_id, "room_type_code": candidate},
                {"_id": 0},
            )
            if document:
                return {
                    "room_type_code": candidate,
                    **normalize_occupancy_rule(document),
                }

        # Older imports sometimes changed only letter case.  Keep matching
        # deterministic and tenant-scoped rather than silently losing pricing.
        normalized_candidates = {value.casefold() for value in candidates}
        documents = await collection.find(
            {"tenant_id": tenant_id},
            {"_id": 0},
        ).to_list(length=250)
        for document in documents:
            code = str(document.get("room_type_code") or "").strip()
            if code.casefold() in normalized_candidates:
                return {
                    "room_type_code": code,
                    **normalize_occupancy_rule(document),
                }
    return None
