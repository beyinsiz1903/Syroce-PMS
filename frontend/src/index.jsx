import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import { initI18n } from "@/i18n";
import App from "@/App";

// Sentry lazy: DSN yoksa hiç indirme; varsa render'ı bloklamadan arka planda
// idle'da yükle. Bu sayede @sentry/react (vendor-sentry ~84 KB gzip) entry
// modulepreload zincirinden çıkıyor → ilk paint hızlanır.
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
if (SENTRY_DSN) {
  const ric = (cb) =>
    typeof window !== "undefined" && typeof window.requestIdleCallback === "function"
      ? window.requestIdleCallback(cb, { timeout: 3000 })
      : setTimeout(cb, 1500);
  ric(() => {
    import("@sentry/react").then((Sentry) => {
      Sentry.init({
        dsn: SENTRY_DSN,
        environment: import.meta.env.MODE,
        integrations: [
          Sentry.browserTracingIntegration(),
          Sentry.replayIntegration({ maskAllText: true, blockAllMedia: true }),
        ],
        tracesSampleRate: import.meta.env.PROD ? 0.1 : 1.0,
        replaysSessionSampleRate: 0.0,
        replaysOnErrorSampleRate: 1.0,
        sendDefaultPii: false,
        // Stale-chunk hatalarını düşür: yeni deploy sonrası açık sekmenin eski
        // chunk'ları istemesi beklenen bir durumdur; index.html'deki self-heal
        // handler tek seferlik reload ile çözer. SADECE self-heal o anda bu
        // olayı ele alıyorsa (window.__syroceChunkHealing) düşürülür; reload
        // sonrası TEKRAR eden chunk hatası (= gerçekten bozuk deploy) latch'i
        // tetiklemediğinden raporlanır. Spesifik mesaj sınıfları (geniş substring
        // değil) — gerçek bir bundler/JS hatasını maskelemez.
        beforeSend(event, hint) {
          const CHUNK_ERR = [
            "Importing a module script failed",
            "Failed to fetch dynamically imported module",
            "error loading dynamically imported module",
            "is not a valid JavaScript MIME type",
            "Unable to preload CSS",
            // Resolved-but-invalid module (no default export) normalized by
            // lazyWithPreload.js — keep in sync with INVALID_CHUNK_MODULE_MSG.
            "Dynamically imported module is invalid",
          ];
          const ex = hint && hint.originalException;
          const msg =
            (ex && (ex.message || (typeof ex === "string" ? ex : ""))) ||
            event?.message ||
            event?.exception?.values?.[0]?.value ||
            "";
          const isChunk = msg && CHUNK_ERR.some((c) => msg.indexOf(c) !== -1);
          if (
            isChunk &&
            typeof window !== "undefined" &&
            window.__syroceChunkHealing
          ) {
            return null; // self-heal devrede: iyi huylu stale-tab olayı, düşür
          }
          return event;
        },
      });
    }).catch(() => { /* Sentry yüklenemezse uygulama yine çalışsın */ });
  });
}

if (import.meta.env.DEV) {
  const _origWarn = console.warn;
  console.warn = (...args) => {
    const msg = typeof args[0] === "string" ? args[0] : "";
    if (msg.includes("width(") && msg.includes("height(") && msg.includes("chart")) return;
    _origWarn.apply(console, args);
  };
}

// i18n init: kullanıcının dili + fallback indikten sonra render.
// Toplam ~280 KB JSON (gzip ~50 KB) iniyor; eski statik 1.4 MB yerine.
initI18n().finally(() => {
  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
