"""Walk-in / placeholder guest_name detection.

Bazi eski import/sync akislarinda guests koleksiyonuna `name="C4"`,
`name="V4 Refund"`, `name="X"` gibi anlamsiz placeholder isimler yazilmis
(email pattern: `walk-in-<id>@placeholder.local`). Bu helper, gosterim
katmaninda bu isimleri tespit edip kullaniciya `Misafir <SHORT_ID>` gibi
okunabilir bir fallback gosterir.

NOT: Veri silinmez — DB'deki orijinal name korunur. Sadece API response'unda
gosterilen `guest_name` override edilir. Veri temizligi ayri bir migration
ile yapilmalidir.
"""

from __future__ import annotations

import re

# Bilinen anlamsız placeholder kalipleri:
# - "refund" iceren: "V4 Refund", "Refund 1"
# - kisa kod (harf+rakam): "X", "XX", "C4", "C5", "V1", "V12"
# - sadece rakam: "1", "12"
# DIKKAT: "Ali", "Can", "Ece", "Joe" gibi 2-3 harfli GERCEK isimleri yanlislikla
# placeholder isaretlemiyoruz — sadece rakam iceren kisa kodlar veya tek-harf
# kombinasyonlari placeholder kabul edilir.
_REFUND_RE = re.compile(r"refund", re.IGNORECASE)
# Placeholder kaliplari:
#   - Tek harf: "X", "x"
#   - Harf+rakam: "C4", "V12", "X1", "AB23"
# Gercek 2-3 harfli isimler ("Ali", "Su", "Bo", "Ece", "XX") YANLISLIKLA
# placeholder isaretlenmesin diye 2+ harf-only string'leri kapsama almiyoruz.
_SHORT_CODE_RE = re.compile(r"^[A-Za-z]$|^[A-Za-z]{1,3}\d+$")
_DIGITS_ONLY_RE = re.compile(r"^\d+$")


def is_placeholder_guest_name(name: str | None) -> bool:
    """True ise verilen isim anlamsiz bir placeholder'dir."""
    if not name:
        return True
    n = name.strip()
    if not n:
        return True
    if _REFUND_RE.search(n):
        return True
    if _SHORT_CODE_RE.match(n):
        return True
    if _DIGITS_ONLY_RE.match(n):
        return True
    return False


def display_guest_name(raw_name: str | None, guest_id: str | None) -> str:
    """Gosterim icin kullanilacak ismi dondurur.

    - raw_name anlamli ise oldugu gibi dondurulur.
    - placeholder ise `Walk-in Misafir #XXXX` formatinda fallback (kisa, okunabilir).
    - guest_id da yoksa "Walk-in Misafir" dondurulur.
    """
    if raw_name and not is_placeholder_guest_name(raw_name):
        return raw_name.strip()
    if guest_id:
        # UUID'nin son 4 hex karakterini al — kisa, ayirt edici, gozu yormaz.
        # Tireleri at, son 4'u kullan: "5bad4a34-...-741b7375a9cf" -> "A9CF"
        clean = (guest_id or "").replace("-", "")
        suffix = clean[-4:].upper() if clean else ""
        return f"Walk-in Misafir #{suffix}" if suffix else "Walk-in Misafir"
    return "Walk-in Misafir"
