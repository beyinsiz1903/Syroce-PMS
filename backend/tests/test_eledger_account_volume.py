from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.accounting.eledger_source_package import preflight_eledger_source


class _Cursor:
    def __init__(self, limits: list[int | None]):
        self.limits = limits

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, length=None):
        self.limits.append(length)
        return []


class _Collection:
    def __init__(self):
        self.limits: list[int | None] = []

    def find(self, *_args, **_kwargs):
        return _Cursor(self.limits)

    async def find_one(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_eledger_preflight_reads_the_complete_account_plan():
    accounts = _Collection()
    db = SimpleNamespace(
        gl_journal_entries=_Collection(),
        gl_accounts=accounts,
        gl_periods=_Collection(),
        gl_sequence_reservations=_Collection(),
    )
    settings = {
        "taxpayer_id": "1234567890",
        "legal_name": "Test Hotel",
        "source_application_version": "2026.10",
    }

    await preflight_eledger_source(db, "tenant-1", "2026-10", settings=settings)

    assert accounts.limits == [None]
