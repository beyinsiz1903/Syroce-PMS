"""POS operational reversals must keep source receipt and GL together."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.accounting import gl_router as gl


@pytest.mark.parametrize("source", ["pos_direct", "pos_refund"])
def test_pos_source_reversal_requires_original_receipt(source):
    assert gl._journal_reversal_blocker({"source": source}, False)


@pytest.mark.parametrize("source", ["pos_direct", "pos_refund"])
async def test_direct_reversal_rejects_pos_before_any_posting(monkeypatch, source):
    journal = {"id": "j", "tenant_id": "A", "status": "posted", "source": source,
        "date": "2026-11-12", "lines": [{"account_code": "100", "debit": 33}]}
    database = SimpleNamespace(gl_journal_entries=SimpleNamespace(find_one=AsyncMock(side_effect=[journal, None])),
        billing_instruments=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    monkeypatch.setattr(gl, "db", database)
    post = AsyncMock()
    monkeypatch.setattr(gl, "post_journal_entry", post)
    with pytest.raises(HTTPException) as exc:
        await gl._reverse_journal("j", gl.JournalReversalIn(date="2026-11-12", reason="Sentetik kaynak testi", idempotency_key="pos-source-test"),
            SimpleNamespace(tenant_id="A"))
    assert exc.value.status_code == 409 and "POS" in exc.value.detail
    post.assert_not_awaited()


def test_unallocated_manual_journal_stays_reversible():
    assert gl._journal_reversal_blocker({"source": "manual_voucher"}, False) is None
