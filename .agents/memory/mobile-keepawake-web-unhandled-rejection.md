---
name: expo-keep-awake useKeepAwake() unhandled rejection on web
description: useKeepAwake() throws an uncaught pageerror in headless/background web; render-only smoke's zero-console-error gate then fails.
---

`useKeepAwake()` from `expo-keep-awake` calls `navigator.wakeLock.request('screen')`
on web. When the document is not visible (background tab) or in a headless browser
(CI Playwright smoke), that request rejects with **"Wake Lock permission request
denied"**. The library's `useKeepAwake` hook does NOT catch it, so it surfaces as an
**unhandled promise rejection → Playwright `pageerror`**. The mobile render-only smoke
asserts `consoleErrors.toHaveLength(0)`, so any guest screen using `useKeepAwake()`
(digitalKey, qrBadge, …) hard-fails the smoke — on CI/background only, never on a
real visible device.

**Rule:** never call the library `useKeepAwake()` directly in a screen that smoke
navigates. Use the web-safe wrapper `src/hooks/useKeepAwakeSafe.ts`, which activates
via `activateKeepAwakeAsync(tag).catch(()=>{})` and deactivates best-effort on cleanup.

**Why:** keep-awake is a best-effort enhancement; swallowing the wakeLock rejection
changes nothing functionally (screen just follows normal sleep timing) but keeps the
console clean so the smoke's strict zero-error gate stays meaningful. Catching it is a
genuine robustness win, not fake-green — an unhandled rejection would also reach Sentry
in production.

**How to apply:** any NEW screen wanting keep-awake imports `useKeepAwakeSafe` from
`src/hooks/`, not `useKeepAwake` from `expo-keep-awake`. If smoke shows a `pageerror`
"Wake Lock permission request denied", a screen reverted to the raw hook.
