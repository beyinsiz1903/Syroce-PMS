"""Hotels choose which contracted marketplace agencies see their catalogue."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from models.enums import UserRole
from routers import agency_content

USER = SimpleNamespace(id="u1", tenant_id="t1", role=UserRole.ADMIN, roles=[])


def test_visibility_rules():
    assert agency_content.catalogue_visible_to({}, "a1")
    assert agency_content.catalogue_visible_to({"content_agency_ids": None}, "a1")
    assert agency_content.catalogue_visible_to({"content_agency_ids": ["a1"]}, "a1")
    assert not agency_content.catalogue_visible_to({"content_agency_ids": ["a2"]}, "a1")
    assert not agency_content.catalogue_visible_to({"content_agency_ids": []}, "a1")


def _sysdb(listing):
    return SimpleNamespace(marketplace_listings=SimpleNamespace(
        find_one=AsyncMock(return_value=listing), update_one=AsyncMock(),
    ))


@pytest.mark.asyncio
async def test_selected_mode_accepts_only_contracted_agencies(monkeypatch):
    sysdb = _sysdb({"id": "l1"})
    monkeypatch.setattr(agency_content, "get_system_db", lambda: sysdb)
    monkeypatch.setattr(agency_content, "_contracted_marketplace_agencies", AsyncMock(return_value=[{"id": "a1"}, {"id": "a2"}]))

    with pytest.raises(HTTPException) as exc:
        await agency_content.update_marketplace_distribution(
            agency_content.MarketplaceContentDistribution(mode="selected", agency_ids=["a1", "intruder"]), USER
        )
    assert exc.value.status_code == 400

    result = await agency_content.update_marketplace_distribution(
        agency_content.MarketplaceContentDistribution(mode="selected", agency_ids=["a2", "a1", "a1"]), USER
    )
    assert result["agency_ids"] == ["a1", "a2"]
    assert sysdb.marketplace_listings.update_one.await_args.args[1]["$set"]["content_agency_ids"] == ["a1", "a2"]


@pytest.mark.asyncio
async def test_all_mode_clears_selection_and_creates_settings_without_listing(monkeypatch):
    sysdb = _sysdb({"id": "l1"})
    monkeypatch.setattr(agency_content, "get_system_db", lambda: sysdb)
    await agency_content.update_marketplace_distribution(agency_content.MarketplaceContentDistribution(mode="all"), USER)
    assert sysdb.marketplace_listings.update_one.await_args.args[1]["$set"]["content_agency_ids"] is None

    # Every active hotel is in the agency directory; no listing document is required.
    fresh = _sysdb(None)
    monkeypatch.setattr(agency_content, "get_system_db", lambda: fresh)
    await agency_content.update_marketplace_distribution(agency_content.MarketplaceContentDistribution(mode="all"), USER)
    assert fresh.marketplace_listings.update_one.await_args.kwargs["upsert"] is True
