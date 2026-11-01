"""PMSConnect service quotes, independent of room revenue and PMS receipts.

The provider's total already includes quantity and duration (1.17 pp.88-91).
Channel-origin services may have no API/PMS code at all (FAQ p.145).
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

NS = "{http://www.opentravel.org/OTA/2003/05}"


class ServicePayloadError(ValueError):
    """Payload-free error; never acknowledge a partially read service batch."""


def _number(value, *, integer=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or not math.isfinite(float(result)):
            raise ValueError
        if integer and result != int(result):
            raise ValueError
        return int(result) if integer else float(result)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ServicePayloadError("EXELY_SERVICE_NUMBER_INVALID") from None


def _date(value):
    value = str(value or "").strip()
    if not value:
        return ""
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:10], pattern).date().isoformat()
        except ValueError:
            pass
    raise ServicePayloadError("EXELY_SERVICE_DATE_INVALID")


def _comments(element):
    return element.findall(f"{NS}ServiceDetails/{NS}Comments/{NS}Comment")


def parse_services(reservation, rooms, currency):
    services, seen = [], set()
    nodes = reservation.findall(f"{NS}Services/{NS}Service")
    if nodes and not rooms:
        raise ServicePayloadError("EXELY_SERVICE_ROOM_MISSING")
    if len(nodes) > 1000:
        raise ServicePayloadError("EXELY_SERVICE_LIMIT")
    for node in nodes:
        rph = str(node.get("ServiceRPH") or "").strip()
        if not rph or rph in seen:
            raise ServicePayloadError("EXELY_SERVICE_REFERENCE_INVALID")
        seen.add(rph)
        total = node.find(f"{NS}ServiceDetails/{NS}Total")
        if total is None or total.get("AmountAfterTax") is None:
            raise ServicePayloadError("EXELY_SERVICE_TOTAL_MISSING")
        service_currency = str(total.get("CurrencyCode") or currency or "").strip().upper()
        if not re.fullmatch("[A-Z]{3}", service_currency):
            raise ServicePayloadError("EXELY_SERVICE_CURRENCY_INVALID")
        comments = _comments(node)
        labels = {c.get("Name"): (c.findtext(f"{NS}Text") or "").strip() for c in comments}
        name = labels.get("ServiceName") or next((str(c.get("Name") or "").strip() for c in comments if c.get("Name") not in {None, "ServiceDescription"}), "")
        description = "\n".join((c.findtext(f"{NS}Text") or "").strip() for c in comments).strip()
        timespan = node.find(f"{NS}ServiceDetails/{NS}TimeSpan")
        source_start = str(timespan.get("Start") or timespan.get("StartDate") or "") if timespan is not None else ""
        start = _date(source_start)
        if not start and rooms:
            related = [r for r in rooms if rph in r.get("service_references", [])]
            dates = {_date(r.get("check_in")) for r in related}
            if len(dates) > 1:
                raise ServicePayloadError("EXELY_SERVICE_START_AMBIGUOUS")
            start = next(iter(dates)) if dates else _date(rooms[0].get("check_in"))
        duration = _number(timespan.get("Duration", "1"), integer=True) if timespan is not None else 1
        if duration < 1 or duration > 3660:
            raise ServicePayloadError("EXELY_SERVICE_DURATION_INVALID")
        inclusive = str(node.get("Inclusive") or "").lower()
        if inclusive not in {"true", "false", "1", "0"}:
            raise ServicePayloadError("EXELY_SERVICE_INCLUSIVE_INVALID")
        rates = []
        for rate in node.findall(f"{NS}ServiceDetails/{NS}ServiceRates/{NS}ServiceRate"):
            rates.append({"date": _date(rate.get("EffectiveDate")), "amount": _number(rate.get("AmountAfterTax"))})
        services.append(
            {
                "reference": rph,
                "provider_id": str(node.get("ID") or ""),
                "inventory_code": str(node.get("ServiceInventoryCode") or ""),
                "category_code": str(node.get("ServiceCategoryCode") or ""),
                "name": name or description or "Ek hizmet",
                "description": description,
                "pricing_type": str(node.get("ServicePricingType") or ""),
                "inclusive": inclusive in {"true", "1"},
                "quantity": _number(node.get("Quantity"), integer=True),
                "amount": _number(total.get("AmountAfterTax")),
                "currency": service_currency,
                "start_date": start,
                "source_start": source_start,
                "source_end": str(timespan.get("End") or "") if timespan is not None else "",
                "duration": duration,
                "daily_rates": rates,
            }
        )
    references = {str(ref.get("RPH") or "") for room in reservation.findall(f"{NS}RoomStays/{NS}RoomStay") for ref in room.findall(f"{NS}ServiceRPHs/{NS}ServiceRPH")}
    if references - seen:
        raise ServicePayloadError("EXELY_SERVICE_REFERENCE_MISSING")
    return services


def assign_services(services, rooms):
    """Own a shared/group service once, without inventing a per-room price."""
    assigned = [[] for _ in rooms]
    for service in services:
        owners = [i for i, room in enumerate(rooms) if service["reference"] in room.get("service_references", [])]
        owner = owners[0] if owners else 0
        if not rooms:
            raise ServicePayloadError("EXELY_SERVICE_ROOM_MISSING")
        assigned[owner].append({**service, "scope": "room" if len(owners) == 1 else "reservation", "room_stay_indexes": [str(rooms[i].get("index_number") or "") for i in owners]})
    return assigned


def parse_service_inventory(body):
    result = []
    for node in body.findall(f"{NS}Services/{NS}Service"):
        comments = {c.get("Name"): (c.findtext(f"{NS}Text") or "").strip() for c in _comments(node)}
        result.append(
            {
                "provider_id": str(node.get("ID") or ""),
                "pms_code": str(node.get("ServiceInventoryCode") or ""),
                "name": comments.get("ServiceName", ""),
                "description": comments.get("ServiceDescription", ""),
                "type": str(node.get("Type") or ""),
                "pricing_type": str(node.get("ServicePricingType") or ""),
            }
        )
    return result
