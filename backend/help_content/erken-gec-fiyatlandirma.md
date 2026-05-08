# Erken Giriş / Geç Çıkış Fiyatlandırması

Standart check-in (varsayılan 14:00) ve check-out (varsayılan 12:00) saatleri dışında oda kullanımına saat-bazlı otomatik ek ücret kuralları.

## Yapılandırma

**Yönetim > Ayarlar > Erken Giriş / Geç Çıkış Ücretleri** ekranından:

- **Standart Giriş / Çıkış Saati** (0-23 arası tam saat)
- **Erken Giriş Kuralları** listesi
- **Geç Çıkış Kuralları** listesi

Her kural: **etiket**, **başlangıç saati**, **bitiş saati**, **ücret tipi**, **değer**.

## Ücret Tipleri

| Tip | Anlamı |
|-----|--------|
| **Sabit Tutar** | Sabit para birimi tutarı (örn. 800 TL) |
| **Gecelik %** | Gecelik oda ücretinin % kadarı |
| **Toplam %** | Konaklama toplamının % kadarı |
| **Ücretsiz** | Ek ücret uygulanmaz |

## Varsayılan Kurallar (Türkiye)

**Erken giriş**:
- 08:00 öncesi → 800 TL Sabit
- 08:00–12:00 → %50 Gecelik
- 12:00–14:00 → Ücretsiz

**Geç çıkış**:
- 12:00–14:00 → Ücretsiz
- 14:00–18:00 → %50 Gecelik
- 18:00 sonrası → %100 Gecelik

## Otomatik Uygulama

Check-in / check-out sırasında sistem misafirin **gerçek saatini** kurallarla eşleştirir; uygun kuraldan ek ücret folio'ya otomatik olarak adisyon olarak yazılır.

## Önemli Notlar

- Saat aralıklarında **çakışma veya boşluk olmamalı**; aksi takdirde kullanıcının görmediği saatler "ücretsiz" sayılır.
- `Bitiş Saati` aralığa **dâhil değildir** (`from <= saat < to`). Yani "18:00 sonrası" kuralı 18-23 ise saat 23'te çıkış için kural geçerli olmaz; uç değerleri dikkatli yapılandırın.
- Para birimi rezervasyonun para biriminden alınır (varsayılan TRY).
- Kural değişiklikleri **audit log**'a yazılır.

## Manuel Ek Ücret

Otomatik kural eşleşmezse veya yöneticinin takdiri gerekiyorsa **Folio > Adisyon Ekle** üzerinden manuel kalem girilebilir.
