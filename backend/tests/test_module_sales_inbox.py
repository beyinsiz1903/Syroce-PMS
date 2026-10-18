"""Durable platform quote queue, per-admin receipts and strict tenant boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import email
from core.module_sales_requests import follow_up_utc
from routers import marketplace

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
PLATFORM = SimpleNamespace(role="super_admin", id="root-a", tenant_id="platform", email="root@example.test")
OTHER_PLATFORM = SimpleNamespace(role="super_admin", id="root-b", tenant_id="different", email="root-b@example.test")
HOTEL = SimpleNamespace(role="admin", id="hotel-admin", tenant_id="hotel-a", email="hotel@example.test")


@pytest.fixture(autouse=True)
def context(monkeypatch, ledger_db):
    monkeypatch.setattr(marketplace, "_db", lambda: ledger_db)
    monkeypatch.delenv("MARKETPLACE_SALES_EMAIL", raising=False)
    monkeypatch.setattr(email, "send_email", AsyncMock(side_effect=AssertionError("No external email allowed in queue tests")))


async def seed_product(database):
    await database.marketplace_products.insert_one(
        {
            "key": "hr",
            "name": "İnsan Kaynakları",
            "active": True,
            "price_try": 1490,
            "unit_price_try": 1490,
            "included_units": 25,
            "pricing_model": "employee",
            "tax_rate_pct": 20,
            "price_version": 2,
        }
    )
    await database.tenants.insert_one({"id": HOTEL.tenant_id, "property_name": "Kartepe", "email": HOTEL.email})


async def test_quote_persists_quantity_and_appears_in_platform_queue_without_email(ledger_db):
    await seed_product(ledger_db)
    response = await marketplace.request_quote(marketplace.QuoteRequest(product_key="hr", quantity=26), HOTEL)
    assert response["ok"] is True
    assert response["delivery"] == {"admin_queue": True, "email": "not_configured"}
    assert "Satış ve modül talepleri" in response["destination"]
    stored = await ledger_db.marketplace_quote_requests.find_one({"id": response["request_id"]})
    assert stored["tenant_id"] == HOTEL.tenant_id
    assert stored["quantity"] == 26
    assert stored["price_snapshot"]["total_try"] == 3576
    assert stored["price_snapshot"]["price_version"] == 2
    inbox = await marketplace.admin_quote_inbox(PLATFORM)
    assert inbox["unread_count"] == inbox["open_count"] == inbox["new_count"] == 1
    assert inbox["notifications"][0]["request_id"] == response["request_id"]
    assert inbox["notifications"][0]["action_url"].startswith("/admin/module-requests?request=")
    result = await marketplace.admin_quote_requests(PLATFORM, "open", "", 50, 0)
    assert result["total"] == 1
    assert result["requests"][0]["tenant_name"] == "Kartepe"


@pytest.mark.parametrize("failure", ["provider", "metadata"])
async def test_email_failure_never_turns_a_durable_quote_into_failed_request(ledger_db, monkeypatch, failure):
    await seed_product(ledger_db)
    monkeypatch.setenv("MARKETPLACE_SALES_EMAIL", "sales@example.test")
    monkeypatch.setattr(email, "send_email", AsyncMock(side_effect=RuntimeError("Provider down")) if failure == "provider" else AsyncMock(return_value={"sent": True}))
    if failure == "metadata":
        from motor.motor_asyncio import AsyncIOMotorCollection

        original = AsyncIOMotorCollection.update_one

        async def fail_metadata(collection, query, patch, *args, **kwargs):
            if collection.name == "marketplace_quote_requests" and "delivery.email" in patch.get("$set", {}):
                raise RuntimeError("Delivery metadata write failed")
            return await original(collection, query, patch, *args, **kwargs)

        monkeypatch.setattr(AsyncIOMotorCollection, "update_one", fail_metadata)
    response = await marketplace.request_quote(marketplace.QuoteRequest(product_key="hr"), HOTEL)
    assert response["ok"] is True
    assert await ledger_db.marketplace_quote_requests.count_documents({}) == 1
    assert response["delivery"]["email"] == ("failed" if failure == "provider" else "sent")
    assert (await marketplace.admin_quote_inbox(PLATFORM))["unread_count"] == 1


async def test_historical_requests_are_visible_and_read_receipts_are_per_admin(ledger_db):
    await ledger_db.marketplace_quote_requests.insert_many(
        [
            {"id": "883f5403-legacy", "tenant_id": "hotel-a", "product_name": "POS", "status": "new", "created_at": "2026-10-18T10:00:00+00:00"},
            {"id": "legacy-contacted", "tenant_id": "hotel-b", "status": "contacted", "created_at": "2026-10-18T09:00:00+00:00"},
            {"id": "legacy-closed", "tenant_id": "hotel-c", "status": "closed", "created_at": "2026-10-18T08:00:00+00:00"},
        ]
    )
    first = await marketplace.admin_quote_inbox(PLATFORM)
    assert first["unread_count"] == first["open_count"] == 2
    await marketplace.admin_acknowledge_quotes(marketplace.QuoteReadRequest(request_ids=["883f5403-legacy", "missing"]), PLATFORM)
    await marketplace.admin_acknowledge_quotes(marketplace.QuoteReadRequest(request_ids=["883f5403-legacy"]), PLATFORM)
    assert (await marketplace.admin_quote_inbox(PLATFORM))["unread_count"] == 1
    assert (await marketplace.admin_quote_inbox(OTHER_PLATFORM))["unread_count"] == 2
    assert await ledger_db.marketplace_quote_request_reads.count_documents({}) == 1
    assert (await ledger_db.marketplace_quote_requests.find_one({"id": "883f5403-legacy"}))["status"] == "new"
    filtered = await marketplace.admin_quote_requests(PLATFORM, "in_progress", "", 50, 0)
    assert filtered["requests"][0]["id"] == "legacy-contacted"
    assert filtered["requests"][0]["status"] == "in_progress"
    assert filtered["summary"]["open"] == 2


async def test_queue_pagination_search_and_counts_do_not_hide_older_requests(ledger_db):
    await ledger_db.marketplace_quote_requests.insert_many(
        [
            {"id": f"request-{i:03}", "tenant_id": "hotel-b" if i % 2 else "hotel-a", "tenant_name": "Example [otel]", "status": "new", "created_at": f"2026-10-18T10:{i // 60:02}:{i % 60:02}+00:00"}
            for i in range(235)
        ]
    )
    first = await marketplace.admin_quote_requests(PLATFORM, "open", "", 100, 0)
    last = await marketplace.admin_quote_requests(PLATFORM, "open", "", 100, 200)
    assert first["total"] == last["total"] == 235
    assert len(first["requests"]) == 100 and first["has_more"] is True
    assert len(last["requests"]) == 35 and last["has_more"] is False
    found = await marketplace.admin_quote_requests(PLATFORM, "all", "request-003", 50, 0)
    assert found["total"] == 1 and found["requests"][0]["id"] == "request-003"
    literal_search = await marketplace.admin_quote_requests(PLATFORM, "all", "[otel]", 50, 0)
    assert literal_search["total"] == 235
    assert literal_search["summary"]["new"] == 235


@pytest.mark.parametrize("role", ["admin", "front_desk", "finance", "guest"])
async def test_hotel_roles_cannot_list_acknowledge_or_update_platform_requests(role):
    user = SimpleNamespace(role=role, id="hotel-user", tenant_id="hotel-a")
    for call in (
        lambda: marketplace.admin_quote_inbox(user),
        lambda: marketplace.admin_quote_requests(user, "all", "", 50, 0),
        lambda: marketplace.admin_acknowledge_quotes(marketplace.QuoteReadRequest(request_ids=["q"]), user),
        lambda: marketplace.admin_update_quote_request("q", marketplace.QuoteRequestUpdate(status="won"), user),
    ):
        with pytest.raises(HTTPException) as failure:
            await call()
        assert failure.value.status_code == 403


async def test_sales_update_stores_utc_follow_up_and_history(ledger_db):
    await ledger_db.marketplace_quote_requests.insert_one({"id": "q", "tenant_id": "hotel-a", "status": "new"})
    payload = marketplace.QuoteRequestUpdate(status="in_progress", follow_up_at="2026-10-19T10:30", assignee="Sales")
    assert payload.follow_up_at == "2026-10-19T07:30:00+00:00"
    await marketplace.admin_update_quote_request("q", payload, PLATFORM)
    row = await ledger_db.marketplace_quote_requests.find_one({"id": "q"})
    assert row["follow_up_at"] == "2026-10-19T07:30:00+00:00"
    assert row["assignee"] == "Sales"
    assert await ledger_db.marketplace_quote_request_history.count_documents({"request_id": "q", "changed_by": PLATFORM.id}) == 1


def test_invalid_follow_up_and_quantities_are_rejected():
    assert follow_up_utc("2026-10-19T10:30:00+03:00") == "2026-10-19T07:30:00+00:00"
    for value in ("not-a-date", "2026-02-31T10:00"):
        with pytest.raises(ValidationError):
            marketplace.QuoteRequestUpdate(status="new", follow_up_at=value)
    for quantity in (0, -1, 10001, 1.5):
        with pytest.raises(ValidationError):
            marketplace.QuoteRequest(product_key="hr", quantity=quantity)


async def test_http_routes_validate_pagination_and_enforce_platform_access(ledger_db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from core.security import get_current_user

    app = FastAPI()
    app.include_router(marketplace.router)
    app.dependency_overrides[get_current_user] = lambda: PLATFORM
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/module-store/admin/quote-requests")
        assert result.status_code == 200
        assert result.json()["total"] == 0
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status_filter": "invalid"}, {"search": "x" * 201}):
            assert (await client.get("/api/module-store/admin/quote-requests", params=params)).status_code == 422
        app.dependency_overrides[get_current_user] = lambda: HOTEL
        assert (await client.get("/api/module-store/admin/quote-requests/inbox")).status_code == 403
        assert (await client.post("/api/module-store/admin/quote-requests/acknowledge", json={"request_ids": ["q"]})).status_code == 403


async def test_acknowledging_visible_quotes_cannot_swallow_a_new_request(ledger_db):
    await ledger_db.marketplace_quote_requests.insert_one({"id": "first", "status": "new", "created_at": "2026-10-18T10:00:00+00:00"})
    visible = (await marketplace.admin_quote_inbox(PLATFORM))["notifications"]
    await ledger_db.marketplace_quote_requests.insert_one({"id": "later", "status": "new", "created_at": "2026-10-18T10:01:00+00:00"})
    await marketplace.admin_acknowledge_quotes(marketplace.QuoteReadRequest(request_ids=[item["request_id"] for item in visible]), PLATFORM)
    inbox = await marketplace.admin_quote_inbox(PLATFORM)
    assert inbox["unread_count"] == 1
    assert inbox["notifications"][0]["request_id"] == "later"
    await marketplace.admin_update_quote_request("later", marketplace.QuoteRequestUpdate(status="won"), PLATFORM)
    assert (await marketplace.admin_quote_inbox(PLATFORM))["unread_count"] == 0
