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
from routers.infra_hardening import router as infra_router
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


# ── Wave 5: backup status shape contract ──
# Spec probes recorded a P2 expecting `last_backup_at`; the deployed contract
# nests the latest completed run under `last_successful` (with completed_at).
# Lock the deployed shape so the spec's expectation maps onto reality without
# loosening anything.


def test_backup_status_route_registered():
    # infra_hardening mounts under /api/infra → /api/infra/backup/status.
    assert "/api/infra/backup/status" in _paths(infra_router)


def test_backup_status_shape_has_last_successful_and_metrics():
    from infra.backup_manager import backup_manager

    status = backup_manager.get_status()
    assert "enabled" in status
    # `last_successful` is the deployed equivalent of the spec's last_backup_at;
    # it is either None (no backup yet) or a dict carrying completed_at.
    assert "last_successful" in status
    ls = status["last_successful"]
    assert ls is None or ("completed_at" in ls)
