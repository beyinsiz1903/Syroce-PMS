"""
User provisioning — saf (DB'siz) birim testleri.

Rol/paket (tier) dogrulama mantigi ve gecici sifre uretimi gibi saf fonksiyonlar
burada, hicbir DB/sunucu olmadan kosar. Privilege-escalation onleme (super_admin
vb. atanamaz) ve paket-duyarli rol haritasi bu testlerle cimlenir.
"""
import pytest

from domains.admin.router.users import (
    ASSIGNABLE_ROLES_BY_TIER,
    _assignable_roles_for_tier,
    _gen_temp_password,
    _normalize_tier,
)

# Tenant-admin tarafindan ASLA atanmamasi gereken yuksek/ozel roller.
_FORBIDDEN_ROLES = {
    "super_admin", "guest", "agency_admin", "agency_agent", "call_center_agent",
}


def test_normalize_tier_aliases():
    assert _normalize_tier("pro") == "professional"
    assert _normalize_tier("professional") == "professional"
    assert _normalize_tier("ultra") == "enterprise"
    assert _normalize_tier("enterprise") == "enterprise"
    assert _normalize_tier("basic") == "basic"
    assert _normalize_tier(None) == "basic"
    assert _normalize_tier("  PRO ") == "professional"
    assert _normalize_tier("bilinmeyen") == "basic"


def test_privileged_roles_never_assignable():
    for tier_roles in ASSIGNABLE_ROLES_BY_TIER.values():
        for forbidden in _FORBIDDEN_ROLES:
            assert forbidden not in tier_roles, (
                f"{forbidden} hicbir pakette atanabilir olmamali"
            )


def test_basic_tier_is_minimal():
    roles = set(_assignable_roles_for_tier("basic"))
    assert roles == {"admin", "staff"}


def test_tier_is_monotonic_superset():
    basic = set(_assignable_roles_for_tier("basic"))
    professional = set(_assignable_roles_for_tier("professional"))
    enterprise = set(_assignable_roles_for_tier("enterprise"))
    assert basic <= professional <= enterprise
    # sales yalniz enterprise'da
    assert "sales" in enterprise
    assert "sales" not in professional


def test_unknown_tier_falls_back_to_basic():
    assert _assignable_roles_for_tier("bilinmeyen") == _assignable_roles_for_tier("basic")


def test_temp_password_strength_and_uniqueness():
    p1 = _gen_temp_password()
    p2 = _gen_temp_password()
    assert len(p1) >= 12
    assert p1 != p2  # rastgele
    # belirsiz karakterler cikarilmis olmali
    for ch in ("0", "O", "1", "l", "I"):
        assert ch not in p1
