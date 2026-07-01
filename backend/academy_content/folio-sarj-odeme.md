# Folio Şarj ve Ödeme Satırları

Folio, bir konaklama veya hesabın tüm mali hareketlerini tutar. İki tür satır vardır: **şarj** (borç) ve **ödeme** (tahsilat). Bakiye = şarj toplamı − ödeme toplamı.

## Şarj ekleme

- Konaklama (oda ücreti) gece denetimi sırasında otomatik işlenir.
- Ek hizmetler (mini bar, restoran, spa, çamaşır) ilgili modülden folio'ya aktarılır.
- Manuel şarj eklerken **tutar, açıklama ve şarj tipi** girilir.

## Ödeme alma

- Ödeme tipi seçilir: nakit, kredi kartı, havale, ödeme linki.
- Tahsilat folio bakiyesini düşürür ve aynı anda kasaya yansır.
- Kısmi ödeme mümkündür; kalan bakiye açık kalır.

## Folio işlemleri

| İşlem | Açıklama |
| --- | --- |
| Split | Folio'yu birden fazla hesaba böler (örn. firma + misafir) |
| Routing | Belirli şarjları başka bir folio'ya yönlendirir |
| Transfer | Şarj/ödeme satırını başka folio'ya taşır |

> Kapalı (checkout edilmiş) bir folio'ya yeni şarj/iade eklenemez; sistem fail-closed davranır. Düzeltme gerekirse void/iade yetkili kullanıcı tarafından yapılır.

Bu içerik taslaktır; operatör incelemesi gerekir.
