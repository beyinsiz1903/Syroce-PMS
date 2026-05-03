"""Startup phases — her faz kendi modülünde, başlangıç sırası korunur."""
from bootstrap.phases.a_security import phase_a_security_and_core_indexes
from bootstrap.phases.audit_indexes import ensure_audit_indexes
from bootstrap.phases.b_seed import phase_b_seed_and_exely_conn
from bootstrap.phases.c_domain import phase_c_domain_indexes_and_workers
from bootstrap.phases.d_perf import phase_d_perf_and_marketplace
from bootstrap.phases.e_outbox import phase_e_outbox_and_eventbus
from bootstrap.phases.f_hardening import phase_f_hardening_and_observability
from bootstrap.phases.g_channels import phase_g_channels_and_audit
from bootstrap.phases.perf_indexes import ensure_performance_indexes
from bootstrap.phases.shutdown import shutdown_all

__all__ = [
    "phase_a_security_and_core_indexes",
    "phase_b_seed_and_exely_conn",
    "phase_c_domain_indexes_and_workers",
    "phase_d_perf_and_marketplace",
    "phase_e_outbox_and_eventbus",
    "phase_f_hardening_and_observability",
    "phase_g_channels_and_audit",
    "shutdown_all",
    "ensure_performance_indexes",
    "ensure_audit_indexes",
]
