"""Public demo form -> durable lead -> super-admin inbox contract."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bootstrap.router_registry import _router_dependencies
from domains.admin.router import leads as admin_leads
from domains.sales import crm_router
from domains.sales.schemas import MarketingContactLeadRequest
from models.enums import UserRole


class FakeLeadCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args):
        self.docs = sorted(self.docs, key=lambda doc: doc["created_at"], reverse=True)
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    def __aiter__(self):
        async def iterate():
            for doc in self.docs:
                yield doc
        return iterate()


class FakeLeads:
    def __init__(self):
        self.docs = []

    async def find_one(self, query):
        for doc in self.docs:
            if (
                doc["source"] == query["source"]
                and doc["contact"]["phone"] == query["contact.phone"]
                and doc["hotel"]["property_name"] == query["hotel.property_name"]
                and doc["created_at"] >= query["created_at"]["$gte"]
            ):
                return doc
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["id"])

    def find(self, query):
        return FakeLeadCursor([doc for doc in self.docs if doc["source"] in query["source"]["$in"]])


def test_public_lead_router_has_no_crm_module_auth_guard():
    module = "domains.sales.crm_router"
    assert _router_dependencies(module, None, "public_leads_router") == []
    assert _router_dependencies(module, None, "router") != []


def test_protected_crm_routes_still_require_login():
    app = FastAPI()
    app.include_router(
        crm_router.router,
        dependencies=_router_dependencies("domains.sales.crm_router", None, "router"),
    )
    assert TestClient(app).get("/api/sales/customers").status_code in (401, 403)


def test_anonymous_demo_form_reaches_public_handler(monkeypatch):
    collection = FakeLeads()
    monkeypatch.setattr(crm_router, "db", SimpleNamespace(leads=collection))
    app = FastAPI()
    app.include_router(
        crm_router.public_leads_router,
        dependencies=_router_dependencies("domains.sales.crm_router", None, "public_leads_router"),
    )

    response = TestClient(app).post("/api/leads/contact", json={
        "full_name": "Demo Test", "company": "TEST Otel", "phone": "05550000000",
        "email": "demo@example.com", "message": "Canlı demo istiyorum",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert len(collection.docs) == 1


@pytest.mark.asyncio
async def test_demo_request_reaches_super_admin_inbox_once(monkeypatch):
    collection = FakeLeads()
    fake_db = SimpleNamespace(leads=collection)
    monkeypatch.setattr(crm_router, "db", fake_db)
    monkeypatch.setattr(admin_leads, "db", fake_db)

    request = MarketingContactLeadRequest(
        full_name="Demo Test",
        company="TEST Otel",
        phone="05550000000",
        email="demo@example.com",
        message="Canlı demo istiyorum",
        metadata={
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "otel-pms",
            "landing_path": "/otel-programi",
        },
    )

    first = await crm_router.create_public_marketing_lead(request, user_agent="test", x_forwarded_for=None)
    second = await crm_router.create_public_marketing_lead(request, user_agent="test", x_forwarded_for=None)
    inbox = await admin_leads.admin_list_pms_lite_leads(
        status=None, q=None, follow_up=False, limit=50, offset=0,
        current_user=SimpleNamespace(role=UserRole.SUPER_ADMIN),
    )

    assert first["ok"] is True and first["deduped"] is False
    assert second == {"ok": True, "lead_id": first["lead_id"], "deduped": True}
    assert len(collection.docs) == 1
    assert inbox["total"] == 1
    assert inbox["leads"][0]["lead_id"] == first["lead_id"]
    assert inbox["leads"][0]["source"] == "marketing_contact"
    assert inbox["leads"][0]["utm_source"] == "google"
    assert inbox["leads"][0]["utm_campaign"] == "otel-pms"
    assert inbox["leads"][0]["landing_path"] == "/otel-programi"
