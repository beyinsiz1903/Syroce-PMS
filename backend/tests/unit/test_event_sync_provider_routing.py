import pytest

from channel_manager.application.event_sync_service import EventSyncService
from channel_manager.domain.models.connector_account import ConnectorAccount, ConnectorProvider


class _Repository:
    async def get_active_connectors(self, tenant_id, property_id):
        return [
            {
                "id": "conn-ex-001",
                "provider": "exely",
                "status": "active",
            }
        ]


def test_connector_account_accepts_exely_documents():
    connector = ConnectorAccount.from_doc(
        {
            "id": "conn-ex-001",
            "tenant_id": "tenant-1",
            "property_id": "property-1",
            "provider": "exely",
            "status": "active",
        }
    )

    assert connector.provider is ConnectorProvider.EXELY


@pytest.mark.asyncio
async def test_event_sync_skips_exely_for_its_provider_specific_pipeline():
    result = await EventSyncService(_Repository()).handle_event(
        "tenant-1",
        "booking_created",
        {
            "property_id": "property-1",
            "check_in": "2026-09-20",
            "check_out": "2026-09-21",
        },
    )

    assert result["handled"] is True
    assert result["sync_jobs_created"] == 0
    assert result["jobs"] == [
        {
            "connector_id": "conn-ex-001",
            "status": "skipped",
            "reason": "provider_specific_pipeline",
        }
    ]
