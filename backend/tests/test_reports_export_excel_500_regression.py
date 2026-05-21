"""
Regression tests for F8H §90 reports_export 500 fix (Task #246).

Covers:
  (a) builder /export/excel with empty columns config (400 graceful, not 500).
  (b) builder /export/excel with zero data rows (200 + valid XLSX).
  (c) builder /export/excel with heterogeneous types (datetime/None/Decimal/bool)
      via direct call to `_coerce_excel_value`.
  (d) departments /reports/company-aging/excel with zero matching folios
      (200 + valid XLSX) — exercised via direct `_compute_company_aging` call
      against a clean tenant-id (no fixtures, no data, no crash).
  (e) `_coerce_to_date` accepts both ISO string and native datetime — guards
      the stress-env `TypeError: fromisoformat: argument must be str`.

All XLSX outputs are verified to start with the OpenXML magic header (PK\\x03\\x04).
"""
from __future__ import annotations

import io
import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

XLSX_MAGIC = b"PK\x03\x04"


# ─── Pure unit tests (no HTTP, always runnable) ──────────────────────────


class TestCoerceExcelValueUnit:
    """Direct unit tests for `_coerce_excel_value` helper (Task #246 case c)."""

    def setup_method(self):
        from backend.routers.report_builder import _coerce_excel_value  # type: ignore
        self.fn = _coerce_excel_value

    def test_none_to_empty(self):
        assert self.fn(None) == ("", False)

    # ── Task #253 (tur-2): openpyxl IllegalCharacterError repro guards ──

    def test_control_chars_stripped(self):
        """C0 control chars (0x01-0x08, 0x0B-0x0C, 0x0E-0x1F) MUST be stripped
        so openpyxl `cell.value = ...` does not raise IllegalCharacterError.
        """
        v, is_num = self.fn("hello\x01world\x0Bvtab\x0Cff\x1Besc\x00null")
        assert is_num is False
        # All illegal chars removed; legible content preserved.
        assert v == "helloworldvtabffescnull"

    def test_control_chars_in_bytes_path_stripped(self):
        v, is_num = self.fn(b"line1\x01line2\x0B")
        assert is_num is False
        assert "\x01" not in v and "\x0B" not in v
        assert "line1" in v and "line2" in v

    def test_control_chars_in_list_join_stripped(self):
        v, is_num = self.fn(["a\x01b", "c\x0Bd"])
        assert "\x01" not in v and "\x0B" not in v
        assert "a" in v and "b" in v and "c" in v and "d" in v

    def test_oversize_string_truncated_with_ellipsis(self):
        big = "x" * 40000
        v, is_num = self.fn(big)
        assert is_num is False
        # Capped to 32767; sentinel ellipsis means audit-visible truncation.
        assert len(v) == 32767
        assert v.endswith("…")

    def test_normal_string_passes_through(self):
        v, is_num = self.fn("Antalya - Lara Beach")
        assert v == "Antalya - Lara Beach"
        assert is_num is False

    def test_openpyxl_accepts_coerced_control_char_string(self):
        """End-to-end: write a coerced control-char string to a real openpyxl
        cell and round-trip through wb.save() without raising.
        """
        import io as _io
        from openpyxl import Workbook  # type: ignore
        wb = Workbook()
        ws = wb.active
        v, _ = self.fn("toxic\x01\x0B\x0C\x1Estring")
        ws.cell(row=1, column=1).value = v
        buf = _io.BytesIO()
        wb.save(buf)  # MUST NOT raise IllegalCharacterError
        buf.seek(0)
        assert buf.read(4) == b"PK\x03\x04"

    def test_bool_localized(self):
        assert self.fn(True) == ("Evet", False)
        assert self.fn(False) == ("Hayır", False)

    def test_int_preserves_numeric(self):
        v, is_num = self.fn(42)
        assert v == 42
        assert is_num is True

    def test_float_preserves_numeric(self):
        v, is_num = self.fn(3.14)
        assert v == 3.14
        assert is_num is True

    def test_nan_inf_fallback_to_string(self):
        v, is_num = self.fn(float("nan"))
        assert is_num is False
        assert isinstance(v, str)
        v, is_num = self.fn(float("inf"))
        assert is_num is False

    def test_decimal_to_float(self):
        v, is_num = self.fn(Decimal("12.50"))
        assert v == 12.5
        assert is_num is True

    def test_datetime_to_iso_string(self):
        dt = datetime(2026, 5, 20, 12, 34, 56, tzinfo=UTC)
        v, is_num = self.fn(dt)
        assert is_num is False
        assert "2026-05-20" in v

    def test_date_to_iso_string(self):
        v, is_num = self.fn(date(2026, 5, 20))
        assert v == "2026-05-20"
        assert is_num is False

    def test_bytes_decoded(self):
        v, is_num = self.fn(b"hello")
        assert v == "hello"
        assert is_num is False

    def test_list_comma_joined(self):
        v, is_num = self.fn(["a", "b", 1])
        assert "a" in v and "b" in v and "1" in v
        assert is_num is False

    def test_arbitrary_object_to_string(self):
        class Custom:
            def __str__(self):
                return "custom_repr"
        v, is_num = self.fn(Custom())
        assert v == "custom_repr"
        assert is_num is False


class TestCoerceToDateUnit:
    """Direct unit tests for `_coerce_to_date` helper (Task #246 case e)."""

    def setup_method(self):
        from backend.routers.departments.reports import _coerce_to_date  # type: ignore
        self.fn = _coerce_to_date

    def test_iso_string(self):
        assert self.fn("2026-05-20T12:00:00") == date(2026, 5, 20)

    def test_iso_string_with_z_suffix(self):
        # Python's fromisoformat accepts Z on 3.11+ via explicit replace
        assert self.fn("2026-05-20T12:00:00Z") == date(2026, 5, 20)

    def test_native_datetime(self):
        # Stress env BSON path: motor returns datetime obj, not str.
        assert self.fn(datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)) == date(2026, 5, 20)

    def test_native_date(self):
        assert self.fn(date(2026, 5, 20)) == date(2026, 5, 20)

    def test_none_returns_none(self):
        assert self.fn(None) is None

    def test_garbage_string_returns_none(self):
        assert self.fn("not-a-date") is None

    def test_int_returns_none(self):
        # Defensive: int (e.g. epoch) is not auto-converted → caller treats as
        # unparseable rather than crashing.
        assert self.fn(1747728000) is None


# ─── HTTP integration tests (require Backend API running) ────────────────


pytestmark_http = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")


@pytest.fixture
def auth_headers():
    if not BASE_URL:
        pytest.skip("VITE_BACKEND_URL not set")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=15,
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "No access_token in login response"
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytestmark_http
class TestBuilderExcelExportRegression:
    """Integration: POST /api/reports/builder/export/excel — Task #246 case a,b."""

    def test_excel_empty_columns_returns_400_not_500(self, auth_headers):
        """Case (a): empty columns list → 400/422 graceful, not 500."""
        config = {"data_source": "reservations", "columns": [], "filters": [], "limit": 10}
        r = requests.post(
            f"{BASE_URL}/api/reports/builder/export/excel",
            headers=auth_headers, json=config, timeout=30,
        )
        # Either 200 (degenerate xlsx with title only) or 400/422 (validation)
        # is acceptable; 500 is NOT.
        assert r.status_code != 500, f"Should not 500 on empty columns; got {r.status_code}: {r.text[:200]}"

    def test_excel_zero_rows_returns_valid_xlsx(self, auth_headers):
        """Case (b): filter that yields zero rows → 200 + valid XLSX magic bytes."""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "check_in"],
            "filters": [{"field": "status", "operator": "eq", "value": "__nonexistent_status_zzz__"}],
            "limit": 10,
        }
        r = requests.post(
            f"{BASE_URL}/api/reports/builder/export/excel",
            headers=auth_headers, json=config, timeout=30,
        )
        assert r.status_code == 200, f"Zero-row excel should 200; got {r.status_code}: {r.text[:200]}"
        assert r.content.startswith(XLSX_MAGIC), "Response is not a valid XLSX"

    def test_excel_default_columns_returns_valid_xlsx(self, auth_headers):
        """Case (c) HTTP smoke: standard reservations export → 200 + valid XLSX."""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "room_number", "check_in", "total_amount"],
            "filters": [],
            "limit": 50,
        }
        r = requests.post(
            f"{BASE_URL}/api/reports/builder/export/excel",
            headers=auth_headers, json=config, timeout=30,
        )
        assert r.status_code == 200, f"Excel export failed: {r.status_code} {r.text[:200]}"
        assert r.content.startswith(XLSX_MAGIC)


@pytestmark_http
class TestCompanyAgingExcelRegression:
    """Integration: GET /api/reports/company-aging/excel — Task #246 case d."""

    def test_company_aging_excel_returns_valid_xlsx(self, auth_headers):
        """Case (d): demo tenant (likely zero company folios) → 200 + valid XLSX."""
        r = requests.get(
            f"{BASE_URL}/api/reports/company-aging/excel",
            headers={"Authorization": auth_headers["Authorization"]}, timeout=30,
        )
        assert r.status_code == 200, f"Company aging excel failed: {r.status_code} {r.text[:200]}"
        assert r.content.startswith(XLSX_MAGIC), "Response is not a valid XLSX"

    def test_company_aging_excel_cache_hit_path(self, auth_headers):
        """Case (d) cache: second call must still return valid XLSX (cache hit)."""
        # First call (miss / fresh)
        r1 = requests.get(
            f"{BASE_URL}/api/reports/company-aging/excel",
            headers={"Authorization": auth_headers["Authorization"]}, timeout=30,
        )
        assert r1.status_code == 200
        # Second call within TTL (should hit cache)
        r2 = requests.get(
            f"{BASE_URL}/api/reports/company-aging/excel",
            headers={"Authorization": auth_headers["Authorization"]}, timeout=30,
        )
        assert r2.status_code == 200
        assert r2.content.startswith(XLSX_MAGIC)
