from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import pms_reservations


class _Bookings:
    def __init__(self, booking):
        self.booking = booking

    async def find_one(self, _query):
        return dict(self.booking)


class _FailOnMutation:
    def __getattr__(self, _name):
        raise AssertionError("Koruma reddinden sonra kalıcı işlem yapılmamalı")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_out", "cancelled", "no_show"])
async def test_rate_override_rejects_terminal_bookings_before_writes(monkeypatch, status):
    monkeypatch.setattr(
        pms_reservations,
        "db",
        SimpleNamespace(
            bookings=_Bookings({"id": "booking-1", "status": status, "total_amount": 2500}),
            rate_override_logs=_FailOnMutation(),
        ),
    )
    monkeypatch.setattr(
        pms_reservations,
        "create_audit_log",
        _FailOnMutation(),
    )

    with pytest.raises(HTTPException) as exc:
        await pms_reservations.create_rate_override_with_panel(
            booking_id="booking-1",
            new_rate=2750,
            override_reason="Yetkili fiyat düzeltmesi",
            current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1", name="Yetkili", role="super_admin"),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_rate_override_rejects_noop_before_audit_or_write(monkeypatch):
    monkeypatch.setattr(
        pms_reservations,
        "db",
        SimpleNamespace(
            bookings=_Bookings({"id": "booking-1", "status": "confirmed", "total_amount": 2500}),
            rate_override_logs=_FailOnMutation(),
        ),
    )
    monkeypatch.setattr(pms_reservations, "create_audit_log", _FailOnMutation())

    with pytest.raises(HTTPException) as exc:
        await pms_reservations.create_rate_override_with_panel(
            booking_id="booking-1",
            new_rate=2500,
            override_reason="Aynı fiyat denemesi",
            current_user=SimpleNamespace(tenant_id="tenant-1", id="user-1", name="Yetkili", role="super_admin"),
        )

    assert exc.value.status_code == 409
