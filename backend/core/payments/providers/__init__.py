"""Somut odeme adaptorleri.

Bu paketin import edilmesi adaptorlerin import-time `register_provider`
cagrilarini tetikler; boylece registry tenant ayarina gore dogru adaptoru
bulabilir.
"""
from . import iyzico_adapter  # noqa: F401  (yan etki: register_provider)
from .iyzico_adapter import IyzicoProvider

__all__ = ["IyzicoProvider"]
