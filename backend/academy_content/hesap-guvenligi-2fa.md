# Hesap Güvenliği ve 2FA

Personel hesapları otelin tüm operasyonel ve misafir verisine kapıdır; güvenliği kişisel sorumluluktur.

## Parola ve oturum

- Güçlü, paylaşılmayan parola kullanılır; parola sohbet/araçlara yazılmaz.
- Oturum token'ı kişiseldir; ortak cihazda iş bitince çıkış yapılır.
- Parola değişimi/şüpheli erişimde oturumlar geçersiz kılınabilir.

## İki adımlı doğrulama (2FA/TOTP)

- 2FA, paroladan sonra ek bir tek-kullanımlık kod ister (RFC 6238 TOTP).
- Yetkili/yönetici roller için 2FA güçlü tavsiye edilir.
- Kurtarma kodları güvenli saklanır.

## Rol ve yetki

- Her kullanıcı yalnızca rolünün izin verdiği ekranlara erişir (RBAC).
- Yetki dışı işlem sistemce reddedilir; bu güvenlik amaçlıdır, hata değildir.

> Phishing ve sosyal mühendisliğe dikkat: kimse parolanızı veya 2FA kodunuzu istemez. Şüpheli durumda yöneticiye bildirin.

Bu içerik taslaktır; operatör incelemesi gerekir.
