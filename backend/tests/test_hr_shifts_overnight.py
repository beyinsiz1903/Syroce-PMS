"""Task #258 — Regression coverage for overnight shift contract + overlap guard.

Task #255 introduced `crosses_midnight` on POST /api/hr/shifts and switched
overlap detection to datetime semantics. These tests pin that contract:

  a) crosses_midnight=True + end < start              → 201
  b) crosses_midnight=True + end >= start             → 422
  c) crosses_midnight=False + end <= start            → 422
  d) night shift (22:00-06:00) + next-morning 05:00-09:00 same staff → 409
  e) night shift (22:00-06:00) + next-morning 07:00-15:00 same staff → 201

Lives as a live HTTP integration test against the demo backend (port 8000)
to match the existing conftest fixture pattern (cf. test_inventory_negative_stock_guard).
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


def _future_date(offset_days: int) -> str:
    """Pick a date well in the future to avoid clobbering existing schedules."""
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _pick_staff_id(headers):
    """Resolve a staff_id usable for shift creation against this tenant.

    The demo user IS staff in many seeds (derived from `users`), so falling
    back to /api/auth/me is sufficient when /api/hr/staff is empty or gated.
    """
    r = requests.get(f"{BASE_URL}/api/hr/staff", headers=headers, timeout=15)
    if r.status_code == 200:
        body = r.json() if r.content else {}
        staff = (
            body.get("staff")
            or body.get("staff_members")
            or body.get("items")
            or (body if isinstance(body, list) else [])
        )
        for s in staff or []:
            sid = s.get("id") if isinstance(s, dict) else None
            if sid:
                return sid
    # Fallback to self — `_verify_staff_in_tenant` accepts derived staff.
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=15)
    if me.status_code == 200:
        sid = me.json().get("id")
        if sid:
            return sid
    pytest.skip("could not resolve a staff_id for the demo tenant")


def _create_shift(headers, *, staff_id, shift_date, start_time, end_time,
                  crosses_midnight, shift_type=None, notes=None):
    payload = {
        "staff_id": staff_id,
        "shift_date": shift_date,
        "shift_type": shift_type or ("night" if crosses_midnight else "morning"),
        "start_time": start_time,
        "end_time": end_time,
        "crosses_midnight": crosses_midnight,
        "notes": notes or f"task#258 {uuid.uuid4().hex[:8]}",
    }
    return requests.post(
        f"{BASE_URL}/api/hr/shifts",
        json=payload,
        headers=headers,
        timeout=15,
    )


def _delete_shift(headers, shift_id):
    if not shift_id:
        return
    try:
        requests.delete(
            f"{BASE_URL}/api/hr/shifts/{shift_id}",
            headers=headers,
            timeout=15,
        )
    except Exception:
        pass


@pytest.fixture
def staff_id(demo_auth_headers):
    return _pick_staff_id(demo_auth_headers)


def _skip_if_unauthorized(resp):
    if resp.status_code in (401, 403):
        pytest.skip(f"demo user lacks HR shifts perm (status={resp.status_code})")


class TestOvernightShiftContract:
    def test_a_overnight_end_before_start_accepted(self, demo_auth_headers, staff_id):
        d = _future_date(40)
        r = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="22:00",
            end_time="06:00",
            crosses_midnight=True,
        )
        _skip_if_unauthorized(r)
        sid = (r.json() or {}).get("shift", {}).get("id") if r.ok else None
        try:
            assert r.status_code in (200, 201), (
                f"overnight 22:00→06:00 must be accepted; got "
                f"{r.status_code} {r.text[:200]}"
            )
            body = r.json()
            assert body.get("shift", {}).get("crosses_midnight") is True
        finally:
            _delete_shift(demo_auth_headers, sid)

    def test_b_overnight_end_after_start_rejected(self, demo_auth_headers, staff_id):
        d = _future_date(41)
        r = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="09:00",
            end_time="17:00",
            crosses_midnight=True,
        )
        _skip_if_unauthorized(r)
        sid = (r.json() or {}).get("shift", {}).get("id") if r.ok else None
        try:
            assert r.status_code == 422, (
                f"crosses_midnight=True with end>=start must be 422; got "
                f"{r.status_code} {r.text[:200]}"
            )
            # Surface should explain the contradiction in Turkish.
            assert "gece vardiyas" in r.text.lower() or "overnight" in r.text.lower(), (
                f"422 body should explain overnight contradiction; got {r.text[:200]}"
            )
        finally:
            _delete_shift(demo_auth_headers, sid)

    def test_b2_overnight_equal_times_rejected(self, demo_auth_headers, staff_id):
        d = _future_date(42)
        r = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="08:00",
            end_time="08:00",
            crosses_midnight=True,
        )
        _skip_if_unauthorized(r)
        sid = (r.json() or {}).get("shift", {}).get("id") if r.ok else None
        try:
            assert r.status_code == 422, (
                f"crosses_midnight=True with end==start must be 422; got "
                f"{r.status_code} {r.text[:200]}"
            )
        finally:
            _delete_shift(demo_auth_headers, sid)

    def test_c_same_day_end_before_start_rejected(self, demo_auth_headers, staff_id):
        d = _future_date(43)
        r = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="17:00",
            end_time="09:00",
            crosses_midnight=False,
        )
        _skip_if_unauthorized(r)
        sid = (r.json() or {}).get("shift", {}).get("id") if r.ok else None
        try:
            assert r.status_code == 422, (
                f"crosses_midnight=False with end<=start must be 422; got "
                f"{r.status_code} {r.text[:200]}"
            )
            assert "gece vardiyas" in r.text.lower() or "sonra" in r.text.lower(), (
                f"422 body should hint operator to mark overnight; got {r.text[:200]}"
            )
        finally:
            _delete_shift(demo_auth_headers, sid)

    def test_c2_same_day_equal_times_rejected(self, demo_auth_headers, staff_id):
        d = _future_date(44)
        r = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="10:00",
            end_time="10:00",
            crosses_midnight=False,
        )
        _skip_if_unauthorized(r)
        sid = (r.json() or {}).get("shift", {}).get("id") if r.ok else None
        try:
            assert r.status_code == 422, (
                f"crosses_midnight=False with end==start must be 422; got "
                f"{r.status_code} {r.text[:200]}"
            )
        finally:
            _delete_shift(demo_auth_headers, sid)

    def test_d_overnight_then_overlapping_morning_conflicts(
        self, demo_auth_headers, staff_id
    ):
        d = _future_date(50)
        next_day = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        first = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="22:00",
            end_time="06:00",
            crosses_midnight=True,
        )
        _skip_if_unauthorized(first)
        sid1 = (first.json() or {}).get("shift", {}).get("id") if first.ok else None
        sid2 = None
        try:
            assert first.status_code in (200, 201), (
                f"baseline overnight create failed: "
                f"{first.status_code} {first.text[:200]}"
            )
            # 05:00-09:00 the next morning overlaps the [00:00, 06:00) leg
            # the helper recorded against `next_day`.
            second = _create_shift(
                demo_auth_headers,
                staff_id=staff_id,
                shift_date=next_day,
                start_time="05:00",
                end_time="09:00",
                crosses_midnight=False,
            )
            sid2 = (second.json() or {}).get("shift", {}).get("id") if second.ok else None
            assert second.status_code == 409, (
                f"overnight 22→06 + next-day 05→09 must conflict (409); got "
                f"{second.status_code} {second.text[:200]}"
            )
        finally:
            _delete_shift(demo_auth_headers, sid2)
            _delete_shift(demo_auth_headers, sid1)

    def test_e_overnight_then_non_overlapping_morning_accepted(
        self, demo_auth_headers, staff_id
    ):
        d = _future_date(55)
        next_day = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        first = _create_shift(
            demo_auth_headers,
            staff_id=staff_id,
            shift_date=d,
            start_time="22:00",
            end_time="06:00",
            crosses_midnight=True,
        )
        _skip_if_unauthorized(first)
        sid1 = (first.json() or {}).get("shift", {}).get("id") if first.ok else None
        sid2 = None
        try:
            assert first.status_code in (200, 201), (
                f"baseline overnight create failed: "
                f"{first.status_code} {first.text[:200]}"
            )
            # 07:00-15:00 starts after the [00:00, 06:00) leg ends.
            second = _create_shift(
                demo_auth_headers,
                staff_id=staff_id,
                shift_date=next_day,
                start_time="07:00",
                end_time="15:00",
                crosses_midnight=False,
            )
            sid2 = (second.json() or {}).get("shift", {}).get("id") if second.ok else None
            assert second.status_code in (200, 201), (
                f"overnight 22→06 + next-day 07→15 must NOT conflict; got "
                f"{second.status_code} {second.text[:200]}"
            )
        finally:
            _delete_shift(demo_auth_headers, sid2)
            _delete_shift(demo_auth_headers, sid1)
