---
name: Mobile role-group pinning & all-access
description: How Expo Router mobile pins users to one role group, and how super_admin gets cross-group access without weakening RBAC
---

The mobile (Expo Router) app pins each signed-in user to ONE top-level role
group `(frontdesk|housekeeping|gm|guest)` via AuthGate, which redirects any
out-of-group segment back to `rootForRole(role)`.

**Gotcha:** `normalizeRole` collapses `super_admin`/`admin` into the `'gm'`
AppRole, so you CANNOT distinguish an all-access admin from a real GM using the
normalized `role`. Detect all-access from the **RAW backend role** (`user.role`)
via a separate helper/flag (`isAllAccessRole` / `allAccess` in authStore).

**All-access pattern:** AuthGate has a dedicated `allAccess` branch that permits
residence in ANY of the four `GROUP_SEGMENTS`, redirecting only from `(auth)` or
an unknown segment. Cross-group switching is a plain `router.replace` to the
group root (RoleSwitcher component, rendered only when `allAccess`).

**Why:** Backend RBAC already grants super_admin/admin full authority; the mobile
single-group pinning was a UI-MVP choice, not a permission boundary. Relaxing it
for all-access roles is a navigation affordance only — do NOT treat it as, or
extend it into, a server-side authorization change.

**How to apply:** All four groups' `more.tsx` re-export `(frontdesk)/more`, so a
shared component placed there appears in every group's "Daha" tab. Keep any
all-access UI gated on `allAccess` (returns null otherwise) so single-role users
never see cross-group controls.
