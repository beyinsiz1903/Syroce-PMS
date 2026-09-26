from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.enums import UserRole
from routers import platform_scaling


class _Users:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserted = None

    async def find_one(self, _query):
        return self.existing

    async def insert_one(self, document):
        self.inserted = document


@pytest.mark.asyncio
async def test_chain_headquarters_can_create_user_only_in_verified_member(monkeypatch):
    properties = [
        {"id": "hotel-a", "property_name": "A", "chain_id": "chain-1"},
        {"id": "hotel-b", "property_name": "B", "chain_id": "chain-1"},
    ]
    users = _Users()
    monkeypatch.setattr(
        platform_scaling,
        "resolve_chain_properties",
        lambda *_args, **_kwargs: _async_value((properties[0], properties)),
    )
    monkeypatch.setattr(platform_scaling, "get_system_db", lambda: SimpleNamespace(users=users))
    monkeypatch.setattr(platform_scaling, "hash_password", lambda value: f"hash:{value}")
    monkeypatch.setattr(platform_scaling, "encrypt_user_doc", lambda value: value)

    result = await platform_scaling.api_create_chain_team_member(
        platform_scaling.ChainTeamMemberReq(
            property_id="hotel-b",
            name="Nilay",
            email="nilay@example.com",
            password="password-123",
            role=UserRole.SUPERVISOR,
        ),
        SimpleNamespace(id="hq-user", tenant_id="hotel-a", role=UserRole.ADMIN),
    )

    assert result["property_id"] == "hotel-b"
    assert users.inserted["tenant_id"] == "hotel-b"
    assert users.inserted["role"] == "supervisor"
    assert users.inserted["created_via"] == "chain_headquarters"


@pytest.mark.asyncio
async def test_chain_headquarters_cannot_create_user_outside_verified_chain(monkeypatch):
    own = {"id": "hotel-a", "property_name": "A", "chain_id": "chain-1"}
    monkeypatch.setattr(
        platform_scaling,
        "resolve_chain_properties",
        lambda *_args, **_kwargs: _async_value((own, [own])),
    )

    with pytest.raises(HTTPException) as exc:
        await platform_scaling.api_create_chain_team_member(
            platform_scaling.ChainTeamMemberReq(
                property_id="other-chain-hotel",
                name="Attacker",
                email="attacker@example.com",
                password="password-123",
                role=UserRole.ADMIN,
            ),
            SimpleNamespace(id="hq-user", tenant_id="hotel-a", role=UserRole.ADMIN),
        )

    assert exc.value.status_code == 403


def test_admin_tier_roles_are_valid_login_roles():
    from domains.admin.router.hotel import ROLES_BY_TIER as HOTEL_ROLES_BY_TIER
    from domains.admin.router.tenants import ROLES_BY_TIER

    canonical = {role.value for role in UserRole}
    assert all(set(roles) <= canonical for roles in ROLES_BY_TIER.values())
    assert all(set(roles) <= canonical for roles in HOTEL_ROLES_BY_TIER.values())


async def _async_value(value):
    return value
