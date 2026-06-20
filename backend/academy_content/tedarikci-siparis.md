# Tedarikçi ve Satınalma Siparişi

Satınalma modülü, tedarikçi yönetimi ve satınalma siparişi (PO) süreçlerini kapsar.

## Tedarikçi yönetimi

- Tedarikçide **unvan, VKN, iletişim ve ödeme koşulları** tutulur.
- Aktif/pasif durumu yönetilir; pasif tedarikçiye yeni sipariş açılamaz.

## Satınalma siparişi (PO)

1. İhtiyaç belirlenir; ürün/kalem ve miktar girilir.
2. Tedarikçi ve birim fiyat seçilir; sipariş toplamı hesaplanır.
3. Sipariş **onay akışına** girer; onaysız sipariş tedarikçiye gönderilmez.

## Onay ve durum

| Durum | Anlamı |
| --- | --- |
| Taslak | Henüz onaya gönderilmedi |
| Onay bekliyor | Yetkili onayı bekleniyor |
| Onaylandı | Mal kabule hazır |
| Kapandı | Mal kabul tamamlandı |

> Onay yetkisi role bağlıdır. Yetkisiz kullanıcı siparişi onaylayamaz; sistem fail-closed davranır.

Bu içerik taslaktır; operatör incelemesi gerekir.
