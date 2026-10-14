import pytest
from pydantic import ValidationError

from routers import marketplace_b2b


def test_marketplace_search_requires_an_age_for_every_child():
    with pytest.raises(ValidationError, match="Her çocuk için yaş bilgisi"):
        marketplace_b2b.MarketplaceSearchRequest(
            check_in="2026-10-10",
            check_out="2026-10-11",
            adults=2,
            children=1,
            child_ages=[],
        )


def test_marketplace_search_accepts_discovery_facets():
    request = marketplace_b2b.MarketplaceSearchRequest(
        check_in="2026-10-15",
        check_out="2026-10-17",
        adults=2,
        children=0,
        amenities=["pool", "Deniz Manzarası"],
        meal_plans=["BB", "AI"],
        min_star_rating=4,
        max_price=20_000,
    )

    assert request.amenities == ["pool", "Deniz Manzarası"]
    assert request.meal_plans == ["BB", "AI"]
    assert request.min_star_rating == 4
    assert marketplace_b2b._normalized_tokens(request.amenities) == {"pool", "sea_view"}


def test_marketplace_filter_tokens_are_case_and_separator_safe():
    assert marketplace_b2b._filter_token("Her Şey Dahil") == "ai"
    assert marketplace_b2b._filter_token("sea-view") == "sea_view"


def test_marketplace_reservation_rejects_invalid_child_age():
    with pytest.raises(ValidationError, match="0-17"):
        marketplace_b2b.MarketplaceReservationCreate(
            tenant_id="hotel-1",
            room_type="family",
            check_in="2026-10-10",
            check_out="2026-10-11",
            guest_name="Test Guest",
            adults=2,
            children=1,
            child_ages=[18],
        )


async def _sale_try(_tenant_id):
    return "TRY"


@pytest.mark.asyncio
async def test_marketplace_price_applies_saved_child_age_bands(monkeypatch):
    async def fake_rule(_db, _tenant_id, _room):
        return {
            "pricing_type": "per_person",
            "base_occupancy": 2,
            "extra_adult_rate": 1000,
            "child_age_bands": [
                {"min_age": 0, "max_age": 5, "pricing_mode": "free", "value": 0},
                {"min_age": 6, "max_age": 11, "pricing_mode": "fixed", "value": 400},
                {"min_age": 12, "max_age": 17, "pricing_mode": "adult_rate", "value": 0},
            ],
            "currency": "TRY",
        }

    monkeypatch.setattr(marketplace_b2b, "find_occupancy_rule", fake_rule)
    monkeypatch.setattr(marketplace_b2b, "_sale_currency", _sale_try)
    pricing = {
        "sellable": True,
        "nightly_rates": [{"date": "2026-10-10", "rate": 3000}],
        "total_price": 3000,
    }

    free = await marketplace_b2b._marketplace_occupancy_price(
        tenant_id="hotel-1", room={"room_type": "family"}, pricing=pricing, adults=2, child_ages=[4]
    )
    charged = await marketplace_b2b._marketplace_occupancy_price(
        tenant_id="hotel-1", room={"room_type": "family"}, pricing=pricing, adults=2, child_ages=[8]
    )

    assert free["total_price"] == 3000
    assert charged["total_price"] == 3400
    assert charged["occupancy_pricing"]["child_supplement_nightly"] == 400


PRICING = {"sellable": True, "nightly_rates": [{"date": "2026-11-20", "rate": 4000}], "total_price": 4000}
PER_PERSON = {"pricing_type": "per_person", "base_occupancy": 1, "extra_adult_rate": 1500, "max_occupancy": 3}


async def _price(monkeypatch, rule, *, adults=2, legacy_currency=None):
    async def fake_rule(*_a):
        return rule

    async def legacy(_tenant_id):
        return legacy_currency

    monkeypatch.setattr(marketplace_b2b, "find_occupancy_rule", fake_rule)
    monkeypatch.setattr(marketplace_b2b, "_sale_currency", _sale_try)
    monkeypatch.setattr(marketplace_b2b, "_legacy_rule_currency", legacy)
    return await marketplace_b2b._marketplace_occupancy_price(
        tenant_id="hotel-1", room={"room_type": "Standard"}, pricing=PRICING, adults=adults, child_ages=[]
    )


@pytest.mark.asyncio
async def test_each_hotel_chooses_per_room_or_per_person(monkeypatch):
    per_room = await _price(monkeypatch, {"pricing_type": "per_room", "extra_adult_rate": 1500, "currency": "USD"}, adults=3)
    assert per_room["total_price"] == 4000  # per room: party size never changes the price
    per_person = await _price(monkeypatch, {**PER_PERSON, "currency": "TRY"}, adults=3)
    assert per_person["total_price"] == 4000 + 2 * 1500  # base covers 1 adult, 2 extra adults


@pytest.mark.asyncio
async def test_supplement_in_another_currency_closes_the_room_instead_of_mispricing(monkeypatch):
    usd = await _price(monkeypatch, {**PER_PERSON, "currency": "USD"})
    assert usd["sellable"] is False and usd["reason"] == "occupancy_rule_currency_mismatch"
    # Rules saved before currencies were recorded were entered in the channel currency.
    legacy = await _price(monkeypatch, PER_PERSON, legacy_currency="USD")
    assert legacy["reason"] == "occupancy_rule_currency_mismatch"
    # Percentage supplements are currency-neutral.
    pct = await _price(monkeypatch, {**PER_PERSON, "extra_adult_rate_type": "percentage", "extra_adult_rate": 50, "currency": "USD"})
    assert pct["sellable"] is True and pct["total_price"] == 6000


@pytest.mark.asyncio
async def test_rejected_party_closes_one_room_type_not_the_search(monkeypatch):
    result = await _price(monkeypatch, {**PER_PERSON, "currency": "TRY"}, adults=4)
    assert result["sellable"] is False
    assert result["reason"] == "occupancy_rule_rejected"
    assert "maksimum 3" in result["occupancy_error"]
