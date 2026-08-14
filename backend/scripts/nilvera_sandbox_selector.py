"""Select exactly one Nilvera Sandbox E2E target."""

import os
import sys

SANDBOX_FILE = "tests/integration/test_nilvera_sandbox_e2e.py"
CREATE_RETURN_DISCOVERY_FILE = "tests/integration/test_nilvera_create_return_discovery_v2.py"
CREATE_RETURN_RECONCILIATION_FILE = "tests/integration/test_nilvera_create_return_historical_terminal.py"
INCOMING_ANSWER_TARGET = f"{SANDBOX_FILE}::test_sandbox_incoming_commercial_invoice_answer_contract"
INCOMING_ANSWER_DISCOVERY_TARGET = f"{SANDBOX_FILE}::test_sandbox_discover_incoming_commercial_invoice_answer_candidate"
INCOMING_FIXTURE_TARGET = f"{SANDBOX_FILE}::test_sandbox_prepare_incoming_commercial_invoice_fixture"
RECONCILIATION_TARGET = f"{SANDBOX_FILE}::test_sandbox_reconcile_incoming_commercial_invoice_fixture"
CREATE_RETURN_DISCOVERY_TARGET = (
    f"{CREATE_RETURN_DISCOVERY_FILE}::test_sandbox_create_return_contract_discovery_v2"
)
CREATE_RETURN_RECONCILIATION_TARGET = (
    f"{CREATE_RETURN_RECONCILIATION_FILE}::test_sandbox_reconcile_create_return_historical_ambiguity"
)
PREFLIGHT_TARGET = f"{SANDBOX_FILE}::test_sandbox_incoming_fixture_accounts_preflight"


def select_test_target(
    *,
    run_preflight: bool = False,
    run_outgoing_contract: bool = False,
    run_incoming_fixture: bool,
    run_incoming_answer: bool,
    run_incoming_answer_discovery: bool = False,
    run_reconciliation: bool = False,
    run_create_return_discovery: bool = False,
    run_create_return_reconciliation: bool = False,
) -> str:
    if (
        sum(
            (
                run_outgoing_contract,
                run_preflight,
                run_incoming_fixture,
                run_incoming_answer,
                run_incoming_answer_discovery,
                run_reconciliation,
                run_create_return_discovery,
                run_create_return_reconciliation,
            )
        )
        > 1
    ):
        raise ValueError("BLOCKED_MUTUALLY_EXCLUSIVE_SANDBOX_MODES")
    if run_preflight:
        return PREFLIGHT_TARGET
    if run_outgoing_contract:
        return SANDBOX_FILE
    if run_incoming_fixture:
        return INCOMING_FIXTURE_TARGET
    if run_incoming_answer:
        return INCOMING_ANSWER_TARGET
    if run_incoming_answer_discovery:
        return INCOMING_ANSWER_DISCOVERY_TARGET
    if run_reconciliation:
        return RECONCILIATION_TARGET
    if run_create_return_discovery:
        return CREATE_RETURN_DISCOVERY_TARGET
    if run_create_return_reconciliation:
        return CREATE_RETURN_RECONCILIATION_TARGET
    raise ValueError("BLOCKED_SANDBOX_MODE_REQUIRED")


def _read_bool(name: str) -> bool:
    value = os.environ.get(name, "false").strip().lower()
    if value not in {"true", "false"}:
        raise ValueError("BLOCKED_INVALID_SANDBOX_WORKFLOW_INPUT")
    return value == "true"


def main() -> int:
    try:
        target = select_test_target(
            run_preflight=_read_bool("NILVERA_E2E_RUN_PREFLIGHT"),
            run_outgoing_contract=_read_bool("NILVERA_E2E_RUN_OUTGOING_CONTRACT"),
            run_incoming_fixture=_read_bool("NILVERA_E2E_RUN_INCOMING_FIXTURE"),
            run_incoming_answer=_read_bool("NILVERA_E2E_RUN_INCOMING_ANSWER"),
            run_incoming_answer_discovery=_read_bool("NILVERA_E2E_RUN_INCOMING_ANSWER_DISCOVERY"),
            run_reconciliation=_read_bool("NILVERA_E2E_RUN_RECONCILIATION"),
            run_create_return_discovery=_read_bool("NILVERA_E2E_RUN_CREATE_RETURN_DISCOVERY"),
            run_create_return_reconciliation=_read_bool("NILVERA_E2E_RUN_CREATE_RETURN_RECONCILIATION"),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
