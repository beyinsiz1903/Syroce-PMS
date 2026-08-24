from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from domains.compliance import retention_service


def _match(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_match(row, choice) for choice in expected):
                return False
            continue
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
        elif actual != expected:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def sort(self, *_args):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, count):
        return self.rows[:count]


class _Collection:
    def __init__(self, rows=None):
        self.rows = [dict(row) for row in rows or []]

    def find(self, query, _projection=None):
        return _Cursor(row for row in self.rows if _match(row, query))

    async def find_one(self, query, _projection=None):
        return next((dict(row) for row in self.rows if _match(row, query)), None)

    async def update_one(self, query, update):
        row = next((row for row in self.rows if _match(row, query)), None)
        if row:
            row.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1 if row else 0)

    async def insert_one(self, row):
        self.rows.append(dict(row))
        return SimpleNamespace(inserted_id=len(self.rows))


def _db():
    return SimpleNamespace(
        bookings=_Collection([
            {"tenant_id": "tenant-a", "guest_id": "old", "status": "checked_out", "check_out": "2020-01-01T00:00:00+00:00"},
            {"tenant_id": "tenant-a", "guest_id": "recent", "status": "checked_out", "check_out": "2020-01-01T00:00:00+00:00"},
            {"tenant_id": "tenant-a", "guest_id": "recent", "status": "confirmed", "check_out": "2026-12-01T00:00:00+00:00"},
            {"tenant_id": "tenant-b", "guest_id": "foreign", "status": "checked_out", "check_out": "2020-01-01T00:00:00+00:00"},
        ]),
        guests=_Collection([
            {"tenant_id": "tenant-a", "id": "old", "full_name": "Old Guest", "email": "old@example.com"},
            {"tenant_id": "tenant-a", "id": "recent", "full_name": "Recent Guest"},
            {"tenant_id": "tenant-b", "id": "foreign", "full_name": "Foreign Guest"},
        ]),
        gdpr_requests=_Collection(),
    )


@pytest.mark.asyncio
async def test_retention_preview_is_non_destructive_and_excludes_recent_stay():
    database = _db()
    result = await retention_service.enforce_guest_retention(
        database,
        tenant_id="tenant-a",
        retention_days=365,
        dry_run=True,
        now=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert result["eligible_count"] == 1
    assert result["skipped_recent"] == 1
    assert result["anonymized_count"] == 0
    assert database.guests.rows[0]["full_name"] == "Old Guest"


@pytest.mark.asyncio
async def test_retention_execution_scrubs_only_eligible_tenant_guest(monkeypatch):
    monkeypatch.setenv("ENABLE_GUEST_ANONYMIZATION", "1")
    database = _db()
    result = await retention_service.enforce_guest_retention(
        database,
        tenant_id="tenant-a",
        retention_days=365,
        dry_run=False,
        actor_id="admin-a",
        now=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert result["anonymized_count"] == 1
    assert database.guests.rows[0]["full_name"] == "ANONYMIZED"
    assert database.guests.rows[0]["email"] is None
    assert database.guests.rows[1]["full_name"] == "Recent Guest"
    assert database.guests.rows[2]["full_name"] == "Foreign Guest"
    assert database.gdpr_requests.rows[0]["guest_id"] == "old"


@pytest.mark.asyncio
async def test_retention_execution_fails_closed_without_runtime_flag(monkeypatch):
    monkeypatch.delenv("ENABLE_GUEST_ANONYMIZATION", raising=False)

    with pytest.raises(RuntimeError):
        await retention_service.enforce_guest_retention(
            _db(), tenant_id="tenant-a", retention_days=365, dry_run=False
        )


def test_daily_retention_task_is_registered():
    from celery_app import celery_app

    entry = celery_app.conf.beat_schedule["gdpr-guest-retention"]
    assert entry["task"] == "celery_tasks.gdpr_guest_retention_task"
