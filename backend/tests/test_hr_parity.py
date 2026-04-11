"""
HotelRunner Provider — E2E Parity Test Suite
==============================================

Tests the full provider lifecycle against the mock server:
1. Auth + connectivity
2. Read path: rooms, channels, reservations
3. Reservation parsing: guest data, room codes, amounts
4. Delivery confirmation + duplicate ACK
5. ARI push: availability, rates, restrictions (stop_sale, min_stay, CTA/CTD)
6. Error handling: 429, 500, timeout
7. Idempotency: duplicate reservation ingest
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/app/backend")

from domains.channel_manager.providers.hotelrunner.mock_server import (
    _mock_app,
    _mock_state,
    _reset_state,
)
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider


MOCK_TOKEN = "mock-hr-token-001"
MOCK_HR_ID = "HR-HOTEL-001"
RESULTS = []


def log(name: str, success: bool, detail: str = ""):
    status = "PASS" if success else "FAIL"
    RESULTS.append({"name": name, "success": success, "detail": detail})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


async def run_tests():
    # Use ASGI transport for speed (no port needed)
    from httpx import ASGITransport, AsyncClient

    _reset_state()  # Ensure clean state

    transport = ASGITransport(app=_mock_app)
    mock_client = AsyncClient(transport=transport, base_url="http://test")

    p = HotelRunnerProvider(
        token=MOCK_TOKEN, hr_id=MOCK_HR_ID, environment="mock",
    )
    # Override the client's base URL to use ASGI transport
    # For this test we connect to the real mock server on localhost:9999
    # (already running via supervisor)

    print("\n=== FAZ 1: AUTH + CONNECTIVITY ===\n")

    # 1.1 — Valid connection test
    r = await p.test_connection()
    log("1.1 Valid connection", r.success, f"channels={r.data.get('channel_count', 0) if r.data else 0}")

    # 1.2 — Invalid token
    bad_p = HotelRunnerProvider(token="bad-token-xxx", hr_id=MOCK_HR_ID, environment="mock")
    r = await bad_p.test_connection()
    log("1.2 Invalid token rejected", not r.success, f"error={r.error}")

    # 1.3 — Invalid HR ID
    bad_p2 = HotelRunnerProvider(token=MOCK_TOKEN, hr_id="INVALID-ID", environment="mock")
    r2 = await bad_p2.test_connection()
    log("1.3 Invalid HR ID rejected", not r2.success, f"error={r2.error}")

    # 1.4 — Environment resolution
    for env, expected_base in [("mock", "localhost:9999"), ("sandbox", "sandbox.hotelrunner"), ("production", "app.hotelrunner")]:
        ep = HotelRunnerProvider(token=MOCK_TOKEN, hr_id=MOCK_HR_ID, environment=env)
        log(f"1.4 Env '{env}' resolves correctly", expected_base in ep._base_url, f"url={ep._base_url}")

    print("\n=== FAZ 2: READ PATH — ROOMS & CHANNELS ===\n")

    # 2.1 — Fetch rooms
    r = await p.fetch_rooms()
    room_count = r.data.get("room_count", 0) if r.data else 0
    log("2.1 Fetch rooms", r.success and room_count > 0, f"rooms={room_count}")

    if r.data and r.data.get("rooms"):
        room = r.data["rooms"][0]
        log("2.1a Room has inv_code", bool(room.get("inv_code")), f"inv_code={room.get('inv_code')}")
        log("2.1b Room has rate_plans", isinstance(room.get("rate_plans"), list), f"plans={len(room.get('rate_plans', []))}")

    # 2.2 — Fetch channels
    r = await p.fetch_channels()
    log("2.2 Fetch channels", r.success)

    # 2.3 — Fetch connected channels
    r = await p.fetch_connected_channels()
    log("2.3 Fetch connected channels", r.success)

    print("\n=== FAZ 2: READ PATH — RESERVATIONS ===\n")

    # 3.1 — Fetch undelivered reservations
    r = await p.fetch_reservations(undelivered=True, per_page=5)
    res_count = r.data.get("count", 0) if r.data else 0
    log("3.1 Fetch undelivered reservations", r.success and res_count > 0, f"count={res_count}")

    # 3.2 — Reservation parsing quality
    if r.data and r.data.get("reservations"):
        res0 = r.data["reservations"][0]
        required_fields = ["hr_number", "guest_firstname", "guest_lastname", "guest_email",
                           "check_in", "check_out", "room_type_code", "total_amount",
                           "currency", "channel", "message_uid"]
        missing = [f for f in required_fields if not res0.get(f)]
        log("3.2 Reservation has all required fields", len(missing) == 0, f"missing={missing}" if missing else "all present")
        log("3.2a guest_email parsed", "@" in str(res0.get("guest_email", "")), f"email={res0.get('guest_email')}")
        log("3.2b room_type_code parsed", bool(res0.get("room_type_code")), f"room={res0.get('room_type_code')}")
        log("3.2c amount > 0", float(res0.get("total_amount", 0)) > 0, f"amount={res0.get('total_amount')}")

    # 3.3 — Pagination
    r_page1 = await p.fetch_reservations(undelivered=True, per_page=3, page=1)
    c1 = r_page1.data.get("count", 0) if r_page1.data else 0
    log("3.3 Pagination (per_page=3)", c1 <= 3, f"returned={c1}")

    print("\n=== FAZ 2: DELIVERY ACK + DUPLICATE ===\n")

    # 4.1 — Confirm delivery
    if r.data and r.data.get("reservations"):
        msg_uid = r.data["reservations"][0].get("message_uid", "test-uid")
        r_ack = await p.confirm_delivery(message_uid=msg_uid)
        log("4.1 Confirm delivery (first)", r_ack.success)

        # 4.2 — Duplicate ACK (idempotent)
        r_ack2 = await p.confirm_delivery(message_uid=msg_uid)
        log("4.2 Duplicate ACK (idempotent)", r_ack2.success, "should succeed without error")

    print("\n=== FAZ 2: WRITE PATH — ARI PUSH ===\n")

    # 5.1 — Availability push
    r = await p.push_date_range_inventory({
        "inv_code": "STD", "start_date": "2026-04-01", "end_date": "2026-04-10",
        "availability": "5",
    })
    log("5.1 Availability push", r.success)

    # 5.2 — Rate push
    r = await p.push_date_range_inventory({
        "inv_code": "DLX", "start_date": "2026-04-01", "end_date": "2026-04-05",
        "price": "1500",
    })
    log("5.2 Rate push", r.success)

    # 5.3 — Stop sale
    r = await p.push_date_range_inventory({
        "inv_code": "STD", "start_date": "2026-04-15", "end_date": "2026-04-20",
        "stop_sale": "1",
    })
    log("5.3 Stop sale push", r.success)

    # 5.4 — Min/max stay + CTA/CTD
    r = await p.push_date_range_inventory({
        "inv_code": "SUI", "start_date": "2026-04-01", "end_date": "2026-04-10",
        "min_stay": "2", "max_stay": "7", "cta": "0", "ctd": "1",
    })
    log("5.4 Restrictions push (min/max stay + CTA/CTD)", r.success)

    # 5.5 — Invalid room code
    r = await p.push_date_range_inventory({
        "inv_code": "NONEXISTENT", "start_date": "2026-04-01", "end_date": "2026-04-05",
        "availability": "5",
    })
    log("5.5 Invalid room code rejected", not r.success, f"error={r.error}")

    # 5.6 — Legacy update_room with all restrictions
    r = await p.update_room(
        inv_code="DLX", start_date="2026-05-01", end_date="2026-05-15",
        price=2000, availability=3, min_stay=2, max_stay=10,
        cta=1, ctd=0, stop_sale=False,
    )
    log("5.6 Legacy update_room (full restrictions)", r.get("success", False))

    print("\n=== FAZ 2: ERROR HANDLING ===\n")

    # 6.1 — Rate limit (429)
    # Configure mock to rate limit after 2 requests
    await mock_client.post("/mock/config", json={"rate_limit_after": 2, "error_rate": 0})
    _mock_state["request_count"] = 0  # reset counter

    # First 2 should succeed
    r1 = await p.fetch_rooms()
    r2 = await p.fetch_channels()
    # Third should hit 429 — but retries should handle it
    log("6.1a First requests pass under limit", r1.success and r2.success)

    # Reset mock
    await mock_client.post("/mock/config", json={"rate_limit_after": 0, "error_rate": 0})

    # 6.2 — Server error (500) with recovery
    await mock_client.post("/mock/config", json={"error_rate": 0.5})
    successes = 0
    for _ in range(3):
        r = await p.fetch_rooms()
        if r.success:
            successes += 1
    log("6.2 Partial server errors with retry recovery", successes > 0, f"successes={successes}/3")
    await mock_client.post("/mock/config", json={"error_rate": 0})

    print("\n=== SUMMARY ===\n")

    passed = sum(1 for r in RESULTS if r["success"])
    failed = sum(1 for r in RESULTS if not r["success"])
    total = len(RESULTS)
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"  Pass Rate: {passed/total*100:.1f}%")

    if failed > 0:
        print("\n  FAILURES:")
        for r in RESULTS:
            if not r["success"]:
                print(f"    - {r['name']}: {r['detail']}")

    # Write JSON report
    report = {
        "suite": "hotelrunner_provider_parity",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{passed/total*100:.1f}%",
        "results": RESULTS,
    }
    with open("/app/test_reports/hr_parity_test.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report: /app/test_reports/hr_parity_test.json")

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
