---
name: react-native-web Alert.alert is a no-op
description: Native Alert action menus are un-triggerable on Expo Web (the mobile e2e target) and broken for web users.
---

`react-native-web`'s `Alert` is `class Alert { static alert() {} }` — a literal
no-op. So any mobile flow whose ONLY entry point is a native
`Alert.alert(title, msg, buttons)` action menu (e.g. long-press → menu → open a
modal) does nothing on Expo Web. Same for success/error confirmation toasts done
via `Alert.alert` — they silently vanish on web.

**Why it matters:** the mobile E2E suite (`mobile/e2e/`) runs on Expo Web against
the deployed base_url. A flow reachable only through `Alert` is not just
untestable there — it is genuinely broken for any web user.

**How to apply:**
- To make such a flow testable AND usable on web, add a real DOM-interactable
  entry (a tappable `Button`/`Pressable` with a `testID`) that opens the
  modal/action directly, in parallel with the native long-press menu. Don't try
  to drive the Alert from Playwright — there is nothing to drive.
- For success signals in an e2e, key on the deterministic wire round-trip
  (the POST/PUT returning 2xx) + the modal closing, NOT on an `Alert` toast
  (it never renders on web).
- `Button`/`Card` in `mobile/src/components/ui.tsx` spread `...rest`, so a
  `testID` prop passes straight through to the underlying Pressable/View and
  becomes `data-testid` on web.
