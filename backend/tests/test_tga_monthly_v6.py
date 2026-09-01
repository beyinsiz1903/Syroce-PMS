from datetime import UTC, date, datetime

from core.tga_outbound import TGA_PATH, calculate_monthly_v6_rows


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def test_v6_uses_official_monthly_endpoint_and_weekend_definition() -> None:
    assert TGA_PATH == "/tesis-aylik-rapor/"
    rows = calculate_monthly_v6_rows(
        [
            {
                "id": "b1",
                "check_in": _dt("2026-08-07T14:00:00"),  # Friday
                "check_out": _dt("2026-08-09T11:00:00"),
                "adults": 2,
                "children": 1,
                "guest_id": "g1",
            }
        ],
        {"g1": "Türkiye"},
        date(2026, 8, 1),
        date(2026, 9, 1),
    )

    assert rows == [
        {
            "iso_kodu": "TUR",
            "haftaici_toplam_giris_yapan_misafir": 0,
            "haftasonu_toplam_giris_yapan_misafir": 3,
            "haftaici_toplam_geceleme": 0,
            "haftasonu_toplam_geceleme": 6,
            "haftaici_toplam_satilan_oda_gece": 0,
            "haftasonu_toplam_satilan_oda_gece": 2,
        }
    ]


def test_v6_checkout_is_exclusive_and_month_carry_in_is_not_new_arrival() -> None:
    rows = calculate_monthly_v6_rows(
        [
            {
                "id": "b1",
                "check_in": _dt("2026-07-31T14:00:00"),
                "check_out": _dt("2026-08-02T11:00:00"),
                "adults": 2,
                "guest_id": "g1",
            }
        ],
        {"g1": "unknown value"},
        date(2026, 8, 1),
        date(2026, 9, 1),
    )

    assert rows[0]["iso_kodu"] == "OTHER"
    assert rows[0]["haftasonu_toplam_giris_yapan_misafir"] == 0
    assert rows[0]["haftasonu_toplam_geceleme"] == 2
    assert rows[0]["haftasonu_toplam_satilan_oda_gece"] == 1

