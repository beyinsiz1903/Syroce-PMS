---
name: Pilot dirty-data deterministic 500s
description: Why a pilot-specific, recurring stress FAIL usually means dirty tenant data, not transient infra — and how compute endpoints must defend.
---

# Pilot kirli verisi → pilot'a özgü deterministik 500

Stres suite'inde bir FAIL **pilot token'a özgü** (stress token PASS) ve
**tekrarlıyorsa**, transient altyapı 500'ü DEĞİL, neredeyse her zaman pilot
tenant'taki kirli/legacy veridir. Sebep: stress seed verisi temiz ve tip-güvenli
üretilir (ör. `base_price>0` her zaman); pilot tenant ise elle/legacy girilmiş
bozuk kayıtlar taşır (ör. lowercase duplicate `room_type` "standard", `base_price`
= None / eksik anahtar / 0). Stress cleanup pilot'a dokunmadığı için aynı kayıt
her run'da aynı kod yolunu patlatır.

**Why:** Tenant verisi üzerinde aritmetik/aggregate yapan "compute" endpoint'leri
(pricing, occupancy, forecast, revenue) sayısal alanları doğrudan indeksleyip
çarpan/bölen olarak kullanır. None aritmetiği (TypeError) veya 0'a bölme
(ZeroDivisionError) unhandled 500 verir. Seed-only testler bunu asla görmez.

**How to apply:**
- Pilot'a özgü + tekrarlayan stres FAIL gördüğünde önce pilot veriyi read-only
  sorgula (tenant id'yi loglama), kirli alan ara — speculative-patch yapma.
- Compute handler'larında sayısal alanları savun: ilk geçerli (sayısal,
  non-bool, >0) değeri seç ya da fail-safe 0; bölmeden önce payda guard.
- `recommend-rates` örneği: base_rate'i ilk geçerli base_price'a düşür +
  difference_pct bölmesini `if base_rate else 0.0` ile koru. Benzer yollar:
  diğer ai/revenue compute endpoint'lerinde aynı pattern aranmalı.
- Residual dirty-data yolları (ör. eksik `room_type` KeyError) gerçek veride
  yoksa eklenmez (no speculative-patch); gerçekleşirse ayrı tur.
