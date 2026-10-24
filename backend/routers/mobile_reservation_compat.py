"""Read-only compatibility for the reservation-account URL shipped in iOS 28.

New clients use /api/pms/reservations/{id}/full-detail. Keep the exact same
handler and dependency graph for installed clients; never duplicate financial
logic, bypass authentication, or add aliases for mutations.
"""

from fastapi import APIRouter, Depends

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.user_access_policy import enforce_request_access
from routers.reservation_detail import get_reservation_full_detail


def _require_canonical_account_access(booking_id: str, current_user: User = Depends(get_current_user)):
    # Auth also checks the incoming legacy path. Apply the canonical resource
    # policy as well, so later page/scope restrictions cannot be bypassed by
    # an installed client retaining the older URL.
    enforce_request_access(current_user, f"/api/pms/reservations/{booking_id}/full-detail", "GET")


router = APIRouter(prefix="/api/reservations", tags=["reservation-detail"])
router.add_api_route(
    "/{booking_id}/full-detail",
    get_reservation_full_detail,
    methods=["GET"],
    dependencies=[Depends(_require_canonical_account_access)],
    include_in_schema=False,
)
