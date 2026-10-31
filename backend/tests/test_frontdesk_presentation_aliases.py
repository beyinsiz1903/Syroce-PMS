"""Read-only presentation names must stay findable without tenant/PII widening."""
import json
from pathlib import Path

import pytest

from modules.pms_core.frontdesk_presentation import REGISTRY, TENANT, guest_alias_conditions, guest_alias_matches


def test_backend_and_frontend_share_the_exact_reviewed_registry():
    path = Path(__file__).resolve().parents[2] / "frontend/src/config/frontdeskPresentation.json"
    assert json.loads(path.read_text()) == REGISTRY
    assert len(REGISTRY["guests"]) == len({g["id"] for g in REGISTRY["guests"]}) == 46
    assert len({g["display"] for g in REGISTRY["guests"]}) == 46


@pytest.mark.parametrize("query", ["Ada Erdem", "ada", "ERDEM", "da erd"])
def test_natural_alias_is_found_by_case_prefix_or_infix(query):
    assert any(g["id"] == "3279058f-8264-564a-8ff4-dcab117ca64e" for g in guest_alias_matches(TENANT, query))


@pytest.mark.parametrize("query", ["İpek", "ipek", "IPEK", "İPEK"])
def test_turkish_dotted_and_dotless_letters_do_not_break_alias_lookup(query):
    assert any(g["display"] == "İpek Taner" for g in guest_alias_matches(TENANT, query))


@pytest.mark.parametrize("query", ["", " ", "a", "x" * 201, None, {}, ".*", "does-not-exist"])
def test_invalid_or_unknown_query_does_not_create_a_broad_condition(query):
    assert guest_alias_matches(TENANT, query) == []
    assert guest_alias_conditions(TENANT, query) == []


def test_other_tenants_never_receive_demo_alias_conditions():
    assert guest_alias_matches("other", "Ada Erdem") == []
    assert guest_alias_conditions("other", "Ada Erdem") == []


def test_alias_guest_lookup_is_guarded_by_reviewed_source_identity():
    conditions = guest_alias_conditions(TENANT, "Ada Erdem")
    assert conditions[0]["id"] == "3279058f-8264-564a-8ff4-dcab117ca64e"
    assert conditions[0]["$or"][0] == {"name": "Ada AcceptanceTest"}
    assert conditions[0]["$or"][1] == {"$and": [
        {"$or": [{"name": {"$exists": False}}, {"name": None}, {"name": ""}]},
        {"first_name": "Ada", "last_name": "AcceptanceTest"},
    ]}


def test_presentation_module_is_read_only_and_has_no_credentials_or_real_identity_fields():
    for row in REGISTRY["guests"]:
        assert set(row) == {"id", "original", "display"}
        assert not any(marker in row["display"].lower() for marker in ("demo", "test", "synthetic", "acceptance", "e2e"))
