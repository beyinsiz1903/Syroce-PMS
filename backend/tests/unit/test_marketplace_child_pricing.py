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
        }

    monkeypatch.setattr(marketplace_b2b, "find_occupancy_rule", fake_rule)
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
