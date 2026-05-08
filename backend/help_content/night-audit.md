# Gece Denetimi (Night Audit)

Night Audit, otel günününü kapatan kritik finansal süreçtir. Genellikle 02:00–04:00 arasında yapılır; bittikten sonra bir önceki gün **kilitlenir**.

## Amaçlar

- Tüm açık folio'ların kontrol edilmesi
- Geceleme oda ücretlerinin folio'lara yazılması (room posting)
- Konaklama / şehir vergisinin hesaplanıp eklenmesi
- Tahsilat / ödeme bakiyelerinin kasayla karşılaştırılması
- KBS bildirimlerinin tamamlandığının doğrulanması
- Gün özet raporlarının (doluluk, ADR, RevPAR, ciro) üretilmesi
- Sonraki gün için no-show / iptal kontrolü

## İş Akışı

1. **Night Audit Dashboard**'a girin.
2. **Kontrol Listesi (Audit Checklist)** üzerinde her madde işaretlenir:
   - Açık folio'ların listesi (bakiye varsa uyarı)
   - Bekleyen check-in'ler (no-show olarak işaretlenecek mi?)
   - Eksik KBS bildirimleri
   - Kasa farkı kontrolü
   - Vergi posting'i hazır mı
3. Tüm maddeler yeşilse **"Geceyi Kapat"** butonuna basın.
4. Sistem **tek transaction** içinde room posting + tax + raporu üretir, gün kilitlenir.

## N+1 Sorgu Optimizasyonu

Sistem night audit'te oda × misafir × adisyon kombinasyonlarını **`asyncio.gather` + bulk operations** ile paralel işler — tek bir döngüde sıralı veritabanı çağrısı yapılmaz. Büyük otellerde (200+ oda) tipik kapanış süresi < 30 saniye.

## Kilit Sonrası

- Kilitli güne ait folio'lar düzenlenemez (yalnızca yeni folio veya iptal/iade adisyonu eklenebilir).
- Geçmiş günlere yönelik düzeltme için **manuel revizyon** yetkisi (genellikle yalnızca GM) gerekir; her revizyon audit log'a yazılır.
- TÜİK ve konaklama vergisi raporları yalnızca **kilitli günlerden** üretilir.

## Sık Hatalar

- **"Açık folio var"**: çıkış yapmamış misafir veya açık adisyon. Önce check-out tamamlanmalı.
- **"Kasa farkı"**: kasiyer açık vardiyada. Vardiya kapatılıp ([Vardiya Devri](#/help/shift-handover)) tekrar denenmeli.
- **"KBS eksik"**: kimlik bilgisi eksik check-in. KBS modülünden tamamlanır.
