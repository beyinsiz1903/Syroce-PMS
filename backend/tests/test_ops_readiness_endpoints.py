"""F8W § 09 (Wave 2) — Ops-readiness observability endpoints exist.

Spec 09 (CM outbox depth + conflict queue) recorded P2 "unreachable"
because its probe path list did not include the actually-deployed paths.
These tests lock the deployed route contract so the spec's added candidates
keep matching real endpoints:

  - outbox:   /api/outbox/status            (routers.outbox_admin, /api prefix)
  - conflict: /api/channel-manager/conflict-queue/count  ({count})
              /api/channel-manager/conflict-queue        ({total})
"""

from routers.cm_conflict_queue import router as conflict_router
from routers.outbox_admin import outbox_admin_router


def _paths(router):
    return {r.path for r in router.routes}


def test_outbox_status_route_registered():
    # Router-local path; registry mounts it under /api → /api/outbox/status.
    assert "/outbox/status" in _paths(outbox_admin_router)


def test_conflict_queue_count_route_registered():
    paths = _paths(conflict_router)
    assert "/api/channel-manager/conflict-queue/count" in paths
    assert "/api/channel-manager/conflict-queue" in paths
