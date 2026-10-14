"""Every active hotel is visible to agencies; sales still need an approved contract."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import agency_hotel_directory as directory
from routers import agency_contracts
from routers import marketplace_b2b as marketplace


class _Coll:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, *_a, **_k):
        rows = self.rows
        ids = (query.get("id") or query.get("tenant_id") or {}).get("$in") if isinstance(query.get("id") or query.get("tenant_id"), dict) else None
        if ids is not None:
            key = "id" if "id" in query else "tenant_id"
            rows = [r for r in rows if r.get(key) in ids]
        return SimpleNamespace(to_list=AsyncMock(return_value=copy.deepcopy(rows)))


def _sysdb():
    return SimpleNamespace(
        tenants=_Coll([
            {"id": "t-open", "property_name": "Canyon Kartepe", "location": "Kocaeli"},
            {"id": "t-hidden", "property_name": "Hidden Hotel"},
            {"id": "t-off", "property_name": "Closed Hotel", "is_active": False},
            {"id": "t-unpaid", "property_name": "Unpaid Hotel", "subscription_status": "suspended"},
        ]),
        marketplace_listings=_Coll([{"tenant_id": "t-hidden", "is_listed": False}]),
        hotel_content=_Coll([{"tenant_id": "t-open", "images": ["/api/uploads/t-open/hotel-content/hotel/a.webp"], "star_rating": 5,
                              "meal_plans": ["BB"], "description": "Dağ oteli", "room_types": [{"room_type": "Suite", "name": "Jakuzi Suite"}]}]),
        hotel_settings=_Coll([{"tenant_id": "t-open", "currency": "eur"}]),
    )


@pytest.mark.asyncio
async def test_directory_lists_active_hotels_without_a_listing_document():
    profiles = await directory.hotel_profiles(_sysdb(), include_hidden=False)
    assert [p["tenant_id"] for p in profiles] == ["t-open"]
    teaser = directory.teaser(profiles[0])
    assert teaser == {
        "tenant_id": "t-open", "hotel_name": "Canyon Kartepe", "city": "Kocaeli", "country": "TR", "star_rating": 5,
        "meal_plans": ["BB"], "room_type_names": ["Jakuzi Suite"], "cover_photo": "/api/uploads/t-open/hotel-content/hotel/a.webp",
        "summary": "Dağ oteli", "currency": "EUR",
    }


@pytest.mark.asyncio
async def test_hidden_hotel_keeps_contracts_but_refuses_new_proposals(monkeypatch):
    monkeypatch.setattr(marketplace, "get_system_db", _sysdb)
    assert (await marketplace._get_listing_or_404("t-hidden"))["hidden"] is True
    with pytest.raises(HTTPException) as exc:
        await marketplace._get_listing_or_404("t-hidden", for_proposal=True)
    assert exc.value.status_code == 404
    for inactive in ("t-off", "t-unpaid"):
        with pytest.raises(HTTPException):
            await marketplace._get_listing_or_404(inactive)


@pytest.mark.asyncio
async def test_bulk_proposal_reports_each_hotel(monkeypatch):
    calls = []

    async def propose(data, agency):
        calls.append((data.tenant_id, data.currency))
        if data.tenant_id == "t-dup":
            raise HTTPException(409, "zaten pending")
        return {"contract": {"hotel_name": data.tenant_id, "contract_code": f"SOZ-{data.tenant_id}"}}

    async def listing(tenant_id, for_proposal=False):
        return {"currency": "EUR" if tenant_id == "t-open" else "TRY"}

    monkeypatch.setattr(agency_contracts, "contract_propose", propose)
    monkeypatch.setattr(agency_contracts, "_listing_dep", listing)
    data = agency_contracts.ContractProposeBulk(tenant_ids=["t-open", "t-dup", "t-open"], commission_pct=12,
                                               valid_from="2026-11-01", valid_to="2027-10-31")

    result = await agency_contracts.contract_propose_bulk(data, {"agency_id": "a1"})

    assert calls == [("t-open", "EUR"), ("t-dup", "TRY")]  # de-duplicated, per-hotel currency
    assert (result["sent"], result["failed"]) == (1, 1)
    assert result["results"][1] == {"tenant_id": "t-dup", "ok": False, "error": "zaten pending"}
