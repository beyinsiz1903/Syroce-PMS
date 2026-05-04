# Syroce PMS Mobil (MVP)

Expo + React Native + TypeScript ile Syroce PMS'in resmi mobil istemcisi.

## Kurulum

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL="https://<replit-dev-domain>" npx expo start
```

`EXPO_PUBLIC_API_URL` arka uç (FastAPI, port 8000) için temel URL. Yerel geliştirmede Replit dev domain'ini kullanın; backend `/api/...` ön ekiyle yanıt verir.

Quick-ID servisi varsayılan olarak aynı host üzerinde port `8099`'da beklenir; özelleştirmek için `EXPO_PUBLIC_QUICKID_URL` ortam değişkenini ayarlayın.

## Demo

- `info@syroce.com` / `Syroce2026`

## MVP Kapsamı

- JWT login + secure-store oturum
- Role-based tab navigation (front_desk, housekeeping, gm, guest_app)
- Resepsiyon "Bugün" — bugünkü check-in / check-out, walk-in FAB, no-show riski
- Hızlı check-in (QR + kimlik tarama → Quick-ID → guest oluşturma → check-in)
- Hızlı check-out (folio + ödeme + paylaşım)
- Walk-in 30 sn akış
- Misafir arama + profil (VIP, kara liste rozetleri)
- Kat hizmetleri oda listesi, kat filtresi, uzun bas → durum değiştir

Karanlık mod ve Türkçe arayüz desteklenir; emoji kullanılmaz.
