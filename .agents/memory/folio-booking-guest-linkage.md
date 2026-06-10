---
name: Folio <- booking <- guest linkage is one-way
description: How to resolve booking/guest FROM a folio in PMS, and why reverse {'folio_id'} lookups silently return None (from-folio invoice + night-audit room-charge consequences).
---

# Folio / booking / guest linkage is one-directional

The PMS data model links these one way only:

- `folio.booking_id -> booking.id` and `folio.guest_id -> guest.id` ARE set at
  walk-in / check-in (folio doc carries both).
- The booking is **never** back-linked: nothing in any booking-creation path
  (walk_in, _do_checkin, pms_core) writes `folio_id` onto the booking document.
- The guest's **name** lives on the `guests` collection. A booking only carries
  `guest_id` (no `guest_name` for walk-in/quick bookings).

**How to apply:** any code that needs the booking or guest *starting from a
folio* must go `folio.booking_id -> bookings.find_one({id, tenant_id})`, and for
the customer name `folio.guest_id` (or `booking.guest_id`) ->
`guests.find_one({id, tenant_id})`. Fallback chain for display name:
`booking.guest_name -> guest.name -> folio.guest_name -> 'Guest'` (truthiness,
not `dict.get(x,'Guest')` — an empty-string field returns '' and trips the
min-length-2 invoice customer-name validator -> HTTP 400).

**Why:** the "generate invoice from folio" endpoint
(`POST /api/accounting/invoices/from-folio`) used the reverse lookup
`bookings.find_one({'folio_id': request.folio_id})`, which ALWAYS returned None,
so every folio invoice silently fell back to customer "Guest" with
`booking_id=None` (and would have 400'd outright once the empty-name path hit
the validator). Verified live end-to-end (money chain 23/23) after switching to
the forward lookup.

## Night-audit room revenue → folio.balance (FIXED)

There are THREE night-audit room-charge code paths; know which is reachable:

- **REACHABLE LEAK** = `modules/pms_core/night_audit_engine.py::_post_room_charges`
  (route `POST /api/pms-core/night-audit/run`, NOT module-gated). It inserted
  room `folio_charges` but never `$inc`-ed `folio.balance` → auto-posted room
  revenue never landed on the balance, so checkout's outstanding-balance / 402
  guard (reads `folio.balance`) let guests check out unsettled. THIS was the bug.
- **DEAD** = `domains/pms/night_audit/service.py::_post_room_charges`
  (`run_scheduled_audit` has zero callers; scheduler imports
  `core.night_audit_hardened.start_night_audit`). Fixed for consistency only.
- **CANONICAL SAFE** = `core/night_audit_hardened.py` — already `$inc`s balance;
  use it as the reference for `$inc` semantics.

**Fix applied:** after inserting room charges, `$inc` each affected folio's
balance by the sum of ACTUALLY-inserted line totals (`amount+tax_amount`,
grouped by folio, keyed off `inserted_ids` only), with a tenant-scoped filter
`{"id": fid, "tenant_id": tenant_id}`. Do NOT back-link `folio_id` onto bookings
(too cross-cutting); resolve the folio forward via
`folios.find_one({booking_id, tenant_id, status:'open'})`.

**integrity-check false-positive** (`financial_service.py::get_integrity_check`,
route `GET /api/night-audit/integrity-check`, module-gated → needs tenant
`modules.night_audit=true`): because `booking.folio_id` is ALWAYS None (one-way
link), the old "missing folio" check flagged EVERY checked-in booking. Fix:
also query the `folios` collection for open guest folios and treat a booking as
missing only when `not (b.folio_id or b.id in open_folio_bids)`.

**Idempotency:** sequential re-run for the same business date is safe — the
pre-fetch guard skips folios already carrying `night_audit_date == business_date`
before any insert/`$inc`, so balance can't double-count.

**Residual (pre-existing, NOT introduced here):** the pms-core engine has no
run-level lock and the hardened dedup unique index does NOT cover its charge
docs (engine uses `night_audit_date`/`charge_category`; index wants
`business_date`/`charge_type`). Two *concurrent* same-date runs could double-post
charges AND balance. Follow-up candidate: per-(tenant,business_date) lock or
align the engine's field names with the dedup index.

**Why:** verified live end-to-end on an isolated throwaway tenant (balance went
0 → exactly 1650.0 for a 3000/2-night stay +10% tax; integrity-check flagged the
folio-less booking and not the folio-having one). `$inc` (not full recompute) is
correct here — it mirrors every other write path and won't mask drift.
