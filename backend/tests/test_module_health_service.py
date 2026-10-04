from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from modules.pms_core import module_health_service as health_module


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit):
        return self.rows


class _Collection:
    def __init__(self, *, row=None, rows=None, count=0):
        self.row = row
        self.rows = rows or []
        self.count = count
        self.find_one_calls = []

    async def find_one(self, query, *args, **kwargs):
        self.find_one_calls.append((query, args, kwargs))
        return self.row

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)

    async def count_documents(self, *_args, **_kwargs):
        return self.count


@pytest.mark.asyncio
async def test_module_health_reports_license_setup_usage_and_errors_without_secrets(monkeypatch):
    last_sync = datetime.now(UTC).isoformat()
    fake_db = SimpleNamespace(
        tenants=_Collection(row={
            "modules": {"messaging_whatsapp": True, "channel_exely": True},
            "subscription_status": "active",
            "subscription_plan": "professional",
        }),
        tenant_subscriptions=_Collection(rows=[{"product_key": "e_invoice", "status": "active", "end_date": None}]),
        module_health_events=_Collection(rows=[
            {"module_key": "whatsapp", "status": "error", "message": "Webhook doğrulanamadı", "created_at": "2026-10-03T09:00:00+00:00"},
            {"module_key": "frontdesk", "status": "used", "occurred_at": "2026-10-03T08:30:00+00:00", "created_at": "2026-10-03T08:30:00+00:00"},
        ]),
        bookings=_Collection(),
        housekeeping_tasks=_Collection(),
        maintenance_requests=_Collection(),
        folio_transactions=_Collection(),
        report_exports=_Collection(),
        guests=_Collection(),
        rate_change_audit=_Collection(),
        channel_manager_syncs=_Collection(row={"sync_timestamp": "2026-10-03T08:00:00+00:00"}),
        messaging_logs=_Collection(),
        invoice_sync_logs=_Collection(row={"created_at": "2026-10-03T07:00:00+00:00"}),
        channel_integrations=_Collection(row={"status": "active"}),
        messaging_provider_configs=_Collection(),
        invoice_integrations=_Collection(row={"status": "active"}),
        hotelrunner_connections=_Collection(row={
            "is_active": True,
            "auto_sync_reservations": True,
            "last_sync_at": last_sync,
            "environment": "production",
        }),
        exely_connections=_Collection(),
        provider_connections=_Collection(),
        hotelrunner_room_mappings=_Collection(count=1),
        exely_room_mappings=_Collection(),
    )
    monkeypatch.setattr(health_module, "db", fake_db)

    snapshot = await health_module.ModuleHealthService().get_snapshot("tenant-a")
    by_key = {row["key"]: row for row in snapshot["modules"]}

    assert snapshot["subscription"] == {"status": "active", "plan": "professional"}
    assert by_key["frontdesk"]["status"] == "healthy"
    assert by_key["frontdesk"]["last_used_at"] == "2026-10-03T08:30:00+00:00"
    assert by_key["channel_manager"]["status"] == "healthy"
    assert by_key["channel_manager"]["integration_status"] == "configured"
    assert by_key["channel_manager"]["operational_status"] == "production"
    assert by_key["channel_manager"]["providers"][0]["operational_status"]["production_ready"] is True
    assert by_key["whatsapp"]["status"] == "error"
    assert by_key["whatsapp"]["integration_status"] == "not_configured"
    assert by_key["whatsapp"]["last_error"] == "Webhook doğrulanamadı"
    assert by_key["e_invoice"]["license_status"] == "licensed"
    assert by_key["e_invoice"]["integration_status"] == "configured"
    assert "api_key" not in str(snapshot).lower()


@pytest.mark.asyncio
async def test_module_health_marks_expired_and_unconfigured_modules_for_attention(monkeypatch):
    empty = _Collection()
    fake_db = SimpleNamespace(
        tenants=_Collection(row={"modules": {}, "subscription_status": "active", "plan": "basic"}),
        tenant_subscriptions=_Collection(rows=[{"product_key": "messaging_whatsapp", "status": "expired", "end_date": "2026-01-01T00:00:00+00:00"}]),
        module_health_events=_Collection(),
        bookings=empty,
        housekeeping_tasks=empty,
        maintenance_requests=empty,
        folio_transactions=empty,
        report_exports=empty,
        guests=empty,
        rate_change_audit=empty,
        channel_manager_syncs=empty,
        messaging_logs=empty,
        invoice_sync_logs=empty,
        channel_integrations=empty,
        messaging_provider_configs=empty,
        invoice_integrations=empty,
    )
    monkeypatch.setattr(health_module, "db", fake_db)

    snapshot = await health_module.ModuleHealthService().get_snapshot("tenant-a")
    by_key = {row["key"]: row for row in snapshot["modules"]}

    assert by_key["whatsapp"]["license_status"] == "expired"
    assert by_key["whatsapp"]["status"] == "attention"
    assert by_key["channel_manager"]["status"] == "attention"
    assert by_key["frontdesk"]["status"] == "unknown"
    assert snapshot["summary"]["total"] == 10
