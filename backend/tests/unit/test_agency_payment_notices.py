"""Agency reports a payment on an agreed statement; the hotel verifies or rejects it."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.agency_statements import outstanding
from routers import agency_statements as st

USER = SimpleNamespace(id="u", email="ops@hotel.test", tenant_id="t1", role="admin", roles=[])
AGENCY = {"agency_id": "a1", "user": {"email": "acente@example.com"}}


class _Store:
    """agency_statements double: field equality, array-index guards, $elemMatch + positional $."""

    def __init__(self, doc):
        self.doc = doc

    def _match(self, query):
        d = self.doc
        for key, cond in query.items():
            if key in ("payment_notices", "payments") and isinstance(cond, dict) and "$elemMatch" in cond:
                if not any(all(item.get(k) == v for k, v in cond["$elemMatch"].items()) for item in d.get(key) or []):
                    return False
            elif "." in key:
                field, index, *rest = key.split(".")
                items = d.get(field) or []
                item = items[int(index)] if int(index) < len(items) else None
                if isinstance(cond, dict) and "$exists" in cond:
                    if (item is not None) != cond["$exists"]:
                        return False
                elif item is None or item.get(rest[0]) != cond:
                    return False
            elif isinstance(cond, dict) and "$in" in cond:
                if d.get(key) not in cond["$in"]:
                    return False
            elif d.get(key) != cond:
                return False
        return True

    async def find_one(self, query, *_a, **_k):
        return copy.deepcopy(self.doc) if self._match(query) else None

    async def find_one_and_update(self, query, update, array_filters=None, **_k):
        if not self._match(query):
            return None
        for key, value in update.get("$set", {}).items():
            if key.startswith("payment_notices.$[n]."):
                flt = {k[2:]: v for k, v in array_filters[0].items()}
                for item in self.doc["payment_notices"]:
                    if all(item.get(k) == v for k, v in flt.items()):
                        item[key.split(".", 2)[2]] = value
        update = {**update, "$set": {k: v for k, v in update.get("$set", {}).items() if not k.startswith("payment_notices.$[n].")}}
        elem = (query.get("payment_notices") or {}).get("$elemMatch") if isinstance(query.get("payment_notices"), dict) else None
        target = next((n for n in self.doc.get("payment_notices") or [] if all(n.get(k) == v for k, v in elem.items())), None) if elem else None
        for key, value in update.get("$set", {}).items():
            if key.startswith("payment_notices.$."):
                target[key.split(".", 2)[2]] = value
            else:
                self.doc[key] = value
        for key, value in update.get("$push", {}).items():
            self.doc.setdefault(key, []).append(copy.deepcopy(value))
        return copy.deepcopy(self.doc)


@pytest.fixture
def world(monkeypatch, tmp_path):
    import importlib

    doc = {"id": "s1", "tenant_id": "t1", "agency_id": "a1", "number": "EKS-1", "currency": "TRY", "status": "agreed",
           "hotel_name": "Demo", "agency_name": "Test", "payments": [], "totals": {"net_balance": 6800.0}}
    store = _Store(doc)
    monkeypatch.setattr(st, "get_system_db", lambda: SimpleNamespace(agency_statements=store))
    monkeypatch.setattr(st, "_notify_agency", AsyncMock())
    monkeypatch.setattr(st, "_notify_hotel", AsyncMock())
    monkeypatch.setattr(st, "_require_hotel_admin", lambda _u: "t1")
    monkeypatch.setattr(importlib.import_module("routers.uploads"), "PRIVATE_UPLOAD_DIR", tmp_path / "_private")
    return store


async def _report(amount, reference, proof=None):
    return await st.report_payment("s1", amount=amount, paid_at="2026-10-15", reference=reference,
                                   method="bank_transfer", proof=proof, agency=AGENCY)


@pytest.mark.asyncio
async def test_report_then_verify_credits_the_statement(world):
    import io

    from fastapi import UploadFile

    pdf = UploadFile(io.BytesIO(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"), filename="dekont.pdf")
    reported = await _report(6800, "EFT-123", proof=pdf)
    notice = reported["payment_notices"][0]
    assert notice["status"] == "pending" and notice["has_proof"] and "proof_path" not in notice
    assert outstanding(world.doc) == 6800  # a report alone credits nothing
    st._notify_hotel.assert_awaited()

    verified = await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)
    assert verified["payment_notices"][0]["status"] == "verified"
    assert verified["status"] == "settled" and verified["outstanding"] == 0
    assert world.doc["payments"][0]["reference"] == "EFT-123"
    with pytest.raises(HTTPException):  # decided once
        await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)


@pytest.mark.asyncio
async def test_report_rules(world):
    with pytest.raises(HTTPException) as over:
        await _report(6801, "EFT-1")
    assert over.value.status_code == 409
    await _report(4000, "EFT-1")
    with pytest.raises(HTTPException) as pending_cap:  # 6800 - 4000 pending = 2800 left
        await _report(3000, "EFT-2")
    assert "kalan 2800.00" in pending_cap.value.detail
    with pytest.raises(HTTPException) as dup:
        await _report(100, "eft-1")
    assert dup.value.status_code == 409
    with pytest.raises(HTTPException) as other:
        await st.report_payment("s1", amount=10, paid_at="2026-10-15", reference="EFT-9", method="x", proof=None,
                                agency={"agency_id": "intruder"})
    assert other.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_requires_reason_and_frees_the_amount(world):
    notice = (await _report(6800, "EFT-7"))["payment_notices"][0]
    rejected = await st.reject_payment_notice("s1", notice["id"], st.NoticeRejection(note="Hesaba ulaşmadı"), USER)
    assert rejected["payment_notices"][0]["status"] == "rejected" and rejected["outstanding"] == 6800
    await _report(6800, "EFT-8")  # rejected amount no longer blocks a new report


@pytest.mark.asyncio
async def test_notice_needs_an_agreed_statement_with_agency_debt(world):
    world.doc["status"] = "issued"
    with pytest.raises(HTTPException):
        await _report(10, "EFT-3")
    world.doc.update(status="agreed", totals={"net_balance": -1200.0})  # hotel owes the agency
    with pytest.raises(HTTPException) as exc:
        await _report(10, "EFT-4")
    assert "bakiye yok" in exc.value.detail


@pytest.mark.asyncio
async def test_fake_pdf_proof_is_refused(world):
    import io

    from fastapi import UploadFile

    html = UploadFile(io.BytesIO(b"<html><script>alert(1)</script></html>"), filename="dekont.pdf")
    with pytest.raises(HTTPException) as exc:
        await _report(100, "EFT-5", proof=html)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_notifies_the_agency_once(world):
    notice = (await _report(6800, "EFT-11"))["payment_notices"][0]
    await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)
    titles = [call.args[2] for call in st._notify_agency.await_args_list]
    assert titles == ["ödeme bildiriminiz doğrulandı"]


@pytest.mark.asyncio
async def test_manual_payment_with_same_reference_closes_the_notice(world):
    notice = (await _report(3000, "EFT-12"))["payment_notices"][0]
    result = await st.record_payment("s1", st.PaymentCreate(amount=3000, direction="agency_to_hotel",
                                                            paid_at="2026-10-15", reference="eft-12 "), USER)
    assert result["payment_notices"][0]["status"] == "verified" and result["outstanding"] == 3800
    assert len(world.doc["payments"]) == 1  # the same money counted once
    with pytest.raises(HTTPException):
        await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)
    await _report(3800, "EFT-13")  # the verified notice no longer reserves the balance


@pytest.mark.asyncio
async def test_statement_with_pending_notice_cannot_be_voided(world):
    await _report(100, "EFT-14")
    with pytest.raises(HTTPException) as exc:
        await st.void_statement("s1", st.ResolveRequest(note="yeniden düzenle"), USER)
    assert exc.value.status_code == 409 and "ödeme bildirimi" in exc.value.detail


@pytest.mark.asyncio
async def test_reference_letter_case_cannot_pay_twice(world):
    await st.record_payment("s1", st.PaymentCreate(amount=3000, direction="agency_to_hotel", paid_at="2026-10-15", reference="eft-case"), USER)
    again = await st.record_payment("s1", st.PaymentCreate(amount=3000, direction="agency_to_hotel", paid_at="2026-10-15", reference=" EFT-CASE "), USER)
    assert len(world.doc["payments"]) == 1 and again["outstanding"] == 3800


@pytest.mark.asyncio
async def test_failed_decision_write_leaves_nothing_half_done_and_can_be_retried(world):
    notice = (await _report(6800, "EFT-20"))["payment_notices"][0]
    real = world.find_one_and_update
    world.find_one_and_update = AsyncMock(side_effect=RuntimeError("db down"))
    with pytest.raises(RuntimeError):
        await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)
    assert world.doc["payments"] == [] and world.doc["payment_notices"][0]["status"] == "pending"
    assert world.doc["status"] == "agreed"
    world.find_one_and_update = real
    done = await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)
    assert done["status"] == "settled" and done["payment_notices"][0]["status"] == "verified"
    assert world.doc["payments"][0]["notice_id"] == notice["id"]


@pytest.mark.asyncio
async def test_concurrent_rejection_wins_over_a_verification_in_flight(world):
    notice = (await _report(6800, "EFT-21"))["payment_notices"][0]
    real = world.find_one_and_update

    async def reject_first(query, update, **kwargs):
        world.doc["payment_notices"][0]["status"] = "rejected"  # other operator, between read and write
        return await real(query, update, **kwargs)

    world.find_one_and_update = reject_first
    with pytest.raises(HTTPException) as exc:
        await st.verify_payment_notice("s1", notice["id"], st.NoticeDecision(), USER)
    assert exc.value.status_code == 409
    assert world.doc["payments"] == [] and world.doc["payment_notices"][0]["status"] == "rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("role,path", [
    ("housekeeping", "t1/../_private/agency-payment-proofs/t1/s1/n1.pdf"),
    ("super_admin", "_private/agency-payment-proofs/t1/s1/n1.pdf"),
])
async def test_generic_upload_route_never_serves_payment_proofs(monkeypatch, tmp_path, role, path):
    import routers.uploads as uploads

    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(uploads, "PRIVATE_UPLOAD_DIR", tmp_path / "_private")
    proof = tmp_path / "_private/agency-payment-proofs/t1/s1/n1.pdf"
    proof.parent.mkdir(parents=True)
    proof.write_bytes(b"%PDF-1.4 secret")
    user = SimpleNamespace(id="u2", tenant_id="t1", role=role)
    with pytest.raises(HTTPException) as exc:
        await uploads.get_upload(path, optional_user=user, optional_vendor_id=None)
    assert exc.value.status_code == 404
