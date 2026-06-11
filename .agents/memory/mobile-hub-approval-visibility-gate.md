---
name: Mobile hub approval-category visibility gate
description: How to pick the visibility gate when adding a category to /api/mobile/hub/approvals
---

When adding a new category to the unified mobile approvals endpoint
(`backend/domains/pms/mobile_router/hub.py`), gate its visibility on the role
set that the underlying decision endpoint actually restricts to — not merely on
an `_can(user, op)` operation probe.

**Why:** the procurement PR-status endpoint requires BOTH
`require_op("manage_sales")` AND `require_procurement` (PROCUREMENT_ROLES).
`manage_sales` is ALSO held by SALES, who must never see satınalma approvals. So
the hub category uses a role-based `_can_procurement` (PROCUREMENT_ROLES +
super_admin bypass), mirroring `require_procurement`, which is strictly narrower
than the op. Visibility narrowing only — the decision endpoint still enforces its
own RBAC, so this can never widen access.

**How to apply:** for each hub approval category, find the approve/reject
endpoint, enumerate EVERY guard it stacks, and gate visibility on the most
restrictive one. If an op-based probe would expose the items to a role that the
stacked guards would later 403, use a role-based probe instead.
