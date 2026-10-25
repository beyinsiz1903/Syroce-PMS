# Mapping quarantine and night audit

`pending_mapping` / legacy `ota_unmatched_hold` is an integration exception,
not an accepted PMS arrival or proof that a guest did not arrive. Never repair
such a record with arbitrary room assignment, check-in/out or automatic no-show.

The selected tenant's read-only `/api/channel-manager/conflict-queue/mapping-issues`
combines legacy holds, Exely/HotelRunner pending-mapping inboxes and unified
import reviews (`unmapped_room_type` / `unmapped_rate_plan`). Exact property +
provider + external identity is one displayed exception. All source row IDs are
retained; grouping does not delete, cancel, acknowledge or financially settle them.
Missing source identity is not guessed from name or stay dates.

At the open **business date**, exceptions arriving today or earlier block close.
Invalid arrival dates also block; future mapping exceptions warn. Preview,
normal execution, skip-validations execution, resume-before-posting and final
date-roll recheck share the same read contract. An unreadable inbox fails closed.
The final recheck reduces late-arrival races, but is not a transactional ingest
fence: provider intake and day-close do not share one database transaction.

The calendar separates source review from room assignment and offers the
provider's integration screen, not a No-Show button, for mapping exceptions.
Opening the panel performs GETs only, with no implicit auto-assignment or
legacy duplicate reconciliation. Normal explicit assignment tools remain.

## Recovery for an overdue exception

1. Read the source identity and provider inbox/version; establish authoritative
   cancellation/delivery/stay status before deciding anything about the guest.
2. Correct the exact room/rate mapping and use the provider's existing controlled
   replay/reconciliation path. Do not enable ARI or polling merely to clear a badge.
3. If a historical test record must be retired, use an explicitly authorized,
   reasoned, audited resolution. This change does not add a bulk-hide/delete path.
4. Confirm the exception disappeared from both preview and calendar for the same
   tenant, and verify no duplicate booking, charge, payment or official notification.

Already-closed days are not rewritten or resealed. A clean current preview is
not retrospective certification of historical financial reports.
