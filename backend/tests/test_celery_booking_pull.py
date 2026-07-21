import pytest
from unittest.mock import AsyncMock, patch
import celery_tasks
from core.tenant_db import TenantViolationError

@pytest.mark.asyncio
async def test_booking_pull_async_trusted_tenant_success():
    """Celery task uses the task arg as trusted tenant for atomic guard."""
    task_tenant_id = "tenant-A"

    fake_reservation = {"id": "res-1", "guest": {}, "room_type": "RT"}
    fake_payload = {"id": "booking-1", "tenant_id": task_tenant_id}

    with patch("celery_tasks.get_db") as mock_get_db, \
         patch("celery_tasks.BookingCredentialManager.get_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("celery_tasks.BookingAPIClient") as MockClient, \
         patch("celery_tasks.ensure_guest_record", new_callable=AsyncMock) as mock_guest, \
         patch("celery_tasks.find_room_for_reservation", new_callable=AsyncMock) as mock_room, \
         patch("celery_tasks.BookingReservationMapper") as MockMapper, \
         patch("core.atomic_booking.create_booking_atomic", new_callable=AsyncMock) as mock_atomic:

        # Setup mocks
        mock_get_db.return_value = (AsyncMock(), AsyncMock())
        mock_creds.return_value = {"key": "val"}
        mock_api = MockClient.return_value
        mock_api.fetch_reservations = AsyncMock(return_value={"reservations": [fake_reservation]})
        
        mock_mapper = MockMapper.return_value
        mock_mapper.to_ota_record.return_value = {"channel_booking_id": "cb1", "room_type": "RT"}
        mock_mapper.to_booking_payload.return_value = fake_payload
        
        mock_guest.return_value = "guest-1"
        mock_room.return_value = "room-1"

        await celery_tasks._booking_pull_async(task_tenant_id)

        mock_atomic.assert_awaited_once_with(
            tenant_id=task_tenant_id,
            booking_doc=fake_payload,
        )

@pytest.mark.asyncio
async def test_booking_pull_async_tenant_mismatch_fails():
    """If payload tenant doesn't match task tenant, the guard rejects and task fails."""
    task_tenant_id = "tenant-A"
    spoofed_payload = {"id": "booking-1", "tenant_id": "tenant-B"}

    fake_reservation = {"id": "res-1"}

    with patch("celery_tasks.get_db") as mock_get_db, \
         patch("celery_tasks.BookingCredentialManager.get_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("celery_tasks.BookingAPIClient") as MockClient, \
         patch("celery_tasks.ensure_guest_record", new_callable=AsyncMock) as mock_guest, \
         patch("celery_tasks.find_room_for_reservation", new_callable=AsyncMock) as mock_room, \
         patch("celery_tasks.BookingReservationMapper") as MockMapper, \
         patch("core.atomic_booking.create_booking_atomic", new_callable=AsyncMock) as mock_atomic:

        mock_get_db.return_value = (AsyncMock(), AsyncMock())
        mock_creds.return_value = {"key": "val"}
        mock_api = MockClient.return_value
        mock_api.fetch_reservations = AsyncMock(return_value={"reservations": [fake_reservation]})
        
        mock_mapper = MockMapper.return_value
        mock_mapper.to_ota_record.return_value = {"channel_booking_id": "cb1"}
        mock_mapper.to_booking_payload.return_value = spoofed_payload
        
        mock_guest.return_value = "guest-1"
        mock_room.return_value = "room-1"
        
        # Atomic guard throws TenantViolationError when payload != tenant_id
        mock_atomic.side_effect = TenantViolationError("Booking tenant does not match operation tenant")

        out = await celery_tasks._booking_pull_async(task_tenant_id)
        assert out['success'] is False
        assert 'Booking tenant does not match operation tenant' in out['error']
