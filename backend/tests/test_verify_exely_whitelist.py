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


# ── Verdict model: PASS / REVIEW / FAIL (Paket 1 Mayıs 2026) ─────────────


def test_verdict_pass_when_clean():
    f = verify({"EXELY_IP_WHITELIST": "1.2.3.4"}, environment="production", expect_ips=[])
    assert f.verdict == "PASS"
    assert not f.blockers and not f.warnings


def test_verdict_review_when_warnings_only():
    """Staging bypass yields a warning but no blocker -> REVIEW."""
    f = verify(
        {"ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK": "1"},
        environment="staging",
        expect_ips=[],
    )
    assert not f.blockers
    assert f.warnings
    assert f.verdict == "REVIEW"


def test_verdict_fail_when_blockers_present():
    f = verify({}, environment="production", expect_ips=[])
    assert f.blockers
    assert f.verdict == "FAIL"


def test_main_returns_0_on_review(monkeypatch, capsys):
    """REVIEW (warnings only) must NOT block deploy by default — exit 0."""
    monkeypatch.delenv("EXELY_IP_WHITELIST", raising=False)
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", "1")
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    rc = verify_mod.main(["--env", "staging"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "verdict=REVIEW" in out


def test_main_strict_warnings_escalates_review_to_fail(monkeypatch, capsys):
    """--strict-warnings: REVIEW becomes exit 1 for tight CI/deploy gates."""
    monkeypatch.delenv("EXELY_IP_WHITELIST", raising=False)
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", "1")
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    rc = verify_mod.main(["--env", "staging", "--strict-warnings"])
    out = capsys.readouterr().out
    # Verdict text stays REVIEW (not promoted to FAIL); only exit code changes.
    assert "verdict=REVIEW" in out
    assert rc == 1


def test_main_strict_warnings_does_not_change_pass(monkeypatch, capsys):
    monkeypatch.setenv("EXELY_IP_WHITELIST", "1.2.3.4")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    rc = verify_mod.main(["--env", "production", "--strict-warnings"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "verdict=PASS" in out


# ── IP/token redaction (security: no raw IPs in output) ──────────────────


def test_redact_ipv4_masks_third_octet():
    assert verify_mod._redact_ip("1.2.3.4") == "1.2.x.4"
    assert verify_mod._redact_ip("203.0.113.42") == "203.0.x.42"


def test_redact_ipv4_cidr_preserves_suffix():
    assert verify_mod._redact_ip("10.0.0.0/24") == "10.0.x.0/24"


def test_redact_ipv6_keeps_first_and_last_segment():
    redacted = verify_mod._redact_ip("2001:db8::1")
    assert redacted.startswith("2001:")
    assert redacted.endswith(":1")
    assert "…" in redacted


def test_redact_invalid_token_never_echoed():
    """Bad tokens must NEVER appear verbatim — only length fingerprint."""
    out = verify_mod._redact_ip("not-an-ip")
    assert "not-an-ip" not in out
    assert out.startswith("<invalid:")


def test_redact_empty_token():
    assert verify_mod._redact_ip("") == "<empty>"


def test_production_info_does_not_leak_raw_ip():
    """Configured whitelist preview must be redacted in info messages."""
    f = verify(
        {"EXELY_IP_WHITELIST": "203.0.113.42,198.51.100.7"},
        environment="production",
        expect_ips=[],
    )
    joined = " ".join(f.info + f.blockers + f.warnings)
    assert "203.0.113.42" not in joined
    assert "198.51.100.7" not in joined
    # But redacted forms are present (operator can still match by knowing IPs).
    assert "203.0.x.42" in joined
    assert "198.51.x.7" in joined


def test_invalid_token_blocker_does_not_leak_raw_value():
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4,super-secret-not-an-ip,5.6.7.8"},
        environment="production",
        expect_ips=[],
    )
    joined = " ".join(f.blockers + f.info + f.warnings)
    assert "super-secret-not-an-ip" not in joined
    # Length fingerprint allowed.
    assert any("invalid IP token" in b for b in f.blockers)


def test_cidr_blocker_does_not_leak_raw_range():
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4,10.0.0.0/24"},
        environment="production",
        expect_ips=[],
    )
    joined = " ".join(f.blockers + f.info + f.warnings)
    assert "10.0.0.0/24" not in joined
    assert "10.0.x.0/24" in joined


def test_expect_ips_missing_blocker_does_not_leak_raw_ip():
    f = verify(
        {"EXELY_IP_WHITELIST": "1.2.3.4"},
        environment="production",
        expect_ips=["203.0.113.99"],
    )
    joined = " ".join(f.blockers + f.info + f.warnings)
    assert "203.0.113.99" not in joined
    assert "203.0.x.99" in joined


def test_proxy_invalid_warning_does_not_leak_raw_token():
    f = verify(
        {
            "EXELY_IP_WHITELIST": "1.2.3.4",
            "EXELY_TRUST_FORWARDED": "1",
            "EXELY_TRUSTED_PROXY_IPS": "10.0.0.1,garbage-proxy",
        },
        environment="production",
        expect_ips=[],
    )
    joined = " ".join(f.blockers + f.info + f.warnings)
    assert "garbage-proxy" not in joined


def test_main_output_contains_no_raw_ip(monkeypatch, capsys):
    """End-to-end: CLI stdout must redact configured IPs."""
    monkeypatch.setenv("EXELY_IP_WHITELIST", "203.0.113.42,198.51.100.7")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", raising=False)
    monkeypatch.delenv("EXELY_TRUST_FORWARDED", raising=False)
    verify_mod.main(["--env", "production"])
    out = capsys.readouterr().out
    assert "203.0.113.42" not in out
    assert "198.51.100.7" not in out
    assert "203.0.x.42" in out
