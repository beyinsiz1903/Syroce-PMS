# Kasa & POS (Cashier)

Tahsilat, iade, döviz bozma ve kasa sayım işlemlerinin merkezî modülü.

## Tahsilat Türleri

- **Nakit** (TL ve döviz — kur otomatik dönüştürülür)
- **Kredi Kartı** (POS entegrasyonu — terminal seçilir)
- **Banka Transferi / Havale** (manuel referans)
- **Çek** (vade tarihi)
- **Online ödeme linki** (e-posta/SMS ile gönderilir)

## PCI-DSS Uyum

- **Kart numarası tam (PAN) hiçbir yerde saklanmaz**; yalnızca son 4 hane ve token tutulur (PCI-DSS v4.0).
- POS entegrasyonu **tokenization** ile çalışır; ham kart bilgisi sistem üzerinden geçmez.
- Loglar **maskelenir** (örn. `4123****5678`).

## İade

- **Tam iade** veya **kısmi iade** desteklenir.
- Kart işlemi orijinal işlem ID'siyle iadelendirilir (chargeback koruması).
- Her iade kayıt sebebi ve yetkili kullanıcı imzasıyla **audit log**'a yazılır.

## Döviz Bozma

Misafire döviz bozma hizmeti verilebilir. Günlük kur **TCMB**'den otomatik çekilir; otel komisyonu yapılandırılabilir. Bozulan döviz envanteri kasa sayımında ayrı satırdadır.

## Kasa Sayım & Vardiya

Vardiya sonunda **Vardiya Devri** ekranından kasa sayımı yapılır (bkz. [Vardiya Devri](#/help/shift-handover)). Beklenen vs sayılan farkı sistem otomatik hesaplar; fark açıklaması zorunludur.

## Çoklu Kasa

Bir resepsiyonda birden fazla kasiyer varsa her biri kendi **alt-kasası**nı yönetir. GM seviyesinde tüm alt-kasalar tek dashboard'da görüntülenir.

## Raporlar

- Günlük kasa raporu (yöntem × tutar)
- Aylık tahsilat dağılımı
- Kasiyer performansı (işlem sayısı, fark trendi)
