"""Migration keşfi — ``versions/`` paketindeki migration birimlerini bulur.

Her ``versions/v*.py`` modülü modül seviyesinde bir ``MIGRATION`` değişkeni
tanımlar (bir ``Migration`` örneği). ``discover_migrations`` bu modülleri yükler,
``MIGRATION`` örneklerini toplar ve ``version`` alanına göre sıralı döndürür.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil

from .base import Migration

logger = logging.getLogger("bootstrap.migrations.registry")


def discover_migrations() -> list[Migration]:
    """``versions/`` paketindeki tüm ``MIGRATION`` birimlerini sıralı döndürür."""
    from . import versions

    found: list[Migration] = []
    seen_versions: set[str] = set()
    for mod_info in pkgutil.iter_modules(versions.__path__):
        name = mod_info.name
        if name.startswith("_"):
            continue
        module = importlib.import_module(f"{versions.__name__}.{name}")
        migration = getattr(module, "MIGRATION", None)
        if migration is None:
            continue
        if not isinstance(migration, Migration):
            logger.warning(
                "versions.%s.MIGRATION bir Migration örneği değil — atlandı", name,
            )
            continue
        if not migration.version:
            logger.warning("versions.%s migration'ında version boş — atlandı", name)
            continue
        if migration.version in seen_versions:
            raise ValueError(
                f"Çift migration versiyonu: {migration.version} (versions.{name})"
            )
        seen_versions.add(migration.version)
        found.append(migration)

    found.sort(key=lambda m: m.version)
    return found
