from types import SimpleNamespace

import pytest

from core import utils


class _AggregateCursor:
    async def to_list(self, _limit):
        return []


class _Collection:
    def __init__(self):
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return _AggregateCursor()


@pytest.mark.asyncio
async def test_folio_balance_includes_legacy_rows_unless_explicitly_voided(monkeypatch):
    charges = _Collection()
    payments = _Collection()
    monkeypatch.setattr(utils, "db", SimpleNamespace(folio_charges=charges, payments=payments))

    await utils.calculate_folio_balance("folio-1", "tenant-1")

    assert charges.pipelines[0][0]["$match"]["voided"] == {"$ne": True}
    assert payments.pipelines[0][0]["$match"]["voided"] == {"$ne": True}
