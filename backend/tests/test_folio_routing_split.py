"""Targeted verification for Split-Billing penny-accurate allocation math.

Saf matematik (DB yok): split_kurus / split_amount kurus-tam dagitimi.
Kritik invariant: sum(paylar) == total daima; arta kalan kurus deterministik
olarak remainder_index'e gider; toplam orijinal tutardan asla sapmaz.
"""
from __future__ import annotations

from domains.pms.folio_routing_split import split_amount, split_kurus


def test_fifty_fifty_exact():
    assert split_kurus(10000, [50.0, 50.0], 0) == [5000, 5000]


def test_three_way_equal_remainder_to_index():
    # 100.00 / 3 = 33.33 / 33.33 / 33.34 (arta kalan 1 kurus son paya)
    assert split_kurus(10000, [1.0, 1.0, 1.0], 2) == [3333, 3333, 3334]
    # Arta kalan kurus ilk paya yonlendirilirse:
    assert split_kurus(10000, [1.0, 1.0, 1.0], 0) == [3334, 3333, 3333]


def test_percentage_thirds_sum_preserved():
    shares = split_kurus(10000, [33.33, 33.33, 33.34], 0)
    assert sum(shares) == 10000


def test_zero_weights_all_to_remainder():
    assert split_kurus(10000, [0.0, 0.0, 0.0], 1) == [0, 10000, 0]


def test_single_weight_gets_everything():
    assert split_kurus(7355, [100.0], 0) == [7355]


def test_penny_amount_three_way():
    # 0.01'in 3'e bolunmesi: iki sifir pay + 1 kurus remainder'a
    assert split_kurus(1, [1.0, 1.0, 1.0], 2) == [0, 0, 1]


def test_uneven_percentage_70_30():
    assert split_kurus(10000, [70.0, 30.0], 0) == [7000, 3000]
    # 9999: floor paylari [6999, 2999], arta kalan 1 kurus remainder_index=0'a.
    assert split_kurus(9999, [70.0, 30.0], 0) == [7000, 2999]
    # remainder_index=1 olunca arta kalan kurus ikinci paya gider.
    assert split_kurus(9999, [70.0, 30.0], 1) == [6999, 3000]


def test_remainder_index_out_of_range_falls_back_to_zero():
    assert split_kurus(10000, [1.0, 1.0, 1.0], 99) == [3334, 3333, 3333]


def test_empty_weights():
    assert split_kurus(10000, [], 0) == []


def test_sum_invariant_property_many():
    # Genis bir tutar/agirlik kombinasyonunda toplam daima korunur.
    for total in (1, 7, 99, 100, 12345, 999999):
        for weights in ([1.0, 1.0, 1.0], [50.0, 50.0], [33.33, 33.33, 33.34], [10.0, 20.0, 70.0]):
            for ri in range(len(weights)):
                shares = split_kurus(total, weights, ri)
                assert sum(shares) == total
                assert all(s >= 0 for s in shares)


def test_split_amount_wrapper_three_way():
    amounts = split_amount(100.00, [1.0, 1.0, 1.0], 2)
    assert amounts == [33.33, 33.33, 33.34]
    assert round(sum(amounts), 2) == 100.00


def test_split_amount_fifty_fifty():
    assert split_amount(100.00, [50.0, 50.0], 0) == [50.00, 50.00]
