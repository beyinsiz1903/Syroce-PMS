from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from modules.observability.distributed_tracing import TracingService
from modules.observability.request_tracing_middleware import RequestTracingMiddleware


def _trace(path: str, duration_ms: float, *, status: int = 200, completed_at: datetime | None = None) -> dict:
    completed = completed_at or datetime.now(UTC)
    return {
        "trace_id": f"{path}-{duration_ms}-{completed.timestamp()}",
        "request_path": path,
        "method": "GET",
        "status_code": status,
        "duration_ms": duration_ms,
        "is_slow": duration_ms > 1000,
        "started_at_iso": completed.isoformat(),
        "completed_at": completed.isoformat(),
    }


def test_trace_window_excludes_expired_entries():
    service = TracingService()
    service._recent_traces.extend(
        [
            _trace("/api/current", 50),
            _trace("/api/expired", 80, completed_at=datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    recent = service._traces_in_window(1)

    assert [trace["request_path"] for trace in recent] == ["/api/current"]


@pytest.mark.asyncio
async def test_summary_reports_p95_max_errors_and_real_window_counts():
    service = TracingService()
    traces = [_trace("/api/bookings", value) for value in [20, 30, 40, 50, 1200]]
    traces.append(_trace("/api/bookings", 60, status=500))
    service._load_traces_in_window = AsyncMock(return_value=traces)

    summary = await service.get_trace_summary(hours=1)

    endpoint = summary["endpoints"][0]
    assert summary["window_hours"] == 1
    assert summary["window_scope"] == "multi_worker_rolling"
    assert summary["total_requests"] == 6
    assert summary["total_errors"] == 1
    assert summary["total_slow"] == 1
    assert endpoint["p95_ms"] == 1200
    assert endpoint["max_ms"] == 1200
    assert endpoint["errors"] == 1


@pytest.mark.asyncio
async def test_slow_endpoint_detects_single_tail_spike_even_when_average_is_fast():
    service = TracingService()
    traces = [_trace("/api/folio", value) for value in [50, 60, 70, 1200]]
    service._load_traces_in_window = AsyncMock(return_value=traces)

    slow = await service.get_slow_endpoints(threshold_ms=1000)

    assert len(slow) == 1
    assert slow[0]["path"] == "/api/folio"
    assert slow[0]["avg_ms"] < 1000
    assert slow[0]["max_ms"] == 1200
    assert slow[0]["slow_count"] == 1


@pytest.mark.asyncio
async def test_middleware_normalizes_dynamic_ids_before_trace_storage(monkeypatch):
    service = TracingService()
    monkeypatch.setattr("modules.observability.distributed_tracing.tracing", service)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    messages = []

    async def send(message):
        messages.append(message)

    middleware = RequestTracingMiddleware(app)
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/staff/da49b206-4825-40bc-a559-c2a80fdf9b8f",
            "headers": [],
        },
        receive,
        send,
    )

    assert service._recent_traces[-1]["request_path"] == "/api/staff/{id}"
    response_headers = dict(messages[0]["headers"])
    assert b"x-correlation-id" in response_headers
    assert b"x-request-id" in response_headers
