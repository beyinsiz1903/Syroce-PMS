from __future__ import annotations

import os

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from core.folio_ledger_service import FolioLedgerService


class _Cursor:
    def __init__(self):
        self.limit: int | None = -1

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, length=None):
        self.limit = length
        return [{"id": "entry-1", "amount": 20}]


@pytest.mark.asyncio
async def test_folio_ledger_reads_all_entries_for_balance_detail(monkeypatch):
    service = FolioLedgerService()
    cursor = _Cursor()
    monkeypatch.setattr(service, "_require_folio", _existing_folio)
    monkeypatch.setattr(service, "compute_balance", _balance)
    monkeypatch.setattr(service.coll, "find", lambda *_args, **_kwargs: cursor)

    ledger = await service.get_ledger("tenant-1", "folio-1")

    assert ledger["entry_count"] == 1
    assert cursor.limit is None


async def _existing_folio(*_args, **_kwargs):
    return {"id": "folio-1"}


async def _balance(*_args, **_kwargs):
    return 20.0
