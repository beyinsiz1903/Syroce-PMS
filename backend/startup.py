"""
startup.py — Application Lifecycle Handlers

Startup and shutdown events for the FastAPI application.
Called by server.py during bootstrap orchestration.

The original 964-line on_startup body has been split into 7 phase
helpers in `bootstrap.startup_phases` for readability/maintainability.
Execution order and fail-closed semantics (security/KBS/prod-validator
blocks still raise) are preserved EXACTLY as before.
"""

import logging

from bootstrap.startup_phases import (
    phase_a_security_and_core_indexes,
    phase_b_seed_and_exely_conn,
    phase_c_domain_indexes_and_workers,
    phase_d_perf_and_marketplace,
    phase_e_outbox_and_eventbus,
    phase_f_hardening_and_observability,
    phase_g_channels_and_audit,
    shutdown_all,
)
from core.database import db

logger = logging.getLogger(__name__)


async def on_startup(app):
    """Run all startup initialization tasks (delegates to phase helpers)."""

    # Expose db via app.state for health checks
    app.state.db = db

    await phase_a_security_and_core_indexes(app)
    await phase_b_seed_and_exely_conn(app)
    await phase_c_domain_indexes_and_workers(app)
    await phase_d_perf_and_marketplace(app)
    await phase_e_outbox_and_eventbus(app)
    await phase_f_hardening_and_observability(app)
    await phase_g_channels_and_audit(app)


async def on_shutdown(app):
    """Graceful shutdown: close connections and stop workers."""
    await shutdown_all(app)
