"""Regression matrix for two-property, multi-device authentication boundaries.

The scenarios in this file deliberately combine the tenant, device-session,
refresh and privileged-workspace contracts.  They are kept independent from a
running demo property so every pull request exercises the security boundary.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from core.security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_admin_tenant_context_token,
    create_refresh_token,
    create_token,
    get_current_user,
)
from modules.folio.services.open_folio_service import OpenFolioService
from modules.inventory.services.create_room_block_service import CreateRoomBlockService
from modules.inventory.services.release_room_block_service import ReleaseRoomBlockService
from modules.reservations.services.create_reservation_service import CreateReservationService
from modules.reservations.services.update_reservation_service import UpdateReservationService
from routers.auth import _enforce_refresh_invariants

TENANT_A = "hotel-a"
TENANT_B = "hotel-b"


def _user_doc(*, user_id="user-a", tenant_id=TENANT_A, role="admin"):
    return {
        "id": user_id,
        "tenant_id": tenant_id,
        "email": f"{user_id}@example.com",
        "name": user_id,
        "role": role,
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_two_tenants_cannot_exchange_access_tokens_between_users_or_devices():
    """A token's tenant is bound to its server-side user record, not UI state."""
    forged_cross_property_token = create_token("user-a", TENANT_B, session_id="device-a")
    system_db = AsyncMock()
    system_db.users.find_one = AsyncMock(return_value=_user_doc())

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security.is_session_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=system_db),
        patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda value: value),
    ):
        with pytest.raises(HTTPException) as error:
            await get_current_user(credentials=MagicMock(credentials=forged_cross_property_token))

    assert error.value.status_code == 401


def test_refresh_token_cannot_change_the_property_of_its_user():
    """Refresh rejects a token whose tenant differs from the user record."""
    refresh_token, _ = create_refresh_token("user-a", TENANT_B, session_id="device-a")
    import jwt

    payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    with pytest.raises(HTTPException) as error:
        _enforce_refresh_invariants(_user_doc(), payload, kind="refresh")

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_on_one_device_does_not_end_the_same_user_on_another_device():
    """A workstation logout revokes its own family only; the parallel device stays valid."""
    token_a = create_token("user-a", TENANT_A, session_id="device-a")
    token_b = create_token("user-a", TENANT_A, session_id="device-b")
    system_db = AsyncMock()
    system_db.users.find_one = AsyncMock(return_value=_user_doc())

    async def revoked(_jti, *, session_id=None):
        return session_id == "device-a"

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(side_effect=revoked)),
        patch("core.security.is_session_revoked", new=AsyncMock(side_effect=revoked)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=system_db),
        patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda value: value),
    ):
        with pytest.raises(HTTPException):
            await get_current_user(credentials=MagicMock(credentials=token_a))
        active = await get_current_user(credentials=MagicMock(credentials=token_b))

    assert active.tenant_id == TENANT_A


@pytest.mark.asyncio
async def test_privileged_context_switch_has_an_actor_and_an_effective_property():
    """Only a signed admin context token can change the effective tenant."""
    token, _ = create_admin_tenant_context_token("super-1", TENANT_A, TENANT_B)
    system_db = AsyncMock()
    system_db.users.find_one = AsyncMock(return_value=_user_doc(user_id="super-1", role="super_admin"))
    system_db.tenants.find_one = AsyncMock(return_value={"id": TENANT_B, "property_name": "Hotel B", "is_active": True})

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security.is_session_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=system_db),
        patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda value: value),
    ):
        user = await get_current_user(credentials=MagicMock(credentials=token))

    assert (user.actor_tenant_id, user.tenant_id, user.is_impersonating) == (TENANT_A, TENANT_B, True)


@pytest.mark.parametrize(
    "service",
    [
        CreateReservationService(),
        UpdateReservationService(),
        OpenFolioService(),
        CreateRoomBlockService(),
        ReleaseRoomBlockService(),
    ],
)
def test_property_header_can_never_override_authenticated_tenant_for_mutations(service):
    """Every shared mutation service rejects a foreign x-property-id value."""
    with pytest.raises(HTTPException) as error:
        service._enforce_property_scope(TENANT_A, TENANT_B)

    assert error.value.status_code == 403
