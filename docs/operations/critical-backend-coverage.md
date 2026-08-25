# Critical backend coverage policy

The backend CI uses two complementary coverage gates:

1. A repository-wide floor catches broad coverage loss.
2. Per-file floors protect business-critical paths even when the repository-wide percentage remains unchanged.

The policy is stored in `scripts/critical_backend_coverage.json` and enforced by
`scripts/check_critical_coverage.py` against the JSON report produced by the complete
provider-safe backend test suite.

The initial critical set covers reservation lifecycle, HotelRunner authentication,
night audit, reservation creation and modification, folio operations, and authentication.
Low legacy baselines are intentionally recorded rather than hidden. Their floors must be
raised in focused test tranches; they must never be lowered merely to make CI green.

The first tranche raises `modules/pms_core/reservation_state_machine.py` from 26.42%
to at least 90%. It covers cancellation and no-show guards, room-night release,
availability restoration, notifications, audit records, outbox events, room cleanup,
and failure isolation for non-critical side effects.
