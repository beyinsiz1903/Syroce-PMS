"""Complaint resolution must not claim an email unless delivery is confirmed."""

from types import SimpleNamespace

import pytest

from domains.pms.misc import complaints


@pytest.mark.asyncio
async def test_resolution_without_guest_does_not_claim_email():
    result = await complaints._notify_guest_resolved(
        {"id": "complaint-1"},
        "resolved",
        SimpleNamespace(tenant_id="tenant-a"),
    )

    assert result is False


@pytest.mark.asyncio
async def test_folio_adjustment_error_is_sanitized(monkeypatch):
    class _Folios:
        async def find_one(self, *args, **kwargs):
            raise RuntimeError("guest-identifier-provider-payload")

    monkeypatch.setattr(complaints, "db", SimpleNamespace(folios=_Folios()))

    result = await complaints._post_compensation_to_folio(
        {
            "id": "complaint-1",
            "booking_id": "booking-1",
            "compensation_offered": "discount",
            "compensation_amount": 10,
        },
        SimpleNamespace(tenant_id="tenant-a", id="user-1"),
    )

    assert result == {"folio_adjusted": False, "reason": "Folyo sorgusu hata verdi"}
    assert "guest-identifier" not in result["reason"]
