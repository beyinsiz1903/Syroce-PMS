"""Versiyonlu DB migration çerçevesi.

Açılışta indeks fazlarından ÖNCE çalışan, sıralı/versiyonlu, rollback'li ve
fail-closed bir migration sistemi. Mevcut indeks kodu yerinde kalır; bundan
sonraki tüm şema/indeks değişiklikleri bu sistemden geçer.

Genel kullanım:
    from bootstrap.migrations import run_migrations, get_migration_status
"""

from .base import (
    LEDGER_COLLECTION,
    LOCK_COLLECTION,
    STATUS_APPLIED,
    STATUS_FAILED,
    STATUS_ROLLED_BACK,
    Migration,
)
from .registry import discover_migrations
from .runner import (
    MigrationError,
    get_migration_status,
    run_migrations,
)

__all__ = [
    "Migration",
    "MigrationError",
    "run_migrations",
    "get_migration_status",
    "discover_migrations",
    "LEDGER_COLLECTION",
    "LOCK_COLLECTION",
    "STATUS_APPLIED",
    "STATUS_FAILED",
    "STATUS_ROLLED_BACK",
]
