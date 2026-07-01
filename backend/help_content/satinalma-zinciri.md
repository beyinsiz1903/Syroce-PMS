# Satın Alma Zinciri

Syroce PMS, **PR (Talep) → RFQ (Teklif İsteme) → PO (Sipariş) → GRN (Mal Kabul) → Stok Güncelleme** adımlarını uçtan uca takip eder.

## 1. Satın Alma Talebi (Purchase Request — PR)

Bir departman ihtiyacı oluştuğunda **Satın Alma > Talepler** ekranından yeni PR oluşturulur. Onay akışı tutara göre çalışır (örnek: 5.000 TL altı şef, üstü genel müdür onayı).

## 2. Teklif İsteme (RFQ)

Onaylı PR'lar için en az 3 tedarikçiden teklif istenebilir. Sistem yan yana karşılaştırma tablosu sunar.

## 3. Satın Alma Siparişi (Purchase Order — PO)

Tedarikçi seçimi yapıldıktan sonra PO açılır. PO PDF olarak indirilebilir veya tedarikçiye otomatik e-posta ile gönderilir.

## 4. Mal Kabul (Goods Received Note — GRN)

Mallar otele geldiğinde GRN oluşturulur:

- Sipariş edilen miktar gelmemişse **kısmi kabul** mümkündür.
- Sipariş edilenden fazla mal kabul edilmek istenirse sistem **422** ile reddeder.
- Aynı PO için **eşzamanlı GRN** denemelerinde MongoDB transaction snapshot izolasyonu devreye girer; başarısız çağrı **409 (WriteConflict)** alır ve kullanıcı tekrar dener.

## 5. Stok Güncellemesi

GRN onaylandıktan sonra ilgili depo stok seviyesi otomatik güncellenir. Stok hareketi audit log'a kayıt olur.

## Görünür Değişiklik Logu

Her PR/PO/GRN değişikliği **Entity History Drawer** (sağ kenardaki tarih ikonu) üzerinden zaman çizelgesi olarak görüntülenebilir; eski-yeni alan karşılaştırması (snapshot diff) sunulur.
