from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import utils


class _AggregateCursor:
    async def to_list(self, _limit):
        return []

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _Collection:
    def __init__(self):
        self.pipelines = []
        self.queries = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return _AggregateCursor()

    def find(self, query, *args):
        self.queries.append(query)
        return _AggregateCursor()


@pytest.mark.asyncio
async def test_folio_balance_includes_legacy_rows_unless_explicitly_voided(monkeypatch):
    charges = _Collection()
    payments = _Collection()
    monkeypatch.setattr(utils, "db", SimpleNamespace(folio_charges=charges, payments=payments,
        folios=SimpleNamespace(find_one=AsyncMock(return_value={"id": "folio-1", "currency": "TRY"}))))

    await utils.calculate_folio_balance("folio-1", "tenant-1")

    assert charges.queries[0] == {"folio_id": {"$in": ["folio-1"]}, "tenant_id": "tenant-1", "voided": {"$ne": True}}
    assert payments.queries[0] == {"folio_id": {"$in": ["folio-1"]}, "tenant_id": "tenant-1"}
