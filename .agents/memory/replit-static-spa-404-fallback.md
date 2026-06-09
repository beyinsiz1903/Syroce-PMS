---
name: Replit static deploy SPA needs 404.html
description: A client-side SPA on a Replit Static Deployment must ship a 404.html copy of index.html or deep-link/hard navigations return an empty 404 and the app never boots.
---

Replit Static Deployments do NOT rewrite unknown routes to index.html. A path that
isn't a real file returns an empty `HTTP 404` (size 0), so a hard navigation to a
client-side route (e.g. `/login`, `/checkin`) never loads the SPA shell — the bundle
never executes and nothing renders.

**Fix:** copy `index.html` -> `404.html` into the publicDir root after build. Replit
serves `404.html` for any unmatched path, so every deep route falls back to the SPA
shell and the client router resolves the correct screen. (Confirmed via Replit docs:
"Static Deployment Configuration" — 404.html is served for unknown routes.)

**Why it bit us:** the Expo Web (`web.output="single"`) F10A mobile smoke bundle
rendered fine when entered at `/` (client redirect to `/login` worked), but the
Playwright harness does `page.goto('/login')` — a hard navigation — and every test
failed at `smoke-login-email` not visible. Root cause was the missing SPA fallback,
NOT a broken bundle. The deployed `/` screenshot showing a working login screen is
the giveaway: if `/` renders but `/<deep-route>` 404s, you need 404.html.

**How to apply:** any static-hosted SPA whose tests/users deep-link to client routes
must emit `404.html` in the build. For Expo Web this lives in `mobile/build-web.sh`
(`cp dist/index.html dist/404.html`). The screenshot tool follows the client redirect
so it can hide this bug — verify a raw `curl -o /dev/null -w '%{http_code}'` on a deep
route returns 200 (a real file or fallback), not an empty 404, before trusting render.

**Sequel — the 404.html fallback still serves a 404 STATUS.** Once `404.html`=index.html
is shipped, a deep-link (`/login`) serves the REAL SPA shell and the app BOOTS and renders
— but Replit static returns it with `HTTP 404` (no SPA-rewrite-to-200 mode exists; the
deployment skill confirms "no server-side processing"). So `curl /login` = 404 status with
the full index.html body. This is harmless to humans but a strict E2E console-error gate
(`consoleErrors.toHaveLength(0)`) catches the browser's "Failed to load resource: 404" on
the main-document navigation and fails EVERY role's `page.goto('/<route>')`.
**Fix is at the test observer, NOT a substring allowlist** (which would also hide real broken
chunk/asset 404s = fake-green): record main-document 404 URLs from the response stream
(`resourceType()==='document' && isNavigationRequest()`) and drop ONLY their console twin at
flush(); also drop 401/403 resource console errors to mirror the network-observer role-gating
policy. Every other 404/5xx and all page errors still fail, and `inspect.ok` independently
proves the shell rendered — so it is not fake-green.
