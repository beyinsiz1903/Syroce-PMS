from datetime import date

import pytest

from routers import housekeeping


@pytest.mark.asyncio
async def test_housekeeping_operational_date_uses_authoritative_pms_date(monkeypatch):
    calls = []

    async def fake_ensure(database, tenant_id):
        calls.append((database, tenant_id))
        return {"business_date": "2026-08-23"}

    monkeypatch.setattr(housekeeping, "ensure_business_date_initialized", fake_ensure)

    result = await housekeeping._operational_date("the-canyon")

    assert result == date(2026, 8, 23)
    assert calls == [(housekeeping.db, "the-canyon")]
