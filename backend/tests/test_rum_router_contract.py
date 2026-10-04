from routers.rum import ALLOWED_ROUTES, RumBatch, SessionRumEvent, _p95


def test_rum_contract_accepts_only_operational_dimensions():
    event = RumBatch.model_validate({
        "events": [{
            "route": "/app/dashboard",
            "route_duration_ms": 1200,
            "navigation_ms": 180,
            "lcp_ms": 900,
            "inp_ms": 80,
            "cls": 0.02,
            "api_count": 4,
            "api_p95_ms": 130,
        }],
    }).events[0]

    assert event.route in ALLOWED_ROUTES
    assert set(event.model_dump()) == {
        "route", "route_duration_ms", "navigation_ms", "lcp_ms", "inp_ms", "cls", "api_count", "api_p95_ms",
    }


def test_rum_p95_uses_upper_nearest_rank():
    assert _p95([10, 20, 30, 40, 50]) == 50
    assert _p95([]) is None


def test_session_rum_contract_accepts_only_lifecycle_names():
    assert SessionRumEvent.model_validate({"event": "refresh"}).event == "refresh"
