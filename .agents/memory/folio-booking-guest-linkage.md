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

## Adjacent UNFIXED bug (night audit room revenue) — separate task

`night_audit/service.py::_post_nightly_room_charges` reads
`booking.get("folio_id")` (always None, per above) for the auto-posted nightly
room charge. Consequence: the charge is written with `folio_id=None` AND the
`folio.balance` `$inc` is **skipped** (it is guarded by `if booking.get("folio_id")`).
So auto-posted ROOM revenue never lands on the folio balance for ANY checked-in
booking — and since checkout's outstanding-balance / HTTP-402 guard reads
`folio.balance`, a guest can check out without the room charge being settled.
Revenue-integrity (P1-class), affects all bookings not just walk-ins.

**Fix direction (do NOT back-link folio_id onto bookings — too cross-cutting):**
inside night audit resolve the folio via
`folios.find_one({booking_id, tenant_id, folio_type:'guest', status:'open'})`,
post the charge against that folio id and `$inc` its balance. Also needs a
residue check for historical `folio_id=None` room charges. Left as its own
follow-up (out of scope for the invoice fix).
