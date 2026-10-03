import pytest

from routers import integrations_overview


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, _selector, _projection):
        return _Cursor(self.rows)


class _Database:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, name):
        return _Collection(self.collections.get(name, []))


@pytest.mark.asyncio
async def test_whatsapp_summary_keeps_trial_and_production_evidence_separate(monkeypatch):
    monkeypatch.setattr(
        integrations_overview,
        "db",
        _Database(
            {
                "messaging_provider_configs": [
                    {"enabled": True, "is_sandbox": True, "health_status": "healthy"},
                    {"enabled": True, "is_sandbox": False, "health_status": "healthy"},
                    {"enabled": True, "is_sandbox": False, "health_status": "failed"},
                    {"enabled": False, "is_sandbox": False, "health_status": "unknown"},
                ]
            }
        ),
    )

    summary = await integrations_overview._tenant_operational_summary("whatsapp")

    assert summary == {
        "production_verified": 1,
        "trial": 1,
        "setup_pending": 1,
        "connection_error": 1,
    }


@pytest.mark.asyncio
async def test_missing_tenant_connection_is_never_reported_as_production(monkeypatch):
    monkeypatch.setattr(integrations_overview, "db", _Database({}))

    summary = await integrations_overview._tenant_operational_summary("whatsapp")

    assert summary["setup_pending"] == 1
    assert summary["production_verified"] == 0
