# Mobil, mobil web ve masaüstü özellik matrisi

Bu belge, mobil uygulamanın masaüstü PMS'in küçük bir kopyası olmadığını; vardiya
operasyonları için güvenli bir eşlikçi olduğunu açıklar. Yetkilendirme her zaman
backend'dedir; görünürlük yalnızca sunucunun kullanıcı bağlamıyla uyumlu bir UX
kararıdır.

| Alan | Native mobil | Mobil web | Masaüstü web | Sınır / not |
|---|---|---|---|---|
| Oturum açma ve yenileme | Var | Var | Var | Güvenli cihaz deposu yalnızca native'de |
| Şifre sıfırlama | E-posta bağlantısı + yeni şifre ekranı | Web sıfırlama akışı | Web sıfırlama akışı | İstek hesabın varlığını açıklamaz |
| Tesis bağlamı | Aktif tesis gösterilir | Aktif tesis | Çoklu tesis çalışma alanı | JWT tek tesislidir; native'de sahte geçiş yok |
| Ön büro / kat hizmetleri | Vardiya akışları | Desteklenir | Tam | Backend izinleri belirleyicidir |
| Finans raporu | Özet, tarih aralığı, ayrıntı verisi, OS paylaşımı | Özet | Tam raporlama / dışa aktarma | Paylaşım kullanıcı onayıyla yapılır |
| Kamera / hızlı kimlik | Native cihaz yeteneği | Tarayıcı iznine bağlı | Tarayıcıya bağlı | Hassas veri cihazda kalıcı tutulmaz |
| Push bildirim | Native | Tarayıcı desteğine bağlı | Tarayıcı desteğine bağlı | Cihaz kaydı oturum kapatırken silinir |
| Çevrimdışı kuyruk | Seçili operasyonlar | Sınırlı | Sınırlı | Finansal kapanış çevrimdışı yapılmaz |
| Hata izleme | PII'siz native olaylar | RUM | RUM + Sentry | Stack, gövde, token veya e-posta gönderilmez |
| Yönetim / kurulum | Bilgi ve yönlendirme | Kısmi | Tam | Çoklu tesis, rol ve entegrasyon ayarları webdedir |

## Ürün ilkeleri

1. Native mobil, yüksek frekanslı vardiya işlemlerini hızlandırır.
2. Finansal, yönetimsel ve çok tesisli kararlar masaüstü çalışma alanında kalır.
3. API izin hatası asla mobil görünürlük kontrolüyle telafi edilmez.
4. Her paylaşım ve dış uygulamaya aktarma, operatörün açık işletim sistemi onayıyla başlar.
