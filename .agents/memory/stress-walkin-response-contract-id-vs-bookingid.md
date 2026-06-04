---
name: Walk-in stress success check must read booking_id, not id
description: The /pms-core/walk-in response has no `id` field; a stress spec keying success on body.id is a fake-RED that empties the downstream chain.
---

The walk-in create+check-in endpoint returns a result with NO top-level `id`:
`{success, booking_id, folio_id, room_number, guest_id}` (the handler returns the
service dict as-is, no response_model rename). The booking identifier is `booking_id`.

**Rule:** a stress/E2E step that counts walk-in success and harvests the new booking
id must read `body.booking_id`, never `body.id`. The canonical day-turnover walk-in
pattern just checks `r.ok` (HTTP 200) — adding `&& r.body?.id` is over-strict AND
wrong-field: every genuine 200+success:true call is mis-counted as fail.

**Why:** in the 24h full-sim spec this exact drift made the morning walk-in batch
report ok=0 (HTTP-200 successes logged as `s200` failures) → a persistent REVIEW
fake-RED. Worse, the harvested array (`walkInBookingIds`) is only pushed when the
wrong field is truthy, so it stayed empty and the evening folio-charge/payment phases
fell back to stale checked-in bookings (closed folios → s400) or SKIPped — one field
typo cascaded into ~4 REVIEW + 1 SKIP.

**How to apply:** distinguish the two failure modes before "fixing" a low-success
walk-in batch — `s400` is a genuine reject (room not in {available,inspected}, or
overbooking/booking conflict; backend correctly returns success:false → handler 400),
but `s200`-counted-as-fail means the success predicate is reading the wrong response
field. Fixing the field is doctrine-compliant (true contract, not assertion-loosening;
the 400/overbooking rejects still count as fail). Agent cannot dispatch full stress;
verify with `node --check` + contract read, final green is the operator's CI run.
