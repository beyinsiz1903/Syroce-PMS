"""Deterministic, non-reversible fencing keys for provider raw events."""

from __future__ import annotations

import hashlib


def raw_event_fence_key(tenant_id: str, provider_event_id: str) -> str:
    """Scope an event identity to its tenant without retaining provider data."""
    material = "\x1f".join((str(tenant_id), str(provider_event_id)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
