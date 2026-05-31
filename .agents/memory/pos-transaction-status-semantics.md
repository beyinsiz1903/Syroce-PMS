---
name: POS transaction status semantics & inventory deplete
description: How pos_transactions status is written across POS write paths, why transfer-table needed an open-tab surface, and that close_order does not auto-decrement inventory.
---

# POS pos_transactions status + inventory deplete

- `create_order` writes **pos_orders** with `status='pending'` (NOT pos_transactions).
- `close_order` writes **pos_transactions** with `status='completed'`.
- The **transfer-table** endpoint filters `pos_transactions` on `(tenant, outlet, from_table, status='open')`. Before the open-tab surface existed, NO production write path ever produced a status='open' row, so transfer-table was effectively dead-code for the v2 lifecycle (its happy path could only be a structural REVIEW/skip).
- An **open-tab write surface** (`POST /api/pos/v2/tabs/open` → status='open'; `POST /api/pos/v2/tabs/close` → completed) is what makes transfer-table's happy path reachable end-to-end.

**Why:** A stress spec kept recording transfer-table happy-path as REVIEW because there was no honest way to create the open state. The fix is a real product surface, not test trickery.

**How to apply:** If a POS/transfer flow seems "unreachable," check which collection+status each write path produces before assuming a backend bug. Don't fake an open tab in a test — open one through the real surface, then settle it in `finally`.

## Inventory deplete
- `close_order` does **NOT** auto-decrement inventory — there is no recipe→close→decrement wiring. The production deplete path is the atomic movement endpoint `POST /api/accounting/inventory/movement` (`movement_type=out|in`, out is overdraft-guarded → 409). Any test claiming "close → decrement" is fake-green.

## Recipe surface field mismatch
- Recipes are created via `POST /api/fnb/recipes` (writes `db.recipes` with `dish_name`, `ingredients`, `selling_price`; needs `manage_sales` op).
- They are read via `GET /api/fnb/mobile/recipes` which projects `menu_item_name`/`menu_item_id`/`serving_size` (so `dish_name` is absent from the read), but `ingredients` IS returned — so prefix-tagged ingredient names survive the round-trip for visibility checks. Count via `body.recipes.length`.
