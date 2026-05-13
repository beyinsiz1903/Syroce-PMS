#!/usr/bin/env python3
"""
CM Backlog Alarm — Cron-friendly threshold alert for outbox + breakers
=======================================================================
Reads ``backend/infra/cm_observability_check.get_cm_observability_snapshot``
and exits with a verdict-coded status so cron / Sentry-cron / Replit
scheduled jobs can route alerts.

Run modes:
  $ python backend/scripts/cm_backlog_alert.py
  $ python backend/scripts/cm_backlog_alert.py --json    # machine output
  $ python backend/scripts/cm_backlog_alert.py --quiet   # no stdout on OK

Exit codes (the cron's only contract):
  0 → OK / DEGRADED-but-not-failing (no page)
  1 → FAIL — outbox or breaker state crossed the FAIL threshold;
              page the on-call and check the dashboard pill banner.
  2 → SCRIPT ERROR (db unreachable, env malformed) — page DBA, not on-call.

Sentry routing (recommended):
  * Wrap this command with ``sentry-cli monitors run cm-backlog -- \\
      python backend/scripts/cm_backlog_alert.py --json``
  * Configure the monitor's failure_issue_threshold = 1 so a single
    exit-1 raises an issue.

Privacy: stdout/stderr never include tenant_ids, IPs, or event payloads
— only counts + threshold reasons. Safe to log to public CI sinks.
"""
import argparse
import asyncio
import json
import logging
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="Emit JSON snapshot to stdout")
    p.add_argument("--quiet", action="store_true", help="Suppress stdout when verdict is OK")
    p.add_argument(
        "--treat-degraded-as-fail",
        action="store_true",
        help="Exit 1 on DEGRADED verdict too (stricter cron policy)",
    )
    p.add_argument(
        "--sentry-capture",
        action="store_true",
        help=(
            "If SENTRY_DSN is set, push FAIL verdict and sampler errors as "
            "Sentry events with subsystem=cm-backlog tag (in-process "
            "alternative to sentry-cli monitor wrap; both can coexist)."
        ),
    )
    return p


def _sentry_capture(level: str, message: str, extra: dict | None = None) -> None:
    """Best-effort Sentry capture for cron context.

    Never raises. Tags follow the SENTRY_ALERT_POLICY.md taxonomy:
      subsystem=cm-backlog, severity=warning|error|fatal.
    No tenant_ids, IPs, or payloads are forwarded — only counts +
    threshold reasons (already scrub-safe in cm_observability_check).
    """
    try:
        if not os.environ.get("SENTRY_DSN"):
            return
        import sentry_sdk

        if not sentry_sdk.Hub.current.client:
            sentry_sdk.init(
                dsn=os.environ["SENTRY_DSN"],
                environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
                send_default_pii=False,
                traces_sample_rate=0.0,
            )
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("subsystem", "cm-backlog")
            scope.set_tag("severity", level)
            scope.set_tag("source", "cm_backlog_alert.py")
            if extra:
                for k, v in extra.items():
                    if k in ("backlog", "failed", "oldest_seconds", "open", "verdict"):
                        scope.set_tag(k, str(v))
            sentry_sdk.capture_message(message, level="error" if level == "fatal" else level)
    except Exception:
        pass


async def _run(args) -> int:
    # Lazy import — script may be invoked outside an app context where
    # the DB module isn't on sys.path until the workdir is set correctly.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from core.database import db
        from infra.cm_observability_check import get_cm_observability_snapshot
    except Exception as e:
        sys.stderr.write(f"[FATAL] import error: {type(e).__name__}: {e}\n")
        if args.sentry_capture:
            _sentry_capture("fatal", f"cm_backlog_alert import error: {type(e).__name__}")
        return 2

    try:
        snapshot = await get_cm_observability_snapshot(db)
    except Exception as e:
        sys.stderr.write(f"[FATAL] snapshot error: {type(e).__name__}: {e}\n")
        if args.sentry_capture:
            _sentry_capture("fatal", f"cm_backlog_alert snapshot error: {type(e).__name__}")
        return 2

    verdict = snapshot.get("verdict", "unknown")

    if args.json:
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        if not (args.quiet and verdict == "ok"):
            outbox = snapshot.get("outbox", {})
            cb = snapshot.get("circuit_breakers", {})
            print(
                f"[{verdict.upper()}] outbox: backlog={outbox.get('backlog')}, "
                f"failed={outbox.get('failed')}, "
                f"oldest={outbox.get('oldest_seconds')}s | "
                f"breakers: open={cb.get('open')}, "
                f"half_open={cb.get('half_open')}, total={cb.get('total')}"
            )
            for r in (outbox.get("reasons") or []) + (cb.get("reasons") or []):
                print(f"  • {r}")

    if verdict == "fail":
        if args.sentry_capture:
            outbox = snapshot.get("outbox", {})
            cb = snapshot.get("circuit_breakers", {})
            _sentry_capture(
                "error",
                "CM backlog FAIL: " + "; ".join(
                    (outbox.get("reasons") or []) + (cb.get("reasons") or [])
                )[:500],
                extra={
                    "verdict": verdict,
                    "backlog": outbox.get("backlog"),
                    "failed": outbox.get("failed"),
                    "oldest_seconds": outbox.get("oldest_seconds"),
                    "open": cb.get("open"),
                },
            )
        return 1
    if verdict == "degraded" and args.treat_degraded_as_fail:
        return 1
    # "unknown" verdict = sampler error (DB unreachable, etc.). Cron must
    # NOT silently pass — escalate to DBA queue (exit 2) so the on-call
    # rotation differentiates "real CM problem" (exit 1) from "we can't
    # measure CM at all" (exit 2). The outbox or breakers sub-block will
    # carry an `error_type` field to triage from logs.
    if verdict == "unknown":
        outbox_err = (snapshot.get("outbox") or {}).get("error_type")
        cb_err = (snapshot.get("circuit_breakers") or {}).get("error_type")
        if outbox_err or cb_err:
            sys.stderr.write(
                f"[FATAL] sampler error — outbox={outbox_err} "
                f"breakers={cb_err}\n"
            )
            if args.sentry_capture:
                _sentry_capture(
                    "fatal",
                    f"cm_backlog_alert sampler error: outbox={outbox_err} breakers={cb_err}",
                )
            return 2
    return 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    # Cron context fallback: backend/start.sh aliases MONGO_URL=$MONGO_ATLAS_URI for
    # the long-running app, but cron jobs don't go through start.sh. Without this
    # fallback, this script would silently default to localhost:27017 (see
    # core/database.py:19) and report verdict=unknown every cycle in production.
    if not os.environ.get("MONGO_URL") and os.environ.get("MONGO_ATLAS_URI"):
        os.environ["MONGO_URL"] = os.environ["MONGO_ATLAS_URI"]
    args = _build_parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
