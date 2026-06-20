# Adisyon Kapanış ve Folio Aktarımı

Sipariş tamamlandığında adisyon kapatılır ve ödeme alınır ya da oda folio'suna aktarılır.

## Kapanış

- Adisyon kapatıldığında işlem **"completed" durumuna** geçer ve POS satış kaydı oluşur.
- Kapalı adisyona yeni kalem eklenemez.

## Ödeme yöntemi

- Nakit/kart ile yerinde tahsilat yapılabilir.
- Veya tutar misafirin **oda folio'suna** aktarılır (room charge); bu durumda ödeme checkout'ta alınır.
- Folio aktarımında adisyon, ilgili rezervasyonun folio_id ve booking bilgisine bağlanır.

## Önemli noktalar

- Adisyon kapanışı **stoğu otomatik düşürmez**; stok hareketi mal kabul/sayım ile yönetilir.
- Oda folio'suna aktarım için geçerli ve açık bir konaklama gerekir; kapalı folio aktarımı reddeder.

> Yanlış odaya aktarımı önlemek için oda/misafir eşleşmesi kapanıştan önce doğrulanmalıdır.

Bu içerik taslaktır; operatör incelemesi gerekir.
