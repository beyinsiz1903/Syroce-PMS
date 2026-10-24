"""A controlled catch-up must not move today's postings to the UTC date."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms import frontdesk_router as api


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["TRY", "USD", "EUR"])
@pytest.mark.parametrize("split", [False, True])
async def test_every_routed_charge_retains_open_day_currency_and_session(monkeypatch, code, split):
    session = object()
    charges = SimpleNamespace(insert_one=AsyncMock())
    folios = SimpleNamespace(update_one=AsyncMock())
    database = SimpleNamespace(folio_charges=charges, folios=folios,
        tenant_settings=SimpleNamespace(find_one=AsyncMock(return_value={"business_date": "2026-10-02"})))
    monkeypatch.setattr(api, "db", database)
    guest = {"id": "guest", "currency": code}
    company = {"id": "company", "currency": code}
    allocations = [{"folio": guest, "amount": 125.5}]
    if split:
        allocations = [{"folio": guest, "amount": 75.5}, {"folio": company, "amount": 50}]
    result = await api._post_charge_allocations("hotel", "booking", "food", "Akşam yemeği",
        125.5, 1, 125.5, guest, allocations, split, "split-id" if split else None,
        "2026-10-24T12:00:00+00:00", "operator", currency=code, session=session)
    assert sum(row["total"] for row in result) == 125.5
    for call in charges.insert_one.await_args_list:
        row = call.args[0]
        assert call.kwargs["session"] is session
        assert row["business_date"] == "2026-10-02"
        assert row["date"].startswith("2026-10-24")
        assert row["currency"] == code
    assert folios.update_one.await_count == len(allocations)
