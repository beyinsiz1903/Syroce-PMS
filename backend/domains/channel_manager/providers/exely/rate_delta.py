"""Build Exely price deltas from durable, property-scoped delivery receipts."""

from datetime import date, timedelta
from itertools import groupby

from .rate_placements import money


def rate_periods(operation, update):
    if operation == "rate":
        messages = [{**update, "rate_amount": update["value"]}]
    else:
        messages = update["value"]
    return [
        {**{key: row[key] for key in ("room_type_code", "rate_plan_code", "start_date", "end_date", "currency")},
         "guest_prices": row.get("guest_prices") or [{
             "kind": "adult_main", "number_of_guests": row.get("number_of_guests"),
             "amount": f"{float(row['rate_amount']):.2f}",
         }]}
        for row in messages
    ]


def _placement_key(price):
    return price["kind"], price.get("number_of_guests"), price.get("min_age"), price.get("max_age")


def changed_rate_messages(messages, receipts):
    """Receipts are newest first. An older ACK must never mask a newer write."""
    history = {}
    for receipt in receipts:
        for period in receipt["rate_periods"]:
            key = period["room_type_code"], period["rate_plan_code"]
            history.setdefault(key, []).append((receipt["state"], period))

    def changed_prices(message, day):
        prices = message["guest_prices"]
        unresolved = {_placement_key(price): price for price in prices}
        same = set()
        for state, period in history.get((message["room_type_code"], message["rate_plan_code"]), ()):
            if not unresolved:
                break
            if not period["start_date"] <= day <= period["end_date"]:
                continue
            for previous in period["guest_prices"]:
                key = _placement_key(previous)
                if key[0] == "adult_main" and key[1] is None:
                    # A legacy write without an occupancy can affect a main-bed price.
                    keys = [candidate for candidate in unresolved if candidate[0] == "adult_main"]
                else:
                    keys = [key] if key in unresolved else []
                for affected in keys:
                    if state in {"sending", "ambiguous", "reconciliation_pending"}:
                        raise UnconfirmedRateDelivery
                    price = unresolved.pop(affected)
                    if (key == affected and state == "confirmed" and period["currency"] == message["currency"]
                            and money(previous["amount"]) == money(price["amount"])):
                        same.add(affected)
        return [price for price in prices if _placement_key(price) not in same]

    result = []
    for message in messages:
        if "guest_prices" not in message:
            result.append(message)
            continue
        start = date.fromisoformat(message["start_date"])
        end = date.fromisoformat(message["end_date"])
        days = ((start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1))
        for prices, group in groupby(days, key=lambda day: changed_prices(message, day)):
            start_day = end_day = next(group)
            for end_day in group:
                pass
            if prices:
                result.append({**message, "start_date": start_day, "end_date": end_day, "guest_prices": prices})
    return result


class UnconfirmedRateDelivery(Exception):
    """The latest write to a selected placement still has an unknown outcome."""
