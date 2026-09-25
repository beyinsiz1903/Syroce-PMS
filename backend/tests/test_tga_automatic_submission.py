from datetime import date

import pytest

from core import tga_outbound


class _Aggregate:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length: int):
        return self.rows[:length]


class _Charges:
    def __init__(self, rows):
        self.rows = rows
        self.pipeline = None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return _Aggregate(self.rows)


class _Db:
    def __init__(self, rows):
        self.folio_charges = _Charges(rows)


@pytest.mark.asyncio
async def test_automatic_price_uses_net_room_amount_and_selling_rate(monkeypatch):
    fake_db = _Db([{"net_room_revenue_try": 10_000, "room_nights": 4}])
    monkeypatch.setattr(tga_outbound, "db", fake_db)

    async def rate(_day):
        return 50.0, date(2026, 9, 25)

    monkeypatch.setattr(tga_outbound, "_tcmb_eur_selling_rate", rate)
    result = await tga_outbound.calculate_automatic_average_price_eur(
        "tenant-1", 2026, 9, data_through=date(2026, 9, 25)
    )

    assert result["average_price_eur"] == 50.0
    assert result["net_room_revenue_try"] == 10_000
    assert result["room_nights"] == 4
    assert result["tcmb_eur_selling_rate"] == 50.0
    match = fake_db.folio_charges.pipeline[0]["$match"]
    assert match["business_date"] == {"$gte": "2026-09-01", "$lt": "2026-09-26"}


@pytest.mark.asyncio
async def test_automatic_price_fails_closed_without_posted_room_revenue(monkeypatch):
    monkeypatch.setattr(tga_outbound, "db", _Db([]))
    with pytest.raises(ValueError, match="Night Audit oda geliri"):
        await tga_outbound.calculate_automatic_average_price_eur(
            "tenant-1", 2026, 9, data_through=date(2026, 9, 25)
        )


def test_monthly_rows_stop_at_automatic_cutoff():
    rows = tga_outbound.calculate_monthly_v6_rows(
        [
            {
                "check_in": "2026-09-24T14:00:00+00:00",
                "check_out": "2026-09-28T11:00:00+00:00",
                "adults": 2,
                "guest_id": "g1",
            }
        ],
        {"g1": "Türkiye"},
        date(2026, 9, 1),
        date(2026, 9, 26),
    )
    assert sum(row["haftaici_toplam_satilan_oda_gece"] + row["haftasonu_toplam_satilan_oda_gece"] for row in rows) == 2
