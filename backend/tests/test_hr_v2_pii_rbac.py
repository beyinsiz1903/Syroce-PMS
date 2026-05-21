"""HR v2 Foundation (Task #262) — PII masking + RBAC unit tests.

Direct unit tests for `_mask_hr_pii` and `_user_has_hr_op` helpers — DB or
FastAPI client booting yok; helper'lar pure (RolePermissionService + Permission
enum üzerinden çalışır). Test'ler şu doctrine'i doğrular:

- `manage_hr` perm'i olan kullanıcı: UNMASK (HR Admin / SUPER_ADMIN / SUPERVISOR).
- `view_hr` perm'i olan ama `manage_hr` olmayan kullanıcı: MASK (Finance).
- Hiç HR perm'i olmayan kullanıcı: MASK (Front Desk / Housekeeping).
- Self-service istisnası: kaydın id'i veya e-posta'sı kullanıcıyla
  eşleşiyorsa UNMASK (link table olmadan deterministic mapping).
- Boş e-posta self-match YASAK (anonymous record leak guard).
"""
from types import SimpleNamespace

import pytest

from backend.domains.hr.router import _mask_hr_pii, _user_has_hr_op  # type: ignore
from backend.models.enums import Permission, UserRole


def _user(role: UserRole, *, uid: str = "u-1", email: str = "u1@hotel.test",
          granted: list[Permission] | None = None):
    return SimpleNamespace(
        id=uid, email=email, role=role,
        granted_permissions=granted or [],
        tenant_id="t-1",
    )


SAMPLE = {
    "id": "s-1",
    "name": "Ayşe Yılmaz",
    "email": "ayse@hotel.test",
    "phone": "+905551234567",
    "national_id": "12345678901",
    "iban": "TR330006100519786457841326",
    "salary": 45000,
    "hourly_rate": 230.5,
    "monthly_salary": 45000,
}


class TestMaskHrPii:
    def test_super_admin_unmasks_all(self):
        u = _user(UserRole.SUPER_ADMIN)
        out = _mask_hr_pii(dict(SAMPLE), u)
        assert out["phone"] == SAMPLE["phone"]
        assert out["national_id"] == SAMPLE["national_id"]
        assert out["iban"] == SAMPLE["iban"]
        assert out["salary"] == SAMPLE["salary"]

    def test_admin_unmasks_all(self):
        # ADMIN should bypass via _is_super_admin or via MANAGE_HR grant in
        # ROLE_PERMISSIONS. Either way the unmask gate triggers.
        u = _user(UserRole.ADMIN)
        out = _mask_hr_pii(dict(SAMPLE), u)
        assert out["phone"] == SAMPLE["phone"]
        assert out["salary"] == SAMPLE["salary"]

    def test_supervisor_unmasks_all(self):
        u = _user(UserRole.SUPERVISOR)
        out = _mask_hr_pii(dict(SAMPLE), u)
        assert out["phone"] == SAMPLE["phone"]
        assert out["national_id"] == SAMPLE["national_id"]
        assert out["salary"] == SAMPLE["salary"]

    def test_finance_masks_pii(self):
        # Finance has VIEW_HR but NOT MANAGE_HR — must mask.
        u = _user(UserRole.FINANCE)
        out = _mask_hr_pii(dict(SAMPLE), u)
        assert out["phone"].startswith("***")
        assert out["phone"] != SAMPLE["phone"]
        assert out["national_id"].startswith("***-**-")
        assert out["iban"].startswith("****")
        assert out["salary"] is None
        assert out["hourly_rate"] is None
        assert out["monthly_salary"] is None
        # Non-PII passes through.
        assert out["name"] == SAMPLE["name"]
        assert out["email"] == SAMPLE["email"]

    def test_front_desk_masks_pii(self):
        u = _user(UserRole.FRONT_DESK)
        out = _mask_hr_pii(dict(SAMPLE), u)
        assert out["salary"] is None
        assert out["iban"].startswith("****")

    def test_housekeeping_masks_pii(self):
        u = _user(UserRole.HOUSEKEEPING)
        out = _mask_hr_pii(dict(SAMPLE), u)
        assert out["national_id"].startswith("***-**-")

    def test_self_unmask_by_id(self):
        # Finance + own record (id match) → unmask.
        u = _user(UserRole.FINANCE, uid="s-1")
        out = _mask_hr_pii(dict(SAMPLE), u, self_id="s-1")
        assert out["salary"] == SAMPLE["salary"]
        assert out["phone"] == SAMPLE["phone"]

    def test_self_unmask_by_email(self):
        # Finance + own record (email match) → unmask (link-table-less self map).
        u = _user(UserRole.FINANCE, uid="other-id", email="ayse@hotel.test")
        out = _mask_hr_pii(dict(SAMPLE), u, self_id="other-id",
                           self_email="ayse@hotel.test")
        assert out["salary"] == SAMPLE["salary"]

    def test_self_unmask_email_case_insensitive(self):
        u = _user(UserRole.FINANCE, uid="x", email="Ayse@Hotel.TEST")
        out = _mask_hr_pii(dict(SAMPLE), u, self_id="x",
                           self_email="Ayse@Hotel.TEST")
        assert out["salary"] == SAMPLE["salary"]

    def test_empty_email_does_not_self_unmask(self):
        # Record with empty email + user with empty email → must NOT unmask.
        rec = dict(SAMPLE)
        rec["email"] = ""
        u = _user(UserRole.FINANCE, uid="x", email="")
        out = _mask_hr_pii(rec, u, self_id="x", self_email="")
        assert out["salary"] is None
        assert out["phone"].startswith("***")

    def test_encrypted_pii_returns_empty(self):
        rec = dict(SAMPLE)
        rec["national_id"] = "aes256gcm:abc123=="
        rec["iban"] = "aes256gcm:zzz"
        rec["phone"] = "aes256gcm:pppp"
        u = _user(UserRole.FRONT_DESK)
        out = _mask_hr_pii(rec, u)
        assert out["national_id"] == ""
        assert out["iban"] == ""
        assert out["phone"] == ""

    def test_none_record_passthrough(self):
        assert _mask_hr_pii(None, _user(UserRole.FRONT_DESK)) is None

    def test_non_dict_record_passthrough(self):
        assert _mask_hr_pii("not-a-dict", _user(UserRole.FRONT_DESK)) == "not-a-dict"


class TestUserHasHrOp:
    def test_super_admin_has_all_hr_ops(self):
        u = _user(UserRole.SUPER_ADMIN)
        assert _user_has_hr_op(u, "view_hr") is True
        assert _user_has_hr_op(u, "manage_hr") is True

    def test_supervisor_has_both(self):
        u = _user(UserRole.SUPERVISOR)
        assert _user_has_hr_op(u, "view_hr") is True
        assert _user_has_hr_op(u, "manage_hr") is True

    def test_finance_has_view_not_manage(self):
        # Finance must read HR but cannot mutate (least-privilege per KVKK).
        u = _user(UserRole.FINANCE)
        assert _user_has_hr_op(u, "view_hr") is True
        assert _user_has_hr_op(u, "manage_hr") is False

    def test_front_desk_has_neither(self):
        u = _user(UserRole.FRONT_DESK)
        assert _user_has_hr_op(u, "view_hr") is False
        assert _user_has_hr_op(u, "manage_hr") is False

    def test_housekeeping_has_neither(self):
        u = _user(UserRole.HOUSEKEEPING)
        assert _user_has_hr_op(u, "view_hr") is False
        assert _user_has_hr_op(u, "manage_hr") is False
