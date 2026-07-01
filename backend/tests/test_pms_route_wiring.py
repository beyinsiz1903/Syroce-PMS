"""
PMS Route Wiring Regression Test
---------------------------------
Verifies that ALL 59 PMS routes are registered and reachable after decomposition.
This test only checks route EXISTENCE (405/422/401 are acceptable — they prove the
route is wired). A 404 means the route was lost during refactoring.
"""
import pytest
from httpx import ASGITransport, AsyncClient

PMS_ROUTES = [
    # (method, path)
    # ── Rooms ──
    ("POST", "/api/pms/rooms"),
    ("GET", "/api/pms/rooms"),
    ("POST", "/api/pms/rooms/bulk/range"),
    ("POST", "/api/pms/rooms/bulk/template"),
    ("POST", "/api/pms/rooms/bulk/delete"),
    ("POST", "/api/pms/rooms/import-csv"),
    ("POST", "/api/pms/rooms/TESTID/images"),
    ("PUT", "/api/pms/rooms/TESTID"),
    ("GET", "/api/pms/rooms/availability"),
    # ── Companies ──
    ("GET", "/api/pms/companies"),
    # ── Guests ──
    ("POST", "/api/pms/guests"),
    ("GET", "/api/pms/guests"),
    ("GET", "/api/pms/guests/search"),
    ("GET", "/api/pms/guests/TESTID"),
    ("PUT", "/api/pms/guests/TESTID"),
    # ── Bookings ──
    ("POST", "/api/pms/bookings"),
    ("GET", "/api/pms/bookings"),
    ("POST", "/api/pms/quick-booking"),
    ("POST", "/api/bookings/TESTID/approve"),
    ("POST", "/api/bookings/TESTID/reject"),
    ("PUT", "/api/pms/bookings/TESTID"),
    ("POST", "/api/bookings/TESTID/override"),
    ("GET", "/api/bookings/TESTID/override-logs"),
    ("POST", "/api/pms/bookings/multi-room"),
    # ── Room move history ──
    ("POST", "/api/pms/room-move-history"),
    # ── Dashboard ──
    ("GET", "/api/pms/dashboard"),
    ("GET", "/api/pms/operational-alerts"),
    ("GET", "/api/pms/room-alternatives/101"),
    # ── Room services ──
    ("GET", "/api/pms/room-services"),
    ("PUT", "/api/pms/room-services/TESTID"),
    # ── Room blocks ──
    ("GET", "/api/pms/room-blocks"),
    ("POST", "/api/pms/room-blocks"),
    ("PATCH", "/api/pms/room-blocks/TESTID"),
    ("POST", "/api/pms/room-blocks/TESTID/cancel"),
    # ── Staff tasks ──
    ("GET", "/api/pms/staff-tasks"),
    ("POST", "/api/pms/staff-tasks"),
    ("PUT", "/api/pms/staff-tasks/TESTID"),
    # ── Allotment contracts ──
    ("GET", "/api/pms/allotment-contracts"),
    ("POST", "/api/pms/allotment-contracts"),
    ("POST", "/api/pms/allotment-contracts/TESTID/release"),
    # ── Group reservations ──
    ("GET", "/api/pms/group-reservations"),
    ("POST", "/api/pms/group-reservations"),
    # ── Setup status ──
    ("GET", "/api/pms/setup-status"),
    # ── Room details enhanced ──
    ("GET", "/api/rooms/TESTID/details-enhanced"),
    ("POST", "/api/rooms/TESTID/notes"),
    ("POST", "/api/rooms/TESTID/minibar-update"),
    # ── Reservation details ──
    ("GET", "/api/reservations/TESTID/details-enhanced"),
    ("GET", "/api/reservations/double-booking-check"),
    ("GET", "/api/reservations/adr-visibility"),
    ("POST", "/api/reservations/rate-override-panel"),
    ("GET", "/api/reservations/TESTID/ota-details"),
    ("POST", "/api/reservations/TESTID/extra-charges"),
    ("POST", "/api/reservations/multi-room"),
    ("GET", "/api/reservations/search"),
    # ── Room queue ──
    ("POST", "/api/rooms/queue/add"),
    ("GET", "/api/rooms/queue/list"),
    ("POST", "/api/rooms/queue/assign-priority"),
    ("POST", "/api/rooms/queue/notify-guest"),
    ("DELETE", "/api/rooms/queue/TESTID"),
]


@pytest.fixture
def app():
    """Import the FastAPI app."""
    import importlib
    mod = importlib.import_module("server")
    return mod.app


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PMS_ROUTES, ids=[f"{m} {p}" for m, p in PMS_ROUTES])
async def test_pms_route_is_wired(app, method, path):
    """Every PMS route must be reachable (not 404). Auth errors (401/403) or
    validation errors (422) are fine — they prove the route exists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.request(method, path, headers={"Authorization": "Bearer fake"})
        assert resp.status_code != 404, f"Route LOST: {method} {path} returned 404"
