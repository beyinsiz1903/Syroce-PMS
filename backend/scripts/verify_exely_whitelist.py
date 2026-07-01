"""Verify Exely webhook IP-allowlist environment configuration.

Pilot Readiness Checklist hard-blocker #1 — production guard.

Run before any production / pilot deploy:
    python backend/scripts/verify_exely_whitelist.py --env production
    python backend/scripts/verify_exely_whitelist.py --env production \
        --expect-ips 1.2.3.4,5.6.7.8

Exit codes:
    0 — PASS or REVIEW (deploy may proceed; REVIEW means warnings present)
    1 — FAIL (at least one BLOCKER finding; deploy must NOT proceed)

Verdict model (Paket 1, May 2026):
    PASS   — blockers=0, warnings=0
    REVIEW — blockers=0, warnings>0  (operator should inspect; not auto-blocking)
    FAIL   — blockers>0

Use --strict-warnings to escalate REVIEW to exit 1 in CI/deploy gates.

Security: ham IP/token değerleri loglara veya readiness JSON'a sızmamalı
(IP allowlist parola değil ama güvenlik konfigürasyonu — Sentry/CI/log
sink'lerine ham yazmıyoruz). Tüm IP'ler `_redact_ip` ile maskelenir.

What this checks (read backend/domains/channel_manager/providers/exely/
exely_webhook_router.py around line 381 for the matching enforcement):

  1. EXELY_IP_WHITELIST is set and non-empty in production. If empty/unset
     the webhook router fail-closes with a 503 — Exely cannot deliver any
     reservation, no-show or cancel events to the pilot tenant.

  2. Each token in EXELY_IP_WHITELIST is a valid plain IPv4/IPv6 ADDRESS
     (NOT a CIDR). The webhook does literal string match
     (`source_ip not in allowed`); a CIDR token like "1.2.3.0/24" will
     never match because Exely's outbound IP is delivered as a bare
     address. CIDR support exists ONLY for EXELY_TRUSTED_PROXY_IPS, not
     for the allowlist itself.

  3. ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK is NOT set to "1" in production.
     This is the dev/staging fail-open escape hatch — leaving it on in
     production lets any anonymous attacker who knows a HotelCode forge
     reservations (revenue fraud, channel-state poisoning).

  4. If EXELY_TRUST_FORWARDED=1 is opted in, EXELY_TRUSTED_PROXY_IPS must
     contain at least one valid IP/CIDR. Otherwise X-Forwarded-For is
     silently ignored (peer fallback) — operators usually intend XFF to
     be honored when behind a reverse proxy/LB, so silent degradation
     causes Exely deliveries to be allowlist-rejected.

  5. (Optional) --expect-ips comma list: every expected IP must appear
     in EXELY_IP_WHITELIST as an exact token. Useful for asserting the
     known pilot Exely outbound IPs are present.

Output is human-readable + machine-parseable summary tail:
    SUMMARY blockers=N warnings=M info=K verdict=PASS|REVIEW|FAIL
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from dataclasses import dataclass, field


@dataclass
class Findings:
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def block(self, msg: str) -> None:
        self.blockers.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.info.append(msg)

    @property
    def verdict(self) -> str:
        """PASS (clean) / REVIEW (warnings only) / FAIL (any blocker)."""
        if self.blockers:
            return "FAIL"
        if self.warnings:
            return "REVIEW"
        return "PASS"


def _is_plain_ip(token: str) -> bool:
    try:
        ipaddress.ip_address(token)
        return True
    except ValueError:
        return False


def _is_ip_or_cidr(token: str) -> bool:
    try:
        ipaddress.ip_network(token, strict=False)
        return True
    except ValueError:
        return False


def _parse_csv(spec: str) -> list[str]:
    return [t.strip() for t in (spec or "").split(",") if t.strip()]


def _redact_ip(token: str) -> str:
    """Mask IP/CIDR tokens for safe logging.

    Examples:
      1.2.3.4         -> 1.2.x.4
      10.0.0.0/24     -> 10.0.x.0/24
      2001:db8::1     -> 2001:db8:…:1
      not-an-ip       -> <invalid:9>     (length only; never echo the bad token)
      ""              -> <empty>

    Goal: enough fingerprint for an operator who already knows the
    expected IPs to identify which entry is wrong, but not enough for a
    log-scraper to learn the allowlist.
    """
    if not token:
        return "<empty>"
    # Strip CIDR suffix for parsing, re-attach after masking.
    suffix = ""
    body = token
    if "/" in token:
        body, _, suffix_raw = token.partition("/")
        suffix = f"/{suffix_raw}"
    try:
        addr = ipaddress.ip_address(body)
    except ValueError:
        # Try as network (e.g. "10.0.0.0/24" already split above; here
        # handles malformed tokens). Never echo the raw bad token.
        return f"<invalid:{len(token)}>"
    if isinstance(addr, ipaddress.IPv4Address):
        parts = body.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.{parts[3]}{suffix}"
        return f"<ipv4:{len(token)}>"
    # IPv6: keep first segment + last segment, ellipsis between
    expanded = addr.exploded.split(":")  # 8 groups, zero-padded
    if len(expanded) >= 2:
        first = expanded[0].lstrip("0") or "0"
        last = expanded[-1].lstrip("0") or "0"
        return f"{first}:…:{last}{suffix}"
    return f"<ipv6:{len(token)}>"


def _redact_list(tokens: list[str]) -> list[str]:
    return [_redact_ip(t) for t in tokens]


# Must match backend/server.py production classification exactly.
# server.py: `_env in ("production", "prod", "live")` (case-sensitive there,
# but we normalize to lower so deploy YAML quirks like "Production" don't
# silently downgrade the gate).
_PROD_ALIASES = {"production", "prod", "live"}


def _is_production(env_label: str) -> bool:
    return (env_label or "").strip().lower() in _PROD_ALIASES


def verify(env: dict[str, str], *, environment: str, expect_ips: list[str]) -> Findings:
    """Pure function — easy to unit-test. `env` is a dict (e.g. os.environ).

    All IP/token values are redacted via `_redact_ip` in finding messages
    so that callers (readiness API, CI logs, Sentry breadcrumbs) never
    propagate the raw allowlist downstream.
    """
    f = Findings()
    is_prod = _is_production(environment)

    # ── Check 1 & 2: EXELY_IP_WHITELIST presence + token validity ──────
    raw = (env.get("EXELY_IP_WHITELIST") or "").strip()
    tokens = _parse_csv(raw)
    if not tokens:
        if is_prod:
            f.block("EXELY_IP_WHITELIST is empty/unset. Production webhook will 503 every Exely delivery (see exely_webhook_router.py:391).")
        else:
            f.note(f"EXELY_IP_WHITELIST is empty (environment={environment}); OK for non-production but webhook will reject all events.")
    else:
        f.note(f"EXELY_IP_WHITELIST has {len(tokens)} token(s) (redacted preview): {_redact_list(tokens)}")
        bad_tokens: list[str] = []
        cidr_tokens: list[str] = []
        for tok in tokens:
            if _is_plain_ip(tok):
                continue
            if _is_ip_or_cidr(tok):
                cidr_tokens.append(tok)
            else:
                bad_tokens.append(tok)
        if bad_tokens:
            f.block(f"EXELY_IP_WHITELIST contains {len(bad_tokens)} invalid IP token(s) (redacted): {_redact_list(bad_tokens)}. Each entry must parse with ipaddress.ip_address().")
        if cidr_tokens:
            f.block(
                f"EXELY_IP_WHITELIST contains {len(cidr_tokens)} CIDR range(s) "
                f"(redacted): {_redact_list(cidr_tokens)}. "
                "The webhook does LITERAL string match — CIDR will never match. "
                "Expand each range to plain /32 (or /128) addresses."
            )

    # ── Check 3: ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK must be off in prod ──
    bypass = (env.get("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK") or "").strip()
    if bypass == "1":
        if is_prod:
            f.block("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 in production. This is the dev fail-open escape hatch and must NEVER be set in prod.")
        else:
            f.warn(f"ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 (environment={environment}); ensure this never leaks to production.")

    # ── Check 4: EXELY_TRUST_FORWARDED ↔ EXELY_TRUSTED_PROXY_IPS pair ──
    trust_xff = (env.get("EXELY_TRUST_FORWARDED") or "").strip() == "1"
    proxy_spec = (env.get("EXELY_TRUSTED_PROXY_IPS") or "").strip()
    if trust_xff:
        proxy_tokens = _parse_csv(proxy_spec)
        if not proxy_tokens:
            f.block("EXELY_TRUST_FORWARDED=1 but EXELY_TRUSTED_PROXY_IPS is empty. X-Forwarded-For will be silently ignored — Exely deliveries behind a proxy will be allowlist-rejected by peer IP.")
        else:
            valid = [t for t in proxy_tokens if _is_ip_or_cidr(t)]
            invalid = [t for t in proxy_tokens if not _is_ip_or_cidr(t)]
            if invalid:
                f.warn(f"EXELY_TRUSTED_PROXY_IPS has {len(invalid)} invalid token(s) (skipped at runtime, redacted): {_redact_list(invalid)}")
            if not valid:
                f.block("EXELY_TRUSTED_PROXY_IPS has zero valid IP/CIDR entries — X-Forwarded-For will not be honored at runtime.")
            else:
                f.note(f"EXELY_TRUSTED_PROXY_IPS has {len(valid)} valid entry/entries.")
    else:
        if proxy_spec:
            f.note("EXELY_TRUSTED_PROXY_IPS is set but EXELY_TRUST_FORWARDED is not '1' — proxy list is ignored. Set EXELY_TRUST_FORWARDED=1 if you intended to honor X-Forwarded-For.")

    # ── Check 5: --expect-ips coverage ──────────────────────────────────
    if expect_ips:
        missing = [ip for ip in expect_ips if ip not in tokens]
        if missing:
            f.block(f"Expected IP(s) missing from EXELY_IP_WHITELIST: {len(missing)} entry/entries (redacted): {_redact_list(missing)}. Pilot Exely outbound IPs must be added before go-live.")
        else:
            f.note(f"All {len(expect_ips)} expected IP(s) present in whitelist.")

    return f


def _print_report(f: Findings, *, environment: str) -> None:
    print(f"=== Exely Whitelist Verification (environment={environment}) ===")
    if f.blockers:
        print(f"\n[BLOCKER] ({len(f.blockers)})")
        for b in f.blockers:
            print(f"  x {b}")
    if f.warnings:
        print(f"\n[WARNING] ({len(f.warnings)})")
        for w in f.warnings:
            print(f"  ! {w}")
    if f.info:
        print(f"\n[INFO] ({len(f.info)})")
        for i in f.info:
            print(f"  - {i}")
    print(f"\nSUMMARY blockers={len(f.blockers)} warnings={len(f.warnings)} info={len(f.info)} verdict={f.verdict}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--env",
        default=os.environ.get("ENVIRONMENT", "development"),
        help="Environment label (production / staging / development). Production triggers BLOCKER instead of WARNING for missing whitelist.",
    )
    parser.add_argument(
        "--expect-ips",
        default="",
        help="Comma-separated list of IPs that MUST appear in EXELY_IP_WHITELIST. Use to assert pilot Exely outbound IPs are present.",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Treat REVIEW (warnings>0) as failure — exit 1 instead of 0. Use in CI/deploy gates that require zero warnings.",
    )
    args = parser.parse_args(argv)

    expect_ips = _parse_csv(args.expect_ips)
    findings = verify(dict(os.environ), environment=args.env, expect_ips=expect_ips)
    _print_report(findings, environment=args.env)
    if findings.blockers:
        return 1
    if args.strict_warnings and findings.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
