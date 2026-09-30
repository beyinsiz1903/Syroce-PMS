from types import SimpleNamespace

import pytest

from security.guest_data_visibility import (
    normalize_guest_data_visibility,
    protect_guest_row,
    user_guest_data_visibility,
)


def test_explicit_policy_is_user_specific_and_overrides_admin_role():
    user = SimpleNamespace(
        role="admin",
        granted_permissions=["view_guest_pii"],
        guest_data_visibility={"name": "hidden", "email": "masked"},
    )

    policy, source = user_guest_data_visibility(user)

    assert source == "user"
    assert policy["name"] == "hidden"
    assert policy["email"] == "masked"


def test_users_with_same_role_can_have_different_visibility():
    visible_user = SimpleNamespace(role="staff", guest_data_visibility={"identity": "full"})
    hidden_user = SimpleNamespace(role="staff", guest_data_visibility={"identity": "hidden"})
    row = {"guest_name": "Ayşe Yılmaz", "national_id": "12345678901"}

    assert protect_guest_row(row, visible_user)["national_id"] == "12345678901"
    assert protect_guest_row(row, hidden_user)["national_id"] is None


def test_protection_masks_and_hides_nested_guest_values():
    user = SimpleNamespace(
        role="staff",
        guest_data_visibility={
            "name": "masked",
            "email": "masked",
            "phone": "masked",
            "identity": "hidden",
            "birth_date": "hidden",
            "address": "hidden",
            "nationality": "hidden",
            "notes": "hidden",
            "financial": "hidden",
            "identity_photo": "hidden",
        },
    )
    protected = protect_guest_row(
        {
            "guest_name": "Ayşe Yılmaz",
            "email": "ayse@example.com",
            "phone": "05321234567",
            "passport_number": "U1234567",
            "total_amount": 9000,
            "guest": {"address": "Örnek Sokak", "notes": "VIP"},
        },
        user,
    )

    assert protected["guest_name"] != "Ayşe Yılmaz"
    assert protected["email"] == "a***@example.com"
    assert protected["phone"].endswith("4567")
    assert protected["passport_number"] is None
    assert protected["total_amount"] is None
    assert protected["guest"] == {"address": None, "notes": None}


@pytest.mark.parametrize(
    "policy",
    [
        {"unsupported": "hidden"},
        {"email": "sometimes"},
    ],
)
def test_invalid_policy_is_rejected(policy):
    with pytest.raises(ValueError):
        normalize_guest_data_visibility(policy)
