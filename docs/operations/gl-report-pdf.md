# Genel muhasebe PDF çıktıları

Mizan, gelir tablosu, bilanço ve yevmiye PDF'leri Excel/JSON ile aynı `_export_rows` satırlarını kullanır. Finansal kayıtlara yazılmaz. Satırlar ve açıklamalar kesilmez; uzun kelimeler sütun içinde, gerektiğinde bir satır sonraki sayfaya devam ederek sarılır. Sütun başlıkları her sayfada tekrarlanır.

PDF, GL'nin TRY tutarlarını iki ondalıkla gösterir. USD/EUR tahsilatı doğrudan TRY sayılmaz: GL'de kayıtlı, önceden değerlenmiş tutar gösterilir. Dönem veya hesap tarihi ile para birimi sayfanın başında belirtilir.

## Yazı tipi gereksinimi

Üretim imajının mevcut `fonts-dejavu-core` paketi kullanılır:

- `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`
- `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`

İmaj dışı Linux kurulumunda bu paket ayrıca yüklenmelidir. Yerel macOS'ta sistemin Arial TTF dosyaları kullanılabilir. Uygun Unicode font bulunamazsa PDF 503 ile durur; Türkçe harfleri bozan Helvetica'ya sessiz geçiş yapılmaz. Excel çıktısı bundan etkilenmez.

## Kabul

26 Ekim 2026'da yalnız Demo Hotel'den indirilmiş JSON/Excel/PDF kanıtı üzerinde:

- Dört Excel: 16 mizan, 3 gelir tablosu, 14 bilanço ve 483 yevmiye satırı API ile birebir eşleşti.
- Eski yevmiye PDF'sinde sayfa dışında 1.829 kelime bulundu; eski PDF'lerde Türkçe glifler eksikti.
- Yeni yerel PDF çıktılarının bütün hücreleri aynı API satırlarıyla karşılaştırıldı. Yeni yevmiye 35 sayfa; 483 satırın tamamı ve iki ondalıklı tutarları korundu. Dört PDF'nin tüm kelimeleri sayfa sınırları içinde. İlk/son sayfalar görüntülenerek kontrol edildi.
- Bu yerel kabul, henüz yayınlanmamış değişikliğin canlı kabulü değildir. Yayın sonrası aynı filtrelerle dört PDF tekrar indirilip karşılaştırılmalıdır.

Regresyonlar uzun Türkçe metin, XML işareti, negatif/küsuratlı değer, eksik değer, sütun sayısı, Unicode font zorunluluğu ve çok sayfalı sarımı kapsar.
