"""
HotelRunner Integration Router (Aggregator)
============================================

This file is the public entry-point for the
`/api/channel-manager/hotelrunner` API surface. After the Phase 1–5
refactor it contains only the parent `APIRouter` definition plus the
`include_router(...)` calls that mount four concern-focused sub-routers
from the `hotelrunner/` package:

  - router_schemas.py    : Pydantic request/response DTOs (no endpoints)
  - sync_log.py          : `log_sync` helper (UI-facing sync history writer)
  - factory.py           : `get_provider` helper (connection + secrets resolution)
  - router_mappings.py   : 4 endpoints — room mapping CRUD (DB-only)
  - router_internal.py   : 5 endpoints — read-only diagnostics (DB-only +
                           in-process usage counters)
  - router_connection.py : 7 endpoints — connection/settings + channel
                           discovery + transaction lookup (provider HTTP
                           egress for /test, /channels, /transactions)
  - router_sync.py       : 6 endpoints — CRITICAL push/pull (rooms,
                           rooms/update, rooms/bulk-update, reservations,
                           reservations/sync, reservations/{id}/confirm).
                           Live HotelRunner HTTP egress with retry,
                           rate-limit, and observability.

All paths and methods exposed before the refactor are preserved
byte-for-byte. Handler bodies were copied verbatim into their respective
sub-router; helper import names were normalized to `get_provider` and
`log_sync` (canonical path: `hotelrunner.factory` and `hotelrunner.sync_log`).
The temporary back-compat shims for legacy `_get_provider` / `_log_sync`
imports were removed on 2026-04-25 after a repo-wide scan confirmed all
4 lazy callers (availability_auto_sync, availability_reconciliation_worker,
hr_rate_manager_router, unified_rate_manager_router) were migrated to
canonical imports and a 6-endpoint live smoke (HTTP 403 = endpoint
resolved, auth gate active) passed.
"""
from fastapi import APIRouter

from domains.channel_manager.providers.hotelrunner import (
    router_connection,
    router_internal,
    router_mappings,
    router_sync,
)

router = APIRouter(prefix="/api/channel-manager/hotelrunner", tags=["HotelRunner Integration"])

# Phase 2: DB-only sub-routers.
router.include_router(router_mappings.router)
router.include_router(router_internal.router)
# Phase 3: connection / settings sub-router (provider HTTP egress for
# /test, /channels, /channels/connected, /transactions/{tid}).
router.include_router(router_connection.router)
# Phase 4: CRITICAL push/pull sub-router (live HotelRunner integration).
router.include_router(router_sync.router)
