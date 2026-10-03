"""Inventory-integrity regression checks for mobile spare-part usage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import maintenance


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [0, -1])
async def test_spare_part_usage_rejects_non_positive_quantities(monkeypatch, quantity):
    monkeypatch.setattr(
        maintenance,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-1", username="tech")),
    )
    monkeypatch.setattr(maintenance, "db", SimpleNamespace())

    with pytest.raises(HTTPException) as error:
        await maintenance.use_spare_part_mobile("task-1", "part-1", quantity, credentials=None)

    assert error.value.status_code == 422
