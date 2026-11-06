"""Read-only checks for one complete PMSConnect envelope per operation.

Never split a selection, remove a tariff, or relax provider quotas here.
PMSConnect 1.17.1 pp.9-12 and 23 define category budgets and the explicit
PriceUploadIsAllowed flag. Missing optional flags are not proof of a derived
tariff; only an explicit provider prohibition can mark a tariff read-only.
"""

from collections import defaultdict
from datetime import date

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
