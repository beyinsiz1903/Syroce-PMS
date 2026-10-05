from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_claim_rehydrates_the_target_occupant_not_the_primary_guest(monkeypatch):
    from routers import kbs

    claimed_job = {
        "id": "job-secondary",
        "booking_id": "booking-206",
        "guest_id": "guest-secondary",
        "action": "checkin",
        "status": "in_progress",
        "attempts": 1,
        "max_attempts": 5,
    }
    reports = SimpleNamespace(
        find_one=AsyncMock(
            side_effect=[
                {
                    "booking_id": "booking-206",
                    "guest_id": "guest-secondary",
                    "action": "checkin",
                },
                claimed_job,
            ]
        ),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
    )
    monkeypatch.setattr(kbs, "db", SimpleNamespace(kbs_reports=reports))
    snapshot_builder = AsyncMock(
        return_value=(
            {"id": "booking-206"},
            {"id": "guest-secondary"},
            {
                "guest_name": "Secondary Guest",
                "nationality": "TR",
                "id_number": "12345678901",
                "room_number": "206",
                "check_in": "2026-09-25",
            },
        )
    )
    monkeypatch.setattr(kbs, "_build_payload_snapshot", snapshot_builder)

    result = await kbs.kbs_queue_claim(
        "job-secondary",
        kbs.KBSQueueClaim(worker_id="extension-worker", lease_seconds=300),
        current_user=SimpleNamespace(tenant_id="tenant-canyon"),
        _perm=True,
    )

    snapshot_builder.assert_awaited_once_with(
        "tenant-canyon", "booking-206", "guest-secondary"
    )
    assert result["job"]["guest_id"] == "guest-secondary"

