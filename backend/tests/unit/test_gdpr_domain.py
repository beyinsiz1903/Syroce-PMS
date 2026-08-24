from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from domains.compliance import gdpr_router as module


class FakeCursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


def _matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(row, option) for option in expected):
                return False
            continue
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$nin" in expected and actual in expected["$nin"]:
                return False
            if "$regex" in expected and not str(actual or "").startswith(expected["$regex"].lstrip("^")):
                return False
        elif actual != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = [dict(row) for row in rows or []]

    async def count_documents(self, query):
        return sum(1 for row in self.rows if _matches(row, query))

    async def find_one(self, query, _projection=None):
        return next((dict(row) for row in self.rows if _matches(row, query)), None)

    def find(self, query, _projection=None):
        return FakeCursor(row for row in self.rows if _matches(row, query))

    async def update_one(self, query, update, upsert=False):
        row = next((row for row in self.rows if _matches(row, query)), None)
        if row is None and upsert:
            row = dict(query)
            row.update(update.get("$setOnInsert", {}))
            self.rows.append(row)
        if row is not None:
            row.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1 if row else 0)

    async def insert_one(self, row):
        self.rows.append(dict(row))
        return SimpleNamespace(inserted_id=row.get("id"))


class FakeDB:
    def __init__(self):
        self.guests = FakeCollection([
            {"tenant_id": "tenant-a", "id": "g1"},
            {"tenant_id": "tenant-a", "id": "g2", "anonymized": True},
            {"tenant_id": "tenant-b", "id": "g3"},
        ])
        self.kvkk_consents = FakeCollection([{"tenant_id": "tenant-a", "guest_id": "g1"}])
        self.kvkk_erasure_requests = FakeCollection([])
        self.gdpr_retention_policies = FakeCollection([])
        self.dpa_records = FakeCollection([])
        self.audit_logs = FakeCollection([])


@pytest.mark.asyncio
async def test_retention_policy_is_tenant_scoped_persisted_and_audited(monkeypatch):
    fake_db = FakeDB()
    audits = []

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(module, "db", fake_db)
    monkeypatch.setattr(module, "log_audit_event", fake_audit)
    user = SimpleNamespace(tenant_id="tenant-a", id="user-1")

    result = await module.update_retention_policy(
        module.RetentionPolicyUpdate(
            guest_data_retention_days=900,
            booking_data_retention_days=1900,
            audit_log_retention_days=2000,
            marketing_consent_retention_days=400,
            auto_anonymize=True,
        ),
        current_user=user,
        _permission=None,
    )

    assert result["guest_data_retention_days"] == 900
    assert result["policies"][0]["auto_anonymize"] is True
    assert fake_db.gdpr_retention_policies.rows[0]["tenant_id"] == "tenant-a"
    assert audits[0]["action"] == "gdpr.retention_policy.updated"


@pytest.mark.asyncio
async def test_compliance_status_uses_real_checks_and_frontend_contract(monkeypatch):
    fake_db = FakeDB()
    fake_db.gdpr_retention_policies.rows.append({"tenant_id": "tenant-a", "configured": True})
    fake_db.dpa_records.rows.append({"tenant_id": "tenant-a", "status": "active"})
    monkeypatch.setattr(module, "db", fake_db)

    result = await module.get_compliance_status(SimpleNamespace(tenant_id="tenant-a"))

    assert result["total_guests"] == 2
    assert result["guests_with_consent"] == 1
    assert result["anonymized_guests"] == 1
    assert result["data_processing_agreements"] == 1
    assert result["compliance_score"] == 75
    assert result["status"] == "action_required"


def test_retention_rejects_invalid_or_negative_days():
    with pytest.raises(ValidationError):
        module.RetentionPolicyUpdate(guest_data_retention_days=-1)

