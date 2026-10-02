"""Konaklaması başlayan kayıtlarda eski fiyat paneli koruması."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import pms_reservations


class _Bookings:
    async def find_one(self, query):
        assert query == {"id": "booking-1", "tenant_id": "tenant-1"}
        return {
            "id": "booking-1",
            "status": "checked_in",
            "total_amount": 2500,
        }


class _MustNotMutate:
    def __getattr__(self, name):
        raise AssertionError(f"Koruma sonrası mutasyon çağrılmamalı: {name}")


@pytest.mark.asyncio
async def test_rate_override_panel_rejects_checked_in_booking(monkeypatch):
    monkeypatch.setattr(
        pms_reservations,
        "db",
        SimpleNamespace(
            bookings=_Bookings(),
            rate_override_logs=_MustNotMutate(),
        ),
    )
    monkeypatch.setattr(pms_reservations, "create_audit_log", _MustNotMutate())

    current_user = SimpleNamespace(
        tenant_id="tenant-1",
        id="user-1",
        name="Yetkili",
        role="super_admin",
    )

    with pytest.raises(HTTPException) as error:
        await pms_reservations.create_rate_override_with_panel(
            booking_id="booking-1",
            new_rate=3000,
            override_reason="Tahakkuk farkı kontrolü",
            current_user=current_user,
        )

    assert error.value.status_code == 409
    assert "günlük fiyat düzeltmesi" in error.value.detail.lower()
