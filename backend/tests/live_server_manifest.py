"""Manifest of tests that require a live server (making real HTTP requests)."""

LIVE_SERVER_TESTS = {
    "tests/test_admin_control_panel_api.py",
    "tests/test_admin_tenants_api.py",
    "tests/test_agency_portal_api.py",
    "tests/test_sandbox_simulation_api.py",
}
