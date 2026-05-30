---
name: Permission-key reuse over-grants
description: Why gating a route on a convenient-but-wrong permission silently widens access, and how to catch it.
---

# Each route must enforce the permission that matches its action

A finance folio `void_payment` route was gated on `post_payment` (POST_PAYMENT) instead
of `void_payment` (VOID_CHARGE). FRONT_DESK holds POST_PAYMENT but not VOID_CHARGE, so
the wrong key silently let front-desk staff void payments. A parallel implementation in
`pms_hardening.py` used the correct key, so the two diverged.

**Why:** permission keys often read as near-synonyms ("post" vs "void" a payment), so a
copy-paste or a "good enough" guard passes review and tests that only check the happy
path. The gap is an over-grant, which is invisible until a lower-privilege role exercises
the route.

**How to apply:**
- When two routes perform related-but-distinct actions over the same resource, verify each
  enforces its *own* operation key — do not assume the sibling's guard is correct or that
  one key covers both.
- Test the negative case: assert a role that should be blocked (has the sibling permission
  but not this one) actually gets denied, plus a source-contract assertion that pins the
  literal op string so a re-loosening regresses loudly.
- `OPERATION_PERMISSIONS` is the source of truth for op→permission mapping; ADMIN/SUPER_ADMIN
  bypass all checks, unknown ops fail-closed to denied.
