# Fatura, E-Arşiv ve Konaklama Vergisi

Konaklama tamamlandığında folio bakiyesi faturalandırılır. Sistem PDF fatura ve e-arşiv akışını destekler.

## Fatura kesimi

- Fatura, misafire veya anlaşmalı firmaya kesilebilir; firma faturasında **VKN/unvan** bilgisi kullanılır.
- Folio bakiyesi sıfırlanmadan (ödeme tamamlanmadan) checkout/fatura akışı uyarı verir.
- Düzenlenen fatura numarası tekildir ve geri alınamaz; iptal gerekiyorsa iade/iptal süreci işletilir.

## E-Arşiv / E-Fatura

- Mükellef tipine göre belge e-arşiv veya e-fatura olarak üretilir.
- Tedarikçi VKN ve gerekli yapılandırma eksikse sistem fail-closed davranır (yanlış belge üretmez).

## Konaklama Vergisi (Turizm/Konaklama Vergisi)

- Vergi, yapılandırmaya bağlı olarak konaklama tutarı üzerinden **otomatik** hesaplanır.
- Oran ve muafiyetler ayarlardan yönetilir; resepsiyon manuel oran girmez.
- Vergi ayrı bir kalem olarak folio ve faturada görünür.

> KDV (örn. yüzde 10/20) ile konaklama vergisi farklı kalemlerdir; ikisi ayrı satır olarak gösterilir.

Bu içerik taslaktır; mali mevzuat ve oranlar için otel muhasebesi ile teyit edilmelidir.
