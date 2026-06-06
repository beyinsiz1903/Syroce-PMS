---
name: Expo Web secure-store is an empty native module
description: Why Expo-Web login hangs at post-login redirect, and the platform-split storage fix
---

On Expo Web, `expo-secure-store`'s native module is empty (`node_modules/expo-secure-store/build/ExpoSecureStore.web.js` is literally `export default {}`). So `SecureStore.setItemAsync/getItemAsync/deleteItemAsync` call an `undefined` method (`setValueWithKeyAsync`, etc.) and **throw a TypeError on web** — they do NOT no-op.

Symptom this caused: the F10 Expo-Web Playwright smoke hung at `page.waitForURL` (post-login redirect) for ALL roles, ~32s each. The login API itself returned HTTP 200 with a valid token (creds/tenant fine) — the failure was purely client-side token-persist: `login()` -> `setToken()` throws -> `apiLogin` throws -> `authStore.login` catch never sets the in-memory `user` -> `AuthGate` (redirects off zustand `user`) never navigates.

**Why a throw (not no-op) is provable from the symptom:** if web `setItemAsync` silently no-opped, login would set `user` and redirect (test would pass the login step). It timed out, so it must throw.

Fix (do NOT weaken auth): platform-split module `mobile/src/storage/secureStore.{ts,web.ts}`. Native `.ts` re-exports the 3 used fns from `expo-secure-store` (native bit-for-bit unchanged). `.web.ts` backs the same async API with `window.localStorage`, best-effort/never-throws. Repoint the importers (`src/api/client.ts`, `src/state/authStore.ts`, `src/state/settingsStore.ts`) to it. Metro resolves `.web.ts` for web only.

**How to apply:** any time a mobile feature stores via SecureStore and must also run on Expo Web (E2E smoke), route it through `src/storage/secureStore`, never import `expo-secure-store` directly. Only `getItemAsync/setItemAsync/deleteItemAsync` are in use.
