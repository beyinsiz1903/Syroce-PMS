# Vardiya Devri

Vardiyalar arasında nakit, açık görevler ve kritik notlar tek ekrandan devredilir.

## Devir Akışı

1. **Vardiya Devri** ekranını açın.
2. **Kasa sayımı**: nakit, kart slip, döviz nakdi tek tek girilir; sistem beklenen tutarla karşılaştırır.
3. **Açık görevler**: bekleyen check-in/out, yarım kalan rezervasyon notları, müşteri talepleri.
4. **Acil mesajlar**: VIP misafir notları, bakım sorunları, güvenlik olayları.
5. **Onayla**: devralan kullanıcı sayım ve notları gördükten sonra "Devir Aldım"a basar; her iki taraf da imzalamış sayılır.

## Kasa Farkı

- **Pozitif fark** (eksik): kasiyer açıklama girer, supervisor onayına düşer.
- **Negatif fark** (fazla): aynı şekilde belgelenir.
- Tekrar eden farklar kullanıcı bazlı **trend raporu**na yansır.

## Vardiya Raporu

Devir sonrası otomatik PDF rapor üretilir:

- Vardiya başlangıç/bitiş saati
- İşlem sayısı (check-in, check-out, ödeme, iptal)
- Toplam tahsilat (yöntem dağılımı)
- Açık kalan görevler

PDF supervisor'a e-posta ile gönderilir; **audit log**'a kaydedilir.

## İpuçları

- Vardiya kapatılmadan **night audit** başlamaz; gün sonu yaklaşmadan kasa kapanmalıdır.
- Resepsiyon birden fazla kullanıcı ortak çalışıyorsa **alt-kasa** açılabilir; her kullanıcı kendi alt-kasasını devreder.
