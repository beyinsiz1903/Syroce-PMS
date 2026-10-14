"""Legacy hotel contracts: season net rates and contract commission govern sales."""

from routers.agency_portal import _legacy_contract_terms

PRICING = {
    "sellable": True,
    "nightly_rates": [{"date": "2026-11-30", "rate": 1000.0}, {"date": "2026-12-01", "rate": 1000.0}],
    "total_price": 2000.0,
}


def test_net_rate_contract_uses_season_price_per_night_and_no_commission():
    contract = {
        "contract_type": "net_rate",
        "season_rates": [{"room_type_id": "Superior", "season_start": "2026-11-01", "season_end": "2026-11-30", "price": 700}],
    }
    pricing, commission = _legacy_contract_terms(contract, "Superior", PRICING, 10)
    assert [n["rate"] for n in pricing["nightly_rates"]] == [700.0, 1000.0]  # Dec 1 outside the season
    assert pricing["total_price"] == 1700.0
    assert commission == 0.0


def test_net_rate_for_other_room_type_keeps_calendar_price():
    contract = {"contract_type": "net_rate", "season_rates": [{"room_type_id": "Suite", "season_start": "2026-01-01", "season_end": "2026-12-31", "price": 1}]}
    pricing, _ = _legacy_contract_terms(contract, "Superior", PRICING, 10)
    assert pricing["total_price"] == 2000.0


def test_commission_contract_keeps_price_and_uses_contract_rate():
    pricing, commission = _legacy_contract_terms({"contract_type": "commission", "commission_rate": 18}, "Superior", PRICING, 10)
    assert pricing["total_price"] == 2000.0
    assert commission == 18.0


def test_without_contract_agency_default_applies():
    pricing, commission = _legacy_contract_terms(None, "Superior", PRICING, 12)
    assert pricing is PRICING and commission == 12.0
