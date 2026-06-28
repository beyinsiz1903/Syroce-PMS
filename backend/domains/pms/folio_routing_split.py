"""
Folio Routing — Split Allocation Math (pure, no I/O)
====================================================
Kategori-bazli yonlendirme kurallarinda bir charge'i birden cok folyoya
oransal (percentage) veya esit (equal) bolerken kullanilan kurus-tam
(penny-accurate) dagitim matematigi. Saf fonksiyon: DB/IO yok, test edilebilir.

Kural: floor paylari integer kurus uzerinden hesaplanir; arta kalan kurus(lar)
deterministik olarak remainder_index'teki folyoya yazilir (cagiran taraf bunu
master/payor folyosu — sirket/acente/grup master — olarak secer, yoksa misafir
folyosu). Toplam HICBIR ZAMAN orijinal tutardan sapmaz.
"""

from __future__ import annotations


def split_kurus(total_kurus: int, weights: list[float], remainder_index: int) -> list[int]:
    """Toplam kurusu agirliklara gore integer floor paylarina boler; arta kalan
    kurusu remainder_index'teki paya ekler. sum(sonuc) == total_kurus daima.

    Agirliklar 2 ondalik hassasiyetle integer'a olceklenir; tum aritmetik
    integer'dir, boylece float drift kaynakli yanlis floor imkansizdir.
    """
    n = len(weights)
    if n == 0:
        return []
    if remainder_index < 0 or remainder_index >= n:
        remainder_index = 0
    total_kurus = int(total_kurus)
    int_weights = [int(round(w * 100)) for w in weights]
    total_weight = sum(int_weights)
    if total_weight <= 0:
        shares = [0] * n
        shares[remainder_index] = total_kurus
        return shares
    shares = [(total_kurus * w) // total_weight for w in int_weights]
    remainder = total_kurus - sum(shares)
    shares[remainder_index] += remainder
    return shares


def split_amount(total_amount: float, weights: list[float], remainder_index: int) -> list[float]:
    """split_kurus'un para (TL) cinsinden sarmalayicisi. Yuvarlamadan kaynakli
    sapma olmamasi icin hesap kurus uzerinden yapilir, sonra 2 ondaliga donulur.
    """
    total_kurus = int(round(total_amount * 100))
    return [round(s / 100.0, 2) for s in split_kurus(total_kurus, weights, remainder_index)]
