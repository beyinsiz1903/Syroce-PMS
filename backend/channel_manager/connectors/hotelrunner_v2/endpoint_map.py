"""
HotelRunner v2 — Endpoint Map
===============================

Endpoint-based version mapping.
HR API uses mixed v1/v2 paths — do NOT assume single API version.

Source: https://developers.hotelrunner.com/custom-apps/rest-api
"""

# ── Base URL ─────────────────────────────────────────────────────────
BASE_URL_PRODUCTION = "https://app.hotelrunner.com"
BASE_URL_SANDBOX = "https://sandbox.hotelrunner.com"

# ── Endpoint Map ─────────────────────────────────────────────────────
# Each endpoint has: path, method, api_version

ENDPOINTS = {
    # Inventory
    "rooms_list": {
        "path": "/api/v2/apps/rooms",
        "method": "GET",
        "api_version": "v2",
        "description": "Get room list (rates, inv_code, capacities)",
    },
    "rooms_update": {
        "path": "/api/v2/apps/rooms/~",
        "method": "PUT",
        "api_version": "v2",
        "description": "Update room ARI (availability, price, stop_sale, CTA/CTD, min_stay)",
    },

    # Reservations
    "reservations_list": {
        "path": "/api/v2/apps/reservations",
        "method": "GET",
        "api_version": "v2",
        "description": "Retrieve reservations with pagination",
    },
    "reservations_confirm": {
        "path": "/api/v2/apps/reservations/~",
        "method": "PUT",
        "api_version": "v2",
        "description": "Confirm/acknowledge reservation delivery",
    },

    # Info / Transaction
    "channels_list": {
        "path": "/api/v1/apps/infos/channels",
        "method": "GET",
        "api_version": "v1",
        "description": "Get connected channel list",
    },
    "transaction_details": {
        "path": "/api/v1/apps/infos/transaction_details",
        "method": "GET",
        "api_version": "v1",
        "description": "Get ARI update transaction status/logs",
    },
}


def get_path(endpoint_name: str) -> str:
    """Get the path for a named endpoint."""
    ep = ENDPOINTS.get(endpoint_name)
    if not ep:
        raise ValueError(f"Unknown endpoint: {endpoint_name}")
    return ep["path"]
