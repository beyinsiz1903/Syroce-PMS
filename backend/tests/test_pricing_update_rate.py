"""
Unit tests for PricingService.update_room_rate de-fake (WAVE 6).

Dogrular: gecersiz fiyat -> success:False; provider yok/var -> her halde
pushed:False + pushed_to:[] (uydurma kanal listesi YOK); rate_updates audit
kaydina pushed_to_channels:[] yazilir. Canli sunucu GEREKMEZ (db + provider mock).
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from domains.revenue.pricing.pricing_service import PricingService


class _FakeRateUpdates:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, doc):
        self.inserted.append(doc)
        return SimpleNamespace(inserted_id="x")


class _FakeDB:
    def __init__(self):
        self.rate_updates = _FakeRateUpdates()


def _svc():
    svc = PricingService()
    svc._db = _FakeDB()
    return svc


def _ctx():
    return SimpleNamespace(tenant_id="t1", actor_id="u1")


@pytest.mark.asyncio
async def test_update_rate_invalid_rate_fails_closed():
    svc = _svc()
    # eksik new_rate
    r = await svc.update_room_rate(_ctx(), {"room_type": "Standard", "target_date": "2026-04-20"})
    assert r.data["success"] is False
    assert r.data["pushed"] is False
    assert r.data["pushed_to"] == []
    # gecersiz: 0 / negatif / bool
    for bad in (0, -5, True):
        r = await svc.update_room_rate(
            _ctx(), {"room_type": "Standard", "target_date": "2026-04-20", "new_rate": bad}
        )
        assert r.data["success"] is False, f"new_rate={bad!r} gecersiz olmaliydi"
    # gecersiz: room_type yok
    r = await svc.update_room_rate(_ctx(), {"target_date": "2026-04-20", "new_rate": 120})
    assert r.data["success"] is False
    # gecersiz: tarih yok
    r = await svc.update_room_rate(_ctx(), {"room_type": "Standard", "new_rate": 120})
    assert r.data["success"] is False
    # hicbir gecersiz cagri rate_updates'e YAZMAMALI (uydurma kayit yok)
    assert svc._db.rate_updates.inserted == []


@pytest.mark.asyncio
async def test_update_rate_no_provider_records_local_no_push(monkeypatch):
    svc = _svc()
    import services.cm_provider as provider_svc
    monkeypatch.setattr(
        provider_svc, "_detect_active_provider",
        AsyncMock(return_value={"provider": None, "configuration_error": "not_configured"}),
    )
    r = await svc.update_room_rate(
        _ctx(), {"room_type": "Deluxe", "target_date": "2026-04-20", "new_rate": 150}
    )
    d = r.data
    assert d["success"] is True
    assert d["pushed"] is False
    assert d["pushed_to"] == []
    assert d["provider"] is None
    assert d["channels_updated"] == 0
    # audit kaydi YAZILDI ama uydurma kanal listesi YOK
    assert len(svc._db.rate_updates.inserted) == 1
    assert svc._db.rate_updates.inserted[0]["pushed_to_channels"] == []
    assert svc._db.rate_updates.inserted[0]["new_rate"] == 150


@pytest.mark.asyncio
async def test_update_rate_with_provider_still_not_pushed(monkeypatch):
    svc = _svc()
    import services.cm_provider as provider_svc
    monkeypatch.setattr(
        provider_svc, "_detect_active_provider",
        AsyncMock(return_value={"provider": "exely", "configuration_error": None}),
    )
    r = await svc.update_room_rate(
        _ctx(), {"room_type": "Standard", "target_date": "2026-04-20", "new_rate": 200}
    )
    d = r.data
    # provider olsa bile bu legacy uc GERCEK push yapmaz (dürüst: pushed False)
    assert d["success"] is True
    assert d["pushed"] is False
    assert d["queued"] is False
    assert d["pushed_to"] == []
    assert d["provider"] == "exely"
    assert svc._db.rate_updates.inserted[0]["pushed_to_channels"] == []
