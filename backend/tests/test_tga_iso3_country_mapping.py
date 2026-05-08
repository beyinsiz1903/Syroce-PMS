"""ISO-3166-1 alpha-3 ülke kodu çözümleyici testleri.

Task #150: TGA gönderiminde misafir uyrukları ISO 3-harf koduna çevrilirken
yalnızca yaygın 50 küçük ülke kümesi tanımlıydı; eşleşmeyenler "ZZZ" olarak
gönderiliyordu. Bu test paketi, `pycountry` üzerine inşa edilen yeni
sözlüğün dünyadaki tüm ülkeleri ve Türkçe alias'ları doğru çözdüğünü ve
"ZZZ"'nin yalnızca gerçekten bilinmeyen / boş uyruk için kullanıldığını
doğrular.
"""
from __future__ import annotations

import pytest

from core.tga_outbound import ISO3_BY_KEY, _to_iso3


# ── Olumlu eşleşmeler: en az 20 farklı ülke girişi (görev kabul kriteri) ──
@pytest.mark.parametrize(
    "raw,expected",
    [
        # 2-harf ISO (alpha_2)
        ("TR", "TUR"),
        ("DE", "DEU"),
        ("fr", "FRA"),  # küçük harf
        ("BR", "BRA"),
        ("US", "USA"),
        ("KR", "KOR"),
        ("CN", "CHN"),
        ("JP", "JPN"),
        ("NL", "NLD"),
        ("AT", "AUT"),
        # 3-harf ISO (alpha_3) — passthrough
        ("TUR", "TUR"),
        ("DEU", "DEU"),
        # Türkçe isimler
        ("Türkiye", "TUR"),
        ("TURKIYE", "TUR"),
        ("Almanya", "DEU"),
        ("Fransa", "FRA"),
        ("Hollanda", "NLD"),
        ("Brezilya", "BRA"),
        ("Güney Kore", "KOR"),
        ("Çin", "CHN"),
        ("İsviçre", "CHE"),
        ("Birleşik Krallık", "GBR"),
        ("ABD", "USA"),
        ("Yunanistan", "GRC"),
        ("Rusya", "RUS"),
        # İngilizce isimler / aliaslar
        ("GERMANY", "DEU"),
        ("BRAZIL", "BRA"),
        ("Russian Federation", "RUS"),
        ("Russia", "RUS"),
        ("United Kingdom", "GBR"),
        ("United States", "USA"),
        ("England", "GBR"),
        ("South Korea", "KOR"),
        ("Vietnam", "VNM"),
        ("Taiwan", "TWN"),
        ("Hong Kong", "HKG"),
        # Yaygın kısaltmalar
        ("UK", "GBR"),
        ("USA", "USA"),
        ("U.S.A.", "USA"),
    ],
)
def test_to_iso3_resolves_known_countries(raw: str, expected: str) -> None:
    assert _to_iso3(raw) == expected


# ── Negatif yol: "ZZZ" yalnızca gerçekten bilinmeyen / boş için ──
@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "Atlantis", "XX", "QQ", "Wakanda", "ZZ"],
)
def test_to_iso3_returns_zzz_only_for_unknown(raw: str | None) -> None:
    assert _to_iso3(raw) == "ZZZ"


def test_to_iso3_does_not_return_zzz_for_real_countries() -> None:
    """Tüm pycountry ülkeleri (~249) ZZZ değil, kendi alpha_3'ünü döner."""
    import pycountry

    misses: list[str] = []
    for c in pycountry.countries:
        for attr in ("alpha_2", "alpha_3", "name"):
            v = getattr(c, attr, None)
            if not v:
                continue
            got = _to_iso3(v)
            if got != c.alpha_3:
                misses.append(f"{attr}={v!r} -> {got} (want {c.alpha_3})")
    assert not misses, f"{len(misses)} ülke yanlış çözüldü: {misses[:10]}"


def test_iso3_index_covers_full_world() -> None:
    """Sözlük en az ~240 ülke (alpha_2 sayısı) içermeli — eski 50'lik tablo değil."""
    # alpha_2 anahtarlarını sayıyoruz (her ülkenin kendi alpha_2'si tek)
    two_letter = {k for k in ISO3_BY_KEY if len(k) == 2 and k.isalpha()}
    assert len(two_letter) >= 240, (
        f"Sadece {len(two_letter)} alpha_2 anahtar bulundu; "
        "tüm dünya yüklenmemiş olabilir."
    )


def test_iso3_index_handles_recently_renamed_country() -> None:
    """Türkiye'nin BM'deki resmi adı 2022'de 'Turkey' → 'Türkiye' oldu;
    sözlük her iki yazılışı da kabul etmeli."""
    assert _to_iso3("Türkiye") == "TUR"
    assert _to_iso3("Turkey") == "TUR"
    assert _to_iso3("TURKIYE") == "TUR"


def test_iso3_whitespace_and_case_insensitive() -> None:
    assert _to_iso3("  tr  ") == "TUR"
    assert _to_iso3("Tr") == "TUR"
    assert _to_iso3("tR") == "TUR"


def test_iso3_full_turkish_name_coverage() -> None:
    """CLDR (babel) tüm 250+ ülke için Türkçe isim verir; her birinin
    `_to_iso3` ile doğru alpha_3'e çözüldüğünü doğrula.

    Bu, "tüm dünyanın Türkçe isimleri" kabul kriterinin sistematik
    (manuel alias değil, veri-destekli) garantisidir.
    """
    pycountry = pytest.importorskip("pycountry")
    babel = pytest.importorskip("babel")

    a2_to_a3 = {c.alpha_2: c.alpha_3 for c in pycountry.countries}
    tr_names = babel.Locale("tr").territories

    checked = 0
    misses: list[str] = []
    for code, tr_name in tr_names.items():
        if not (isinstance(code, str) and len(code) == 2 and code.isalpha()):
            continue
        a3 = a2_to_a3.get(code)
        if not a3:
            # CLDR'da olup pycountry'de olmayan (ör. eski/özel kodlar) atla
            continue
        got = _to_iso3(tr_name)
        if got != a3:
            misses.append(f"{code} {tr_name!r} -> {got} (want {a3})")
        checked += 1

    # CLDR ~250 ISO ülke için TR isim sağlar; en az 240'ı doğru çözülmeli
    assert checked >= 240, f"Yalnızca {checked} CLDR Türkçe isim test edildi"
    assert not misses, (
        f"{len(misses)} Türkçe isim yanlış çözüldü: {misses[:10]}"
    )


def test_iso3_diacritic_insensitive() -> None:
    """Diakritiksiz yazımlar (Cin, Isvicre, Almanca klavye olmadan girilen
    misafirler) da doğru çözülmeli."""
    assert _to_iso3("Cin") == "CHN"
    assert _to_iso3("Isvicre") == "CHE"
    assert _to_iso3("Turkiye") == "TUR"
    assert _to_iso3("Almanya") == "DEU"
