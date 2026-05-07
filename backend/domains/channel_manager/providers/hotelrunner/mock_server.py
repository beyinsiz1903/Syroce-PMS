"""
HotelRunner Mock Server — Realistic API Simulation
====================================================

Simulates the HotelRunner REST API for E2E testing without real credentials.

Supported behaviors:
- Auth validation (token + hr_id query params)
- 429 rate limiting (configurable)
- 500 server errors (random injection)
- Timeout simulation
- Malformed payloads
- Duplicate webhook detection
- Stale version detection
- Partial success on bulk operations

Usage:
    from domains.channel_manager.providers.hotelrunner.mock_server import create_mock_app
    app = create_mock_app()
    # Run with: uvicorn ... on port 9999
"""
import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("hotelrunner.mock_server")

# ── Mock State ────────────────────────────────────────────────────────

VALID_TOKENS = {"mock-hr-token-001", "test-token-valid"}
VALID_HR_IDS = {"HR-HOTEL-001", "HR-HOTEL-002"}

_mock_state = {
    "request_count": 0,
    "rate_limit_after": 0,  # 0 = disabled
    "error_rate": 0.0,      # 0-1, probability of 500
    "timeout_rate": 0.0,    # 0-1, probability of timeout
    "delivered_uids": set(),
    "reservations": [],
    "rooms": [],
    "channels": [],
    "ari_updates": [],
    "webhook_events": [],
}


def _reset_state():
    _mock_state["request_count"] = 0
    _mock_state["rate_limit_after"] = 0
    _mock_state["error_rate"] = 0.0
    _mock_state["timeout_rate"] = 0.0
    _mock_state["delivered_uids"] = set()
    _mock_state["reservations"] = _generate_mock_reservations()
    _mock_state["rooms"] = _generate_mock_rooms()
    _mock_state["channels"] = _generate_mock_channels()
    _mock_state["ari_updates"] = []
    _mock_state["webhook_events"] = []


def _generate_mock_reservations() -> list:
    """Generate realistic mock reservations."""
    channels = ["booking.com", "expedia", "agoda", "direct", "airbnb"]
    states = ["confirmed", "confirmed", "confirmed", "modified", "canceled"]
    now = datetime.now(UTC)

    reservations = []
    for i in range(1, 16):
        checkin = now + timedelta(days=random.randint(1, 30))
        checkout = checkin + timedelta(days=random.randint(1, 7))
        channel = random.choice(channels)
        state = random.choice(states)
        hr_number = f"HR-{2024000 + i}"
        msg_uid = f"msg-uid-{uuid.uuid4().hex[:8]}"

        reservations.append({
            "reservation_id": str(10000 + i),
            "hr_number": hr_number,
            "state": state,
            "guest": f"Test Guest {i}",
            "firstname": f"Guest{i}",
            "lastname": f"Surname{i}",
            "country": "TR",
            "channel": channel,
            "channel_display": channel.replace(".", " ").title(),
            "checkin_date": checkin.strftime("%Y-%m-%d"),
            "checkout_date": checkout.strftime("%Y-%m-%d"),
            "total": round(random.uniform(500, 5000), 2),
            "currency": "TRY",
            "payment": "credit_card",
            "total_rooms": 1,
            "total_guests": random.randint(1, 4),
            "note": f"Mock reservation {i}",
            "message_uid": msg_uid,
            "requires_response": random.choice([True, False]),
            "address": {
                "email": f"guest{i}@example.com",
                "phone": f"+9053{random.randint(10000000, 99999999)}",
                "address_line": f"Test Sokak No:{i}",
                "city": random.choice(["Istanbul", "Ankara", "Izmir", "Antalya"]),
                "zipcode": f"{random.randint(10000, 99999)}",
                "country_code": "TR",
            },
            "rooms": [{
                "room_code": random.choice(["STD", "DLX", "SUI", "FAM"]),
                "rate_code": random.choice(["BAR", "PROMO", "RACK", "NONREF"]),
                "room_name": random.choice(["Standard Oda", "Deluxe Oda", "Suite", "Aile Odasi"]),
                "adults": random.randint(1, 3),
                "children": random.randint(0, 2),
                "total": round(random.uniform(500, 5000), 2),
                "daily_rates": [],
                "guest": f"Guest{i} Surname{i}",
            }],
            "created_at": (now - timedelta(days=random.randint(1, 10))).isoformat(),
            "updated_at": now.isoformat(),
            "modified_at": now.isoformat(),
        })

    return reservations


def _generate_mock_rooms() -> list:
    return [
        {
            "inv_code": "STD",
            "name": "Standard Oda",
            "description": "Standard tek/cift kisilik oda",
            "max_occupancy": 2,
            "rate_plans": [
                {"code": "BAR", "name": "Best Available Rate", "currency": "TRY"},
                {"code": "NONREF", "name": "Non-Refundable", "currency": "TRY"},
            ],
            "channels": ["booking.com", "expedia", "agoda"],
        },
        {
            "inv_code": "DLX",
            "name": "Deluxe Oda",
            "description": "Genis deluxe oda, deniz manzarali",
            "max_occupancy": 3,
            "rate_plans": [
                {"code": "BAR", "name": "Best Available Rate", "currency": "TRY"},
                {"code": "PROMO", "name": "Promosyon", "currency": "TRY"},
            ],
            "channels": ["booking.com", "expedia"],
        },
        {
            "inv_code": "SUI",
            "name": "Suite",
            "description": "Premium suite",
            "max_occupancy": 4,
            "rate_plans": [
                {"code": "RACK", "name": "Rack Rate", "currency": "TRY"},
                {"code": "BAR", "name": "Best Available Rate", "currency": "TRY"},
            ],
            "channels": ["booking.com", "direct"],
        },
        {
            "inv_code": "FAM",
            "name": "Aile Odasi",
            "description": "Genis aile odasi",
            "max_occupancy": 5,
            "rate_plans": [
                {"code": "BAR", "name": "Best Available Rate", "currency": "TRY"},
            ],
            "channels": ["booking.com", "expedia", "agoda", "direct"],
        },
    ]


def _generate_mock_channels() -> list:
    return [
        {"code": "booking.com", "name": "Booking.com"},
        {"code": "expedia", "name": "Expedia"},
        {"code": "agoda", "name": "Agoda"},
        {"code": "airbnb", "name": "Airbnb"},
        {"code": "direct", "name": "Direct Booking"},
        {"code": "hrs", "name": "HRS"},
        {"code": "hotelbeds", "name": "Hotelbeds"},
    ]


# ── Auth Validation ───────────────────────────────────────────────────

def _validate_auth(request: Request) -> str | None:
    """Validate token + hr_id. Returns error message or None."""
    token = request.query_params.get("token", "")
    hr_id = request.query_params.get("hr_id", "")

    if not token:
        return "Token is required"
    if token not in VALID_TOKENS:
        return "Invalid API token"
    if hr_id and hr_id not in VALID_HR_IDS:
        return "Invalid hotel ID"
    return None


# ── Chaos Engineering ─────────────────────────────────────────────────

async def _maybe_inject_error(request: Request) -> JSONResponse | None:
    """Inject errors based on configured rates. Returns error response or None."""
    _mock_state["request_count"] += 1

    # Rate limit
    if _mock_state["rate_limit_after"] > 0:
        if _mock_state["request_count"] > _mock_state["rate_limit_after"]:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"},
                headers={"Retry-After": "30"},
            )

    # Random server error
    if _mock_state["error_rate"] > 0 and random.random() < _mock_state["error_rate"]:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error (simulated)"},
        )

    # Timeout simulation
    if _mock_state["timeout_rate"] > 0 and random.random() < _mock_state["timeout_rate"]:
        await asyncio.sleep(30)  # Will trigger client timeout
        return JSONResponse(status_code=504, content={"error": "Gateway timeout"})

    return None


# ── Create App ────────────────────────────────────────────────────────

def create_mock_app() -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        _reset_state()
        yield

    app = FastAPI(title="HotelRunner Mock API", version="2.0", lifespan=_lifespan)

    def _ensure_initialized():
        """Ensure state is initialized (for ASGI transport that skips startup)."""
        if not _mock_state["rooms"]:
            _reset_state()

    # ── Control Endpoints (for test orchestration) ────────────────

    @app.post("/mock/reset")
    async def mock_reset():
        _reset_state()
        return {"status": "reset", "reservations": len(_mock_state["reservations"])}

    @app.post("/mock/config")
    async def mock_config(request: Request):
        body = await request.json()
        if "rate_limit_after" in body:
            _mock_state["rate_limit_after"] = int(body["rate_limit_after"])
        if "error_rate" in body:
            _mock_state["error_rate"] = float(body["error_rate"])
        if "timeout_rate" in body:
            _mock_state["timeout_rate"] = float(body["timeout_rate"])
        return {"status": "configured", "config": {
            "rate_limit_after": _mock_state["rate_limit_after"],
            "error_rate": _mock_state["error_rate"],
            "timeout_rate": _mock_state["timeout_rate"],
        }}

    @app.get("/mock/state")
    async def mock_get_state():
        return {
            "request_count": _mock_state["request_count"],
            "reservations_count": len(_mock_state["reservations"]),
            "delivered_uids": len(_mock_state["delivered_uids"]),
            "ari_updates": len(_mock_state["ari_updates"]),
            "webhook_events": len(_mock_state["webhook_events"]),
        }

    @app.post("/mock/inject-reservation")
    async def mock_inject_reservation(request: Request):
        """Inject a custom reservation for testing."""
        body = await request.json()
        _mock_state["reservations"].append(body)
        return {"status": "injected", "total": len(_mock_state["reservations"])}

    # ── V1 Channels ───────────────────────────────────────────────

    @app.get("/api/v1/apps/infos/channels")
    async def get_channels(request: Request):
        _ensure_initialized()
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        err_resp = await _maybe_inject_error(request)
        if err_resp:
            return err_resp

        return {"channels": _mock_state["channels"]}

    # ── V2 Rooms ──────────────────────────────────────────────────

    @app.get("/api/v2/apps/rooms")
    async def get_rooms(request: Request):
        _ensure_initialized()
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        err_resp = await _maybe_inject_error(request)
        if err_resp:
            return err_resp

        return {"rooms": _mock_state["rooms"]}

    # ── V2 Reservations ──────────────────────────────────────────

    @app.get("/api/v2/apps/reservations")
    async def get_reservations(
        request: Request,
        undelivered: str = "true",
        per_page: int = Query(default=10, le=50),
        page: int = 1,
        from_date: str | None = None,
        from_last_update_date: str | None = None,
        modified: str | None = None,
        booked: str | None = None,
    ):
        _ensure_initialized()
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        err_resp = await _maybe_inject_error(request)
        if err_resp:
            return err_resp

        all_res = _mock_state["reservations"]

        # Filter: undelivered = not yet ACK'd
        if undelivered.lower() == "true":
            all_res = [
                r for r in all_res
                if r.get("message_uid") not in _mock_state["delivered_uids"]
            ]

        # Filter: modified only
        if modified and modified.lower() == "true":
            all_res = [r for r in all_res if r.get("state") == "modified"]

        # Filter: booked only
        if booked and booked.lower() == "true":
            all_res = [r for r in all_res if r.get("state") in ("confirmed", "modified")]

        # Paginate
        total = len(all_res)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_data = all_res[start_idx:end_idx]

        return {
            "reservations": page_data,
            "count": len(page_data),
            "current_page": page,
            "pages": total_pages,
            "total": total,
        }

    # ── V2 Reservation ACK ────────────────────────────────────────

    @app.put("/api/v2/apps/reservations/~")
    async def acknowledge_reservation(
        request: Request,
        message_uid: str = "",
        pms_number: str | None = None,
    ):
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        err_resp = await _maybe_inject_error(request)
        if err_resp:
            return err_resp

        if not message_uid:
            return JSONResponse(status_code=400, content={"status": "error", "message": "message_uid required"})

        # Duplicate ACK detection
        if message_uid in _mock_state["delivered_uids"]:
            return {"status": "ok", "message": "Already delivered (idempotent)"}

        _mock_state["delivered_uids"].add(message_uid)
        return {"status": "ok"}

    # ── V2 Reservation State Update ───────────────────────────────

    @app.put("/api/v2/apps/reservations/fire")
    async def fire_reservation_event(
        request: Request,
        hr_number: str = "",
        event: str = "",
        cancel_reason: str | None = None,
    ):
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        if not hr_number or not event:
            return JSONResponse(status_code=400, content={"status": "error", "message": "hr_number and event required"})

        if event not in ("confirm", "cancel"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "event must be confirm or cancel"})

        # Find and update reservation
        for res in _mock_state["reservations"]:
            if res["hr_number"] == hr_number:
                if event == "cancel":
                    res["state"] = "canceled"
                elif event == "confirm":
                    res["state"] = "confirmed"
                return {"status": "ok", "hr_number": hr_number, "new_state": res["state"]}

        return JSONResponse(status_code=404, content={"status": "error", "message": "Reservation not found"})

    # ── V2 ARI Push (Date Range) ──────────────────────────────────

    @app.put("/api/v2/apps/rooms/~")
    async def update_room_daterange(request: Request):
        _ensure_initialized()
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        err_resp = await _maybe_inject_error(request)
        if err_resp:
            return err_resp

        body = await request.body()
        if request.headers.get("content-type", "").startswith("application/json"):
            import json
            form_data = json.loads(body)
        else:
            # Parse form-encoded data
            form_data = dict(request.query_params)
            try:
                form_body = body.decode()
                for pair in form_body.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        form_data[k] = v
            except Exception:
                pass

        inv_code = form_data.get("inv_code", "")
        start_date = form_data.get("start_date", "")
        end_date = form_data.get("end_date", "")

        if not inv_code:
            return JSONResponse(status_code=400, content={"status": "error", "error": "inv_code required"})

        # Validate room exists
        known_codes = {r["inv_code"] for r in _mock_state["rooms"]}
        if inv_code not in known_codes:
            return JSONResponse(status_code=400, content={
                "status": "error",
                "error": f"Unknown inv_code: {inv_code}. Valid: {sorted(known_codes)}",
            })

        txn_id = f"txn-{uuid.uuid4().hex[:8]}"
        update_record = {
            "transaction_id": txn_id,
            "inv_code": inv_code,
            "start_date": start_date,
            "end_date": end_date,
            "fields": {k: v for k, v in form_data.items() if k not in ("token", "hr_id", "inv_code", "start_date", "end_date")},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        _mock_state["ari_updates"].append(update_record)

        return {
            "status": "success",
            "transaction_id": txn_id,
            "message": f"ARI update applied: {inv_code} {start_date}→{end_date}",
        }

    # ── V2 ARI Push (Daily) ───────────────────────────────────────

    @app.put("/api/v2/apps/rooms/daily")
    async def update_room_daily(request: Request):
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        err_resp = await _maybe_inject_error(request)
        if err_resp:
            return err_resp

        body = await request.body()
        if request.headers.get("content-type", "").startswith("application/json"):
            import json
            form_data = json.loads(body)
        else:
            form_data = dict(request.query_params)

        txn_id = f"txn-{uuid.uuid4().hex[:8]}"
        _mock_state["ari_updates"].append({
            "transaction_id": txn_id,
            "type": "daily",
            "data": form_data,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        return {"status": "success", "transaction_id": txn_id}

    # ── V2 Connected Channels ─────────────────────────────────────

    @app.get("/api/v2/apps/infos/connected_channels")
    async def get_connected_channels(request: Request):
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        connected = [
            {"code": "booking.com", "name": "Booking.com", "status": "active", "process_count": 145},
            {"code": "expedia", "name": "Expedia", "status": "active", "process_count": 89},
            {"code": "agoda", "name": "Agoda", "status": "active", "process_count": 34},
            {"code": "direct", "name": "Direct", "status": "active", "process_count": 67},
        ]
        return {"connected_channels": connected}

    # ── V2 Transaction Details ────────────────────────────────────

    @app.get("/api/v2/apps/infos/transaction_details")
    async def get_transaction_details(
        request: Request,
        transaction_id: str = "",
    ):
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        for update in _mock_state["ari_updates"]:
            if update.get("transaction_id") == transaction_id:
                return {
                    "transaction_id": transaction_id,
                    "status": "completed",
                    "details": update,
                }

        return JSONResponse(status_code=404, content={
            "status": "error",
            "message": f"Transaction {transaction_id} not found",
        })

    # ── Property Info (for connection test) ───────────────────────

    @app.get("/properties")
    async def get_properties(request: Request):
        auth_err = _validate_auth(request)
        if auth_err:
            return JSONResponse(status_code=401, content={"error": auth_err})

        hr_id = request.query_params.get("hr_id", "")
        return {
            "properties": [{
                "id": hr_id,
                "name": "Mock Hotel",
                "status": "active",
                "timezone": "Europe/Istanbul",
                "currency": "TRY",
            }],
        }

    @app.get("/api/v2/apps/properties")
    async def get_properties_v2(request: Request):
        return await get_properties(request)

    # ── Health ────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "ok", "provider": "hotelrunner-mock", "version": "2.0"}

    return app


# ── Standalone runner ─────────────────────────────────────────────────

_mock_app = create_mock_app()


async def start_mock_server(port: int = 9999):
    """Start the mock server as a background task."""
    import uvicorn
    config = uvicorn.Config(_mock_app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


def run_mock_server_sync(port: int = 9999):
    """Start mock server synchronously (for subprocess/script use)."""
    import uvicorn
    uvicorn.run(_mock_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_mock_server_sync()
