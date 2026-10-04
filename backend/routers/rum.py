"""Privacy-preserving real-user route performance telemetry."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/observability/rum", tags=["RUM Performance"])

# Recurrent operational module entries only. Detail and redirect routes are
# intentionally excluded: they create duplicate/noisy samples and are not an
# honest measure of the workspace a hotel operator opens for their work.
# The browser maintains the equivalent path list to avoid sending telemetry
# for untracked routes; this server-side map remains the acceptance and alert
# authority.
RUM_ROUTE_BUDGETS = {
    "/app/dashboard": {"route": 5000, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/pms": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/reservation-calendar": {"route": 6500, "lcp": 4500, "inp": 500, "api": 2500},
    "/arrival-list": {"route": 5000, "lcp": 4000, "inp": 500, "api": 2000},
    "/departure-list": {"route": 5000, "lcp": 4000, "inp": 500, "api": 2000},
    "/night-audit": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/housekeeping": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/pos": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/cashier": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/invoices": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/general-ledger": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/raporlar": {"route": 6500, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/rms": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/sales": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/guest-relations": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/procurement": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/mice": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/channel-manager": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/channels": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/integration-hub": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/settings": {"route": 5000, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/folio-management": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/room-requests": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/tasks": {"route": 5000, "lcp": 4000, "inp": 500, "api": 2000},
    "/hr": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/app/xchange": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
    "/app/revenue-hub": {"route": 6000, "lcp": 4500, "inp": 600, "api": 2500},
    "/messaging-center": {"route": 5500, "lcp": 4000, "inp": 500, "api": 2000},
}
ALLOWED_ROUTES = frozenset(RUM_ROUTE_BUDGETS)
MAX_EVENTS_PER_BATCH = 10
_indexes_ready = False


class RumEvent(BaseModel):
    route: str
    route_duration_ms: int = Field(ge=0, le=600_000)
    navigation_ms: int | None = Field(default=None, ge=0, le=120_000)
    lcp_ms: int | None = Field(default=None, ge=0, le=120_000)
    inp_ms: int | None = Field(default=None, ge=0, le=120_000)
    cls: float | None = Field(default=None, ge=0, le=10)
    api_count: int = Field(ge=0, le=500)
    api_p95_ms: int | None = Field(default=None, ge=0, le=120_000)


class RumBatch(BaseModel):
    events: list[RumEvent] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)


class SessionRumEvent(BaseModel):
    event: Literal["login", "restore", "refresh", "logout", "expired"]


async def _ensure_indexes() -> None:
    """Keep sampled telemetry bounded even when no separate data-retention job runs."""
    global _indexes_ready
    if _indexes_ready:
        return
    collection = db.client_rum_events
    await collection.create_index([("tenant_id", 1), ("route", 1), ("received_at", -1)])
    await collection.create_index("received_at", expireAfterSeconds=30 * 24 * 60 * 60)
    session_collection = db.client_rum_session_events
    await session_collection.create_index([("tenant_id", 1), ("event", 1), ("received_at", -1)])
    await session_collection.create_index("received_at", expireAfterSeconds=30 * 24 * 60 * 60)
    _indexes_ready = True


@router.post("/events", status_code=202)
async def record_events(payload: RumBatch, current_user: User = Depends(get_current_user)):
    """Store sampled aggregates only; authenticated context supplies tenant scope."""
    await _ensure_indexes()
    received_at = datetime.now(UTC)
    rows = [
        {**event.model_dump(), "tenant_id": current_user.tenant_id, "received_at": received_at}
        for event in payload.events
        if event.route in ALLOWED_ROUTES
    ]
    if rows:
        await db.client_rum_events.insert_many(rows, ordered=False)
    return {"accepted": len(rows)}


@router.post("/session-events", status_code=202)
async def record_session_event(payload: SessionRumEvent, current_user: User = Depends(get_current_user)):
    """Record a sampled session lifecycle event without client-supplied identity."""
    await _ensure_indexes()
    await db.client_rum_session_events.insert_one({
        "event": payload.event,
        "tenant_id": current_user.tenant_id,
        "received_at": datetime.now(UTC),
    })
    return {"accepted": 1}


def _p95(values: list[int | float]) -> int | float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95 + 0.999999) - 1))]


@router.get("/summary")
async def performance_summary(
    hours: int = 24,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Return route p95s and explicit alert flags for an operator dashboard."""
    hours = min(max(hours, 1), 168)
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = await db.client_rum_events.find(
        {"tenant_id": current_user.tenant_id, "received_at": {"$gte": since}}, {"_id": 0, "route": 1, "route_duration_ms": 1, "navigation_ms": 1, "lcp_ms": 1, "inp_ms": 1, "api_p95_ms": 1},
    ).to_list(5_000)
    by_route: dict[str, list[dict]] = {}
    for row in rows:
        by_route.setdefault(row["route"], []).append(row)
    result = []
    for route, items in sorted(by_route.items()):
        duration = _p95([row["route_duration_ms"] for row in items])
        navigation = _p95([row["navigation_ms"] for row in items if row.get("navigation_ms") is not None])
        lcp = _p95([row["lcp_ms"] for row in items if row.get("lcp_ms") is not None])
        inp = _p95([row["inp_ms"] for row in items if row.get("inp_ms") is not None])
        api = _p95([row["api_p95_ms"] for row in items if row.get("api_p95_ms") is not None])
        budget = RUM_ROUTE_BUDGETS[route]
        alerts = [name for name, value, limit in (("route", duration, budget["route"]), ("navigation", navigation, 2000), ("lcp", lcp, budget["lcp"]), ("inp", inp, budget["inp"]), ("api", api, budget["api"])) if value is not None and value > limit]
        result.append({"route": route, "samples": len(items), "p95_route_ms": duration, "p95_navigation_ms": navigation, "p95_lcp_ms": lcp, "p95_inp_ms": inp, "p95_api_ms": api, "budget_ms": budget, "alerts": alerts})
    return {"since": since, "hours": hours, "routes": result}
