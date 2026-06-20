# Adisyon Açma ve Sipariş

POS modülü restoran, bar ve diğer satış noktalarının (outlet) adisyonlarını yönetir.

## Adisyon açma

- Satış noktası (outlet) ve masa seçilerek adisyon açılır.
- Açık adisyon **"open" durumundadır**; üzerine sipariş eklenebilir.
- Misafir oda numarasıyla eşleştirilirse adisyon folio'ya bağlanabilir.

## Sipariş ekleme

- Menüden ürün seçilir, miktar girilir.
- Her kalem adisyona eklenir; ara toplam anlık güncellenir.
- İkram/iskonto yetkiye bağlıdır.

## Masa işlemleri

- **Masa transferi** yalnızca açık (open) adisyonlarda yapılır; adisyon başka masaya taşınır.
- Adisyon birleştirme/bölme satış noktası kurallarına göre yönetilir.

> Sipariş oluşturma idempotent ve atomiktir: aynı sipariş anahtarı tekrar gönderilirse kalem mükerrer işlenmez. Bu, çift tıklama/yeniden gönderimde çift adisyonu önler.

Bu içerik taslaktır; operatör incelemesi gerekir.
