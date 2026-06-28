"""TGA Tesis Entegrasyon — Türkiye Turizm Tanıtım ve Geliştirme Ajansı.

Resmi API: POST https://tesis-entegrasyon.tga.gov.tr/otel-veri/
Doc:       https://tesis-entegrasyon.tga.gov.tr/docs

Akış:
  1. Tenant ayarları (`db.tenants.tga` sub-doc): `belge_no`, `vergi_no`,
     `api_key_enc` (core.crypto ile şifreli), `environment` (test|live),
     `enabled`. API anahtarı tesise özel TGA tarafından verilir.
  2. `build_daily_payload(tenant_id, date)` — bir günlük TGA payload'ı:
        toplam_oda, toplam_kisi (in-house),
        giren_oda, giren_kisi (o gün giren),
        net_oda_geliri,
        demografik_veriler[] — ISO 3-harf ülke × yetiskin/cocuk/oda/...,
        kanal_veriler[]      — satış kanalı (Direkt/Acenta/OTA/...) × oda/kişi/gelir.
     Sadece **fiili** konaklamalar (cancelled / no_show hariç).
  3. `send_batch(tenant_id, end_date, days=7)` — son N günü tek POST'ta
     TGA endpoint'ine gönderir; sonucu `integration_tga_outbox` koleksiyonuna
     yazar (status=sent|failed, retries, response).
  4. `safe_post_async` ile DNS-rebinding-safe outbound (SXI standardı).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.crypto import AADContext, get_crypto_service
from core.database import db

logger = logging.getLogger(__name__)

TGA_BASE_URL_LIVE = "https://tesis-entegrasyon.tga.gov.tr"
TGA_BASE_URL_TEST = os.environ.get("TGA_BASE_URL_TEST", "https://tesis-entegrasyon-test.tga.gov.tr")
TGA_PATH = "/otel-veri/"
HTTP_TIMEOUT_S = 30.0
OUTBOX_COLL = "integration_tga_outbox"

# ── Retry / backoff ─────────────────────────────────────────────────────────
# Failed outbox kayıtları exponential backoff ile yeniden gönderilir.
# Adımlar (saniye): 5dk, 15dk, 1sa, 4sa. Toplam ~5sa20dk; sonrasında 4sa
# aralıklarla 24 saat dolana kadar denenir, 24sa+ hâlâ başarısız ise
# alert (audit "TGA_DELIVERY_FAILED") yazılıp `failed_permanent`'e geçer.
RETRY_BACKOFF_STEPS: list[int] = [300, 900, 3600, 14400]
ALERT_THRESHOLD_SECONDS: int = 24 * 3600


def _next_backoff_seconds(retry_count: int) -> int:
    """`retry_count` = bu denemeden ÖNCE yapılan retry sayısı (0 ise hiç).

    Sıralı adımlardan birini döner; aşılırsa son adımı kullanır (4sa cap).
    """
    if retry_count < 0:
        retry_count = 0
    idx = min(retry_count, len(RETRY_BACKOFF_STEPS) - 1)
    return RETRY_BACKOFF_STEPS[idx]


# ── ISO 3-letter country mapping (TGA payload requires ISO-3166-1 alpha-3) ──
# Tam ISO-3166-1 sözlüğü `pycountry` üzerinden çözümlenir; aşağıdaki tablo
# yalnızca pycountry'nin tanımadığı yerel/halk dilindeki isimleri (Türkçe
# karşılıklar, "Russia" yerine resmi "Russian Federation" gibi farklılıklar,
# yaygın kısaltmalar) kapsar.
_ALIAS_OVERRIDES: dict[str, str] = {
    # ── Türkçe ülke isimleri (pycountry yalnızca İngilizce/resmi isimleri bilir) ──
    "TURKIYE": "TUR",
    "TÜRKİYE": "TUR",
    "TURKEY": "TUR",
    "ALMANYA": "DEU",
    "INGILTERE": "GBR",
    "İNGILTERE": "GBR",
    "ENGLAND": "GBR",
    "BIRLESIK KRALLIK": "GBR",
    "BİRLEŞİK KRALLIK": "GBR",
    "BIRLEŞIK KRALLIK": "GBR",
    "BIRLESIK KRALLİK": "GBR",
    "ABD": "USA",
    "AMERIKA": "USA",
    "AMERİKA": "USA",
    "AMERIKA BIRLESIK DEVLETLERI": "USA",
    "AMERİKA BİRLEŞİK DEVLETLERİ": "USA",
    "RUSYA": "RUS",
    "RUSSIA": "RUS",
    "FRANSA": "FRA",
    "HOLLANDA": "NLD",
    "ITALYA": "ITA",
    "İTALYA": "ITA",
    "BELCIKA": "BEL",
    "BELÇİKA": "BEL",
    "BELÇIKA": "BEL",
    "AVUSTURYA": "AUT",
    "ISVICRE": "CHE",
    "İSVİÇRE": "CHE",
    "İSVIÇRE": "CHE",
    "ISVEC": "SWE",
    "İSVEÇ": "SWE",
    "NORVEC": "NOR",
    "NORVEÇ": "NOR",
    "DANIMARKA": "DNK",
    "FINLANDIYA": "FIN",
    "FİNLANDİYA": "FIN",
    "IRLANDA": "IRL",
    "İRLANDA": "IRL",
    "YUNANISTAN": "GRC",
    "YUNANİSTAN": "GRC",
    "BULGARISTAN": "BGR",
    "BULGARİSTAN": "BGR",
    "ROMANYA": "ROU",
    "MACARISTAN": "HUN",
    "CEKYA": "CZE",
    "ÇEKYA": "CZE",
    "CEK CUMHURIYETI": "CZE",
    "ÇEK CUMHURİYETİ": "CZE",
    "SLOVAKYA": "SVK",
    "POLONYA": "POL",
    "UKRAYNA": "UKR",
    "ISPANYA": "ESP",
    "İSPANYA": "ESP",
    "PORTEKIZ": "PRT",
    "PORTEKİZ": "PRT",
    "ISRAIL": "ISR",
    "İSRAİL": "ISR",
    "SUUDI ARABISTAN": "SAU",
    "SUUDİ ARABİSTAN": "SAU",
    "BIRLESIK ARAP EMIRLIKLERI": "ARE",
    "BİRLEŞİK ARAP EMİRLİKLERİ": "ARE",
    "KATAR": "QAT",
    "KUVEYT": "KWT",
    "BAHREYN": "BHR",
    "UMMAN": "OMN",
    "JAPONYA": "JPN",
    "CIN": "CHN",
    "ÇİN": "CHN",
    "GUNEY KORE": "KOR",
    "GÜNEY KORE": "KOR",
    "SOUTH KOREA": "KOR",
    "KUZEY KORE": "PRK",
    "NORTH KOREA": "PRK",
    "HINDISTAN": "IND",
    "HİNDİSTAN": "IND",
    "AVUSTRALYA": "AUS",
    "YENI ZELANDA": "NZL",
    "YENİ ZELANDA": "NZL",
    "KANADA": "CAN",
    "BREZILYA": "BRA",
    "BREZİLYA": "BRA",
    "MEKSIKA": "MEX",
    "MEKSİKA": "MEX",
    "ARJANTIN": "ARG",
    "ARJANTİN": "ARG",
    "SILI": "CHL",
    "ŞİLİ": "CHL",
    "KOLOMBIYA": "COL",
    "KOLOMBİYA": "COL",
    "PERU": "PER",
    "VENEZUELA": "VEN",
    "AZERBAYCAN": "AZE",
    "GURCISTAN": "GEO",
    "GÜRCİSTAN": "GEO",
    "ERMENISTAN": "ARM",
    "ERMENİSTAN": "ARM",
    "KAZAKISTAN": "KAZ",
    "KAZAKİSTAN": "KAZ",
    "OZBEKISTAN": "UZB",
    "ÖZBEKİSTAN": "UZB",
    "TURKMENISTAN": "TKM",
    "TÜRKMENİSTAN": "TKM",
    "KIRGIZISTAN": "KGZ",
    "TACIKISTAN": "TJK",
    "TACİKİSTAN": "TJK",
    "MOGOLISTAN": "MNG",
    "MOĞOLİSTAN": "MNG",
    "TAYLAND": "THA",
    "VIETNAM": "VNM",
    "VİETNAM": "VNM",
    "ENDONEZYA": "IDN",
    "MALEZYA": "MYS",
    "FILIPINLER": "PHL",
    "FİLİPİNLER": "PHL",
    "SINGAPUR": "SGP",
    "SİNGAPUR": "SGP",
    "PAKISTAN": "PAK",
    "BANGLADES": "BGD",
    "BANGLADEŞ": "BGD",
    "SRI LANKA": "LKA",
    "NEPAL": "NPL",
    "AFGANISTAN": "AFG",
    "AFGANİSTAN": "AFG",
    "IRAN": "IRN",
    "İRAN": "IRN",
    "IRAK": "IRQ",
    "SURIYE": "SYR",
    "SURİYE": "SYR",
    "URDUN": "JOR",
    "ÜRDÜN": "JOR",
    "LUBNAN": "LBN",
    "LÜBNAN": "LBN",
    "FILISTIN": "PSE",
    "FİLİSTİN": "PSE",
    "PALESTINE": "PSE",
    "MISIR": "EGY",
    "MISİR": "EGY",
    "FAS": "MAR",
    "CEZAYIR": "DZA",
    "CEZAYİR": "DZA",
    "TUNUS": "TUN",
    "LIBYA": "LBY",
    "LİBYA": "LBY",
    "SUDAN": "SDN",
    "ETIYOPYA": "ETH",
    "ETİYOPYA": "ETH",
    "KENYA": "KEN",
    "TANZANYA": "TZA",
    "UGANDA": "UGA",
    "GUNEY AFRIKA": "ZAF",
    "GÜNEY AFRİKA": "ZAF",
    "NIJERYA": "NGA",
    "NİJERYA": "NGA",
    "GANA": "GHA",
    "SENEGAL": "SEN",
    "MAKEDONYA": "MKD",
    "KUZEY MAKEDONYA": "MKD",
    "SIRBISTAN": "SRB",
    "SİRBİSTAN": "SRB",
    "SERBIA": "SRB",
    "HIRVATISTAN": "HRV",
    "HİRVATİSTAN": "HRV",
    "SLOVENYA": "SVN",
    "BOSNA HERSEK": "BIH",
    "BOSNA-HERSEK": "BIH",
    "KARADAG": "MNE",
    "KARADAĞ": "MNE",
    "MONTENEGRO": "MNE",
    "ARNAVUTLUK": "ALB",
    "KOSOVA": "XKX",
    "KOSOVO": "XKX",
    "MOLDOVA": "MDA",
    "BELARUS": "BLR",
    "LITVANYA": "LTU",
    "LETONYA": "LVA",
    "ESTONYA": "EST",
    "IZLANDA": "ISL",
    "İZLANDA": "ISL",
    "MALTA": "MLT",
    "KIBRIS": "CYP",
    "GUNEY KIBRIS": "CYP",
    "GÜNEY KIBRIS": "CYP",
    "KKTC": "TUR",  # KKTC pasaportları TGA'da TR uyrukla raporlanır
    "LUKSEMBURG": "LUX",
    "LÜKSEMBURG": "LUX",
    "MONAKO": "MCO",
    "VATIKAN": "VAT",
    "VATİKAN": "VAT",
    "ANDORRA": "AND",
    "SAN MARINO": "SMR",
    "LIHTENSTAYN": "LIE",
    "LİHTENŞTAYN": "LIE",
    # Yaygın İngilizce kısaltma/alias'lar
    "USA": "USA",
    "U.S.": "USA",
    "U.S.A.": "USA",
    "UK": "GBR",
    "U.K.": "GBR",
    "GREAT BRITAIN": "GBR",
    "TAIWAN": "TWN",
    "HONG KONG": "HKG",
    "MACAU": "MAC",
    "BRUNEI": "BRN",
    "LAOS": "LAO",
    "BURMA": "MMR",
    "MYANMAR": "MMR",
    "IVORY COAST": "CIV",
    "CAPE VERDE": "CPV",
    "EAST TIMOR": "TLS",
    "VATICAN": "VAT",
    "HOLY SEE": "VAT",
    "CONGO": "COG",
    "DR CONGO": "COD",
    "DRC": "COD",
}


def _norm_variants(s: str) -> list[str]:
    """Bir ham ülke metni için makul arama anahtarları döner.

    Üretilen varyantlar:
      1. Boşlukları sıkıştırılmış default upper-case.
      2. Türkçe locale-aware upper varyantı (i→İ, ı→I).
      3. Dotless varyantı (İ→I, ı→i sonra upper).
      4. Diakritiksiz ASCII-fold edilmiş upper-case
         (örn. "Çin" → "CIN", "İsviçre" → "ISVICRE", "Côte d'Ivoire" → "COTE D'IVOIRE").
      5. Ek olarak noktalama temizlenmiş hâli (örn. "U.S.A." → "USA",
         "Côte d'Ivoire" → "COTE DIVOIRE").
    """
    import unicodedata

    base = " ".join(str(s).strip().split())
    if not base:
        return []
    folded = "".join(ch for ch in unicodedata.normalize("NFKD", base) if not unicodedata.combining(ch))
    raw = [
        base.upper(),
        base.replace("i", "İ").replace("ı", "I").upper(),
        base.replace("İ", "I").replace("ı", "i").upper(),
        folded.upper(),
    ]
    # Noktalama temizlenmiş ek varyant
    import re

    raw.append(re.sub(r"[^\w\s]", "", folded).upper())
    raw.append(re.sub(r"[^\w]", "", folded).upper())
    seen: set[str] = set()
    out: list[str] = []
    for v in raw:
        v = " ".join(v.split())
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _build_iso3_index() -> dict[str, str]:
    """Tüm ISO-3166-1 ülke kayıtları + CLDR Türkçe isimler + alias
    override'ları → arama indexi.

    Katmanlar (öncelik artan sırada — sonradan yazılanlar baskındır):
      1. ``pycountry``: alpha_2, alpha_3, İngilizce name/official/common.
      2. CLDR (``babel.Locale('tr')``): tam dünya Türkçe isimleri
         (~263 territory). Diakritiksiz ASCII-fold varyantı da indekslenir,
         böylece "Cin"/"Isvicre" gibi yazımlar da çözülür.
      3. ``_ALIAS_OVERRIDES``: halk dili kısaltmalar (UK/USA/Russia/Turkey…).
    """
    index: dict[str, str] = {}
    try:
        import pycountry  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - paket eksik kalırsa fallback
        logger.warning("[tga] pycountry not installed; only alias overrides active")
        pycountry = None  # type: ignore[assignment]
    else:
        for c in pycountry.countries:
            a3 = c.alpha_3
            for attr in ("alpha_2", "alpha_3", "name", "official_name", "common_name"):
                v = getattr(c, attr, None)
                if not v:
                    continue
                for key in _norm_variants(str(v)):
                    index[key] = a3

    # CLDR Türkçe ülke isimleri — 263 territory için tam kapsama
    try:
        from babel import Locale  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover
        logger.warning("[tga] babel not installed; Turkish CLDR names skipped")
    else:
        try:
            tr = Locale("tr").territories
            # alpha_2 → alpha_3 dönüşümü için pycountry indirect lookup
            a2_to_a3: dict[str, str] = {}
            if pycountry is not None:
                for c in pycountry.countries:
                    a2_to_a3[c.alpha_2] = c.alpha_3
            for code, name in tr.items():
                # Yalnızca ISO-3166-1 ülke kodları (2-harf, region birleşimleri değil)
                if not (isinstance(code, str) and len(code) == 2 and code.isalpha()):
                    continue
                a3 = a2_to_a3.get(code)
                if not a3:
                    continue
                for key in _norm_variants(name):
                    index.setdefault(key, a3)
        except Exception as exc:  # pragma: no cover
            logger.warning("[tga] babel CLDR territories load failed: %s", exc)

    # Override'lar pycountry/CLDR'ı geçersiz kılar (örn. KKTC→TUR, ABD→USA)
    for raw_key, a3 in _ALIAS_OVERRIDES.items():
        for key in _norm_variants(raw_key):
            index[key] = a3
    return index


# Geriye dönük uyumluluk: dış kod hâlâ `ISO3_BY_KEY` referansı kullanabilir.
ISO3_BY_KEY: dict[str, str] = _build_iso3_index()
_ISO3_VALUES: frozenset[str] = frozenset(ISO3_BY_KEY.values())


def _to_iso3(raw: str | None) -> str:
    """Ham ülke (TR / 'Türkiye' / 'GERMANY' / 'tr' …) → ISO-3166-1 alpha-3.

    Çözümleme sırası:
      1. Boş/None → ``ZZZ`` (gerçek bilinmeyen).
      2. Tam ISO-3166-1 sözlüğünden (pycountry) alpha_2/alpha_3/isim eşleşmesi.
      3. Türkçe ve halk dili alias'lar (`_ALIAS_OVERRIDES`).
      4. Hiçbiri eşleşmezse ``ZZZ``.
    """
    if not raw:
        return "ZZZ"
    s = str(raw).strip()
    if not s:
        return "ZZZ"
    for key in _norm_variants(s):
        hit = ISO3_BY_KEY.get(key)
        if hit:
            return hit
        # 3 harfli geçerli ISO3 doğrudan kabul (örn. mapping kapsamı dışı yeni kod)
        if len(key) == 3 and key.isalpha() and key in _ISO3_VALUES:
            return key
    return "ZZZ"


# ── Config (per tenant) ─────────────────────────────────────────────────────


def _aad(tenant_id: str) -> AADContext:
    return AADContext(
        tenant_id=tenant_id,
        provider="tga",
        environment=os.environ.get("APP_ENV", "development"),
        context_type="credential",
    )


async def get_tga_config(tenant_id: str, *, decrypt_api_key: bool = False) -> dict[str, Any]:
    """Tenant'ın TGA ayarları. `decrypt_api_key=False` → API key maskeli."""
    doc = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "tga": 1}) or {}
    cfg = (doc.get("tga") or {}) if isinstance(doc, dict) else {}
    out = {
        "belge_no": cfg.get("belge_no") or "",
        "vergi_no": cfg.get("vergi_no") or "",
        "environment": cfg.get("environment") or "test",
        "enabled": bool(cfg.get("enabled")),
        "api_key_set": bool(cfg.get("api_key_enc")),
        "updated_at": cfg.get("updated_at"),
    }
    if decrypt_api_key and cfg.get("api_key_enc"):
        try:
            svc = get_crypto_service()
            out["api_key"] = svc.decrypt(cfg["api_key_enc"], aad=_aad(tenant_id))
        except Exception as exc:
            logger.warning("[tga] api_key decrypt failed tenant=%s err=%s", tenant_id, exc)
            out["api_key"] = None
    return out


async def set_tga_config(
    tenant_id: str,
    *,
    belge_no: str | None = None,
    vergi_no: str | None = None,
    api_key: str | None = None,
    environment: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """TGA ayarlarını günceller. `api_key` boş/None → mevcut korunur."""
    cur = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "tga": 1}) or {}
    cfg = dict((cur.get("tga") or {}) if isinstance(cur, dict) else {})
    if belge_no is not None:
        cfg["belge_no"] = belge_no.strip()
    if vergi_no is not None:
        cfg["vergi_no"] = vergi_no.strip()
    if environment is not None:
        if environment not in ("test", "live"):
            raise ValueError("environment must be 'test' or 'live'")
        cfg["environment"] = environment
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if api_key:
        svc = get_crypto_service()
        cfg["api_key_enc"] = svc.encrypt(api_key.strip(), aad=_aad(tenant_id))
    cfg["updated_at"] = datetime.now(UTC).isoformat()
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"tga": cfg}})
    return await get_tga_config(tenant_id)


# ── Payload builder ─────────────────────────────────────────────────────────

# Internal channel → TGA "satis_kanali" eşlemesi.
_CHANNEL_LABEL = {
    "direct": "Direkt",
    "walk_in": "Walk-in",
    "agency": "Acenta",
    "booking_com": "Online (Booking.com)",
    "expedia": "Online (Expedia)",
    "airbnb": "Online (Airbnb)",
    "hotelrunner": "Online (HotelRunner)",
    "exely": "Online (Exely)",
    "ota": "Online",
}


def _channel_label(b: dict[str, Any]) -> str:
    raw = b.get("source_channel") or b.get("channel") or "direct"
    key = str(raw).strip().lower()
    return _CHANNEL_LABEL.get(key, key.title() or "Direkt")


async def _fetch_active_bookings(
    tenant_id: str,
    day_start: datetime,
    day_end: datetime,
) -> list[dict[str, Any]]:
    """O gün içinde gerçek konaklama olarak sayılan rezervasyonlar.

    Whitelist statü: ``confirmed`` (garantili rezervasyon), ``checked_in``
    (in-house) ve ``checked_out`` (o gün/önceki gün ayrılmış). ``pending``,
    ``hold/tentative``, ``cancelled``, ``no_show`` regülasyon raporuna
    DAHİL EDİLMEZ — fiili olmayan kayıtlar TGA'ya gönderilmemelidir.
    """
    cur = db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "checked_in", "checked_out"]},
            "check_in": {"$lt": day_end.isoformat()},
            "check_out": {"$gt": day_start.isoformat()},
        },
        {
            "_id": 0,
            "id": 1,
            "check_in": 1,
            "check_out": 1,
            "adults": 1,
            "children": 1,
            "total_amount": 1,
            "currency": 1,
            "source_channel": 1,
            "channel": 1,
            "guest_id": 1,
            "room_id": 1,
            "nightly_breakdown": 1,
            "rate_per_night": 1,
        },
    )
    return await cur.to_list(length=20000)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except Exception:
        return None


def _per_night_rate(b: dict[str, Any], target_date: date | None = None) -> float:
    """Bir rezervasyon için **belirtilen gece** net oda geliri.

    Öncelik sırası:
      1. ``nightly_breakdown[target_date]`` — varsa o gece için saklanmış
         spesifik tutar (değişken günlük fiyatlandırmada doğru dağıtım).
      2. ``rate_per_night`` — sabit gece tarifesi.
      3. ``total_amount / nights`` — fallback (eşit dağıtım).
    """
    ci = _parse_dt(b.get("check_in"))
    co = _parse_dt(b.get("check_out"))
    if not ci or not co:
        return 0.0
    nights = max(1, (co.date() - ci.date()).days)
    # 1) nightly_breakdown lookup
    nb = b.get("nightly_breakdown")
    if target_date is not None and isinstance(nb, (list, dict)):
        key = target_date.isoformat()
        try:
            if isinstance(nb, dict):
                v = nb.get(key)
                if v is not None:
                    return float(v)
            else:  # list of {date, amount} dicts
                for item in nb:
                    if not isinstance(item, dict):
                        continue
                    d = str(item.get("date") or item.get("night") or "")[:10]
                    if d == key:
                        amt = item.get("amount") or item.get("rate") or item.get("price")
                        if amt is not None:
                            return float(amt)
        except Exception:
            pass
    # 2) sabit gece tarifesi
    if b.get("rate_per_night"):
        try:
            return float(b["rate_per_night"])
        except Exception:
            pass
    # 3) eşit dağıtım fallback
    try:
        return float(b.get("total_amount") or 0.0) / nights
    except Exception:
        return 0.0


async def _guest_country_map(tenant_id: str, guest_ids: list[str]) -> dict[str, str]:
    """guest_id → nationality (raw). Tek sorgu."""
    if not guest_ids:
        return {}
    cur = db.guests.find(
        {"tenant_id": tenant_id, "id": {"$in": list(set(guest_ids))}},
        {"_id": 0, "id": 1, "nationality": 1, "country": 1},
    )
    out: dict[str, str] = {}
    async for g in cur:
        out[g["id"]] = g.get("nationality") or g.get("country") or ""
    return out


async def build_daily_payload(
    tenant_id: str,
    target_date: date,
    *,
    currency_default: str = "TRY",
) -> dict[str, Any]:
    """Bir günlük TGA payload bloğu (data[] içine konacak tek eleman)."""
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    bookings = await _fetch_active_bookings(tenant_id, day_start, day_end)
    guest_ids = [b["guest_id"] for b in bookings if b.get("guest_id")]
    countries = await _guest_country_map(tenant_id, guest_ids)

    # Toplamlar
    toplam_oda = 0
    toplam_kisi = 0
    giren_oda = 0
    giren_kisi = 0
    net_oda_geliri = 0.0

    # Demografi: iso3 → {yetiskin, cocuk, oda, giren_oda, giren_kisi, net_gelir}
    demo: dict[str, dict[str, float]] = defaultdict(lambda: {"yetiskin": 0, "cocuk": 0, "oda": 0, "giren_oda": 0, "giren_kisi": 0, "net_gelir": 0.0})
    # Kanal: label → {oda, kisi, giren_oda, giren_kisi, net_gelir}
    kanal: dict[str, dict[str, float]] = defaultdict(lambda: {"oda": 0, "kisi": 0, "giren_oda": 0, "giren_kisi": 0, "net_gelir": 0.0})

    for b in bookings:
        ci = _parse_dt(b.get("check_in"))
        co = _parse_dt(b.get("check_out"))
        if not ci or not co:
            continue
        adults = int(b.get("adults") or 1)
        children = int(b.get("children") or 0)
        kisi = adults + children
        rate = _per_night_rate(b, target_date)
        iso3 = _to_iso3(countries.get(b.get("guest_id") or "", ""))
        ch = _channel_label(b)

        # In-house (gece konaklayan): check_in <= day_start AND check_out > day_start
        in_house = ci.date() <= target_date < co.date()
        # O gün giren: check_in date == target_date
        is_arrival = ci.date() == target_date

        if in_house:
            toplam_oda += 1
            toplam_kisi += kisi
            net_oda_geliri += rate
            demo[iso3]["oda"] += 1
            demo[iso3]["yetiskin"] += adults
            demo[iso3]["cocuk"] += children
            demo[iso3]["net_gelir"] += rate
            kanal[ch]["oda"] += 1
            kanal[ch]["kisi"] += kisi
            kanal[ch]["net_gelir"] += rate
        if is_arrival:
            giren_oda += 1
            giren_kisi += kisi
            demo[iso3]["giren_oda"] += 1
            demo[iso3]["giren_kisi"] += kisi
            kanal[ch]["giren_oda"] += 1
            kanal[ch]["giren_kisi"] += kisi

    return {
        "rapor_tarihi": target_date.isoformat(),
        "para_birimi": currency_default,
        "toplam_oda": toplam_oda,
        "toplam_kisi": toplam_kisi,
        "giren_oda": giren_oda,
        "giren_kisi": giren_kisi,
        "net_oda_geliri": round(net_oda_geliri, 2),
        "demografik_veriler": [
            {
                "iso_kodu": iso,
                "yetiskin": int(v["yetiskin"]),
                "cocuk": int(v["cocuk"]),
                "oda": int(v["oda"]),
                "giren_oda": int(v["giren_oda"]),
                "giren_kisi": int(v["giren_kisi"]),
                "net_gelir": round(v["net_gelir"], 2),
            }
            for iso, v in sorted(demo.items())
        ],
        "kanal_veriler": [
            {
                "satis_kanali": k,
                "oda": int(v["oda"]),
                "kisi": int(v["kisi"]),
                "giren_oda": int(v["giren_oda"]),
                "giren_kisi": int(v["giren_kisi"]),
                "net_gelir": round(v["net_gelir"], 2),
            }
            for k, v in sorted(kanal.items())
        ],
    }


async def build_batch_envelope(
    tenant_id: str,
    end_date: date,
    *,
    days: int = 7,
) -> dict[str, Any]:
    """`days` gün geriye dönük TGA envelope (POST gövdesi)."""
    cfg = await get_tga_config(tenant_id)
    data: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        d = end_date - timedelta(days=i)
        data.append(await build_daily_payload(tenant_id, d))
    return {
        "tesis_belge_no": cfg["belge_no"],
        "vergi_no": cfg["vergi_no"],
        "data": data,
    }


# ── Sender (POST + outbox) ──────────────────────────────────────────────────


def _base_url(env: str) -> str:
    return TGA_BASE_URL_LIVE if env == "live" else TGA_BASE_URL_TEST


async def _post_envelope(cfg: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """TGA endpoint'ine tek POST. Sadece sonuç dict'i döner; outbox'a yazmaz.

    Çıktı alanları: ``status`` (sent|failed), opsiyonel ``http_status``,
    ``response_text``, ``error``.
    """
    url = f"{_base_url(cfg['environment']).rstrip('/')}{TGA_PATH}"
    headers = {"Content-Type": "application/json", "X-API-Key": cfg["api_key"]}
    # Lazy import — tests / CLI import bu modülü httpx olmadan da kullanabilsin.
    from integrations.xchange.safety import EgressDenied, safe_post_async

    try:
        r = await safe_post_async(url, timeout=HTTP_TIMEOUT_S, json=envelope, headers=headers)
        ok = 200 <= r.status_code < 300
        return {
            "status": "sent" if ok else "failed",
            "http_status": r.status_code,
            "response_text": (r.text or "")[:1000],
        }
    except EgressDenied as ed:
        return {"status": "failed", "error": f"egress_denied: {ed}"}
    except Exception as exc:  # network / timeout
        return {"status": "failed", "error": str(exc)[:500]}


async def send_batch(
    tenant_id: str,
    end_date: date,
    *,
    days: int = 7,
    triggered_by: str = "scheduler",
) -> dict[str, Any]:
    """Son `days` günü TGA'ya gönderir, sonucu outbox'a yazar.

    Başarısız olursa ``retry_count=0`` ve ``next_retry_at`` (ilk backoff
    adımı, varsayılan 5dk) ile kayıt yazılır; ``retry_failed_outbox`` bu
    kayıtları ilerleyen ticklerde tekrar dener.
    """
    cfg = await get_tga_config(tenant_id, decrypt_api_key=True)
    if not cfg.get("enabled"):
        return {"status": "skipped", "reason": "disabled"}
    if not cfg.get("api_key") or not cfg.get("belge_no") or not cfg.get("vergi_no"):
        return {"status": "skipped", "reason": "missing_config"}

    envelope = await build_batch_envelope(tenant_id, end_date, days=days)
    started_dt = datetime.now(UTC)
    started_at = started_dt.isoformat()

    out_doc: dict[str, Any] = {
        "tenant_id": tenant_id,
        "end_date": end_date.isoformat(),
        "days": days,
        "environment": cfg["environment"],
        "triggered_by": triggered_by,
        "started_at": started_at,
        "request_summary": {
            "tesis_belge_no": cfg["belge_no"],
            "rapor_tarihleri": [d["rapor_tarihi"] for d in envelope["data"]],
            "toplam_oda_sum": sum(d["toplam_oda"] for d in envelope["data"]),
            "net_oda_geliri_sum": round(sum(d["net_oda_geliri"] for d in envelope["data"]), 2),
        },
        "retry_count": 0,
        "next_retry_at": None,
    }

    result = await _post_envelope(cfg, envelope)
    finished_dt = datetime.now(UTC)
    out_doc.update(result)
    out_doc["finished_at"] = finished_dt.isoformat()

    if out_doc.get("status") == "failed":
        out_doc["first_failed_at"] = started_at
        out_doc["next_retry_at"] = (finished_dt + timedelta(seconds=_next_backoff_seconds(0))).isoformat()

    try:
        await db[OUTBOX_COLL].insert_one(out_doc)
    except Exception as exc:
        logger.warning("[tga] outbox insert failed tenant=%s err=%s", tenant_id, exc)

    out_doc.pop("_id", None)
    return out_doc


async def _emit_delivery_failed_alert(
    tenant_id: str,
    doc: dict[str, Any],
    age_seconds: float,
    attempts: int,
) -> None:
    """24 saat içinde başarılamayan gönderim için yönetici uyarısı.

    `audit_logs` koleksiyonuna ``TGA_DELIVERY_FAILED`` action'ı yazar; ayrıca
    tenant kapsamlı bir notification (varsa servis) ile yöneticilere ulaşır.
    """
    try:
        await db.audit_logs.insert_one(
            {
                "tenant_id": tenant_id,
                "user_id": "system",
                "user_name": "TGA Scheduler",
                "user_role": "system",
                "action": "TGA_DELIVERY_FAILED",
                "entity_type": "integration_tga",
                "entity_id": tenant_id,
                "changes": {
                    "outbox_id": str(doc.get("_id") or ""),
                    "end_date": doc.get("end_date"),
                    "days": doc.get("days"),
                    "retry_count": attempts,
                    "age_hours": round(age_seconds / 3600.0, 2),
                    "http_status": doc.get("http_status"),
                    "last_error": (doc.get("error") or doc.get("response_text") or "")[:500],
                    "environment": doc.get("environment"),
                },
                "ip_address": None,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    except Exception as exc:
        logger.warning("[tga] alert audit insert failed tenant=%s err=%s", tenant_id, exc)


async def retry_failed_outbox(*, max_docs: int = 200) -> dict[str, int]:
    """`status=failed` ve `next_retry_at <= now` olan kayıtları tekrar dener.

    İade: ``{"attempted": n, "succeeded": n, "failed": n, "alerted": n,
    "skipped": n}``. Her başarısız retry, ``retry_count``'u arttırır ve
    bir sonraki ``next_retry_at``'i exponential backoff ile günceller.
    24 saatten eski hâlâ başarısız kayıtlar ``failed_permanent``'e alınır
    ve yönetici uyarısı yazılır.
    """
    now = datetime.now(UTC)
    iso_now = now.isoformat()
    cur = (
        db[OUTBOX_COLL]
        .find(
            {
                "status": "failed",
                "next_retry_at": {"$ne": None, "$lte": iso_now},
            }
        )
        .sort("next_retry_at", 1)
        .limit(max_docs)
    )
    docs = await cur.to_list(length=max_docs)
    stats = {"attempted": 0, "succeeded": 0, "failed": 0, "alerted": 0, "skipped": 0}
    for doc in docs:
        stats["attempted"] += 1
        tenant_id = doc.get("tenant_id") or ""
        try:
            end_d = date.fromisoformat(str(doc.get("end_date") or "")[:10])
        except Exception:
            # Bozuk kayıt — tekrar denemeyi durdur.
            await db[OUTBOX_COLL].update_one(
                {"_id": doc["_id"]},
                {"$set": {"next_retry_at": None, "status": "failed_permanent", "error": "invalid_end_date"}},
            )
            stats["skipped"] += 1
            continue
        days = int(doc.get("days") or 7)

        # Config okuma transient bir nedenle (Mongo timeout, decrypt hatası,
        # vault erişilemez) başarısız olursa: retry'yi durdurma; bir
        # sonraki backoff'a ertele. Yalnızca tenant **kasten** disabled ise
        # ya da kalıcı eksik konfig (belge_no/vergi_no boş) varsa
        # `failed_skipped`'e al ve observability için audit yaz.
        try:
            cfg = await get_tga_config(tenant_id, decrypt_api_key=True)
            cfg_read_ok = True
        except Exception as exc:
            logger.warning("[tga-retry] config read failed tenant=%s err=%s", tenant_id, exc)
            cfg = {}
            cfg_read_ok = False

        intentionally_disabled = cfg_read_ok and (cfg.get("enabled") is False or not cfg.get("belge_no") or not cfg.get("vergi_no"))
        if intentionally_disabled:
            update = {"next_retry_at": None, "status": "failed_skipped", "last_retry_at": iso_now}
            await db[OUTBOX_COLL].update_one({"_id": doc["_id"]}, {"$set": update})
            # Observability — sessizce düşmesin.
            try:
                await db.audit_logs.insert_one(
                    {
                        "tenant_id": tenant_id,
                        "user_id": "system",
                        "user_name": "TGA Scheduler",
                        "user_role": "system",
                        "action": "TGA_DELIVERY_SKIPPED",
                        "entity_type": "integration_tga",
                        "entity_id": tenant_id,
                        "changes": {
                            "outbox_id": str(doc.get("_id") or ""),
                            "end_date": doc.get("end_date"),
                            "reason": "tenant_disabled_or_missing_config",
                        },
                        "ip_address": None,
                        "timestamp": iso_now,
                    }
                )
            except Exception as exc:
                logger.warning("[tga-retry] skipped-audit insert failed: %s", exc)
            stats["skipped"] += 1
            continue

        # Config okunamadı veya api_key transient olarak yok → retry'yi
        # durdurma; mevcut retry_count'a göre backoff ile yeniden planla.
        if (not cfg_read_ok) or not cfg.get("api_key"):
            new_count = int(doc.get("retry_count") or 0) + 1
            ffa_raw = doc.get("first_failed_at") or doc.get("started_at")
            ffa = _parse_dt(ffa_raw) or now
            age = (now - ffa).total_seconds()
            update = {
                "retry_count": new_count,
                "last_retry_at": iso_now,
                "error": ("config_unavailable" if not cfg_read_ok else "api_key_unavailable"),
            }
            if age >= ALERT_THRESHOLD_SECONDS:
                update["status"] = "failed_permanent"
                update["next_retry_at"] = None
                update["alerted_at"] = iso_now
                await db[OUTBOX_COLL].update_one({"_id": doc["_id"]}, {"$set": update})
                merged = {**doc, **update}
                await _emit_delivery_failed_alert(tenant_id, merged, age, new_count)
                stats["alerted"] += 1
            else:
                update["status"] = "failed"
                next_secs = _next_backoff_seconds(new_count)
                update["next_retry_at"] = (now + timedelta(seconds=next_secs)).isoformat()
                await db[OUTBOX_COLL].update_one({"_id": doc["_id"]}, {"$set": update})
                stats["failed"] += 1
            continue

        try:
            envelope = await build_batch_envelope(tenant_id, end_d, days=days)
            result = await _post_envelope(cfg, envelope)
        except Exception as exc:
            result = {"status": "failed", "error": f"build_or_post: {exc!s:.500}"}

        new_count = int(doc.get("retry_count") or 0) + 1
        ffa_raw = doc.get("first_failed_at") or doc.get("started_at")
        ffa = _parse_dt(ffa_raw) or now
        update: dict[str, Any] = {
            "retry_count": new_count,
            "last_retry_at": iso_now,
            "finished_at": iso_now,
            "http_status": result.get("http_status"),
            "response_text": result.get("response_text"),
            "error": result.get("error"),
        }

        if result.get("status") == "sent":
            update["status"] = "sent"
            update["next_retry_at"] = None
            update["error"] = None
            stats["succeeded"] += 1
            await db[OUTBOX_COLL].update_one({"_id": doc["_id"]}, {"$set": update})
            logger.info(
                "[tga-retry] tenant=%s end_date=%s attempt=%s -> sent",
                tenant_id,
                end_d.isoformat(),
                new_count,
            )
            continue

        age = (now - ffa).total_seconds()
        if age >= ALERT_THRESHOLD_SECONDS:
            update["status"] = "failed_permanent"
            update["next_retry_at"] = None
            update["alerted_at"] = iso_now
            await db[OUTBOX_COLL].update_one({"_id": doc["_id"]}, {"$set": update})
            # Outbox'taki güncellenmiş alanları kullanarak alert yaz.
            merged = {**doc, **update}
            await _emit_delivery_failed_alert(tenant_id, merged, age, new_count)
            stats["alerted"] += 1
            logger.warning(
                "[tga-retry] tenant=%s end_date=%s attempt=%s age=%.1fh -> alerted",
                tenant_id,
                end_d.isoformat(),
                new_count,
                age / 3600.0,
            )
            continue

        update["status"] = "failed"
        next_secs = _next_backoff_seconds(new_count)
        update["next_retry_at"] = (now + timedelta(seconds=next_secs)).isoformat()
        await db[OUTBOX_COLL].update_one({"_id": doc["_id"]}, {"$set": update})
        stats["failed"] += 1
        logger.info(
            "[tga-retry] tenant=%s end_date=%s attempt=%s -> failed, next in %ss",
            tenant_id,
            end_d.isoformat(),
            new_count,
            next_secs,
        )

    return stats


async def list_send_log(tenant_id: str, *, days: int = 30) -> list[dict[str, Any]]:
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    cur = (
        db[OUTBOX_COLL]
        .find(
            {"tenant_id": tenant_id, "started_at": {"$gte": since}},
            {"_id": 0},
        )
        .sort("started_at", -1)
        .limit(200)
    )
    return await cur.to_list(length=200)


async def ensure_indexes() -> None:
    try:
        await db[OUTBOX_COLL].create_index([("tenant_id", 1), ("started_at", -1)])
        await db[OUTBOX_COLL].create_index([("status", 1), ("started_at", -1)])
        # Retry worker bu indeksi kullanır.
        await db[OUTBOX_COLL].create_index([("status", 1), ("next_retry_at", 1)])
    except Exception as exc:
        logger.warning("[tga] index ensure failed: %s", exc)


async def list_enabled_tenants() -> list[str]:
    """Scheduler için: TGA gönderim aktif olan tenant kimlikleri."""
    cur = db.tenants.find(
        {"tga.enabled": True, "tga.api_key_enc": {"$exists": True, "$ne": None}, "tga.belge_no": {"$exists": True, "$ne": ""}, "tga.vergi_no": {"$exists": True, "$ne": ""}},
        {"_id": 0, "id": 1},
    )
    return [t["id"] async for t in cur if t.get("id")]
