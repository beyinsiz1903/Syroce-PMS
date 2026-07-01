"""F8M § 40 (triage PC3) — GraphQL introspection policy unit tests.

Verifies:
  1. `_introspection_enabled()` is fail-closed for production/stress and
     honours an explicit GRAPHQL_INTROSPECTION opt-in.
  2. The NoSchemaIntrospectionCustomRule validation rule actually rejects
     introspection queries while leaving normal queries working.
"""

import strawberry
from graphql.validation import NoSchemaIntrospectionCustomRule
from strawberry.extensions import AddValidationRules

from graphql_api.schema import _introspection_enabled


# --- policy logic ---------------------------------------------------------

def test_explicit_opt_in_enables(monkeypatch):
    monkeypatch.setenv("GRAPHQL_INTROSPECTION", "true")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    assert _introspection_enabled() is True


def test_explicit_opt_out_disables(monkeypatch):
    monkeypatch.setenv("GRAPHQL_INTROSPECTION", "false")
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    assert _introspection_enabled() is False


def test_production_default_disabled(monkeypatch):
    monkeypatch.delenv("GRAPHQL_INTROSPECTION", raising=False)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    assert _introspection_enabled() is False


def test_stress_default_disabled(monkeypatch):
    monkeypatch.delenv("GRAPHQL_INTROSPECTION", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    monkeypatch.setenv("APP_ENV", "stress")
    assert _introspection_enabled() is False


def test_local_default_enabled(monkeypatch):
    monkeypatch.delenv("GRAPHQL_INTROSPECTION", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert _introspection_enabled() is True


# --- validation-rule mechanics --------------------------------------------

@strawberry.type
class _Q:
    @strawberry.field
    def ping(self) -> str:
        return "pong"


_INTROSPECTION = "{ __schema { types { name } } }"


def test_introspection_rejected_when_rule_applied():
    schema = strawberry.Schema(
        query=_Q,
        extensions=[AddValidationRules([NoSchemaIntrospectionCustomRule])],
    )
    result = schema.execute_sync(_INTROSPECTION)
    assert result.errors, "introspection must be rejected when rule applied"
    assert result.data is None
    # Normal query still works.
    ok = schema.execute_sync("{ ping }")
    assert not ok.errors
    assert ok.data == {"ping": "pong"}


def test_introspection_allowed_without_rule():
    schema = strawberry.Schema(query=_Q)
    result = schema.execute_sync(_INTROSPECTION)
    assert not result.errors
    assert result.data is not None and result.data.get("__schema") is not None
