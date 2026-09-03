"""Shared deterministic occupancy-based room pricing.

The channel manager receives only the base nightly rate.  These rules are the
PMS-side commercial policy used for direct/manual reservations and for an
operator preview before a base rate is sent to the provider.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MONEY = Decimal("0.01")
PRICING_RULE_VERSION = "occupancy-v2"
CHILD_PRICING_MODES = {"free", "fixed", "adult_percentage", "adult_rate"}


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


def _legacy_child_age_bands(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate the v1 free-age/fixed-child rule into complete v2 bands."""

    free_age_max = int(raw.get("child_free_age_max") or 0)
    fixed_rate = float(_decimal(raw.get("extra_child_rate", 0), field="Ek cocuk ucreti"))
    bands = [{"min_age": 0, "max_age": free_age_max, "pricing_mode": "free", "value": 0.0}]
    if free_age_max < 17:
        bands.append(
            {
                "min_age": free_age_max + 1,
                "max_age": 17,
                "pricing_mode": "fixed",
                "value": fixed_rate,
            }
        )
    return bands


def _normalize_child_age_bands(raw: dict[str, Any]) -> list[dict[str, Any]]:
    supplied = raw.get("child_age_bands")
    if supplied in (None, []):
        return _legacy_child_age_bands(raw)
    if not isinstance(supplied, list) or len(supplied) > 18:
        raise OccupancyPricingError("Cocuk yas kademeleri liste olmali ve 18 satiri gecmemeli")

    bands: list[dict[str, Any]] = []
    for item in supplied:
        if not isinstance(item, dict):
            raise OccupancyPricingError("Cocuk yas kademesi gecersiz")
        try:
            min_age = int(item.get("min_age"))
            max_age = int(item.get("max_age"))
        except (TypeError, ValueError) as exc:
            raise OccupancyPricingError("Cocuk yas araligi tam sayi olmali") from exc
        if not 0 <= min_age <= max_age <= 17:
            raise OccupancyPricingError("Cocuk yas araligi 0-17 icinde olmali")

        pricing_mode = str(item.get("pricing_mode") or "").strip()
        if pricing_mode not in CHILD_PRICING_MODES:
            raise OccupancyPricingError("Gecersiz cocuk fiyatlandirma yontemi")
        value = _decimal(item.get("value", 0), field="Cocuk kademe degeri")
        if pricing_mode == "adult_percentage" and value > 100:
            raise OccupancyPricingError("Yetiskin ucreti yuzdesi 0-100 arasinda olmali")
        if pricing_mode in {"free", "adult_rate"}:
            value = Decimal("0.00")
        bands.append(
            {
                "min_age": min_age,
                "max_age": max_age,
                "pricing_mode": pricing_mode,
                "value": float(value),
            }
        )

    bands.sort(key=lambda band: (band["min_age"], band["max_age"]))
    expected_min_age = 0
    for band in bands:
        if band["min_age"] != expected_min_age:
            raise OccupancyPricingError("Cocuk yas kademeleri 0-17 yaslarini bosluk ve cakisma olmadan kapsamalidir")
        expected_min_age = band["max_age"] + 1
    if expected_min_age != 18:
        raise OccupancyPricingError("Cocuk yas kademeleri 0-17 yaslarini tamamen kapsamalidir")
    return bands


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

    child_age_bands = _normalize_child_age_bands(raw)
    return {
        "pricing_type": pricing_type,
        "base_occupancy": base_occupancy,
        "extra_adult_rate_type": raw.get("extra_adult_rate_type", "fixed") if raw.get("extra_adult_rate_type") in ("fixed", "percentage") else "fixed",
        "extra_adult_rate": float(_decimal(raw.get("extra_adult_rate", 0), field="Ek yetiskin ucreti")),
        "extra_child_rate": float(_decimal(raw.get("extra_child_rate", 0), field="Ek cocuk ucreti")),
        "child_free_age_max": child_free_age_max,
        "child_age_bands": child_age_bands,
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
    free_children = 0
    child_breakdown: list[dict[str, Any]] = []

    adult_rate = Decimal("0.00")
    if normalized["pricing_type"] == "per_person":
        extra_adults = max(0, adults - normalized["base_occupancy"])
        included_adult_slots = max(0, normalized["base_occupancy"] - adults)

        adult_rate_val = _decimal(normalized["extra_adult_rate"], field="Ek yetiskin ucreti")
        if normalized["extra_adult_rate_type"] == "percentage":
            adult_rate = (base_rate * adult_rate_val / Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)
        else:
            adult_rate = adult_rate_val

        for age in ages:
            band = next(
                (candidate for candidate in normalized["child_age_bands"] if candidate["min_age"] <= age <= candidate["max_age"]),
                None,
            )
            if band is None:  # Normalization guarantees complete coverage; keep fail-closed.
                raise OccupancyPricingError(f"{age} yas icin cocuk fiyat kademesi bulunamadi")
            mode = band["pricing_mode"]
            if mode == "free":
                amount = Decimal("0.00")
            elif mode == "fixed":
                amount = _decimal(band["value"], field="Cocuk sabit ucreti")
            elif mode == "adult_percentage":
                percentage = _decimal(band["value"], field="Yetiskin ucreti yuzdesi")
                amount = (adult_rate * percentage / Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)
            else:  # adult_rate: the child is an adult-equivalent for occupancy pricing.
                if included_adult_slots > 0:
                    included_adult_slots -= 1
                    amount = Decimal("0.00")
                else:
                    amount = adult_rate
            if amount > 0:
                chargeable_children += 1
            else:
                free_children += 1
            child_breakdown.append(
                {
                    "age": age,
                    "pricing_mode": mode,
                    "rate": float(amount),
                    "counts_as_adult": mode == "adult_rate",
                    "band_min_age": band["min_age"],
                    "band_max_age": band["max_age"],
                }
            )

    adult_supplement = adult_rate * extra_adults
    child_supplement = sum((_decimal(row["rate"], field="Cocuk ucreti") for row in child_breakdown), Decimal("0.00"))
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
        "free_children": free_children,
        "child_breakdown": child_breakdown,
        "extra_adult_rate_type": normalized["extra_adult_rate_type"],
        "extra_adult_rate": normalized["extra_adult_rate"],
        "extra_child_rate": normalized["extra_child_rate"],
        "child_age_bands": normalized["child_age_bands"],
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
