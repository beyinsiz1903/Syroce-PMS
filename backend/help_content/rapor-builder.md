# Özel Rapor Builder & Zamanlayıcı

Standart raporlar dışında kendi raporunuzu sürükle-bırak ile oluşturun ve düzenli aralıklarla otomatik üretin/dağıtın.

## Standart Raporlar

**Raporlar > Standart Raporlar** menüsünde:

- Doluluk (gün/hafta/ay/yıl)
- ADR — Average Daily Rate
- RevPAR — Revenue Per Available Room
- TRevPAR — Total Revenue Per Available Room
- GOPPAR — Gross Operating Profit Per Available Room
- Pickup raporu (rezervasyon hızı)
- Pace raporu (geleceğe yönelik tahmin)
- No-show / iptal trend
- Acente / şirket performansı
- Üretim kanalı dağılımı

## Özel Rapor Builder

**Raporlar > Rapor Builder**:

1. **Veri kaynağı seç**: rezervasyonlar, folio, ödemeler, housekeeping, vb.
2. **Sütunlar seç**: drag-drop ile gerekli alanları seç.
3. **Filtre uygula**: tarih aralığı, oda tipi, acente, ülke vb.
4. **Gruplama**: tarih, oda tipi, kanal vb. kombinasyonları.
5. **Toplama**: SUM, AVG, COUNT, MIN, MAX.
6. **Görselleştir**: tablo, çubuk grafik, çizgi grafik, pasta grafik.
7. **Kaydet**: rapor adı + paylaşım yetkisi (sadece ben / departman / herkes).

## Zamanlayıcı (Scheduler)

Kayıtlı raporları **otomatik** çalıştırın:

- **Sıklık**: günlük, haftalık (gün seçimi), aylık (gün seçimi)
- **Saat**: belirli saat (timezone)
- **Format**: PDF, Excel, CSV
- **Dağıtım**: e-posta listesi (alıcılar virgülle ayrı)

Çalışan zamanlamaların listesi, son çalışma zamanı ve durumu **Raporlar > Zamanlanmış Raporlar** ekranındadır.

## Mevzuat Raporları

Türkiye için zorunlu raporlar ayrı menüde:

- **KBS** ([detay](#/help/kbs-bildirim))
- **TÜİK Aylık** ([detay](#/help/tuik-anketi))
- **Konaklama Vergisi** ([detay](#/help/konaklama-vergisi))
- **Yıldız Sınıflama** ([detay](#/help/yildiz-siniflama))

## Gizlilik & Yetki

- PII içeren raporlar (misafir telefon, kimlik) yalnızca **yetkili roller** tarafından görüntülenebilir.
- Tüm rapor görüntülemeleri ve indirmeleri **audit log**'a yazılır ([detay](#/help/audit-log)).
