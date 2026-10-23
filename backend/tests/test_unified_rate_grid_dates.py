from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.channel_manager import unified_rate_manager_router as router


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["exely", "hotelrunner", "agency", None])
@pytest.mark.parametrize(("start", "end"), [
    ("invalid", "2026-11-10"),
    ("2026-11-10", "2026-02-30"),
    ("2026-1-1", "2026-11-10"),
    ("2026-11-11", "2026-11-10"),
    ("2026-01-01", "2027-01-02"),
    ("9999-12-31", "9999-12-31"),
])
async def test_invalid_grid_range_rejected_before_provider_or_db(monkeypatch, provider, start, end):
    detect = AsyncMock(side_effect=AssertionError("Provider access forbidden"))
    build = AsyncMock(side_effect=AssertionError("Database access forbidden"))
    monkeypatch.setattr(router, "_detect_active_provider", detect)
    monkeypatch.setattr(router, "_build_agency_grid", build)
    with pytest.raises(HTTPException) as exc:
        await router.get_unified_grid(start, end, provider, SimpleNamespace(tenant_id="synthetic-test"))
    assert exc.value.status_code == 422
    detect.assert_not_awaited()
    build.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "end"), [
    ("2026-11-10", "2026-11-10"),
    ("2026-12-31", "2027-01-01"),
    ("2028-01-01", "2028-12-31"),
])
async def test_valid_grid_dates_preserve_inclusive_bounds(monkeypatch, start, end):
    build = AsyncMock(return_value={"grid": []})
    monkeypatch.setattr(router, "_build_agency_grid", build)
    assert await router.get_unified_grid(start, end, "agency", SimpleNamespace(tenant_id="synthetic-test")) == {"grid": []}
    build.assert_awaited_once_with("synthetic-test", start, end)
