from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core import night_audit_hardened as audit
from core.integrations import operational_gl_bridge as bridge
from domains.accounting import gl_router


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


@pytest.mark.parametrize("role,can_value", [("finance", True), ("supervisor", False)])
async def test_pending_valuation_details_require_gl_posting_role(monkeypatch, role, can_value):
    pending = {"id": "pending-run", "business_date": "2026-10-24"}
    cursor = Mock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[pending])
    runs = SimpleNamespace(
        count_documents=AsyncMock(return_value=1),
        find_one=AsyncMock(return_value=None),
        find=Mock(return_value=cursor),
    )
    transactions = SimpleNamespace(count_documents=AsyncMock(return_value=0))
    monkeypatch.setattr(gl_router, "db", SimpleNamespace(night_audit_runs=runs, pos_transactions=transactions))
    monkeypatch.setattr(gl_router, "get_operational_mapping", AsyncMock(return_value={"enabled": True}))

    result = await gl_router.operational_gl_status(SimpleNamespace(role=role, tenant_id="hotel"))

    assert result["can_value_night_audit"] is can_value
    assert result["source_valuation_pending"] == 1
    if can_value:
        assert result["pending_night_audits"] == [pending]
        assert runs.find.call_args.args[0] == {
            "tenant_id": "hotel",
            "status": "completed",
            "dry_run": {"$ne": True},
            "is_dry_run": {"$ne": True},
            "gl_bridge_status": {"$in": ["valuation_required", "failed"]},
        }
    else:
        assert result["pending_night_audits"] == []
        runs.find.assert_not_called()
