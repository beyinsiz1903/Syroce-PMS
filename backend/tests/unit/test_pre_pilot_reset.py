from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from ops.pre_pilot_reset import (
    MODULE_USER_PROFILES,
    PRODUCTION_CONFIRMATION,
    RESET_CONFIRMATION,
    SEED_CONFIRMATION,
    SEED_PRODUCTION_CONFIRMATION,
    CollectionPlan,
    ResetPlan,
    build_module_user_specs,
    build_reset_plan,
    execute_reset,
    module_user_specs_approval_sha256,
    non_super_admin_filter,
    protected_tenant_filter,
    tenant_data_filter,
    tenant_delete_filter,
    validate_reset_execution_guard,
    validate_seed_execution_guard,
)


def _query_key(query: dict[str, Any]) -> str:
    return json.dumps(query, sort_keys=True, default=str)


class _Cursor:
    def __init__(self, documents: list[dict[str, Any]]):
        self._documents = documents

    async def to_list(self, length=None):
        return list(self._documents)


class _Collection:
    def __init__(
        self,
        *,
        find_documents: list[dict[str, Any]] | None = None,
        counts: dict[str, int] | None = None,
    ):
        self.find_documents = find_documents or []
        self.counts = counts or {}
        self.write_count = 0

    def find(self, _query, _projection=None) -> _Cursor:
        return _Cursor(self.find_documents)

    async def count_documents(self, query: dict[str, Any]) -> int:
        return self.counts.get(_query_key(query), 0)

    async def insert_one(self, _document):
        self.write_count += 1
        raise AssertionError("dry-run planner attempted a write")

    async def update_one(self, _query, _update):
        self.write_count += 1
        raise AssertionError("dry-run planner attempted a write")

    async def delete_many(self, _query):
        self.write_count += 1
        raise AssertionError("dry-run planner attempted a write")


class _Database:
    name = "hotel_pms_test"

    def __init__(self):
        protected_ids = ("tenant-protected",)
        candidate_filter = tenant_data_filter(protected_ids)
        protected_filter = protected_tenant_filter(protected_ids)
        protected_tenant_count_filter = {
            "$or": [
                {"id": {"$in": list(protected_ids)}},
                {"_id": {"$in": list(protected_ids)}},
            ]
        }
        self._collections = {
            "users": _Collection(
                find_documents=[{"id": "sa-1", "tenant_id": "tenant-protected"}],
                counts={_query_key(non_super_admin_filter()): 2},
            ),
            "tenants": _Collection(
                counts={
                    _query_key(tenant_delete_filter(protected_ids)): 1,
                    _query_key(protected_tenant_count_filter): 1,
                }
            ),
            "bookings": _Collection(
                counts={
                    _query_key({}): 3,
                    _query_key(candidate_filter): 2,
                    _query_key(protected_filter): 1,
                }
            ),
            "new_tenant_records": _Collection(
                counts={_query_key(candidate_filter): 1}
            ),
        }

    def __getattr__(self, name: str) -> _Collection:
        try:
            return self._collections[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, name: str) -> _Collection:
        return self._collections[name]

    async def list_collection_names(self) -> list[str]:
        return list(self._collections)


def _safe_plan() -> ResetPlan:
    return ResetPlan(
        database_name="hotel_pms_test",
        super_admin_count=1,
        super_admin_ids=("sa-1",),
        protected_tenant_ids=(),
        non_super_admin_user_count=2,
        removable_tenant_count=1,
        collections=(
            CollectionPlan(
                collection="users",
                delete_filter=non_super_admin_filter(),
                candidate_count=2,
                protected_count=1,
            ),
        ),
        unknown_tenant_collections=(),
        unknown_tenant_document_count=0,
    )


def _reset_env(environment: str = "test") -> dict[str, str]:
    return {
        "APP_ENV": environment,
        "PRE_PILOT_RESET_ALLOWED": "1",
        "PRE_PILOT_RESET_BACKUP_ATTESTED": "1",
    }


def _seed_env(environment: str = "test") -> dict[str, str]:
    return {
        "APP_ENV": environment,
        "PRE_PILOT_RBAC_SEED_ALLOWED": "1",
    }


@pytest.mark.asyncio
async def test_reset_planner_is_read_only_and_blocks_unknown_tenant_collections() -> None:
    database = _Database()

    plan = await build_reset_plan(database)

    assert plan.super_admin_ids == ("sa-1",)
    assert plan.protected_tenant_ids == ("tenant-protected",)
    assert plan.non_super_admin_user_count == 2
    assert plan.removable_tenant_count == 1
    assert plan.unknown_tenant_collections == ("new_tenant_records",)
    assert plan.blockers == ("BLOCKED_UNKNOWN_TENANT_COLLECTIONS",)
    assert all(collection.write_count == 0 for collection in database._collections.values())

    summary = plan.public_summary()
    assert summary["write_count"] == 0
    assert len(summary["approval_sha256"]) == 64
    assert "super_admin_ids" not in summary


def test_reset_plan_fingerprint_changes_with_reviewed_counts() -> None:
    first = _safe_plan()
    second = ResetPlan(
        **{
            **first.__dict__,
            "non_super_admin_user_count": first.non_super_admin_user_count + 1,
        }
    )

    assert first.approval_sha256 != second.approval_sha256


def test_reset_guard_accepts_exact_test_plan_only() -> None:
    plan = _safe_plan()

    validate_reset_execution_guard(
        execute=True,
        confirmation=RESET_CONFIRMATION,
        production_confirmation=None,
        expected_database_name=plan.database_name,
        expected_super_admin_count=1,
        approved_plan_sha256=plan.approval_sha256,
        plan=plan,
        environ=_reset_env(),
    )

    with pytest.raises(RuntimeError, match="BLOCKED_PRE_PILOT_RESET_PLAN_MISMATCH"):
        validate_reset_execution_guard(
            execute=True,
            confirmation=RESET_CONFIRMATION,
            production_confirmation=None,
            expected_database_name=plan.database_name,
            expected_super_admin_count=1,
            approved_plan_sha256="0" * 64,
            plan=plan,
            environ=_reset_env(),
        )


@pytest.mark.parametrize(
    ("environment", "expected_error"),
    [
        ("unknown", "BLOCKED_PRE_PILOT_ENVIRONMENT_UNKNOWN"),
        ("", "BLOCKED_PRE_PILOT_ENVIRONMENT_UNKNOWN"),
    ],
)
def test_reset_guard_fails_closed_for_unknown_environment(
    environment: str,
    expected_error: str,
) -> None:
    plan = _safe_plan()
    env = _reset_env(environment)
    if not environment:
        env.pop("APP_ENV")

    with pytest.raises(RuntimeError, match=expected_error):
        validate_reset_execution_guard(
            execute=True,
            confirmation=RESET_CONFIRMATION,
            production_confirmation=None,
            expected_database_name=plan.database_name,
            expected_super_admin_count=1,
            approved_plan_sha256=plan.approval_sha256,
            plan=plan,
            environ=env,
        )


def test_production_reset_requires_second_flag_and_confirmation() -> None:
    plan = _safe_plan()
    env = _reset_env("production")

    with pytest.raises(RuntimeError, match="BLOCKED_PRE_PILOT_PRODUCTION_RESET_NOT_ALLOWED"):
        validate_reset_execution_guard(
            execute=True,
            confirmation=RESET_CONFIRMATION,
            production_confirmation=PRODUCTION_CONFIRMATION,
            expected_database_name=plan.database_name,
            expected_super_admin_count=1,
            approved_plan_sha256=plan.approval_sha256,
            plan=plan,
            environ=env,
        )

    env["PRE_PILOT_RESET_PRODUCTION_ALLOWED"] = "1"
    validate_reset_execution_guard(
        execute=True,
        confirmation=RESET_CONFIRMATION,
        production_confirmation=PRODUCTION_CONFIRMATION,
        expected_database_name=plan.database_name,
        expected_super_admin_count=1,
        approved_plan_sha256=plan.approval_sha256,
        plan=plan,
        environ=env,
    )


@pytest.mark.asyncio
async def test_execute_reset_rejects_before_first_write_when_guard_fails() -> None:
    plan = _safe_plan()
    audit_collection = _Collection()
    database = SimpleNamespace(
        name=plan.database_name,
        pre_pilot_reset_runs=audit_collection,
    )

    with pytest.raises(RuntimeError, match="BLOCKED_PRE_PILOT_RESET_NOT_ALLOWED"):
        await execute_reset(
            database,
            plan,
            confirmation=RESET_CONFIRMATION,
            production_confirmation=None,
            expected_database_name=plan.database_name,
            expected_super_admin_count=1,
            approved_plan_sha256=plan.approval_sha256,
            environ={"APP_ENV": "test"},
        )

    assert audit_collection.write_count == 0


def test_module_user_specs_are_deterministic_unique_and_pii_safe() -> None:
    first = build_module_user_specs("tenant-1", "pilot.example.com")
    second = build_module_user_specs("tenant-1", "pilot.example.com")

    assert first == second
    assert len(first) == len(MODULE_USER_PROFILES) == 14
    assert len({spec.id for spec in first}) == len(first)
    assert len({spec.username for spec in first}) == len(first)
    assert all(spec.role == "staff" for spec in first)
    assert all("dashboard" in spec.module_scopes for spec in first)
    assert all("profile" in spec.module_scopes for spec in first)
    assert all("email" not in spec.public_summary() for spec in first)
    assert len(module_user_specs_approval_sha256(first)) == 64
    assert module_user_specs_approval_sha256(first) != module_user_specs_approval_sha256(
        build_module_user_specs("tenant-2", "pilot.example.com")
    )


def test_seed_guard_requires_exact_reviewed_fingerprint() -> None:
    specs = build_module_user_specs("tenant-1", "pilot.example.com")
    fingerprint = module_user_specs_approval_sha256(specs)

    validate_seed_execution_guard(
        execute=True,
        confirmation=SEED_CONFIRMATION,
        production_confirmation=None,
        expected_database_name="hotel_pms_test",
        actual_database_name="hotel_pms_test",
        approved_plan_sha256=fingerprint,
        actual_plan_sha256=fingerprint,
        environ=_seed_env(),
    )

    with pytest.raises(RuntimeError, match="BLOCKED_PRE_PILOT_RBAC_SEED_PLAN_MISMATCH"):
        validate_seed_execution_guard(
            execute=True,
            confirmation=SEED_CONFIRMATION,
            production_confirmation=None,
            expected_database_name="hotel_pms_test",
            actual_database_name="hotel_pms_test",
            approved_plan_sha256="f" * 64,
            actual_plan_sha256=fingerprint,
            environ=_seed_env(),
        )


def test_production_seed_requires_separate_confirmation() -> None:
    specs = build_module_user_specs("tenant-1", "pilot.example.com")
    fingerprint = module_user_specs_approval_sha256(specs)
    env = _seed_env("production")

    with pytest.raises(RuntimeError, match="BLOCKED_PRE_PILOT_RBAC_SEED_PRODUCTION_NOT_ALLOWED"):
        validate_seed_execution_guard(
            execute=True,
            confirmation=SEED_CONFIRMATION,
            production_confirmation=SEED_PRODUCTION_CONFIRMATION,
            expected_database_name="hotel_pms_test",
            actual_database_name="hotel_pms_test",
            approved_plan_sha256=fingerprint,
            actual_plan_sha256=fingerprint,
            environ=env,
        )

    env["PRE_PILOT_RBAC_SEED_PRODUCTION_ALLOWED"] = "1"
    validate_seed_execution_guard(
        execute=True,
        confirmation=SEED_CONFIRMATION,
        production_confirmation=SEED_PRODUCTION_CONFIRMATION,
        expected_database_name="hotel_pms_test",
        actual_database_name="hotel_pms_test",
        approved_plan_sha256=fingerprint,
        actual_plan_sha256=fingerprint,
        environ=env,
    )
