"""TGA Outbound Payload — birim testleri.

`backend/core/tga_outbound.py` içindeki ``build_daily_payload`` fonksiyonu
TGA'ya (Türkiye Turizm Tanıtım ve Geliştirme Ajansı) gönderilen vergi /
regülasyon raporlarına temel oluşturur. Bu testler MongoDB'ye dokunmadan,
``db.bookings`` ve ``db.guests`` koleksiyonlarını fake bir async cursor ile
maskeleyerek payload üretiminin doğruluğunu pin'ler:

  * Tek gece in-house + o gün giren rezervasyon
  * Çok gece konaklama (gece dağıtımının doğru tarafa düşmesi)
  * O gün giren (arrival) sayacı
  * O gün çıkan (departure) — totallere DAHİL EDİLMEMELİ
  * cancelled / no_show — query whitelist'i ile DIŞARDA bırakılmalı

Ayrıca ``_per_night_rate`` öncelik sırası (nightly_breakdown >
rate_per_night > total_amount/nights) ve ``_to_iso3`` fallback davranışı
ayrı pure-unit testlerle korunur.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from core import tga_outbound as tga


# ── Fake async DB layer ─────────────────────────────────────────────────────

class _FakeCursor:
    """Minimal async cursor: hem ``await .to_list(length=...)`` hem de
    ``async for`` üzerinden tüketilebilir.
    """

    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = list(docs)

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        if length is None:
            return list(self._docs)
        return list(self._docs[:length])

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    """Fake collection için minimal mongo benzeri filtre.

    Sadece testlerde kullanılan operatörleri destekler:
      * eşitlik: ``{"key": value}``
      * ``{"$in": [...]}``
      * ``{"$lt": x}``, ``{"$gt": x}``
    """
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            for op, val in expected.items():
                if op == "$in" and actual not in val:
                    return False
                if op == "$lt" and not (actual is not None and actual < val):
                    return False
                if op == "$gt" and not (actual is not None and actual > val):
                    return False
                if op == "$exists":
                    exists = key in doc and doc[key] is not None
                    if exists != val:
                        return False
                if op == "$ne" and actual == val:
                    return False
        else:
            if actual != expected:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None):
        self.docs: list[dict[str, Any]] = list(docs or [])

    def find(self, query: dict[str, Any] | None = None,
             projection: dict[str, Any] | None = None) -> _FakeCursor:
        q = query or {}
        return _FakeCursor([d for d in self.docs if _matches(d, q)])


class _FakeDB:
    def __init__(self):
        self.bookings = _FakeCollection()
        self.guests = _FakeCollection()


@pytest.fixture
def fake_db(monkeypatch):
    """``core.tga_outbound`` modülünün bağlandığı ``db`` referansını
    in-memory bir fake ile değiştirir.
    """
    fake = _FakeDB()
    monkeypatch.setattr(tga, "db", fake)
    return fake


# ── Synthetic data helpers ──────────────────────────────────────────────────

def _booking(
    *,
    id: str,
    check_in: str,
    check_out: str,
    guest_id: str,
    adults: int = 2,
    children: int = 0,
    total_amount: float = 0.0,
    rate_per_night: float | None = None,
    nightly_breakdown: Any = None,
    source_channel: str = "direct",
    status: str = "checked_in",
    tenant_id: str = "t1",
) -> dict[str, Any]:
    b = {
        "id": id,
        "tenant_id": tenant_id,
        "status": status,
        "check_in": check_in,
        "check_out": check_out,
        "guest_id": guest_id,
        "adults": adults,
        "children": children,
        "total_amount": total_amount,
        "currency": "TRY",
        "source_channel": source_channel,
    }
    if rate_per_night is not None:
        b["rate_per_night"] = rate_per_night
    if nightly_breakdown is not None:
        b["nightly_breakdown"] = nightly_breakdown
    return b


def _guest(*, id: str, nationality: str | None = None,
           country: str | None = None, tenant_id: str = "t1") -> dict[str, Any]:
    return {"id": id, "tenant_id": tenant_id,
            "nationality": nationality, "country": country}


# ── Pure-unit tests: _to_iso3 ───────────────────────────────────────────────

class TestToIso3:
    def test_two_letter_iso(self):
        assert tga._to_iso3("TR") == "TUR"
        assert tga._to_iso3("de") == "DEU"

    def test_already_iso3(self):
        # Mapping'de değer olarak geçen 3 harfli kod kabul edilir.
        assert tga._to_iso3("TUR") == "TUR"
        assert tga._to_iso3("usa") == "USA"

    def test_country_name_turkish(self):
        # Mapping anahtarları zaten upper-case; ``str.upper()`` ile eşleşmesi
        # garanti olan formları kullanıyoruz (TR upper'ı İ değil I üretir,
        # bu yüzden "TURKIYE" / "TÜRKİYE" anahtarları ayrı ayrı tutulur).
        assert tga._to_iso3("turkiye") == "TUR"
        assert tga._to_iso3("almanya") == "DEU"
        assert tga._to_iso3("rusya") == "RUS"

    def test_country_name_english(self):
        assert tga._to_iso3("Germany") == "DEU"

    def test_unknown_country_falls_back_to_zzz(self):
        assert tga._to_iso3("Wakanda") == "ZZZ"
        assert tga._to_iso3("XX") == "ZZZ"
        # 3 harfli ama listede olmayan
        assert tga._to_iso3("QQQ") == "ZZZ"

    def test_empty_or_none_falls_back_to_zzz(self):
        assert tga._to_iso3(None) == "ZZZ"
        assert tga._to_iso3("") == "ZZZ"
        assert tga._to_iso3("   ") == "ZZZ"


# ── Pure-unit tests: _per_night_rate priority ───────────────────────────────

class TestPerNightRatePriority:
    def test_nightly_breakdown_dict_wins(self):
        b = _booking(
            id="b1", check_in="2026-05-01", check_out="2026-05-04",
            guest_id="g1", total_amount=1500.0, rate_per_night=999.0,
            nightly_breakdown={
                "2026-05-01": 100.0,
                "2026-05-02": 200.0,
                "2026-05-03": 300.0,
            },
        )
        assert tga._per_night_rate(b, date(2026, 5, 2)) == 200.0

    def test_nightly_breakdown_list_wins(self):
        b = _booking(
            id="b1", check_in="2026-05-01", check_out="2026-05-04",
            guest_id="g1", total_amount=1500.0, rate_per_night=999.0,
            nightly_breakdown=[
                {"date": "2026-05-01", "amount": 100.0},
                {"date": "2026-05-02", "amount": 250.0},
                {"date": "2026-05-03", "rate": 300.0},
            ],
        )
        assert tga._per_night_rate(b, date(2026, 5, 2)) == 250.0
        assert tga._per_night_rate(b, date(2026, 5, 3)) == 300.0

    def test_nightly_breakdown_missing_falls_through_to_rate_per_night(self):
        b = _booking(
            id="b1", check_in="2026-05-01", check_out="2026-05-04",
            guest_id="g1", total_amount=1500.0, rate_per_night=400.0,
            nightly_breakdown={"2026-05-02": 250.0},
        )
        # 2026-05-03 yok → rate_per_night fallback
        assert tga._per_night_rate(b, date(2026, 5, 3)) == 400.0

    def test_rate_per_night_wins_over_total_div_nights(self):
        b = _booking(
            id="b1", check_in="2026-05-01", check_out="2026-05-04",
            guest_id="g1", total_amount=900.0, rate_per_night=500.0,
        )
        assert tga._per_night_rate(b, date(2026, 5, 2)) == 500.0

    def test_total_div_nights_fallback(self):
        b = _booking(
            id="b1", check_in="2026-05-01", check_out="2026-05-04",
            guest_id="g1", total_amount=900.0,
        )
        # 3 gece: 900 / 3 = 300
        assert tga._per_night_rate(b, date(2026, 5, 2)) == 300.0


# ── Integration-style tests: build_daily_payload ────────────────────────────

TENANT = "t1"


class TestBuildDailyPayload:
    async def test_single_night_in_house_arrival(self, fake_db):
        """Tek gece kalan + o gün giren misafir: hem in-house hem arrival
        sayaçları artmalı, demografi ve kanal aynı tek satıra düşmeli.
        """
        target = date(2026, 5, 10)
        fake_db.guests.docs = [_guest(id="g1", nationality="TR")]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-05-10T14:00:00+00:00",
                check_out="2026-05-11T11:00:00+00:00",
                guest_id="g1", adults=2, children=1,
                total_amount=1000.0, source_channel="direct",
                status="checked_in",
            ),
        ]

        payload = await tga.build_daily_payload(TENANT, target)

        assert payload["rapor_tarihi"] == "2026-05-10"
        assert payload["toplam_oda"] == 1
        assert payload["toplam_kisi"] == 3  # 2 + 1
        assert payload["giren_oda"] == 1
        assert payload["giren_kisi"] == 3
        assert payload["net_oda_geliri"] == 1000.0  # 1 gece, total/1
        # Demografi
        assert payload["demografik_veriler"] == [
            {"iso_kodu": "TUR", "yetiskin": 2, "cocuk": 1, "oda": 1,
             "giren_oda": 1, "giren_kisi": 3, "net_gelir": 1000.0},
        ]
        # Kanal
        assert payload["kanal_veriler"] == [
            {"satis_kanali": "Direkt", "oda": 1, "kisi": 3,
             "giren_oda": 1, "giren_kisi": 3, "net_gelir": 1000.0},
        ]

    async def test_multi_night_rate_distribution_uses_breakdown(self, fake_db):
        """Çok gece konaklamada gece başına gelir, ``nightly_breakdown``
        sayesinde her güne doğru miktarda dağıtılmalı.
        """
        fake_db.guests.docs = [_guest(id="g1", nationality="DE")]
        # 3 geceli: 01→04, breakdown: 100/200/300
        nb = {"2026-05-01": 100.0, "2026-05-02": 200.0, "2026-05-03": 300.0}
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-05-01T14:00:00+00:00",
                check_out="2026-05-04T11:00:00+00:00",
                guest_id="g1", adults=2, children=0,
                total_amount=600.0, nightly_breakdown=nb,
                source_channel="booking_com", status="checked_in",
            ),
        ]

        # 1 Mayıs (arrival + in-house) → 100
        p1 = await tga.build_daily_payload(TENANT, date(2026, 5, 1))
        assert p1["net_oda_geliri"] == 100.0
        assert p1["toplam_oda"] == 1
        assert p1["giren_oda"] == 1

        # 2 Mayıs (in-house, arrival değil) → 200
        p2 = await tga.build_daily_payload(TENANT, date(2026, 5, 2))
        assert p2["net_oda_geliri"] == 200.0
        assert p2["toplam_oda"] == 1
        assert p2["giren_oda"] == 0  # arrival değil
        assert p2["giren_kisi"] == 0
        assert p2["kanal_veriler"][0]["satis_kanali"] == "Online (Booking.com)"

        # 3 Mayıs (in-house, arrival değil) → 300
        p3 = await tga.build_daily_payload(TENANT, date(2026, 5, 3))
        assert p3["net_oda_geliri"] == 300.0

        # 4 Mayıs (departure günü) — totallere DAHİL DEĞİL
        p4 = await tga.build_daily_payload(TENANT, date(2026, 5, 4))
        assert p4["toplam_oda"] == 0
        assert p4["giren_oda"] == 0
        assert p4["net_oda_geliri"] == 0.0

    async def test_arrival_only_increments_giren(self, fake_db):
        """Aynı gün giren ama o anda saymak istediğimiz durumu verifiye eder:
        in-house ve arrival aynı sayaca dokunur, giren_kisi = adults+children.
        """
        target = date(2026, 6, 1)
        fake_db.guests.docs = [_guest(id="g1", nationality="GB")]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-06-01T15:00:00+00:00",
                check_out="2026-06-05T11:00:00+00:00",
                guest_id="g1", adults=1, children=2,
                total_amount=2000.0, source_channel="agency",
                status="confirmed",
            ),
        ]
        p = await tga.build_daily_payload(TENANT, target)
        assert p["giren_oda"] == 1
        assert p["giren_kisi"] == 3
        # 2000/4 gece = 500
        assert p["net_oda_geliri"] == 500.0
        assert p["kanal_veriler"][0]["satis_kanali"] == "Acenta"
        assert p["demografik_veriler"][0]["iso_kodu"] == "GBR"

    async def test_departure_day_excluded(self, fake_db):
        """Sadece o gün ÇIKAN bir rezervasyon: ne in-house ne arrival.
        TGA query whitelist'i + ``in_house`` = ci.date <= D < co.date kuralı
        gereği toplamlara katılmamalı.
        """
        target = date(2026, 7, 10)
        fake_db.guests.docs = [_guest(id="g1", nationality="FR")]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                # 2 gece kaldı, bugün çıkıyor
                check_in="2026-07-08T14:00:00+00:00",
                check_out="2026-07-10T11:00:00+00:00",
                guest_id="g1", adults=2, total_amount=800.0,
                status="checked_out",
            ),
        ]
        p = await tga.build_daily_payload(TENANT, target)
        assert p["toplam_oda"] == 0
        assert p["toplam_kisi"] == 0
        assert p["giren_oda"] == 0
        assert p["giren_kisi"] == 0
        assert p["net_oda_geliri"] == 0.0
        assert p["demografik_veriler"] == []
        assert p["kanal_veriler"] == []

    async def test_cancelled_and_no_show_excluded(self, fake_db):
        """``cancelled`` ve ``no_show`` statüleri TGA'ya kesinlikle gitmez —
        query whitelist'i (``confirmed``/``checked_in``/``checked_out``) bunu
        garanti eder. Aynı gün için aktif bir kayıt da olunca regresyon
        net şekilde görülür.
        """
        target = date(2026, 8, 15)
        fake_db.guests.docs = [
            _guest(id="g1", nationality="TR"),
            _guest(id="g2", nationality="TR"),
            _guest(id="g3", nationality="TR"),
        ]
        fake_db.bookings.docs = [
            # gerçek konaklama
            _booking(
                id="b1",
                check_in="2026-08-15T14:00:00+00:00",
                check_out="2026-08-16T11:00:00+00:00",
                guest_id="g1", adults=2, total_amount=500.0,
                status="checked_in",
            ),
            # iptal — gözükmemeli
            _booking(
                id="b2",
                check_in="2026-08-15T14:00:00+00:00",
                check_out="2026-08-16T11:00:00+00:00",
                guest_id="g2", adults=2, total_amount=999.0,
                status="cancelled",
            ),
            # no-show — gözükmemeli
            _booking(
                id="b3",
                check_in="2026-08-15T14:00:00+00:00",
                check_out="2026-08-16T11:00:00+00:00",
                guest_id="g3", adults=4, total_amount=999.0,
                status="no_show",
            ),
        ]
        p = await tga.build_daily_payload(TENANT, target)
        assert p["toplam_oda"] == 1
        assert p["toplam_kisi"] == 2
        assert p["giren_oda"] == 1
        assert p["giren_kisi"] == 2
        assert p["net_oda_geliri"] == 500.0

    async def test_unknown_country_uses_zzz(self, fake_db):
        """Bilinmeyen ülke kodu/ismi → demografi satırında ``ZZZ``."""
        target = date(2026, 9, 1)
        fake_db.guests.docs = [
            _guest(id="g1", nationality="Wakanda"),
            _guest(id="g2", nationality=None, country=None),
        ]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-09-01T14:00:00+00:00",
                check_out="2026-09-02T11:00:00+00:00",
                guest_id="g1", adults=1, total_amount=200.0,
                status="checked_in",
            ),
            _booking(
                id="b2",
                check_in="2026-09-01T14:00:00+00:00",
                check_out="2026-09-02T11:00:00+00:00",
                guest_id="g2", adults=1, total_amount=300.0,
                status="checked_in",
            ),
        ]
        p = await tga.build_daily_payload(TENANT, target)
        assert len(p["demografik_veriler"]) == 1
        row = p["demografik_veriler"][0]
        assert row["iso_kodu"] == "ZZZ"
        assert row["oda"] == 2
        assert row["yetiskin"] == 2
        assert row["net_gelir"] == 500.0

    async def test_rate_per_night_priority_in_payload(self, fake_db):
        """``nightly_breakdown`` yokken ``rate_per_night`` kullanılmalı,
        ``total_amount/nights`` fallback'ı ezilmemeli.
        """
        target = date(2026, 10, 5)
        fake_db.guests.docs = [_guest(id="g1", nationality="TR")]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-10-05T14:00:00+00:00",
                check_out="2026-10-08T11:00:00+00:00",  # 3 gece
                guest_id="g1", adults=2,
                total_amount=900.0,    # /3 = 300 → kullanılmamalı
                rate_per_night=450.0,  # tercih edilmeli
                status="checked_in",
            ),
        ]
        p = await tga.build_daily_payload(TENANT, target)
        assert p["net_oda_geliri"] == 450.0

    async def test_total_div_nights_fallback_in_payload(self, fake_db):
        """``nightly_breakdown`` ve ``rate_per_night`` yoksa
        ``total_amount/nights`` fallback'i devreye girer.
        """
        target = date(2026, 11, 2)  # 4 gece, 2.günü
        fake_db.guests.docs = [_guest(id="g1", nationality="TR")]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-11-01T14:00:00+00:00",
                check_out="2026-11-05T11:00:00+00:00",
                guest_id="g1", adults=2, total_amount=1200.0,  # /4 = 300
                status="checked_in",
            ),
        ]
        p = await tga.build_daily_payload(TENANT, target)
        assert p["net_oda_geliri"] == 300.0
