# Unified product experience

Scope: hotel workspace navigation, role-aware start, task-oriented application discovery,
shared guest context, combined follow-up inbox, transparent automation, operational copy,
responsive forms and touch workflows. Existing money, inventory and reservation rules remain authoritative.

## Acceptance contract

- Every new entry point uses the existing role, page, tenant and entitlement gates.
- No guest data is persisted in browser preferences or navigation history.
- Preferences are scoped by user and hotel; stale requests cannot reveal the previous context.
- The work inbox reads source records, does not create duplicate tasks, distinguishes failed
  sources from empty results, and states when a preview is incomplete.
- Handover acknowledgement means receipt, not completion; resolution is explicit and audited.
- Automatic recommendations do not silently execute financial or guest-contact actions.
- Forms preserve existing submit contracts; destructive transitions still require confirmation.
- Turkish and English product terms, visible focus, semantic controls and responsive layouts
  are checked with regression tests and local browser review before publication.

## Validation

Record actual commands/results in the PR. Production deployment and real-staff usability
benchmarks are not implied by passing automated tests. No live hotel writes are part of UI QA.

Local results (2026-10-09): full Vitest run 1,295/1,295 passed; final role/navigation/manual
operation regression rerun 24/24 passed; handover pytest suite 17/17 passed; Vite production
build passed. ESLint on touched source files reported zero errors and four warnings in
ChannelHub/PMSModule; the final navigation/helper files passed without warnings. Ruff on
the handover router and its tests passed. `git diff --check` passed.

## Implemented behavior

- Desktop sidebar and labelled mobile menu retain the existing navigation catalogue and
  authorization checks. Super-admin hotel/platform selection filters navigation only;
  it does not change the selected hotel or grant permissions.
- Role-aware start shortcuts and non-administrator login destinations are selected from
  authorized, enabled routes. An explicit login redirect takes precedence.
- Application discovery uses operational groups, scoped favorites and a remembered search.
  Workspace scroll offsets and density preferences are scoped by user and hotel.
- The lazy-loaded guest panel searches existing profiles and reads stay history without
  leaving the current route. Reservation and CRM entry points can open the same panel.
- The work inbox combines accessible task, handover and operational-alert sources. It
  links to their source screens; it is not a second task database or a complete export.
- Handover receipt, work in progress and resolution are separate states. Resolution needs
  a result note and records the actor/time. Legacy acknowledged notes remain unresolved.
  Compare-and-set updates reject conflicting transitions; acknowledgement retries cannot
  replace the first recipient. The API requires the existing frontdesk module scope.
- Messaging automation activation previews the trigger, channel, delay and template before
  confirmation. Existing delivery/consent controls remain authoritative.
- Booking dates are first, fields are localized, layout is responsive, pending submission
  blocks duplicate requests, and obsolete guest searches are cancelled. No pricing rule
  or reservation payload contract changes are introduced.
- Housekeeping presents the next cleaning action; secondary actions are expandable. POS
  adds menu search, keyboard activation and a sticky tablet/desktop cart.
- Dashboard hierarchy, CRM risk wording, channel environment labels, invoice tab wrapping,
  module-store terminology, modal close labels and keyboard focus styling are cleaned up.

## Local visual review

Run the frontend development server and open `/dev/experience-preview.html`. This development-only
fixture uses fabricated data and replaces both application Axios adapters; it is not a production
route and is not included in the production build. Do not use it to validate live integrations.

Reviewed desktop navigation at 1440 × 900 and mobile navigation, booking and guest context at
390 × 844. Page/dialog widths matched the viewport without horizontal overflow in those checks.
Also exercised work-source loading, profile selection and hotel/platform navigation switching.
Automated coverage includes role gates, partial failures, stale guest/hotel requests, reservation
selection, pending submission suppression, POS search/keyboard use and handover state conflicts.

## Release boundaries and remaining acceptance

This is a shared-experience and selected-workflow package, not a complete redesign or certification
of every PMS page. It does not claim zero defects, full WCAG conformance, complete translation of
all legacy modules, or best-in-market usability. Invoices retain their existing record/action model;
channel configuration retains its existing setup flow. A universal saved-filter/draft system and
full guest-contact/folio actions inside the guest panel are not implemented by this package.

Before production acceptance, test real hotel roles and entitlements, property switching,
existing handover records, channel/automation permissions, light/dark themes and actual handheld
devices against staging. Run a complete reservation → stay → payment → checkout scenario with
test data. Measure task completion time and operator error rate with hotel staff before rating
the overall product. CI and deployment status must be reviewed separately; local test success
is not a deployment confirmation.
