---
name: getByText collides with bottom-tab label behind a modal
description: Why an Expo-Web/Playwright getByText('X').first() click times out on a modal control when a persistent tab bar shares the label; fix with a scoped testID.
---

# getByText label collision with a tab bar behind a modal

A Playwright `getByText('Bugün', {exact:true}).first()` click inside an open
DatePicker modal timed out for 60s: the locator resolved to a `<span>Bugün</span>`
but the modal's `#00000088` backdrop `<div tabindex=0>` Pressable intercepted the
tap (114 retries).

Root cause: the persistent bottom-tab bar has a tab whose title is the SAME word
(`tr.tabs.today` = "Bugün"). That tab renders behind the modal overlay. `.first()`
in DOM order grabbed the tab, not the modal's footer preset button — and the
backdrop sits on top of the tab, so the click could never land. The modal's own
footer button was always clickable (it's above the backdrop); only the locator was
ambiguous. Sibling controls "Temizle"/"Kapat" did NOT collide because no tab uses
those words — that asymmetry is the tell.

**Why:** RN-web renders the tab bar as normal page content that stays mounted under
the transparent modal. A bare text match can't distinguish the modal control from
identically-labelled chrome behind it.

**How to apply:**
- When a modal/dialog control's visible label could also appear in persistent
  chrome (tab bar, header), do NOT match it by text. Add a scoped `testID` on the
  control and target `[data-testid="..."]` (RN-web maps `testID` -> `data-testid`).
- Derive the id from the component's existing trigger testID
  (`testID ? \`${testID}-today\` : undefined`) so each instance is unique and
  un-id'd pickers emit nothing. Modal content unmounts on `visible={false}`, so
  closed instances can't produce stale matches.
- This is an honest locator fix, not skip-as-pass: no assertion weakened, no app
  behavior changed (testID is inert render metadata). If a click times out with
  "<div ...> intercepts pointer events" on a visible/stable element, suspect a
  same-label element behind an overlay before suspecting a real UI bug.
- A latent ambiguity like this can stay hidden until an earlier-step fix lets the
  test reach the colliding step for the first time.
