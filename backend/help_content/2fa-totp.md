# 2FA / TOTP Etkinleştirme

İki Faktörlü Doğrulama (2FA), şifre + telefonunuzdan 6 haneli zaman-bazlı kod (RFC 6238 TOTP) ile giriş yapma yöntemidir. Yetki seviyesi yüksek roller (GM, Muhasebe, Super Admin) için **zorunludur**.

## Etkinleştirme Adımları

1. Sağ üst kullanıcı menüsünden **Profilim > Güvenlik**'e girin.
2. **2FA Etkinleştir** butonuna basın.
3. Ekrandaki **QR kodu** Google Authenticator, Microsoft Authenticator, Authy veya 1Password ile tarayın.
4. Uygulamada görünen 6 haneli kodu sisteme girin → onay.
5. Sistem size **8 adet recovery code** verir; **bunları yazdırıp güvenli yerde saklayın**.
6. 2FA etkinleşir.

## Giriş

E-posta + şifre doğrulamasından sonra **6 haneli TOTP kodu** istenir. Kod 30 saniyede bir yenilenir.

## Recovery Code

Telefon kaybı veya değişikliği durumunda 8 recovery code'dan birini girerek tek seferlik giriş yapabilirsiniz. Her kullanılan code geçersiz olur. Bittikçe yeni set üretilir.

## Yöneticiler İçin

- **Yönetim > Kullanıcılar > [kullanıcı] > 2FA Sıfırla**: telefonunu kaybeden kullanıcıyı çözmek için yönetici 2FA'yı sıfırlayabilir; kullanıcı yeniden etkinleştirir.
- **Zorunlu 2FA Politikası**: belirli rollere "2FA olmadan girişe izin verme" politikası uygulanabilir.

## Güvenlik Notları

- TOTP cihazı senkron değilse (saat farkı) kod reddedilir; telefon saatini otomatik senkronize edin.
- Aynı kullanıcı için **aynı anda 2 cihazda** TOTP olamaz; ikinci cihaz eklenirse birinci geçersizleşir.
- Tüm 2FA olayları (etkinleştirme, sıfırlama, başarısız giriş denemeleri) **audit log**'a yazılır.

## Şifre Politikası

- Minimum 12 karakter
- En az 1 büyük harf, 1 sayı, 1 özel karakter
- Son 5 şifre tekrar kullanılamaz
- 90 günde bir zorunlu yenileme (yapılandırılabilir)
- 5 başarısız girişten sonra hesap **15 dk kilit** (üst üste denemelere karşı)
