"""Backend tests for the staff onboarding flow.

Locks in regressions for:
1. Candidate hiring auto-provisions staff member & checklist.
2. Complete onboarding checklist steps one by one.
3. Enforce checklist completion before final staff activation (fail-closed).
"""
from __future__ import annotations

import sys
import datetime as dt
if not hasattr(dt, "UTC"):
    dt.UTC = dt.timezone.utc

from types import SimpleNamespace
from typing import Any
import pytest
from datetime import datetime, timezone
from datetime import timezone as dt_timezone
UTC = dt_timezone.utc
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from domains.hr import router as hr_router
from domains.hr.router import router as hr_api_router

TENANT_ID = "t-onboard-1"
_APPLICANT_ID = "app-123"

_JOB_POSTING = {
    "id": "job-1",
    "tenant_id": TENANT_ID,
    "title": "Housekeeper",
    "status": "active"
}

_APPLICANT = {
    "id": _APPLICANT_ID,
    "tenant_id": TENANT_ID,
    "job_id": "job-1",
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+905555555555",
    "status": "screening"
}


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *_a, **_kw): return self
    def __aiter__(self):
        self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration
    async def to_list(self, length=None):
        return self._docs


class _MockCollection:
    def __init__(self, name, initial_docs=None):
        self.name = name
        self.docs = {d["id"]: dict(d) for d in (initial_docs or [])}

    def find(self, flt, _proj=None):
        res = []
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                res.append(dict(d))
        return _FakeCursor(res)

    async def find_one(self, flt, _proj=None):
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                if "id" in flt and d["id"] == flt["id"]:
                    return dict(d)
                if "staff_id" in flt and d.get("staff_id") == flt["staff_id"]:
                    return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return SimpleNamespace(inserted_id=doc["id"])

    async def update_one(self, flt, update, session=None):
        target = None
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                if "id" in flt and d["id"] == flt["id"]:
                    target = d
                if "staff_id" in flt and d.get("staff_id") == flt["staff_id"]:
                    target = d
        if target:
            if "$set" in update:
                target.update(update["$set"])
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self.job_postings = _MockCollection("job_postings", [_JOB_POSTING])
        self.job_applicants = _MockCollection("job_applicants", [_APPLICANT])
        self.staff_members = _MockCollection("staff_members")
        self.staff_onboarding = _MockCollection("staff_onboarding")
        self.audit_logs = _MockCollection("audit_logs")
        self.tenant_subscriptions = _MockCollection("tenant_subscriptions", [{"id": "sub1", "tenant_id": TENANT_ID, "status": "active", "product_key": "hr_basic"}])


@pytest.fixture
def env(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(hr_router, "db", fake_db)
    import core.entitlements.enforcement as enf
    monkeypatch.setattr(enf, "db", fake_db)

    # Patch _audit helper in HR router
    async def _fake_audit(user, action, entity_type, entity_id, details, **kwargs):
        await fake_db.audit_logs.insert_one({
            "id": str(len(fake_db.audit_logs.docs)),
            "tenant_id": user.tenant_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details
        })
    monkeypatch.setattr(hr_router, "_audit", _fake_audit)

    app = FastAPI()
    app.include_router(hr_api_router)

    from core.security import get_current_user
    async def _hr_user():
        return SimpleNamespace(
            id="u1", username="hr_manager",
            tenant_id=TENANT_ID, role="admin",
            granted_permissions=None,
        )
    app.dependency_overrides[get_current_user] = _hr_user



    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=fake_db, app=app)


def test_staff_onboarding_full_workflow(env):
    # 1. Update applicant status to hired (triggers onboarding)
    res = env.client.post(
        f"/api/hr/applicants/{_APPLICANT_ID}/status",
        json={"status": "hired", "note": "Congratz!"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "hired"

    # Verify staff member and checklist created
    assert len(env.db.staff_members.docs) == 1
    staff_id = list(env.db.staff_members.docs.keys())[0]
    staff = env.db.staff_members.docs[staff_id]
    assert staff["name"] == "Jane Doe"
    assert staff["active"] is False  # not active yet
    assert staff["onboarding_status"] == "pending"

    assert len(env.db.staff_onboarding.docs) == 1
    chk_id = list(env.db.staff_onboarding.docs.keys())[0]
    checklist = env.db.staff_onboarding.docs[chk_id]
    assert checklist["staff_id"] == staff_id
    assert checklist["status"] == "pending"

    # 2. Get Onboarding Status
    get_res = env.client.get(f"/api/hr/staff/{staff_id}/onboarding")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["checklist"]["status"] == "pending"

    # 3. Finalize onboarding before completing steps (must return 409)
    complete_fail = env.client.post(f"/api/hr/staff/{staff_id}/onboarding/complete")
    assert complete_fail.status_code == 409
    assert "Eksik adımlar var" in complete_fail.json()["detail"]

    # 4. Complete each checklist step
    steps_keys = [s["key"] for s in checklist["steps"]]
    for key in steps_keys:
        step_res = env.client.post(
            f"/api/hr/staff/{staff_id}/onboarding/steps/{key}/complete",
            json={"reference_id": f"ref-{key}", "note": f"Completed {key}"}
        )
        assert step_res.status_code == 200, step_res.text

    # Verify checklist status is now completed
    chk_updated = env.db.staff_onboarding.docs[chk_id]
    assert chk_updated["status"] == "completed"

    # 5. Finalize onboarding (success)
    complete_ok = env.client.post(f"/api/hr/staff/{staff_id}/onboarding/complete")
    assert complete_ok.status_code == 200, complete_ok.text
    assert complete_ok.json()["success"] is True

    # Verify staff member is active
    staff_updated = env.db.staff_members.docs[staff_id]
    assert staff_updated["active"] is True
    assert staff_updated["onboarding_status"] == "completed"

    # Verify audit log recorded onboarding complete
    assert any(log["action"] == "hr.staff.onboarding_complete" for log in env.db.audit_logs.docs.values())
