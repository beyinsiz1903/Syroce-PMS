"""Read-only envelope checks and lossless, coarse price dispatch planning.

Keep a selection in one envelope when it fits. For larger price selections,
group by rate plan, retaining all rooms and the complete placement table.
Only an individually oversized period needs contiguous sub-periods; never
expand a range into daily requests or remove a selected tariff or placement.
PMSConnect 1.17.1 pp.9-12 and 23 define category budgets and the explicit
PriceUploadIsAllowed flag. Missing optional flags are not proof of a derived
tariff; only an explicit provider prohibition can mark a tariff read-only.
The distributed provider quota remains authoritative at delivery time.
"""

from collections import defaultdict
from datetime import date, timedelta

from .provider_quota import CHANGES_PER_SECOND


def price_upload_allowed(connection: dict, *rate_codes: str) -> bool | None:
    codes = {str(code) for code in rate_codes if code}
    flags = [row.get("price_upload_is_allowed") for row in connection.get("rate_plans", [])
             if str(row.get("code")) in codes]
    if any(flag is False for flag in flags):
        return False
    if any(flag is True for flag in flags):
        return True
    return None


def category_change_counts(messages: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for message in messages:
        room = str(message["room_type_code"]).strip().casefold()
        nights = (date.fromisoformat(message["end_date"]) - date.fromisoformat(message["start_date"])).days + 1
        # A price for EACH accommodation type/date is a change (spec p9).
        counts[room] += nights * len(message["guest_prices"]) if "guest_prices" in message else nights
    return dict(counts)


def single_envelope_error(operation: str, messages: list[dict]) -> dict | None:
    """Intrinsic envelope limits, independent of transient Redis usage."""
    if len(messages) > 200:
        return {
            "error_code": "EXELY_SINGLE_REQUEST_MESSAGE_LIMIT",
            "message": "Seçim tek Exely isteğinde en fazla 200 dönem içerebilir. Otomatik parçalama yapılmadı; hiçbir kayıt değiştirilmedi.",
        }
    counts = category_change_counts(messages)
    maximum = max(counts.values(), default=0)
    if maximum > CHANGES_PER_SECOND:
        return {
            "error_code": "EXELY_SINGLE_REQUEST_CHANGE_LIMIT",
            "operation": operation,
            "category_change_count": maximum,
            "category_change_limit": CHANGES_PER_SECOND,
            "message": (
                f"Bu seçim bir oda tipi için {maximum} değişiklik içeriyor; Exely tek saniyede en fazla {CHANGES_PER_SECOND} kabul eder. "
                "Oda satırını açıp fiyat planlarını veya tarih aralığını düzenleyin. "
                "Plan/tarih çıkarılmadı, gönderim parçalanmadı ve hiçbir kayıt değiştirilmedi."
            ),
        }
    return None


def plan_rate_envelopes(messages: list[dict]) -> list[list[dict]]:
    """Plan already-validated prices without mutating the caller's selection.

    Exely permits a few requests grouped by rate plan or room type. Every
    envelope still respects the existing per-category change/message budget.
    Quota reservation, pacing and outcome handling belong to delivery, not
    to this pure preflight. Replanning the output is idempotent.
    """
    if not messages:
        return []
    if not single_envelope_error("rate_batch", messages):
        return [messages]

    by_plan: dict[str, list[dict]] = {}
    for message in messages:
        by_plan.setdefault(str(message["rate_plan_code"]), []).append(message)

    envelopes: list[list[dict]] = []
    for group in by_plan.values():
        bins: list[list[dict]] = []
        costs: list[dict[str, int]] = []
        for message in group:
            # Keep every placement together and split a long interval only
            # when that single interval exceeds an envelope's category budget.
            placements = len(message.get("guest_prices", [None]))
            days_per_period = CHANGES_PER_SECOND // placements
            start = date.fromisoformat(message["start_date"])
            end = date.fromisoformat(message["end_date"])
            while start <= end:
                period_end = min(end, start + timedelta(days=days_per_period - 1))
                part = {**message, "start_date": start.isoformat(), "end_date": period_end.isoformat()}
                room = str(part["room_type_code"]).strip().casefold()
                cost = ((period_end - start).days + 1) * placements
                for index, bucket in enumerate(bins):
                    if len(bucket) < 200 and costs[index].get(room, 0) + cost <= CHANGES_PER_SECOND:
                        bucket.append(part)
                        costs[index][room] = costs[index].get(room, 0) + cost
                        break
                else:
                    bins.append([part])
                    costs.append({room: cost})
                start = period_end + timedelta(days=1)
        envelopes.extend(bins)
    return envelopes
