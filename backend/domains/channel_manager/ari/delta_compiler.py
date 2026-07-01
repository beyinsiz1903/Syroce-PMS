"""
ARI Delta Compiler.

Transforms compacted change sets into provider-specific minimal deltas.
Each provider has its own compilation strategy (HotelRunner = REST params, Exely = SOAP period).
"""

import logging

from .events import ARIDelta
from .repositories import compute_outbound_delta_hash

logger = logging.getLogger(__name__)


def compile_delta_hotelrunner(change_set: dict) -> ARIDelta:
    """Compile a change set into HotelRunner REST-compatible delta."""
    payload = change_set["compacted_payload"]
    scope = change_set["change_scope"]

    hr_payload = {}
    if scope == "availability":
        hr_payload["availability"] = payload.get("availability")
        if "stop_sell" in payload:
            hr_payload["stop_sale"] = 1 if payload["stop_sell"] else 0
    elif scope == "rate":
        hr_payload["price"] = payload.get("base_rate")
        hr_payload["currency"] = payload.get("currency", "TRY")
    elif scope == "restriction":
        if "min_los" in payload:
            hr_payload["min_stay"] = payload["min_los"]
        if "cta" in payload:
            hr_payload["cta"] = 1 if payload["cta"] else 0
        if "ctd" in payload:
            hr_payload["ctd"] = 1 if payload["ctd"] else 0
        if "stop_sell" in payload:
            hr_payload["stop_sale"] = 1 if payload["stop_sell"] else 0

    return ARIDelta(
        provider="hotelrunner",
        tenant_id=change_set["tenant_id"],
        property_id=change_set["property_id"],
        change_scope=scope,
        room_type_code=change_set["room_type_code"],
        rate_plan_code=change_set.get("rate_plan_code"),
        date_from=change_set["date_from"],
        date_to=change_set["date_to"],
        payload=hr_payload,
        provider_delta_hash=compute_outbound_delta_hash(
            provider="hotelrunner",
            property_id=change_set["property_id"],
            room_type_code=change_set["room_type_code"],
            rate_plan_code=change_set.get("rate_plan_code", ""),
            date_from=change_set["date_from"],
            date_to=change_set["date_to"],
            payload=hr_payload,
        ),
    )


def compile_delta_exely(change_set: dict) -> ARIDelta:
    """Compile a change set into Exely SOAP-compatible delta."""
    payload = change_set["compacted_payload"]
    scope = change_set["change_scope"]

    exely_payload = {}
    if scope == "availability":
        exely_payload["BookingLimit"] = payload.get("availability", 0)
        if "stop_sell" in payload:
            exely_payload["RestrictionStatus"] = "Close" if payload["stop_sell"] else "Open"
    elif scope == "rate":
        exely_payload["AmountAfterTax"] = str(payload.get("base_rate", 0))
        exely_payload["CurrencyCode"] = payload.get("currency", "TRY")
        if "occupancy_prices" in payload:
            exely_payload["OccupancyPrices"] = payload["occupancy_prices"]
    elif scope == "restriction":
        if "min_los" in payload:
            exely_payload["MinLOS"] = payload["min_los"]
        if "max_los" in payload:
            exely_payload["MaxLOS"] = payload["max_los"]
        if "cta" in payload:
            exely_payload["ArrivalDateBased"] = not payload["cta"]
        if "ctd" in payload:
            exely_payload["DepartureDateBased"] = not payload["ctd"]
        if "stop_sell" in payload:
            exely_payload["RestrictionStatus"] = "Close" if payload["stop_sell"] else "Open"

    return ARIDelta(
        provider="exely",
        tenant_id=change_set["tenant_id"],
        property_id=change_set["property_id"],
        change_scope=scope,
        room_type_code=change_set["room_type_code"],
        rate_plan_code=change_set.get("rate_plan_code"),
        date_from=change_set["date_from"],
        date_to=change_set["date_to"],
        payload=exely_payload,
        provider_delta_hash=compute_outbound_delta_hash(
            provider="exely",
            property_id=change_set["property_id"],
            room_type_code=change_set["room_type_code"],
            rate_plan_code=change_set.get("rate_plan_code", ""),
            date_from=change_set["date_from"],
            date_to=change_set["date_to"],
            payload=exely_payload,
        ),
    )


# Registry of provider compilers
COMPILERS = {
    "hotelrunner": compile_delta_hotelrunner,
    "exely": compile_delta_exely,
}


def compile_delta(change_set: dict) -> ARIDelta:
    """Compile a change set into a provider-specific delta."""
    provider = change_set["provider"]
    compiler = COMPILERS.get(provider)
    if not compiler:
        raise ValueError(f"No delta compiler for provider: {provider}")
    delta = compiler(change_set)
    logger.debug(f"Compiled delta for {provider}: {delta.change_scope} {delta.room_type_code} {delta.date_from}→{delta.date_to}")
    return delta
