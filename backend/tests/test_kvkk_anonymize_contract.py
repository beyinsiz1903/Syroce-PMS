"""F8 (Wave 5) — KVKK/GDPR anonymize contract polish.

Wave 3 locked the feature-flag gate + super-admin guard wiring. Wave 5 locks
the *behavioral* contract of the anonymize handler so a regression cannot
silently weaken right-to-be-forgotten:

  - Disabled flag → 503, no DB mutation (fail-closed).
  - Enabled + missing guest → 404 (tenant-scoped lookup).
  - Enabled + existing guest → PII fields scrubbed to None, full_name set to
    "ANONYMIZED", anonymized markers set, AND an audit row written to
    gdpr_requests (tenant_id, guest_id, type=anonymization, requested_by).

Policy note (documented, intentional): there is NO public hard-delete endpoint
for guests. Right-to-be-forgotten is satisfied by irreversible anonymization
while preserving the tenant-scoped record skeleton for financial/audit
integrity. Soft-delete (status="deleted") exists separately and is blocked when
active bookings reference the guest. This test treats the absence of hard-delete
as a deliberate policy, not a gap.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domains.admin.router.compliance as comp
from domains.admin.router.compliance import (
    _GUEST_PII_FIELDS,
    anonymize_guest,
)


class _Guests:
    def __init__(self, existing):
        self._existing = existing
        self.updated = None

    async def find_one(self, query, *a, **k):
        self.last_query = query
        return self._existing

    async def update_one(self, query, update, *a, **k):
        self.updated = (query, update)
        return SimpleNamespace(modified_count=1)


class _Gdpr:
    def __init__(self):
        self.inserted = None

    async def insert_one(self, doc):
        self.inserted = doc
        return SimpleNamespace(inserted_id="x")


def _user():
    return SimpleNamespace(id="admin1", tenant_id="t1", role="super_admin")


@pytest.mark.asyncio
async def test_anonymize_disabled_returns_503_no_mutation(monkeypatch):
    monkeypatch.delenv("ENABLE_GUEST_ANONYMIZATION", raising=False)
    guests = _Guests({"id": "g1"})
    monkeypatch.setattr(comp, "db", SimpleNamespace(guests=guests, gdpr_requests=_Gdpr()))
    with pytest.raises(HTTPException) as ei:
        await anonymize_guest(guest_id="g1", current_user=_user())
    assert ei.value.status_code == 503
    assert guests.updated is None  # fail-closed, nothing scrubbed


@pytest.mark.asyncio
async def test_anonymize_missing_guest_returns_404(monkeypatch):
    monkeypatch.setenv("ENABLE_GUEST_ANONYMIZATION", "1")
    guests = _Guests(None)  # not found
    monkeypatch.setattr(comp, "db", SimpleNamespace(guests=guests, gdpr_requests=_Gdpr()))
    with pytest.raises(HTTPException) as ei:
        await anonymize_guest(guest_id="ghost", current_user=_user())
    assert ei.value.status_code == 404
    assert guests.last_query.get("tenant_id") == "t1"  # tenant-scoped lookup


@pytest.mark.asyncio
async def test_anonymize_scrubs_pii_and_writes_audit(monkeypatch):
    monkeypatch.setenv("ENABLE_GUEST_ANONYMIZATION", "1")
    guests = _Guests({"id": "g1"})
    gdpr = _Gdpr()
    monkeypatch.setattr(comp, "db", SimpleNamespace(guests=guests, gdpr_requests=gdpr))

    res = await anonymize_guest(guest_id="g1", current_user=_user())

    assert res["ok"] is True
    # PII scrub: every PII field set to None, full_name explicitly ANONYMIZED.
    set_doc = guests.updated[1]["$set"]
    for f in _GUEST_PII_FIELDS:
        if f == "full_name":
            continue
        assert set_doc[f] is None
    assert set_doc["full_name"] == "ANONYMIZED"
    assert set_doc["anonymized"] is True
    assert set_doc["anonymized_by"] == "admin1"
    # Update is tenant-scoped.
    assert guests.updated[0].get("tenant_id") == "t1"
    # Audit row written with required provenance.
    assert gdpr.inserted is not None
    assert gdpr.inserted["type"] == "anonymization"
    assert gdpr.inserted["tenant_id"] == "t1"
    assert gdpr.inserted["guest_id"] == "g1"
    assert gdpr.inserted["requested_by"] == "admin1"


def test_no_public_hard_delete_route_is_intentional():
    """Policy lock: anonymize is the right-to-be-forgotten path; there is no
    hard-delete route on the compliance router by design."""
    paths = {getattr(r, "path", "") for r in comp.router.routes}
    assert "/api/gdpr/guests/{guest_id}/anonymize" in paths
    assert not any("hard-delete" in p or "hard_delete" in p for p in paths)
