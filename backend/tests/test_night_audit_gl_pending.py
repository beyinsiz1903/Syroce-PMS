from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core import night_audit_hardened as audit
from core.integrations import operational_gl_bridge as bridge


@pytest.mark.parametrize("error,status", [(bridge.SourceValuationRequired("explicit valuation needed"), "valuation_required"),
    (RuntimeError("database unavailable"), "failed"), (bridge.OperationalGLBridgeError("corrupt unknown source"), "failed")])
async def test_pending_workflow_does_not_masquerade_as_crash_but_unexpected_errors_still_do(monkeypatch, error, status):
    update = AsyncMock()
    logger = Mock()
    monkeypatch.setattr(audit, "db", SimpleNamespace(night_audit_runs=SimpleNamespace(update_one=update)))
    monkeypatch.setattr(audit, "logger", logger)
    monkeypatch.setattr(bridge, "post_night_audit_daily_to_gl", AsyncMock(side_effect=error))
    await audit._post_close_accounting("hotel", "2026-10-24", "run")
    assert update.call_args.args[0] == {"tenant_id": "hotel", "id": "run"}
    assert update.call_args.args[1]["$set"]["gl_bridge_status"] == status
    assert update.call_args.args[1]["$set"]["gl_bridge_error"] == str(error)
    assert logger.exception.call_count == (status == "failed")
    assert logger.warning.call_count == (status == "valuation_required")


async def test_completed_source_bridge_does_not_fabricate_a_pending_status(monkeypatch):
    update = AsyncMock()
    monkeypatch.setattr(audit, "db", SimpleNamespace(night_audit_runs=SimpleNamespace(update_one=update)))
    monkeypatch.setattr(bridge, "post_night_audit_daily_to_gl", AsyncMock(return_value={"status": "posted"}))
    await audit._post_close_accounting("hotel", "2026-10-24", "run")
    update.assert_not_awaited()
