"""
HotelRunner Provider — API Endpoint Constants
===============================================

Centralizes all magic strings. Single place to update when API paths change.

API Reference: https://developers.hotelrunner.com/custom-apps/rest-api
"""

# ── Base URLs ─────────────────────────────────────────────────────────
BASE_URL = "https://app.hotelrunner.com"
V2_PREFIX = "/api/v2/apps"
V1_PREFIX = "/api/v1/apps"

# ── V2 Endpoints (primary) ───────────────────────────────────────────
ROOMS = f"{V2_PREFIX}/rooms"
RESERVATIONS = f"{V2_PREFIX}/reservations"
RESERVATIONS_FIRE = f"{V2_PREFIX}/reservations/fire"
RESERVATIONS_ACK = f"{V2_PREFIX}/reservations/~"
CONNECTED_CHANNELS = f"{V2_PREFIX}/infos/connected_channels"
TRANSACTION_DETAILS = f"{V2_PREFIX}/infos/transaction_details"

# ── ARI Push Endpoints ───────────────────────────────────────────────
ROOMS_DAILY = f"{V2_PREFIX}/rooms/daily"
ROOMS_DATERANGE = f"{V2_PREFIX}/rooms/~"

# ── V1 Endpoints (info) ──────────────────────────────────────────────
CHANNELS = f"{V1_PREFIX}/infos/channels"

# ── OTA/XML Endpoints (used by advanced ARI adapter) ─────────────────
ARI_AVAILABILITY = "/ari/availability"
ARI_RATES = "/ari/rates"
