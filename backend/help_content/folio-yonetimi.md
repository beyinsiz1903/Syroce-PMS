# Folio ve Adisyon Yönetimi

**Folio**, bir misafirin konaklama süresi boyunca yapılan tüm harcamaların kaydedildiği hesaptır.

## Adisyon Türleri

- **Oda (ROOM)**: konaklama bedeli
- **Yiyecek-İçecek (F&B)**: restoran, bar, room service
- **Şehir Vergisi (CITY_TAX)**: konaklama vergisi
- **Diğer Hizmetler**: spa, çamaşırhane, transfer
- **Mini Bar**: oda içi tüketim

## Manuel Adisyon Ekleme

**Folio > Adisyon Ekle** ile manuel adisyon eklenebilir. Sistem her adisyona benzersiz id ve audit kaydı atar.

## Adisyon İptal (Void)

Hatalı eklenen adisyon iptal edilebilir; ancak **silinmez** — `voided: true` olarak işaretlenir, audit izi korunur. Sebep girilmesi zorunludur.

## Folio Bölme (Split)

Bir misafirin adisyonları birden çok folio'ya bölünebilir (örnek: kişisel harcama vs şirket faturası). **Folio > Böl** menüsünü kullanın.

## Folio Transferi

Bir adisyon başka folio'ya taşınabilir. Misafir başka odaya geçtiyse veya yanlış folio'ya yazılmışsa kullanılır.

## Faturalama

Check-out sırasında folio bakiyesi sıfır değilse uyarı çıkar. Bakiye tahsil edildikten sonra **e-Fatura** veya **e-Arşiv Fatura** otomatik kesilir; misafire e-posta ile gönderilir.

## İpuçları

- **Acente faturalı** rezervasyonlarda oda ücreti acente folio'sunda, ekstralar misafir folio'sunda toplanır.
- **Ön ödeme**: rezervasyon onayında alınan ön ödeme, check-in'de folio'ya transfer edilir.
