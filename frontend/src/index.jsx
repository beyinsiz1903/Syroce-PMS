import React from "react";
import ReactDOM from "react-dom/client";
import * as Sentry from "@sentry/react";
import "@/index.css";
import { initI18n } from "@/i18n";
import App from "@/App";

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
if (SENTRY_DSN) {
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
