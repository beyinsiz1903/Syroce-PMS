from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.enums import UserRole
from routers import agency_content


@pytest.mark.asyncio
async def test_content_update_syncs_existing_marketplace_listing(monkeypatch):
    hotel_content = SimpleNamespace(
        find_one=AsyncMock(return_value={"content_version": 4}),
        update_one=AsyncMock(),
    )
    agencies = SimpleNamespace(update_many=AsyncMock(return_value=SimpleNamespace(modified_count=2)))
    tenant_db = SimpleNamespace(hotel_content=hotel_content, agencies=agencies)
    listings = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    monkeypatch.setattr(agency_content, "db", tenant_db)
    contracts = SimpleNamespace(count_documents=AsyncMock(return_value=3))
    monkeypatch.setattr(
        agency_content, "get_system_db", lambda: SimpleNamespace(marketplace_listings=listings, agency_contracts=contracts)
    )

    data = agency_content.HotelContentUpdate(
        hotel_name="The Canyon Kartepe",
        description="Dağ oteli",
        address="Kartepe",
        city="Kocaeli",
        country="tr",
        star_rating=5,
        meal_plans=["BB"],
        images=["/api/uploads/t1/hotel-content/hotel/hero.webp"],
        amenities=["Jakuzi"],
        room_types=[
            agency_content.RoomTypeContent(
                room_type="suite", name="Jakuzi Suite", images=["room.webp"]
            )
        ],
    )
    user = SimpleNamespace(
        id="u1", email="hotel@example.com", tenant_id="t1", role=UserRole.ADMIN, roles=[]
    )

    response = await agency_content.update_hotel_content(data, user)

    assert response["content_version"] == 5
    assert response["distribution"] == {
        "marketplace_listing_synced": True,
        "published_agencies_updated": 2,
        "contracted_marketplace_agencies": 3,
    }
    listing_update = listings.update_one.await_args.args[1]["$set"]
    assert listing_update["photos"] == data.images
    assert listing_update["city"] == "Kocaeli"
    assert listing_update["country"] == "TR"
    assert listing_update["room_content"][0]["name"] == "Jakuzi Suite"
    agencies.update_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_content_update_does_not_auto_publish_unlisted_hotel(monkeypatch):
    tenant_db = SimpleNamespace(
        hotel_content=SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock()),
        agencies=SimpleNamespace(update_many=AsyncMock(return_value=SimpleNamespace(modified_count=0))),
    )
    listings = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)))
    monkeypatch.setattr(agency_content, "db", tenant_db)
    contracts = SimpleNamespace(count_documents=AsyncMock(return_value=0))
    monkeypatch.setattr(
        agency_content, "get_system_db", lambda: SimpleNamespace(marketplace_listings=listings, agency_contracts=contracts)
    )
    user = SimpleNamespace(
        id="u1", email="hotel@example.com", tenant_id="t1", role=UserRole.ADMIN, roles=[]
    )

    response = await agency_content.update_hotel_content(
        agency_content.HotelContentUpdate(hotel_name="Kapalı listing"), user
    )

    assert response["distribution"]["marketplace_listing_synced"] is False
    assert listings.update_one.await_args.args[0] == {"tenant_id": "t1"}
    assert "$set" in listings.update_one.await_args.args[1]
