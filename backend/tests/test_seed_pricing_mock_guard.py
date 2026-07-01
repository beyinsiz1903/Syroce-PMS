"""Pilot guard regression for the shadow competitor_rates seed script.

Pins the fail-closed tenant isolation of ``scripts.seed_pricing_mock``:
  * the real pilot tenant is accepted,
  * any non-pilot tenant is REJECTED unless an explicit double-opt-in env is set,
  * an empty tenant is rejected.

Doctrine: shadow_seed writes must never land on a non-pilot tenant by default
(production Atlas blast-radius = 0).
"""
from __future__ import annotations

import pytest

from scripts.seed_pricing_mock import PILOT_DEFAULT, _enforce_pilot


def test_pilot_accepted(monkeypatch):
    monkeypatch.delenv("ALLOW_NON_PILOT_SHADOW_SEED", raising=False)
    assert _enforce_pilot(PILOT_DEFAULT) == PILOT_DEFAULT
    # whitespace tolerated
    assert _enforce_pilot(f"  {PILOT_DEFAULT}  ") == PILOT_DEFAULT


def test_non_pilot_rejected_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_NON_PILOT_SHADOW_SEED", raising=False)
    with pytest.raises(SystemExit):
        _enforce_pilot("56e9280e-33f7-4875-9cf2-45e6dce9a7c0")


def test_empty_tenant_rejected(monkeypatch):
    monkeypatch.delenv("ALLOW_NON_PILOT_SHADOW_SEED", raising=False)
    with pytest.raises(SystemExit):
        _enforce_pilot("   ")
    with pytest.raises(SystemExit):
        _enforce_pilot(None)


def test_non_pilot_allowed_only_with_explicit_optin(monkeypatch):
    monkeypatch.setenv("ALLOW_NON_PILOT_SHADOW_SEED", "true")
    assert _enforce_pilot("some-other-tenant") == "some-other-tenant"
    # any non-"true" value stays fail-closed
    monkeypatch.setenv("ALLOW_NON_PILOT_SHADOW_SEED", "1")
    with pytest.raises(SystemExit):
        _enforce_pilot("some-other-tenant")
