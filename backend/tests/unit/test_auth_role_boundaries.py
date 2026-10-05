from routers.auth import _is_marketplace_identity


def test_marketplace_identity_is_kept_out_of_pms_user_model():
    assert _is_marketplace_identity({"role": "marketplace_agent"}) is True
    assert _is_marketplace_identity({"role": "user", "roles": ["marketplace_agent"]}) is True


def test_hotel_identity_remains_on_pms_login_path():
    assert _is_marketplace_identity({"role": "admin"}) is False
    assert _is_marketplace_identity({"role": "finance", "roles": ["finance"]}) is False
