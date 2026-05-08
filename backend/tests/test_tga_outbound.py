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
        self.inserted: list[dict[str, Any]] = []
        self.insert_should_raise: Exception | None = None

    def find(self, query: dict[str, Any] | None = None,
             projection: dict[str, Any] | None = None) -> _FakeCursor:
        q = query or {}
        return _FakeCursor([d for d in self.docs if _matches(d, q)])

    async def find_one(self, query: dict[str, Any] | None = None,
                       projection: dict[str, Any] | None = None) -> dict[str, Any] | None:
        q = query or {}
        for d in self.docs:
            if _matches(d, q):
                return dict(d)
        return None

    async def insert_one(self, doc: dict[str, Any]):
        if self.insert_should_raise is not None:
            raise self.insert_should_raise
        self.inserted.append(doc)
        doc.setdefault("_id", f"oid-{len(self.inserted)}")

        class _Result:
            inserted_id = doc["_id"]
        return _Result()


class _FakeDB:
    def __init__(self):
        self.bookings = _FakeCollection()
        self.guests = _FakeCollection()
        self.tenants = _FakeCollection()
        self._extra: dict[str, _FakeCollection] = {}

    def __getitem__(self, name: str) -> _FakeCollection:
        # Allow ``db[OUTBOX_COLL]`` style access used by ``send_batch``.
        if name not in self._extra:
            self._extra[name] = _FakeCollection()
        return self._extra[name]


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


# ── Helpers for send_batch / envelope tests ─────────────────────────────────

class _FakeResponse:
    """``safe_post_async`` dönüş objesi için minimal yüzey
    (``status_code`` + ``text``).
    """
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def _seed_tenant(
    fake_db: _FakeDB,
    *,
    tenant_id: str = TENANT,
    enabled: bool = True,
    belge_no: str = "BLG-1",
    vergi_no: str = "VRG-1",
    api_key_enc: str | None = "ENC-KEY",
    environment: str = "test",
) -> None:
    """Tenants koleksiyonuna TGA config içeren bir tenant doc'u koyar.

    ``api_key_enc`` ham string'dir; ``get_tga_config`` decrypt'e
    girdiğinde ``_StubCrypto`` aynı string'i geri döner.
    """
    tga_cfg: dict[str, Any] = {
        "belge_no": belge_no,
        "vergi_no": vergi_no,
        "environment": environment,
        "enabled": enabled,
    }
    if api_key_enc is not None:
        tga_cfg["api_key_enc"] = api_key_enc
    fake_db.tenants.docs = [{"id": tenant_id, "tga": tga_cfg}]


class _StubCrypto:
    """``get_crypto_service`` yerine geçen stub: ``decrypt`` çağrısında
    ciphertext'i olduğu gibi geri verir; testler beklenen api_key'i
    bilebilsin diye.
    """
    def decrypt(self, ciphertext: str, *, aad: Any = None) -> str:  # noqa: ARG002
        return ciphertext


@pytest.fixture
def stub_crypto(monkeypatch):
    monkeypatch.setattr(tga, "get_crypto_service", lambda: _StubCrypto())


# ── Tests: build_batch_envelope ─────────────────────────────────────────────

class TestBuildBatchEnvelope:
    async def test_envelope_has_correct_day_count_and_summary_matches(
        self, fake_db, stub_crypto,
    ):
        """N günlük envelope:
          * ``data`` uzunluğu == ``days``
          * Tarihler artan sırada (en eski → en yeni = ``end_date``)
          * ``tesis_belge_no`` / ``vergi_no`` config ile eşleşir
          * ``request_summary`` toplamı (send_batch içinde hesaplanan)
            payload'lardaki ``toplam_oda`` ve ``net_oda_geliri`` ile
            birebir aynı.
        """
        _seed_tenant(fake_db, belge_no="BLG-XYZ", vergi_no="VRG-99")
        # 3 gün boyunca, her güne 1 farklı booking → toplam_oda toplamı = 3
        fake_db.guests.docs = [
            _guest(id="g1", nationality="TR"),
            _guest(id="g2", nationality="DE"),
            _guest(id="g3", nationality="GB"),
        ]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-05-08T14:00:00+00:00",
                check_out="2026-05-09T11:00:00+00:00",
                guest_id="g1", adults=2, total_amount=400.0,
                status="checked_in",
            ),
            _booking(
                id="b2",
                check_in="2026-05-09T14:00:00+00:00",
                check_out="2026-05-10T11:00:00+00:00",
                guest_id="g2", adults=2, total_amount=500.0,
                status="checked_in",
            ),
            _booking(
                id="b3",
                check_in="2026-05-10T14:00:00+00:00",
                check_out="2026-05-11T11:00:00+00:00",
                guest_id="g3", adults=1, total_amount=600.0,
                status="checked_in",
            ),
        ]

        env = await tga.build_batch_envelope(
            TENANT, date(2026, 5, 10), days=3,
        )

        assert env["tesis_belge_no"] == "BLG-XYZ"
        assert env["vergi_no"] == "VRG-99"
        assert len(env["data"]) == 3
        # Tarihler artan sırada; sonuncusu end_date'tir
        assert [d["rapor_tarihi"] for d in env["data"]] == [
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        # Toplamlar (send_batch'in request_summary'sinde kullanılan formül)
        assert sum(d["toplam_oda"] for d in env["data"]) == 3
        assert round(sum(d["net_oda_geliri"] for d in env["data"]), 2) == 1500.0

    async def test_envelope_default_days_is_seven(self, fake_db, stub_crypto):
        """Varsayılan ``days=7`` → tam 7 günlük tarih dizisi üretir,
        son eleman ``end_date`` olur.
        """
        _seed_tenant(fake_db)
        fake_db.guests.docs = []
        fake_db.bookings.docs = []
        env = await tga.build_batch_envelope(TENANT, date(2026, 5, 10))
        assert len(env["data"]) == 7
        assert env["data"][-1]["rapor_tarihi"] == "2026-05-10"
        assert env["data"][0]["rapor_tarihi"] == "2026-05-04"


# ── Tests: send_batch ───────────────────────────────────────────────────────

class TestSendBatch:
    async def test_skipped_when_disabled(self, fake_db, stub_crypto, monkeypatch):
        """``enabled=false`` ise ne POST atılır ne de outbox'a yazılır;
        sonuç ``status=skipped, reason=disabled`` döner.
        """
        _seed_tenant(fake_db, enabled=False)

        called = {"n": 0}

        async def _should_not_be_called(*a, **kw):  # pragma: no cover - guard
            called["n"] += 1
            raise AssertionError("safe_post_async must not be called when disabled")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _should_not_be_called)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=3)
        assert result == {"status": "skipped", "reason": "disabled"}
        assert called["n"] == 0
        # Outbox'a hiçbir şey yazılmamış olmalı
        assert fake_db[tga.OUTBOX_COLL].inserted == []

    async def test_skipped_when_missing_api_key(self, fake_db, stub_crypto, monkeypatch):
        """API anahtarı (api_key_enc) yoksa ``missing_config`` ile skip."""
        _seed_tenant(fake_db, api_key_enc=None)

        async def _should_not_be_called(*a, **kw):  # pragma: no cover - guard
            raise AssertionError("safe_post_async must not be called when api_key missing")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _should_not_be_called)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=2)
        assert result == {"status": "skipped", "reason": "missing_config"}
        assert fake_db[tga.OUTBOX_COLL].inserted == []

    async def test_skipped_when_missing_belge_no(self, fake_db, stub_crypto, monkeypatch):
        """``belge_no`` boşsa da ``missing_config`` ile skip — eksik
        regülasyon kimliği TGA'ya gönderilmemeli.
        """
        _seed_tenant(fake_db, belge_no="")

        async def _should_not_be_called(*a, **kw):  # pragma: no cover - guard
            raise AssertionError("safe_post_async must not be called")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _should_not_be_called)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=2)
        assert result["status"] == "skipped"
        assert result["reason"] == "missing_config"

    async def test_successful_post_writes_sent_outbox(
        self, fake_db, stub_crypto, monkeypatch,
    ):
        """200 dönen POST → outbox kaydı ``status=sent``, request_summary
        toplamları payload toplamlarıyla aynı, gerçek HTTP çağrısı yok.
        """
        _seed_tenant(fake_db, environment="test", api_key_enc="my-secret")
        fake_db.guests.docs = [_guest(id="g1", nationality="TR")]
        fake_db.bookings.docs = [
            _booking(
                id="b1",
                check_in="2026-05-09T14:00:00+00:00",
                check_out="2026-05-10T11:00:00+00:00",
                guest_id="g1", adults=2, total_amount=750.0,
                status="checked_in",
            ),
        ]

        captured: dict[str, Any] = {}

        async def _fake_post(url, *, timeout, json, headers):
            captured["url"] = url
            captured["timeout"] = timeout
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse(200, '{"ok":true}')

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _fake_post)

        result = await tga.send_batch(
            TENANT, date(2026, 5, 10), days=3, triggered_by="unit-test",
        )

        # Çağrı parametreleri
        assert captured["url"].endswith(tga.TGA_PATH)
        assert tga.TGA_BASE_URL_TEST in captured["url"]
        assert captured["headers"]["X-API-Key"] == "my-secret"
        assert captured["headers"]["Content-Type"] == "application/json"
        assert captured["timeout"] == tga.HTTP_TIMEOUT_S
        assert captured["json"]["tesis_belge_no"] == "BLG-1"
        assert len(captured["json"]["data"]) == 3

        # Sonuç
        assert result["status"] == "sent"
        assert result["http_status"] == 200
        assert result["response_text"] == '{"ok":true}'
        assert result["triggered_by"] == "unit-test"
        assert result["environment"] == "test"
        assert result["end_date"] == "2026-05-10"
        assert result["days"] == 3
        # request_summary toplamları payload toplamlarıyla bire bir eşleşmeli
        assert result["request_summary"]["tesis_belge_no"] == "BLG-1"
        assert result["request_summary"]["rapor_tarihleri"] == [
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        assert result["request_summary"]["toplam_oda_sum"] == sum(
            d["toplam_oda"] for d in captured["json"]["data"]
        )
        assert result["request_summary"]["net_oda_geliri_sum"] == round(
            sum(d["net_oda_geliri"] for d in captured["json"]["data"]), 2,
        )
        # 1 gece in-house, 750 TL → toplam 750
        assert result["request_summary"]["toplam_oda_sum"] == 1
        assert result["request_summary"]["net_oda_geliri_sum"] == 750.0

        # Outbox'a yazılmış olmalı (aynı doc, status=sent)
        outbox = fake_db[tga.OUTBOX_COLL].inserted
        assert len(outbox) == 1
        assert outbox[0]["status"] == "sent"
        assert outbox[0]["http_status"] == 200
        assert outbox[0]["tenant_id"] == TENANT

    async def test_http_5xx_marks_failed_and_writes_outbox(
        self, fake_db, stub_crypto, monkeypatch,
    ):
        """5xx yanıt → ``status=failed`` ama outbox kaydı yine de yazılır."""
        _seed_tenant(fake_db)
        fake_db.guests.docs = []
        fake_db.bookings.docs = []

        async def _fake_post(url, *, timeout, json, headers):
            return _FakeResponse(503, "service unavailable")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _fake_post)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=2)

        assert result["status"] == "failed"
        assert result["http_status"] == 503
        assert result["response_text"] == "service unavailable"
        assert "finished_at" in result
        # Outbox'a yazılmalı
        outbox = fake_db[tga.OUTBOX_COLL].inserted
        assert len(outbox) == 1
        assert outbox[0]["status"] == "failed"
        assert outbox[0]["http_status"] == 503

    async def test_egress_denied_marks_failed(
        self, fake_db, stub_crypto, monkeypatch,
    ):
        """``EgressDenied`` → ``status=failed`` ve ``error`` alanı
        ``egress_denied:`` ön ekiyle dolu olmalı; outbox'a yazılır.
        """
        _seed_tenant(fake_db)
        fake_db.guests.docs = []
        fake_db.bookings.docs = []

        from integrations.xchange import safety as _safety

        async def _fake_post(url, *, timeout, json, headers):
            raise _safety.EgressDenied("host not allowed: tesis-entegrasyon.tga.gov.tr")

        monkeypatch.setattr(_safety, "safe_post_async", _fake_post)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=2)

        assert result["status"] == "failed"
        assert "http_status" not in result
        assert result["error"].startswith("egress_denied:")
        assert "host not allowed" in result["error"]
        outbox = fake_db[tga.OUTBOX_COLL].inserted
        assert len(outbox) == 1
        assert outbox[0]["status"] == "failed"
        assert outbox[0]["error"].startswith("egress_denied:")

    async def test_generic_exception_marks_failed(
        self, fake_db, stub_crypto, monkeypatch,
    ):
        """Beklenmedik network hatası (ör. timeout) → ``status=failed`` ve
        ``error`` mesajı 500 char ile sınırlanır. Outbox kaydı yazılır.
        """
        _seed_tenant(fake_db)
        fake_db.guests.docs = []
        fake_db.bookings.docs = []

        async def _fake_post(url, *, timeout, json, headers):
            raise TimeoutError("read timeout after 30s")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _fake_post)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=1)
        assert result["status"] == "failed"
        assert result["error"] == "read timeout after 30s"
        outbox = fake_db[tga.OUTBOX_COLL].inserted
        assert len(outbox) == 1
        assert outbox[0]["status"] == "failed"

    async def test_live_environment_uses_live_base_url(
        self, fake_db, stub_crypto, monkeypatch,
    ):
        """``environment=live`` → POST URL'si LIVE base'i kullanır."""
        _seed_tenant(fake_db, environment="live")
        fake_db.guests.docs = []
        fake_db.bookings.docs = []

        captured: dict[str, Any] = {}

        async def _fake_post(url, *, timeout, json, headers):
            captured["url"] = url
            return _FakeResponse(200, "{}")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _fake_post)

        await tga.send_batch(TENANT, date(2026, 5, 10), days=1)
        assert captured["url"].startswith(tga.TGA_BASE_URL_LIVE)
        assert captured["url"].endswith(tga.TGA_PATH)

    async def test_outbox_insert_failure_does_not_break_caller(
        self, fake_db, stub_crypto, monkeypatch,
    ):
        """Outbox insert hata verirse bile ``send_batch`` çağrı sahibine
        sonucu döndürmeli — log'la geçilir, exception bubble etmez.
        """
        _seed_tenant(fake_db)
        fake_db.guests.docs = []
        fake_db.bookings.docs = []
        fake_db[tga.OUTBOX_COLL].insert_should_raise = RuntimeError("mongo down")

        async def _fake_post(url, *, timeout, json, headers):
            return _FakeResponse(200, "ok")

        from integrations.xchange import safety as _safety
        monkeypatch.setattr(_safety, "safe_post_async", _fake_post)

        result = await tga.send_batch(TENANT, date(2026, 5, 10), days=1)
        assert result["status"] == "sent"
        assert result["http_status"] == 200
        # Caller _id görmemeli
        assert "_id" not in result
