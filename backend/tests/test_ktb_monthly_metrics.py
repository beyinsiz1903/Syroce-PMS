from datetime import UTC, datetime

from modules.regulatory.ktb_monthly import calculate_ktb_stays


def _normalize_country(raw: str | None) -> str:
    if not raw:
        return "Belirtilmemiş"
    return {"TR": "Türkiye", "DE": "Almanya"}.get(raw.upper(), raw)


def _period() -> tuple[datetime, datetime]:
    return datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)


def test_ktb_counts_month_carry_in_as_new_arrival() -> None:
    start, end = _period()
    metrics = calculate_ktb_stays(
        [
            {
                "id": "carry-in",
                "check_in": "2026-08-31T14:00:00+00:00",
                "check_out": "2026-09-02T11:00:00+00:00",
                "adults": 2,
                "children": 0,
                "nationality": "TR",
            }
        ],
        start,
        end,
        _normalize_country,
    )

    assert metrics["arrivals_total"] == 2
    assert metrics["arrivals_domestic"] == 2
    assert metrics["carried_in_guests"] == 2
    assert metrics["room_nights_sold"] == 1
    assert metrics["person_nights_domestic"] == 2


def test_ktb_uses_checkout_exclusive_nights_and_country_split() -> None:
    start, end = _period()
    metrics = calculate_ktb_stays(
        [
            {
                "id": "foreign",
                "check_in": "2026-09-01T14:00:00+00:00",
                "check_out": "2026-09-03T11:00:00+00:00",
                "adults": 1,
                "children": 1,
                "nationality": "DE",
            },
            {
                "id": "checkout-at-boundary",
                "check_in": "2026-08-30T14:00:00+00:00",
                "check_out": "2026-09-01T11:00:00+00:00",
                "adults": 1,
                "nationality": "TR",
            },
        ],
        start,
        end,
        _normalize_country,
    )

    assert metrics["valid_booking_count"] == 1
    assert metrics["arrivals_foreign"] == 2
    assert metrics["room_nights_sold"] == 2
    assert metrics["person_nights_foreign"] == 4
    assert metrics["nights_by_country"] == {"Almanya": 4}


def test_ktb_surfaces_missing_nationality_and_guest_count_fallback() -> None:
    start, end = _period()
    metrics = calculate_ktb_stays(
        [
            {
                "id": "missing-country",
                "confirmation_number": "KTB-1",
                "guest_name": "Eksik Uyruk",
                "check_in": "2026-09-10",
                "check_out": "2026-09-12",
            }
        ],
        start,
        end,
        _normalize_country,
    )

    assert metrics["adults_fallback_count"] == 1
    assert metrics["arrivals_unspecified"] == 1
    assert metrics["person_nights_unspecified"] == 2
    assert metrics["missing_nationality_total"] == 1
    assert metrics["missing_nationality"][0]["id"] == "missing-country"
