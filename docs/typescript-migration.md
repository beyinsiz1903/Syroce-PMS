# TypeScript Migration Stratejisi (Frontend)

**Durum:** PLAN — implementasyon ayrı sprint  
**Hedef:** `frontend/src` JS → TS aşamalı geçiş, çalışan koddan ödün vermeden.  
**Kapsam dışı:** `mobile/` (Expo halihazırda TS), `backend/` (Python).

## Neden TS?

- Run-time tip hatalarının %15–25'ini compile-time'a çek (PMS gibi state-yoğun
  uygulamalarda en yüksek getiri reservation/folio/payment akışlarında).
- IDE refactor güvenliği (135+ sayfa, 200+ component için kritik).
- API contract (FastAPI Pydantic → OpenAPI → typed client) drift'ini engelle.
- `as const` + discriminated unions ile state machine'leri (booking statuses,
  payment methods, room states) güvenle modelle.

## Mevcut durum

- 0 `.ts/.tsx` dosyası (frontend tamamen JSX/JS).
- `vite-plugin-react` + Vite 8 ⇒ TS desteği yapılandırma bedeli ~5 dk.
- ESLint config flat-config; `@typescript-eslint` ekleme ile uyumlu.

## Aşamalı plan (5 sprint)

### Sprint T1 — Tooling kurulumu (1 gün)

- `yarn add -D typescript @types/react @types/react-dom @types/node`
- `tsconfig.json` (allowJs:true, checkJs:false, strict:false, noEmit:true,
  jsx:react-jsx, paths: `@/*` → `src/*`).
- `vite.config.js` `.ts` extension'ları otomatik resolve eder (zaten Vite native).
- ESLint: `@typescript-eslint/parser` + `plugin:@typescript-eslint/recommended`.
- CI: `yarn tsc --noEmit` adımı (warnings only ilk başta).
- **Çıktı**: TS build pipeline çalışır, 0 dosya migrate edilmiş.

### Sprint T2 — Yardımcılar + tipler (2-3 gün)

Önce **bağımsız, leaf** dosyalar (component değil, util/hook):

| Öncelik | Dosya | Sebep |
|---|---|---|
| P0 | `src/lib/dialogs.js` | Promise API kontratı; tip dışa açık |
| P0 | `src/lib/currency.js` | 80+ tüketici, formatCurrency signature |
| P0 | `src/lib/utils.js` | clsx + cn helpers |
| P1 | `src/config/axiosConfig.js` | Interceptor + retry types |
| P1 | `src/hooks/useAuth.jsx` | Auth context = en kritik tip |
| P1 | `src/context/NotificationContext.jsx` | Provider tipleri |

Bu sprint sonunda `src/types/` klasörü açılır:

- `src/types/api.ts` — Backend Pydantic'ten OpenAPI ile auto-gen
  (`openapi-typescript` runner CI step'i).
- `src/types/domain.ts` — Booking, Folio, Room, Guest, Payment unions.

### Sprint T3 — Hooks + Contexts (1 hafta)

`src/hooks/*.jsx` (~25 dosya) + `src/context/*.jsx` (~8 dosya). Her biri
bağımsız; PR başına 5-7 dosya.

- ⚠️ `useState` generic'leri zorla (`useState<Booking | null>(null)`).
- React Query `useQuery<TData, TError>` kullan.

### Sprint T4 — En kırılgan sayfalar (2-3 hafta)

**Triage kriteri**: Bug raporu sayısı + dosya boyutu + state karmaşıklığı.

İlk 10 hedef (örnek — gerçek liste retro'da netleşir):

1. `pages/calendar/ReservationCalendar.jsx` (~1500 satır, drag-drop state)
2. `pages/AIChatbot.jsx` (~800 satır, message state machine)
3. `pages/HousekeepingDashboard.jsx` (task state machine)
4. `pages/NightAuditDashboard.jsx` (audit lifecycle)
5. `pages/FinancialFolios.jsx` (folio + charges nested)
6. `pages/CashierModule.jsx` (payment methods, PCI-DSS)
7. `pages/calendar/components/BookingDetailDialog.jsx` (form state)
8. `pages/checkin/CheckinFlow.jsx` (multi-step wizard)
9. `pages/RoomMapPage.jsx` (room status grid)
10. `pages/PMSModule.jsx` (hub + lazy children)

PR başına 1-2 sayfa. Her PR `tsc --noEmit` clean kapısından geçer.

### Sprint T5 — Strict mode tedrici aç (1 hafta)

`tsconfig.json` adım adım sıkılaştır:

1. `noImplicitAny: true`
2. `strictNullChecks: true`
3. `strictFunctionTypes: true`
4. `noUncheckedIndexedAccess: true`
5. `strict: true` (toplu)

Her flag açılışından önce `tsc --noEmit` 0 hata olmalı.

## Risk + Karşı önlemler

| Risk | Önlem |
|---|---|
| Geniş scope, PR çakışması | Trunk-based; PR başına ≤7 dosya, daily merge |
| Runtime regresyon | Vitest unit + Playwright e2e (M1 yeni eklendi) gating |
| Tip "any" enflasyonu | ESLint `no-explicit-any: warn`; PR review'da bloke |
| OpenAPI drift | Backend CI'da `openapi.json` snapshot diff |
| react-hook-form generic karmaşası | `zodResolver<typeof schema>` pattern |

## Otomasyon yardımcıları

- `npx ts-migrate` (Airbnb) — `.jsx → .tsx` ile `// @ts-expect-error`
  dolgusu; manuel temizleme şart ama %60 zamandan kazandırır.
- `openapi-typescript backend/openapi.json -o src/types/api.ts` — backend
  schema değişiminde otomatik tip update.

## Bitti tanımı

- `frontend/src/**/*.{js,jsx}` = 0 dosya
- `tsc --noEmit` strict modda 0 hata
- CI'da `yarn typecheck` hard gate
- `pages/calendar/ReservationCalendar.tsx` + en kritik 10 sayfa explicit `Booking`
  / `Folio` / `Room` tipleri kullanır
- Bu doküman güncellenir + `digitalocean.md` Stack bölümü "TypeScript" ekler.

## Tahmin

- Tooling: 1 gün
- Util + hook + context: 2 hafta
- Sayfalar (~135): 6-8 hafta (paralel iki dev varsayımıyla)
- Strict mode finalize: 1 hafta
- **Toplam:** ~10 hafta, sürekli operasyonu bozmadan trunk üzerinde.
