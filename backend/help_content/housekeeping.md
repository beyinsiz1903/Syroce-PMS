# Housekeeping (Kat Hizmetleri)

Oda durumlarını, kat görevlilerinin görevlerini ve oda hazırlık sürelerini yöneten modül.

## Oda Durumları

| Durum | Renk | Açıklama |
|-------|------|----------|
| **Temiz / Hazır** | yeşil | Misafir kabulüne hazır |
| **Kirli** | gri | Misafir çıkmış, temizlik bekliyor |
| **Temizlikte** | mavi | Görevli odada |
| **Denetim Bekliyor** | sarı | Temizlik bitti, supervisor onayı gerekli |
| **Bakım** | turuncu | Arıza / bakım nedeniyle satışa kapalı (bkz. [Bakım İş Emirleri](#/help/maintenance)) |
| **OOO (Out of Order)** | kırmızı | Tamamen devre dışı |

## Görev Atama

- **Housekeeping > Dashboard** ekranı tüm odaların durumunu kart/grid olarak gösterir.
- Supervisor, oda bazında **görevli ata** ile bir personeli seçer; mobil uygulamadan görevliye bildirim düşer.
- Akıllı dağıtım: sistem, kalan görevleri hız + uzaklık + departman dengeli olacak şekilde otomatik atayabilir.

## Kontrol Listesi

Her oda tipi için yapılandırılabilir checklist (yatak, banyo, mini bar sayım, amenities yenileme). Görevli her maddeyi mobil uygulamada işaretler.

## Mini Bar Tüketimi

Görevli mini bar sayımını yaparak eksik ürünleri seçer; sistem otomatik olarak misafir folio'suna adisyon ekler ([Folio Yönetimi](#/help/folio-yonetimi)).

## Kayıp Eşya

Temizlik sırasında bulunan eşyalar **Kayıp Eşya** modülüne kaydedilir (bkz. [Kayıp Eşya Yönetimi](#/help/lost-found)).

## Performans

- **Ortalama temizlik süresi** (oda tipi başına)
- **Görev tamamlama oranı** (vardiya başına)
- **Geri dönüş oranı** (denetim reddi)

verileri yöneticiye Housekeeping Dashboard'unda görünür.
