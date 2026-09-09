# MongoDB read-efficiency rollout

## Scope

- System Health loads once on entry; subsequent refresh is manual. User-triggered
  flush actions still refresh their result. Background health collection remains.
- Trace summary reads omit spans and attributes; aggregation semantics unchanged.
- Inventory reconciliation reads the room catalogue once per tenant/run, then
  reads fresh night locks and existing inventory once per date. There is no
  cross-request or cross-tenant availability cache. Booking/payment guards remain.
- ARI push queue: empty ticks back off 10 / 20 / 30 seconds; discovered work
  restores 5-second polling. New work after a long idle can wait up to 30 seconds.
  Provider retries, reservation ingestion and configured provider sync intervals
  are unchanged. This is not a redesign of every Channel Manager worker.
- Add indexes for KBS kind/latest-alert lookup, expired holds and pending ARI
  tenant selection. No KBS sender, delivery schedule or payload changes.
- General notification list polls every 60 seconds only while visible and on
  return to the tab. Existing live messaging socket remains unchanged.
- Notification and HotelRunner rate-calendar reads use explicit response fields.
- Shift lock backfill is a startup integrity task, not continuous polling; retain
  it. No live plan, backup policy, production data or credentials changed.

## Deployment verification

1. Confirm bootstrap creates the three new indexes without errors. Index creation
   can temporarily consume resources; do not equate code deployment with proof
   of index availability.
2. Observe System Health for two minutes: no scheduled refresh requests; manual
   refresh must update all five panels.
3. Hidden notification tab makes no list polls; foreground return refreshes.
4. Reconcile multi-day inventory and compare sellable/hold/OOO counts, retaining
   booking concurrency tests. Verify tenant separation.
5. Empty ARI queue reaches 30-second polls; queued changes are discovered within
   that bound and active polling returns to 5 seconds.
6. Compare Atlas egress and query counts over comparable 24-hour windows. August
   194 GB is not attributable to September query counts alone. No measured
   savings claim until after deployment. M10 fixed charges do not change.
