"""A PMS superadmin cannot sign in on the agency login page (use the
audited admin preview instead); agency users still can."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.security import hash_password
from routers import agency_portal
from routers import marketplace_b2b as marketplace


class _Users:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, *_a, **_k):
        return dict(self.rows[0]) if self.rows else None


REQUEST = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})


def _sysdb(user):
    return SimpleNamespace(
        users=_Users([user]),
        agencies=SimpleNamespace(find_one=AsyncMock(return_value={"id": "ag1", "name": "Eski Acente", "status": "active"})),
        marketplace_login_attempts=SimpleNamespace(count_documents=AsyncMock(return_value=0), insert_one=AsyncMock(),
                                                   delete_many=AsyncMock()),
        marketplace_agencies=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )


@pytest.fixture
def patched(monkeypatch):
    throttle = importlib.import_module("security.auth_throttle")
    for name in ("AGENCY_LOGIN_IP", "AGENCY_LOGIN_ACCOUNT"):
        monkeypatch.setattr(throttle, name, SimpleNamespace(reset=AsyncMock()))
    monkeypatch.setattr(throttle, "enforce", AsyncMock())
    monkeypatch.setattr(agency_portal, "decrypt_user_doc", lambda doc: doc)

    def use(user):
        db = _sysdb(user)
        monkeypatch.setattr(importlib.import_module("core.tenant_db"), "get_system_db", lambda: db)
        monkeypatch.setattr(marketplace, "get_system_db", lambda: db)
        return db

    return use


SUPER = {"id": "sa", "role": "super_admin", "roles": ["super_admin"], "tenant_id": "t1", "hashed_password": hash_password("SuperSifre1234")}


@pytest.mark.asyncio
async def test_superadmin_is_refused_on_both_agency_logins(patched):
    patched(SUPER)
    with pytest.raises(HTTPException) as legacy:
        await agency_portal.agency_login(REQUEST, agency_portal.AgencyLoginRequest(email="sa@example.com", password="SuperSifre1234"))
    assert legacy.value.status_code == 403 and "Acente hesabına geç" in legacy.value.detail

    with pytest.raises(HTTPException) as extranet:
        await marketplace.marketplace_extranet_login(marketplace.MarketplaceLoginRequest(email="sa@example.com", password="SuperSifre1234"), REQUEST)
    assert extranet.value.status_code == 403 and "Acente hesabına geç" in extranet.value.detail


@pytest.mark.asyncio
async def test_legacy_agency_user_still_signs_in(patched):
    patched({"id": "u1", "role": "agency_admin", "roles": ["agency_admin"], "agency_id": "ag1", "tenant_id": "t1",
             "hashed_password": hash_password("AcenteSifre1234")})
    result = await agency_portal.agency_login(REQUEST, agency_portal.AgencyLoginRequest(email="a@example.com", password="AcenteSifre1234"))
    assert result["token"] and result["agency"]["id"] == "ag1"
