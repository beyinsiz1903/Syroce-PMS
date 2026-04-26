# Syroce PMS — Backend

FastAPI backend powering the Syroce Hotel PMS. Multi-tenant architecture with MongoDB, outbox pattern, and integrated channel manager.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI (Python 3.11+) |
| Database | MongoDB 7.0+ (Motor async driver) |
| Auth | JWT (PyJWT) + bcrypt |
| Validation | Pydantic v2 |
| Linting | Ruff (config in `pyproject.toml`) |
| Testing | pytest + pytest-asyncio |
| Encryption | AES-256-GCM with AAD binding |

## Directory Structure

```
backend/
  server.py               # App entrypoint (uvicorn)
  app.py                  # FastAPI app factory
  startup.py              # DB indexes, worker startup
  bootstrap/
    router_registry.py    # All route registration
    middleware_registry.py # Middleware chain
    worker_registry.py    # Background worker startup
    dependency_container.py
  core/
    database.py           # MongoDB connection (Motor)
    tenant_db.py          # Tenant-scoped DB access
    entitlement.py        # Plan-based module enforcement
    metering.py           # Usage event tracking
    feature_flags.py      # Dynamic feature flags
    onboarding.py         # Onboarding automation
    outbox_service.py     # Outbox pattern implementation
    outbox_worker.py      # Outbox dispatch worker
    import_bridge_service.py  # OTA reservation import
    crypto/               # AES-256-GCM encryption
    secrets/              # Secrets management
  controlplane/
    ops_router.py         # Failure management API
    timeline_writer.py    # Event timeline append
    timeline_reader.py    # Timeline query + gap detection
    timeline_router.py    # Timeline API (7 endpoints)
    dashboard_aggregator.py # Health score + metrics
    dashboard_router.py   # Dashboard API (5 endpoints)
    failure_tracker.py    # Structured failure recording
    retry_engine.py       # Idempotent retry with dry-run
    alerting.py           # Alert engine with cooldowns
    runbooks.py           # 14 operational runbooks
  channel_manager/
    domain/               # Reservation, ARI value objects
    application/          # Use cases
    connectors/           # Exely (SOAP), HotelRunner (REST)
    infrastructure/       # Persistence, mapping
    interfaces/           # HTTP routes
  domains/
    admin/                # Entitlement, metering, flags API
    pms/                  # Rooms, bookings, guests
    guest/                # Guest profiles
    revenue/              # Revenue management
    sales/                # Group sales, CRM
  ops/
    deploy_pipeline.py    # 6-gate deploy pipeline
    smoke_test_runner.py  # 8 HTTP smoke tests
    migration_verification.py # Schema drift detection
    auto_rollback_engine.py   # Metric-based rollback
    deploy_router.py      # Deploy API endpoints
  routers/                # HTTP route handlers
  security/               # Guards, rate limiter, isolation
  workers/                # Background workers (ARI, retry)
  tests/                  # Test suite
  _legacy/                # Quarantined legacy files
  docs/                   # Architecture documentation
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server (managed by supervisor in production)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Lint
ruff check .

# Test (curated CI suite)
pytest tests/test_hardening_comprehensive.py tests/test_controlplane_api.py -v
```

## Environment

```bash
# Required in .env
MONGO_URL=<mongodb-connection-string>
DB_NAME=<database-name>
JWT_SECRET=<min-32-chars>
```

## Linting

Ruff configuration in `pyproject.toml`:
- Target: Python 3.11
- Rules: E9, F63, F7, F82
- Excludes: `_legacy/`, test generators, demo data scripts

## Real-time event rooms (Socket.IO)

Live internal-chat events are routed through tenant-scoped rooms instead of
the legacy global `pms` room, so a tenant's read receipts and typing
indicators only reach the directly involved user(s). The auth payload
attached to the socket on `connect` enrols the client into the rooms below
automatically (`websocket_server.py::_internal_chat_rooms`).

| Room name pattern                                | Joined by                                | Used for                                                         |
|--------------------------------------------------|------------------------------------------|------------------------------------------------------------------|
| `internal_chat:{tenant_id}:user:{user_id}`       | the authenticated user of that socket    | DMs, read receipts (sent to the message author), typing-from-partner |
| `internal_chat:{tenant_id}:dept:{department}`    | every authenticated user in that dept    | department-targeted internal messages                            |
| `internal_chat:{tenant_id}:broadcast`            | every authenticated user in the tenant   | tenant-wide announcements                                        |

Rules of thumb when adding a new live event:
- Address the smallest plausible audience (`:user:` first, then `:dept:`, then `:broadcast`).
- Never reuse the global `pms` room for anything user/tenant specific — it is shared across all signed-in clients.
- The 15-second polling fallback in the chat UI must keep covering the WS
  outage path, so live events are an optimisation, not a correctness
  requirement.
