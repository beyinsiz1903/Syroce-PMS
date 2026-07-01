# Kasa Açılış ve Kapanış

Kasa modülü, vardiya bazlı nakit ve kart hareketlerinin izlendiği yerdir. Her vardiya, açılış bakiyesi (devir) ile başlar ve kapanışta sayım yapılarak kapatılır.

## Vardiya açılışı

- Vardiyaya başlarken **açılış bakiyesi** (kasa devri) girilir.
- Açılış kaydı yapılmadan tahsilat işlenmez; sistem kapalı kasaya işlem almaz.
- Her kullanıcı kendi vardiyasından sorumludur; başka kullanıcının açık vardiyası devralınmaz.

## Gün içi hareketler

- Folio tahsilatları (nakit, kredi kartı, havale) otomatik olarak kasaya düşer.
- Manuel **kasa giriş/çıkış** (örn. avans, gider ödemesi) ayrı kalem olarak kaydedilir; açıklama zorunludur.
- Nakit ile kart hareketleri ayrı toplanır.

## Vardiya kapanışı

1. Fiziksel sayım yapılır (nakit, döviz, slip toplamları).
2. Sistem beklenen tutar ile sayılan tutarı karşılaştırır.
3. **Fark (kasa açığı/fazlası)** varsa not düşülür; kapanış kaydı bu farkla birlikte saklanır.

> Kapanış raporu, gün sonu (night audit) için temel girdidir. Sayım yapılmadan vardiya kapatılmamalıdır.

Bu içerik taslaktır; otelinizin kasa prosedürlerine göre operatör tarafından gözden geçirilmelidir.
