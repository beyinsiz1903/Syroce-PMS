# E2E #06 core-pms-flow — Çalıştırma Kanıtı

**Dosya:** `frontend/e2e/06-core-pms-flow.spec.js` (367 satır, 9 test)
**Yerel main commit:** `95106b41` (push bekliyor) + bu turun düzeltmeleri
**Düzeltme commit'i:** bu PR/checkpoint
**Tarih:** Mayıs 2026

## Çalıştırma komutu
```bash
cd frontend
E2E_BASE_URL="https://${REPLIT_DEV_DOMAIN}" \
E2E_API_URL="https://8000-${REPLIT_DEV_DOMAIN}" \
npx playwright test e2e/06-core-pms-flow.spec.js \
  --project=chromium-desktop --reporter=list
```

## Önceki tur (orijinal koşum, düzeltme öncesi)
- **Sonuç:** 8 PASS + 1 SKIP (test 9 UI smoke — auth state inject yetersizdi)
- **Süre:** ~18.3 sn
- **Komut çıktısı:** Replit workflow konsolunda — kalıcı CI artifact yok (yerel run)

## Bu turun düzeltmeleri (ChatGPT review)
1. **Test 8 URL fix:** `&include_completed=true` eklendi — yorumla URL artık eşleşiyor; checkout sonrası `checked_out` kayıt default listeden gizlense bile bulunur.
2. **Test 9 auth state güçlendirme:** `/auth/me` çağrısıyla `freshUser` + `tenant` çekilip `localStorage`'a yazılıyor (`user`, `tenant`, `token_ts`). Frontend `<ProtectedRoute>` artık tam state ile başlıyor → UI smoke artık daha güçlü kanıt sağlar (skip ihtimali azalır).

## Doğrulama prosedürü
Bu dosyayı tekrar koşturmak için:
```bash
cd frontend
npx playwright test e2e/06-core-pms-flow.spec.js \
  --project=chromium-desktop --reporter=list \
  --output=docs/e2e_runs/playwright-report
```
Çıktı `docs/e2e_runs/playwright-report/` altına HTML report olarak düşer; CI ortamında `--reporter=html` + artifact upload tercih edilir.

## Not
ChatGPT haklı: Repo dosyasından koşum çıktısı doğrulanamaz; CI entegrasyonu yapılana kadar her major düzeltmeden sonra bu Markdown güncellenmeli (komut + sonuç + tarih). Asıl CI hedefi: GitHub Actions workflow'u (`.github/workflows/e2e.yml`) — şu an yok, follow-up olarak değerlendirilmeli.
