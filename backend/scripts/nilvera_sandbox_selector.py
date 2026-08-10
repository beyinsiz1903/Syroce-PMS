"""Select exactly one Nilvera Sandbox E2E target."""

import os
import sys

SANDBOX_FILE = "tests/integration/test_nilvera_sandbox_e2e.py"
INCOMING_ANSWER_TARGET = f"{SANDBOX_FILE}::test_sandbox_incoming_commercial_invoice_answer_contract"
INCOMING_FIXTURE_TARGET = f"{SANDBOX_FILE}::test_sandbox_prepare_incoming_commercial_invoice_fixture"
RECONCILIATION_TARGET = f"{SANDBOX_FILE}::test_sandbox_reconcile_incoming_commercial_invoice_fixture"


def select_test_target(
    *,
    run_outgoing_contract: bool = False,
    run_incoming_fixture: bool,
    run_incoming_answer: bool,
    run_reconciliation: bool = False,
) -> str:
    if sum(
        (
            run_outgoing_contract,
            run_incoming_fixture,
            run_incoming_answer,
            run_reconciliation,
        )
    ) > 1:
        raise ValueError("BLOCKED_MUTUALLY_EXCLUSIVE_SANDBOX_MODES")
    if run_outgoing_contract:
        return SANDBOX_FILE
    if run_incoming_fixture:
        return INCOMING_FIXTURE_TARGET
    if run_incoming_answer:
        return INCOMING_ANSWER_TARGET
    if run_reconciliation:
        return RECONCILIATION_TARGET
    raise ValueError("BLOCKED_SANDBOX_MODE_REQUIRED")


def _read_bool(name: str) -> bool:
    value = os.environ.get(name, "false").strip().lower()
    if value not in {"true", "false"}:
        raise ValueError("BLOCKED_INVALID_SANDBOX_WORKFLOW_INPUT")
    return value == "true"


def main() -> int:
    try:
        target = select_test_target(
            run_outgoing_contract=_read_bool("NILVERA_E2E_RUN_OUTGOING_CONTRACT"),
            run_incoming_fixture=_read_bool("NILVERA_E2E_RUN_INCOMING_FIXTURE"),
            run_incoming_answer=_read_bool("NILVERA_E2E_RUN_INCOMING_ANSWER"),
            run_reconciliation=_read_bool("NILVERA_E2E_RUN_RECONCILIATION"),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
