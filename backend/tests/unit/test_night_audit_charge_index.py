from unittest.mock import AsyncMock

import pytest

from core import night_audit_hardened


class _Collection:
    def __init__(self, indexes=None):
        self._indexes = indexes or {}
        self.create_index = AsyncMock()
        self.drop_index = AsyncMock()

    async def index_information(self):
        return self._indexes


class _Database:
    def __init__(self):
        self.collections = {}
        self.folio_charges = _Collection(
            {
                "idx_folio_charges_na_dedup": {
                    "partialFilterExpression": {
                        "business_date": {"$exists": True},
                        "charge_type": {"$exists": True},
                    }
                }
            }
        )
        self.collections["folio_charges"] = self.folio_charges

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


@pytest.mark.asyncio
async def test_night_audit_charge_dedup_index_only_covers_active_charges(monkeypatch):
    database = _Database()
    monkeypatch.setattr(night_audit_hardened, "db", database)

    await night_audit_hardened.ensure_night_audit_indexes()

    database.folio_charges.drop_index.assert_awaited_once_with("idx_folio_charges_na_dedup")
    matching_calls = [
        call for call in database.folio_charges.create_index.await_args_list
        if call.kwargs.get("name") == "idx_folio_charges_na_dedup"
    ]
    assert len(matching_calls) == 1
    assert matching_calls[0].kwargs["unique"] is True
    assert matching_calls[0].kwargs["partialFilterExpression"] == {
        "business_date": {"$exists": True},
        "charge_type": {"$exists": True},
        "voided": False,
    }
