# Otel admini kullanıcı ekranı — 7 Eylül 2026

## Bulgu

Sunucu `POST /api/admin/users` ve `GET /api/admin/tenant-users` için otel
adminine zaten izin veriyordu. Fakat oluşturma düğmesi İK lisansına bağlı
Personel Yönetimi sayfasındaydı. İlk kurulum sihirbazı ise otel adminini
süperadmine özel `/admin/user-roles` sayfasına gönderiyordu. Bu global ekran
tüm otellerin kullanıcılarını ve süperadmin rol atamalarını yönetir;
otel adminine açılması doğru değildir.

## Düzeltme

- Sistem Yönetimi → Otel Kullanıcıları, `/admin/otel-kullanicilari`.
- İK aboneliği veya kullanıcı modül kapsamı gerektirmeyen hesap yönetimi
  giriş noktası. Menü yalnız admin/super_admin; sayfa ayrıca rol kontrolü
  yapıp yetkisiz kullanıcıda API isteği/oluşturma düğmesi göstermiyor.
- Mevcut tenant-sınırlı listeleme ve merkezi atomik kullanıcı oluşturma
  API'lerini kullanır. İstemciden tenant seçimi yapılmaz.
- İlk kurulumun ekip daveti doğru sayfaya yönlendirilir.
- Yenileme, arama, yükleme/hata durumları ve hesap değişince eski listenin
  kaldırılması. Ortak oluşturma düğmesi disabled parametresini uygular.
- Global liste/rol yönetimi süperadmine özel kalır. Paket bazlı atanabilir
  roller ve sunucu yetkileri genişletilmez. Mevcut kullanıcıların rolü veya
  otel aboneliği değiştirilmez.

Bu ekran kullanıcı listeleme ve oluşturma içindir. Mevcut hesapları silme,
rollerini değiştirme veya platform yetkileri verme bu değişiklikte yoktur.

## Testler

- FastAPI ASGI HTTP üzerinden admin listeleme/oluşturma, istemcinin farklı
  tenant göndermesinin etkisizliği, parola alanlarının listelenmemesi,
  yetkisiz rollerin reddi, süperadmin oluşturmanın reddi ve global uçların
  otel adminine gizli kalması. Veritabanı/şifreleme test doubles; üretim hesabı
  oluşturulmaz, e-posta gönderilmez.
- Mevcut provisioning birim testleri (paket/rol sınırları).
- Arayüz rol reddi, modülsüz admin erişimi, yalnız tenant listesi çağrısı,
  oluşturma sonrası yenileme, hata ve menü/route sınırları.
- Navigasyon ve moduleAccess regresyonları; production build, ESLint, Ruff.

Yeni ekran henüz canlı doğrulanmış değildir; merge/deploy sonrası otel admini
oturumunda ekran ve kontrollü test hesabı oluşturma doğrulanmalıdır.
