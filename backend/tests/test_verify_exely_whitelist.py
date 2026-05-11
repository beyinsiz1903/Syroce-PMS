"""Unit tests for backend/scripts/verify_exely_whitelist.py.

Pilot Readiness Checklist hard-blocker #1 regression guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_exely_whitelist.py"
_spec = importlib.util.spec_from_file_location("verify_exely_whitelist", _SCRIPT)
assert _spec and _spec.loader
verify_mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_exely_whitelist"] = verify_mod  # required for @dataclass lookup
_spec.loader.exec_module(verify_mod)
verify = verify_mod.verify


# ── Production fail-closed cases (must BLOCK) ────────────────────────────


def test_production_missing_whitelist_blocks():
    f = verify({}, environment="production", expect_ips=[])
    assert f.blockers, "Empty whitelist must block in production"
    assert any("EXELY_IP_WHITELIST" in b for b in f.blockers)


def test_production_empty_whitelist_blocks():
    f = verify({"EXELY_IP_WHITELIST": "  ,  "}, environment="production", expect_ips=[])
    assert f.blockers
    assert any("empty/unset" in b for b in f.blockers)


def test_production_invalid_token_blocks():
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4,not-an-ip,5.6.7.8"},
        environment="production",
        expect_ips=[],
    )
    assert any("invalid IP token" in b for b in f.blockers)


def test_production_cidr_token_blocks():
    """CIDR ranges silently fail because the webhook does literal string match."""
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4,10.0.0.0/24"},
        environment="production",
        expect_ips=[],
    )
    assert any("CIDR" in b for b in f.blockers)


def test_production_bypass_flag_blocks():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4",
            "ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK": "1",
        },
        environment="production",
        expect_ips=[],
    )
    assert any("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK" in b for b in f.blockers)


def test_production_trust_xff_without_proxies_blocks():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4",
            "EXELY_TRUST_FORWARDED": "1",
            # EXELY_TRUSTED_PROXY_IPS missing
        },
        environment="production",
        expect_ips=[],
    )
    assert any("EXELY_TRUSTED_PROXY_IPS is empty" in b for b in f.blockers)


def test_production_trust_xff_with_only_invalid_proxies_blocks():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4",
            "EXELY_TRUST_FORWARDED": "1",
            "EXELY_TRUSTED_PROXY_IPS": "garbage,also-bad",
        },
        environment="production",
        expect_ips=[],
    )
    assert any("zero valid" in b for b in f.blockers)


def test_production_expect_ip_missing_blocks():
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4"},
        environment="production",
        expect_ips=["1.2.3.4", "9.9.9.9"],
    )
    assert any("missing from EXELY_IP_WHITELIST" in b for b in f.blockers)


# ── Production happy paths (must PASS) ───────────────────────────────────


def test_production_minimal_valid_passes():
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4"},
        environment="production",
        expect_ips=[],
    )
    assert not f.blockers, f"Unexpected blockers: {f.blockers}"


def test_production_with_valid_proxy_setup_passes():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4,5.6.7.8",
            "EXELY_TRUST_FORWARDED": "1",
            "EXELY_TRUSTED_PROXY_IPS": "10.0.0.0/24,172.16.0.1",
        },
        environment="production",
        expect_ips=["1.2.3.4"],
    )
    assert not f.blockers, f"Unexpected blockers: {f.blockers}"


def test_production_ipv6_whitelist_passes():
    f = verify(
        {"EXELY_IP_WHITELIST": "2001:db8::1,1.2.3.4"},
        environment="production",
        expect_ips=[],
    )
    assert not f.blockers


# ── Non-production semantics (warn, don't block) ─────────────────────────


def test_development_missing_whitelist_does_not_block():
    f = verify({}, environment="development", expect_ips=[])
    assert not f.blockers
    assert any("OK for non-production" in n for n in f.info)


def test_staging_bypass_warns_but_does_not_block():
    f = verify(
        {"ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK": "1"},
        environment="staging",
        expect_ips=[],
    )
    assert not f.blockers
    assert any("never leaks to production" in w for w in f.warnings)


# ── XFF without trust-flag — informational only ──────────────────────────


@pytest.mark.parametrize("env_label", ["production", "prod", "live", "PRODUCTION", "Prod", " live "])
def test_production_aliases_treated_as_prod(env_label):
    """server.py treats production|prod|live as prod — script must match.
    Also normalize case/whitespace so deploy YAML quirks don't silently downgrade."""
    f = verify({}, environment=env_label, expect_ips=[])
    assert f.blockers, f"env={env_label!r} must trigger production blocker"
    assert any("EXELY_IP_WHITELIST" in b for b in f.blockers)


@pytest.mark.parametrize("env_label", ["development", "dev", "staging", "test", "qa", ""])
def test_non_production_labels_do_not_block_on_missing_whitelist(env_label):
    f = verify({}, environment=env_label, expect_ips=[])
    assert not f.blockers, f"env={env_label!r} should not block on missing whitelist"


def test_prod_alias_blocks_bypass_flag():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4",
            "ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK": "1",
        },
        environment="prod",
        expect_ips=[],
    )
    assert any("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK" in b for b in f.blockers)


def test_proxy_ips_set_without_trust_flag_is_info():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4",
            "EXELY_TRUSTED_PROXY_IPS": "10.0.0.1",
        },
        environment="production",
        expect_ips=[],
    )
    assert not f.blockers
    assert any("ignored" in n for n in f.info)


# ── CLI entry point smoke ────────────────────────────────────────────────


def test_main_returns_1_on_blocker(monkeypatch, capsys):
    monkeypatch.delenv("EXELY_IP_WHITELIST", raising=False)
    rc = verify_mod.main(["--env", "production"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "verdict=FAIL" in out


def test_main_returns_0_on_pass(monkeypatch, capsys):
    monkeypatch.setenv("EXELY_IP_WHITELIST", "1.2.3.4")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    rc = verify_mod.main(["--env", "production"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "verdict=PASS" in out
