"""Tests for strict fail-closed Nilvera Alias Selection Policy."""

import pytest

from core.integrations.nilvera.alias import resolve_receiver_alias
from core.integrations.nilvera.errors import NilveraBusinessRuleError


def test_empty_list_raises_error():
    with pytest.raises(NilveraBusinessRuleError) as exc:
        resolve_receiver_alias([])
    assert "geçerli aktif etiketi bulunamadı" in str(exc.value)


def test_whitespace_only_aliases_raises_error():
    with pytest.raises(NilveraBusinessRuleError) as exc:
        resolve_receiver_alias(["", "   ", "\t"])
    assert "geçerli aktif etiketi bulunamadı" in str(exc.value)


def test_single_valid_alias_returned():
    assert resolve_receiver_alias(["urn:mail:mypk"]) == "urn:mail:mypk"


def test_exact_duplicates_treated_as_single_alias():
    aliases = ["urn:mail:mypk", "urn:mail:mypk", "  ", "urn:mail:mypk"]
    assert resolve_receiver_alias(aliases) == "urn:mail:mypk"


def test_single_alias_matching_preference_returned():
    assert resolve_receiver_alias(["urn:mail:mypk"], preferred_alias="urn:mail:mypk") == "urn:mail:mypk"


def test_single_alias_mismatching_preference_raises_error():
    with pytest.raises(NilveraBusinessRuleError) as exc:
        resolve_receiver_alias(["urn:mail:mypk"], preferred_alias="urn:mail:otherpk")
    assert "eşleşmiyor" in str(exc.value)
    # Ensure real alias is NOT in the error message for security/log-cleanliness
    assert "urn:mail:mypk" not in str(exc.value)
    assert "urn:mail:otherpk" not in str(exc.value)


def test_multiple_aliases_no_preference_raises_error():
    with pytest.raises(NilveraBusinessRuleError) as exc:
        resolve_receiver_alias(["urn:mail:pk1", "urn:mail:pk2"])
    assert "açık tercih gereklidir" in str(exc.value)
    assert "urn:mail" not in str(exc.value)


def test_multiple_aliases_matching_preference_returned():
    aliases = ["urn:mail:pk1", "urn:mail:pk2"]
    assert resolve_receiver_alias(aliases, preferred_alias="urn:mail:pk2") == "urn:mail:pk2"


def test_multiple_aliases_mismatching_preference_raises_error():
    aliases = ["urn:mail:pk1", "urn:mail:pk2"]
    with pytest.raises(NilveraBusinessRuleError) as exc:
        resolve_receiver_alias(aliases, preferred_alias="urn:mail:pk3")
    assert "bulunamadı" in str(exc.value)
    assert "urn:mail" not in str(exc.value)


def test_preference_matching_is_case_sensitive():
    aliases = ["urn:mail:MYPK"]
    with pytest.raises(NilveraBusinessRuleError):
        resolve_receiver_alias(aliases, preferred_alias="urn:mail:mypk")

    aliases_multi = ["urn:mail:PK1", "urn:mail:PK2"]
    with pytest.raises(NilveraBusinessRuleError):
        resolve_receiver_alias(aliases_multi, preferred_alias="urn:mail:pk1")
