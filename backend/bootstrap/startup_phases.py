"""
Startup phase helpers — thin re-export of `bootstrap.phases` package.

Her faz kendi modülünde (`bootstrap/phases/<faz>.py`):
  - a_security, b_seed, c_domain, d_perf, e_outbox, f_hardening, g_channels
  - shutdown, perf_indexes (PERF-001 helper)
  - audit_indexes (R5 — kapsama doğrulama sonucu eklenen 11 index)

Bu dosya yalnızca dış API uyumluluğu (mevcut import path'leri) için var.
Yeni kod doğrudan `bootstrap.phases` paketinden de import edebilir.
"""
from bootstrap.phases import (
    ensure_audit_indexes,
    ensure_performance_indexes,
    phase_a_security_and_core_indexes,
    phase_b_seed_and_exely_conn,
    phase_c_domain_indexes_and_workers,
    phase_d_perf_and_marketplace,
    phase_e_outbox_and_eventbus,
    phase_f_hardening_and_observability,
    phase_g_channels_and_audit,
    shutdown_all,
)

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
