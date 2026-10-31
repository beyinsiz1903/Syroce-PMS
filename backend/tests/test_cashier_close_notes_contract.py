"""A closing difference explanation must survive into history and Z reports."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import cashier_router as cashier
from domains.pms import cashier_service

USER = SimpleNamespace(id="qa-actor", tenant_id="qa", email="qa@example.invalid", name="Synthetic QA")


def wired(monkeypatch):
    row = {"_id": "shift", "tenant_id": "qa", "status": "open", "opening_amount": 0, "cash_in": 100, "cash_out": 0,
           "transactions": [{"amount": 100, "method": "cash", "direction": "in"}]}
    shifts = SimpleNamespace(find_one=AsyncMock(return_value=row), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    monkeypatch.setattr(cashier, "db", SimpleNamespace(cashier_shifts=shifts))
    monkeypatch.setattr(cashier_service, "reconcile_open_shift_payments", AsyncMock())
    monkeypatch.setattr(cashier, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-26"}))
    return row, shifts


@pytest.mark.asyncio
async def test_close_retains_exact_explanation_actor_and_z_report(monkeypatch):
    row, shifts = wired(monkeypatch)
    result = await cashier.close_shift({"counted_amount": 50, "notes": "  QA sayım farkı; gerçek tahsilat yok  "}, current_user=USER)
    change = shifts.update_one.await_args.args[1]["$set"]
    assert change["closing_notes"] == result["closing_notes"] == "QA sayım farkı; gerçek tahsilat yok"
    assert change["closed_by_id"] == USER.id and result["difference"] == -50
    report = cashier._build_shift_report({**row, **change})
    assert report["closing_notes"] == change["closing_notes"] and report["closed_by_id"] == USER.id


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"counted_amount": 50}, {"counted_amount": 150, "notes": " "}, {"counted_amount": 0, "notes": None}, {"counted_amount": 100, "notes": {}}, {"counted_amount": 100, "notes": "x" * 2001}])
async def test_close_rejects_missing_difference_reason_or_invalid_note_without_mutation(monkeypatch, body):
    _, shifts = wired(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await cashier.close_shift(body, current_user=USER)
    assert exc.value.status_code == 400
    shifts.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_small_difference_without_note_remains_allowed_at_existing_ui_boundary(monkeypatch):
    _, shifts = wired(monkeypatch)
    result = await cashier.close_shift({"counted_amount": 50.01}, current_user=USER)
    assert result["difference"] == -49.99
    assert shifts.update_one.await_args.args[1]["$set"]["closing_notes"] == ""
