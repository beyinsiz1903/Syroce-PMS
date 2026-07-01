"""Geriye dönük uyumluluk köprüsü.

Kanonik uygulama `shared_kernel/pos_idem.py` altına taşındı ki birden fazla
domain (pms, spa, golf) cross-domain import yapmadan aynı idempotency
yardımcılarını kullanabilsin. Mevcut pms-içi import'lar bozulmasın diye bu
modül aynı isimleri (ve aynı `_INDEXES_READY` cache nesnesini) re-export eder.
"""

from __future__ import annotations

from shared_kernel.pos_idem import (
    _INDEXES_READY,
    ensure_compound_unique,
    ensure_idem_index,
    idempotent_insert,
    is_idem_index_ready,
)

__all__ = [
    "_INDEXES_READY",
    "ensure_compound_unique",
    "ensure_idem_index",
    "idempotent_insert",
    "is_idem_index_ready",
]
