from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers.marketplace_b2b import _require_hotel_admin


def test_marketplace_listing_management_rejects_guest_and_staff_roles():
    for role in ("guest", "staff", "front_desk", "agency_admin"):
        with pytest.raises(HTTPException) as error:
            _require_hotel_admin(SimpleNamespace(role=role, tenant_id="hotel-1"))
        assert error.value.status_code == 403


def test_marketplace_listing_management_allows_hotel_management():
    assert _require_hotel_admin(SimpleNamespace(role="admin", tenant_id="hotel-1")) == "hotel-1"
    assert _require_hotel_admin(SimpleNamespace(role="supervisor", tenant_id="hotel-1")) == "hotel-1"

