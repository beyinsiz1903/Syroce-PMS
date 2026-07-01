# Gün Sonu (Night Audit) Akışı

Gün sonu (night audit), bir operasyon gününü kapatıp ertesi güne devreden denetim sürecidir. Tutarlılığı ve mali doğruluğu sağlar.

## Temel adımlar

1. Tüm açık folio'lara **konaklama (oda) ücreti** işlenir.
2. Vergiler (konaklama vergisi, KDV) hesaplanır.
3. Kasa/vardiya kapanışları kontrol edilir.
4. Tarih ileri alınır (rollover); raporlar üretilir.

## Tutarlılık kontrolleri

- No-show ve geç gelişler işaretlenir; no-show terminal durumu korunur ve envanter kilidi serbest bırakılır.
- Açık adisyon/folio uyarıları gözden geçirilir.
- Oda ücreti dedup (tekilleştirme) ile çift işleme engellenir.

## Eş zamanlılık

- Gün sonu, aynı gün için yalnızca bir kez koşmalıdır; eş zamanlı çalıştırma kilit ile engellenir.
- Hata durumunda işlem kısmi başarısız bırakmaz; tutarlı tamamlanır veya geri alınır.

> Gün sonu çalışmadan günlük raporlar ve devir bakiyeleri güvenilir olmaz. Süreç her gün düzenli koşmalıdır.

Bu içerik taslaktır; operatör incelemesi gerekir.
