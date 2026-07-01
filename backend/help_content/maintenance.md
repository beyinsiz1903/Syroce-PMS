# Bakım İş Emirleri

Otel içindeki arıza, bakım ve onarım taleplerini takip eden modül.

## İş Emri Oluşturma

Üç yoldan iş emri açılabilir:

1. **Housekeeping** — temizlik sırasında arıza tespit edilirse
2. **Resepsiyon** — misafir şikâyeti üzerine
3. **Misafir** — oda QR kodundan ([Oda QR Talepleri](#/help/room-qr))

Zorunlu alanlar: lokasyon (oda no / ortak alan), kategori (elektrik, sıhhi tesisat, klima, mobilya, IT), öncelik (Düşük / Normal / Yüksek / Acil), açıklama, fotoğraf (opsiyonel).

## Atama ve Akış

- **Açık → Atandı → Devam Ediyor → Çözüldü → Onaylandı** durum makinesi
- Acil iş emirleri (kaçak su, elektrik kesintisi) ilgili teknisyene **anlık push bildirim** gönderir
- Çözülen iş emri supervisor onayı sonrası kapanır; oda OOO durumundaysa otomatik **satışa açılır**

## Önleyici Bakım (Preventive)

Tekrarlayan bakım planları (klima filtresi 3 ayda bir, jeneratör testi haftada 1) takvime bağlanır. Sistem bakım gününden 7 gün önce uyarır.

## Maliyet Takibi

Her iş emrine kullanılan **malzeme + işçilik** maliyeti girilebilir. Aylık raporda departman bazlı bakım masrafı görüntülenir.

## SLA İzleme

Önceliğe göre SLA (yanıt süresi) tanımlanır. Aşan iş emirleri kırmızı vurgulanır ve yöneticiye bildirim düşer.
