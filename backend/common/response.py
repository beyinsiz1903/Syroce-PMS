"""
Common — Normalized API Response Helpers
Standardised response envelope for all domain endpoints.
"""
from datetime import UTC, datetime
from typing import Any


def api_response(
    data: Any = None,
    *,
    status: str = "ok",
    message: str | None = None,
    severity: str = "info",
    correlation_id: str | None = None,
    action_available: str | None = None,
    suggested_action: str | None = None,
):
    """Build a normalized API response dict."""
    resp = {
        "status": status,
        "severity": severity,
        "last_updated_at": datetime.now(UTC).isoformat(),
    }
    if data is not None:
        resp["data"] = data
    if message:
        resp["message"] = message
    if correlation_id:
        resp["correlation_id"] = correlation_id
    if action_available:
        resp["action_available"] = action_available
    if suggested_action:
        resp["suggested_action"] = suggested_action
    return resp


def from_service_result(result, *, correlation_id: str | None = None):
    """Convert a ServiceResult to a normalized API response."""
    if result.ok:
        return api_response(
            data=result.data,
            status="ok",
            severity="info",
            correlation_id=correlation_id,
        )
    return api_response(
        status="error",
        message=result.error,
        severity="warning",
        correlation_id=correlation_id,
    )
