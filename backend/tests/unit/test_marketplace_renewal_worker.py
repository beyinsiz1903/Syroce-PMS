from datetime import UTC, datetime, timedelta

import pytest

from core.marketplace_renewal_service import process_due_renewals


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, _limit):
        return self

    def __aiter__(self):
        self.iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration as error:
            raise StopAsyncIteration from error


class Collection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.updates = []

    def find(self, *_args, **_kwargs):
        return Cursor(self.rows)

    async def find_one(self, query, *_args, **_kwargs):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items() if not key.startswith("$")):
                return row
        return None

    async def update_one(self, query, update, **kwargs):
        self.updates.append((query, update, kwargs))


class FakeDb:
    def __init__(self, subscription, product=None, payment_method=None):
        self.tenant_subscriptions = Collection([subscription])
        self.marketplace_products = Collection([product] if product else [])
        self.marketplace_payment_methods = Collection([payment_method] if payment_method else [])
        self.marketplace_renewal_attempts = Collection()


@pytest.mark.asyncio
async def test_due_renewal_without_payment_method_enters_dunning_grace_period():
    now = datetime(2026, 10, 9, tzinfo=UTC)
    subscription = {
        "id": "sub-1", "tenant_id": "tenant-1", "product_key": "hr",
        "status": "active", "auto_renew": True, "trial": False,
        "end_date": (now + timedelta(hours=1)).isoformat(),
    }
    db = FakeDb(subscription, product={"key": "hr", "active": True})

    result = await process_due_renewals(db, now=now)

    assert result == {"processed": 1, "renewed": 0, "failed": 1}
    attempt = db.marketplace_renewal_attempts.updates[0][1]["$set"]
    assert attempt["reason"] == "payment_method_required"
    dunning = db.tenant_subscriptions.updates[0][1]["$set"]
    assert dunning["status"] == "past_due"
    assert dunning["renewal_status"] == "payment_action_required"
    assert dunning["grace_until"] == (now + timedelta(days=7)).isoformat()
