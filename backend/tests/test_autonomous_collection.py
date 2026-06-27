"""Task #313 — Otonom tahsilat motoru (no-show cezasi + check-in gunu VCC capture).

Saf birim testi: calisan backend / canli Mongo / gercek PSP gerektirmez. Sahte-yesil
URETILMEZ — davranis gercek motor kodundan (``core.autonomous_collection``) ve gercek
tahsilat cekirdeginden (``core.payments.collection``) gozlenir. Sahte yalnizca Mongo I/O
ve PSP adaptorudur; idempotency/intent/folio/booking yazimlari gercek kod yollarindan
gecer.

Kapsanan davranislar:
- VCC check-in adayi secilir ve tahsil edilir (acik folyo bakiyesi kadar).
- No-show adayi secilir ve ceza tahsil edilir (no_show_fee).
- Cift tarama -> TEK charge (kalici booking marker + para-alinmis intent guard'i).
- Saglayici yapilandirilmamis -> kuyruga not_configured, charge DENENMEZ (fail-closed).
- PSP reddi -> kuyruga failed + attempts artar; MAX asiminda marker=abandoned.
- 3DS gereken -> kuyruga requires_action, booking marker SET EDILMEZ.
"""
from __future__ import annotations

import asyncio

import pytest
from pymongo.errors import DuplicateKeyError

from core import autonomous_collection as ac
from core.payments.contracts import (
    PaymentError,
    PaymentOperation,
    PaymentResult,
    PaymentStatus,
)

TENANT = "tenant-A"
OTHER = "tenant-B"
BUSINESS_DATE = "2026-06-27"


# ───────────────────────────── in-memory Mongo ─────────────────────────────


def _get(doc, dotted):
    return doc.get(dotted)


def _match_value(actual, cond):
    if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
        for op, val in cond.items():
            if op == "$in":
                if actual not in val:
                    return False
            elif op == "$ne":
                if actual == val:
                    return False
            elif op == "$gte":
                if actual is None or actual < val:
                    return False
            elif op == "$lt":
                if actual is None or actual >= val:
                    return False
            elif op == "$exists":
                if (actual is not None) != bool(val):
                    return False
            else:
                raise NotImplementedError(f"operator {op}")
        return True
    return actual == cond


def _match(doc, flt):
    for k, cond in flt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        if not _match_value(doc.get(k), cond):
            return False
    return True


def _apply_update(doc, update, *, on_insert):
    for k, v in update.get("$set", {}).items():
        doc[k] = v
    for k, v in update.get("$inc", {}).items():
        doc[k] = (doc.get(k) or 0) + v
    if on_insert:
        for k, v in update.get("$setOnInsert", {}).items():
            doc[k] = v
    for k in update.get("$unset", {}):
        doc.pop(k, None)


class _UpdRes:
    def __init__(self, matched=0, modified=0, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = upserted_id


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield dict(d)
        return gen()


class _Coll:
    def __init__(self, *, id_field=None):
        self.docs: list[dict] = []
        self._id_field = id_field

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    def find(self, flt, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt)])

    async def insert_one(self, doc, session=None):
        if self._id_field:
            key = doc.get(self._id_field)
            if any(x.get(self._id_field) == key for x in self.docs):
                raise DuplicateKeyError(f"dup {self._id_field}")
        self.docs.append(dict(doc))
        return None

    async def update_one(self, flt, update, session=None, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                before = dict(d)
                _apply_update(d, update, on_insert=False)
                return _UpdRes(matched=1, modified=int(d != before))
        if upsert:
            doc: dict = {}
            for k, v in flt.items():
                if not isinstance(v, dict):
                    doc[k] = v
            _apply_update(doc, update, on_insert=True)
            self.docs.append(doc)
            return _UpdRes(matched=0, modified=0, upserted_id=doc.get(self._id_field or "id"))
        return _UpdRes(matched=0, modified=0)

    async def find_one_and_update(
        self, flt, update, upsert=False, return_document=True, session=None
    ):
        for d in self.docs:
            if _match(d, flt):
                _apply_update(d, update, on_insert=False)
                return dict(d)
        if upsert:
            doc: dict = {}
            for k, v in flt.items():
                if not isinstance(v, dict):
                    doc[k] = v
            _apply_update(doc, update, on_insert=True)
            self.docs.append(doc)
            return dict(doc)
        return None

    async def delete_one(self, flt, session=None):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                self.docs.pop(i)
                return _UpdRes(matched=1)
        return _UpdRes(matched=0)

    async def create_index(self, *a, **kw):
        return "idx"


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def start_transaction(self):
        outer = self

        class _Tx:
            async def __aenter__(self):
                return outer

            async def __aexit__(self, *a):
                return False

        return _Tx()


class _Client:
    async def start_session(self):
        return _Session()


class _DB:
    def __init__(self):
        self.client = _Client()
        self._colls: dict[str, _Coll] = {
            "idempotency_keys": _Coll(id_field="_id"),
            "payment_webhook_events": _Coll(id_field="_id"),
        }

    def _get(self, name):
        if name not in self._colls:
            self._colls[name] = _Coll()
        return self._colls[name]

    def __getattr__(self, name):
        if name.startswith("_") or name == "client":
            raise AttributeError(name)
        return self._get(name)

    def __getitem__(self, name):
        return self._get(name)


# ───────────────────────────── fake PSP provider ────────────────────────────


class _Provider:
    def __init__(self, *, name="fake", behavior="ok"):
        self.name = name
        self.behavior = behavior
        self.charge_calls = 0

    def is_configured(self):
        return True

    async def charge(self, req):
        self.charge_calls += 1
        if self.behavior == "declined":
            return PaymentResult(
                status=PaymentStatus.FAILED, operation=PaymentOperation.CHARGE,
                provider=self.name, tenant_id=req.tenant_id,
                idempotency_key=req.idempotency_key, error_code="card_declined",
                error_message="kart reddedildi",
            )
        if self.behavior == "requires_action":
            return PaymentResult(
                status=PaymentStatus.REQUIRES_ACTION, operation=PaymentOperation.CHARGE,
                provider=self.name, tenant_id=req.tenant_id,
                idempotency_key=req.idempotency_key,
                provider_ref="pr-3ds", requires_action_url="https://3ds.example/redirect",
            )
        return PaymentResult(
            status=PaymentStatus.SUCCEEDED, operation=PaymentOperation.CHARGE,
            provider=self.name, tenant_id=req.tenant_id,
            idempotency_key=req.idempotency_key, amount_minor=req.amount_minor,
            currency=req.currency, provider_ref="pr-ok", provider_txn_ref="tx-ok",
            masked_card="**** **** **** 4242",
        )


# ───────────────────────────────── seeding ─────────────────────────────────


def _seed_vcc_checkin(db, *, tenant=TENANT, booking_id="bk-vcc", balance=150.0):
    db.bookings.docs.append({
        "id": booking_id, "tenant_id": tenant, "check_in": BUSINESS_DATE,
        "status": "confirmed", "currency": "TRY", "paid_amount": 0.0,
    })
    db.vcc_cards.docs.append({
        "id": "card-1", "tenant_id": tenant, "booking_id": booking_id,
    })
    db.folios.docs.append({
        "id": "folio-1", "tenant_id": tenant, "booking_id": booking_id,
        "folio_type": "guest", "status": "open", "balance": balance, "currency": "TRY",
    })


def _seed_no_show(db, *, tenant=TENANT, booking_id="bk-ns", fee=200.0):
    db.bookings.docs.append({
        "id": booking_id, "tenant_id": tenant, "check_in": BUSINESS_DATE,
        "status": "no_show", "currency": "TRY", "paid_amount": 0.0,
        "cancellation_policy": {"no_show_fee": fee},
    })
    db.vcc_cards.docs.append({
        "id": "card-ns", "tenant_id": tenant, "booking_id": booking_id,
    })
    db.folios.docs.append({
        "id": "folio-ns", "tenant_id": tenant, "booking_id": booking_id,
        "folio_type": "guest", "status": "open", "balance": fee, "currency": "TRY",
    })


def _run(db, provider, *, tenant=TENANT):
    async def _patched(_db, _tenant):
        return provider
    orig = ac.get_provider_for_tenant
    ac.get_provider_for_tenant = _patched  # type: ignore[assignment]
    try:
        return asyncio.run(
            ac.run_autonomous_collection(db, tenant, business_date=BUSINESS_DATE)
        )
    finally:
        ac.get_provider_for_tenant = orig  # type: ignore[assignment]


# ───────────────────────────────── tests ───────────────────────────────────


def test_vcc_checkin_charged():
    db = _DB()
    _seed_vcc_checkin(db, balance=150.0)
    provider = _Provider(behavior="ok")

    summary = _run(db, provider)

    assert summary["scanned"] == 1
    assert summary["charged"] == 1
    assert provider.charge_calls == 1
    # Kalici marker set edildi.
    bk = next(b for b in db.bookings.docs if b["id"] == "bk-vcc")
    assert bk.get("autocollect_vcc_checkin_done") is True
    assert bk.get("autocollect_vcc_checkin_status") == "collected"
    # Payment kaydi + folyo bakiyesi dustu (atomik).
    assert len(db.payments.docs) == 1
    assert db.payments.docs[0]["amount"] == 150.0
    folio = next(f for f in db.folios.docs if f["id"] == "folio-1")
    assert folio["balance"] == 0.0
    # Kuyrukta succeeded.
    job = next(j for j in db.autonomous_collection_jobs.docs if j["charge_kind"] == "vcc_checkin")
    assert job["status"] == "succeeded" and job["resolved"] is True


def test_no_show_penalty_charged():
    db = _DB()
    _seed_no_show(db, fee=200.0)
    provider = _Provider(behavior="ok")

    summary = _run(db, provider)

    assert summary["scanned"] == 1 and summary["charged"] == 1
    assert provider.charge_calls == 1
    bk = next(b for b in db.bookings.docs if b["id"] == "bk-ns")
    assert bk.get("autocollect_no_show_done") is True
    assert db.payments.docs[0]["amount"] == 200.0
    assert db.payments.docs[0]["payment_type"] == "final"


def test_double_scan_charges_once():
    db = _DB()
    _seed_vcc_checkin(db, balance=120.0)
    provider = _Provider(behavior="ok")

    first = _run(db, provider)
    assert first["charged"] == 1 and provider.charge_calls == 1

    # Ikinci tarama (ayni gun): kalici marker + para-alinmis intent guard'i devreye girer.
    second = _run(db, provider)
    assert provider.charge_calls == 1, "cift-charge OLMAMALI"
    assert second["charged"] == 0
    # Tek payment kaydi kaldi.
    assert len(db.payments.docs) == 1


def test_provider_not_configured_fail_closed():
    db = _DB()
    _seed_vcc_checkin(db)

    class _NotConfigured(PaymentError):
        error_code = "not_configured"
        http_status = 503

    async def _raise(_db, _tenant):
        raise _NotConfigured("yok")

    orig = ac.get_provider_for_tenant
    ac.get_provider_for_tenant = _raise  # type: ignore[assignment]
    try:
        summary = asyncio.run(
            ac.run_autonomous_collection(db, TENANT, business_date=BUSINESS_DATE)
        )
    finally:
        ac.get_provider_for_tenant = orig  # type: ignore[assignment]

    assert summary["not_configured"] == 1 and summary["charged"] == 0
    # Sahte basari YOK: hicbir payment yazilmadi; booking marker SET EDILMEDI.
    assert len(db.payments.docs) == 0
    bk = next(b for b in db.bookings.docs if b["id"] == "bk-vcc")
    assert bk.get("autocollect_vcc_checkin_done") is not True
    job = db.autonomous_collection_jobs.docs[0]
    assert job["status"] == "not_configured" and job["resolved"] is False


def test_declined_queues_and_increments_attempts_then_abandons(monkeypatch):
    monkeypatch.setenv("AUTOCOLLECT_MAX_ATTEMPTS", "2")
    db = _DB()
    _seed_vcc_checkin(db)
    provider = _Provider(behavior="declined")

    s1 = _run(db, provider)
    assert s1["failed"] == 1 and len(db.payments.docs) == 0
    job = db.autonomous_collection_jobs.docs[0]
    assert job["status"] == "failed" and job["attempts"] == 1
    # Henuz MAX'a ulasilmadi -> marker SET EDILMEDI (tekrar denenebilir).
    bk = next(b for b in db.bookings.docs if b["id"] == "bk-vcc")
    assert bk.get("autocollect_vcc_checkin_done") is not True

    s2 = _run(db, provider)
    assert s2["failed"] == 1
    job = db.autonomous_collection_jobs.docs[0]
    assert job["attempts"] == 2
    # MAX asildi -> marker=abandoned (tekrar taranmaz); job operator icin acik kalir.
    bk = next(b for b in db.bookings.docs if b["id"] == "bk-vcc")
    assert bk.get("autocollect_vcc_checkin_done") is True
    assert bk.get("autocollect_vcc_checkin_status") == "abandoned"
    assert job["resolved"] is False


def test_requires_action_queued_no_marker():
    db = _DB()
    _seed_vcc_checkin(db)
    provider = _Provider(behavior="requires_action")

    summary = _run(db, provider)

    assert summary["requires_action"] == 1 and summary["charged"] == 0
    assert len(db.payments.docs) == 0
    # 3DS otonom tamamlanamaz: marker SET EDILMEZ (operator surdurur).
    bk = next(b for b in db.bookings.docs if b["id"] == "bk-vcc")
    assert bk.get("autocollect_vcc_checkin_done") is not True
    job = db.autonomous_collection_jobs.docs[0]
    assert job["status"] == "requires_action" and job["resolved"] is False


def test_tenant_isolation_other_tenant_untouched():
    db = _DB()
    _seed_vcc_checkin(db, tenant=TENANT, booking_id="bk-a")
    _seed_vcc_checkin(db, tenant=OTHER, booking_id="bk-b")
    provider = _Provider(behavior="ok")

    summary = _run(db, provider, tenant=TENANT)

    assert summary["scanned"] == 1 and summary["charged"] == 1
    # Yalnizca TENANT'in booking'i isaretlendi; OTHER'a dokunulmadi.
    bk_a = next(b for b in db.bookings.docs if b["id"] == "bk-a")
    bk_b = next(b for b in db.bookings.docs if b["id"] == "bk-b")
    assert bk_a.get("autocollect_vcc_checkin_done") is True
    assert bk_b.get("autocollect_vcc_checkin_done") is not True


def test_zero_balance_vcc_skipped():
    db = _DB()
    _seed_vcc_checkin(db, balance=0.0)
    provider = _Provider(behavior="ok")

    summary = _run(db, provider)

    assert summary["scanned"] == 0 and summary["charged"] == 0
    assert provider.charge_calls == 0


def test_no_card_skipped():
    db = _DB()
    db.bookings.docs.append({
        "id": "bk-nocard", "tenant_id": TENANT, "check_in": BUSINESS_DATE,
        "status": "confirmed", "currency": "TRY",
    })
    db.folios.docs.append({
        "id": "folio-x", "tenant_id": TENANT, "booking_id": "bk-nocard",
        "folio_type": "guest", "status": "open", "balance": 99.0,
    })
    provider = _Provider(behavior="ok")

    summary = _run(db, provider)

    assert summary["scanned"] == 0
    assert provider.charge_calls == 0


def test_old_no_show_outside_lookback_skipped(monkeypatch):
    monkeypatch.setenv("AUTOCOLLECT_NO_SHOW_LOOKBACK_DAYS", "3")
    db = _DB()
    # check_in cok eski (pencere disinda) -> tarihsel backfill YOK.
    db.bookings.docs.append({
        "id": "bk-old", "tenant_id": TENANT, "check_in": "2026-01-01",
        "status": "no_show", "currency": "TRY",
        "cancellation_policy": {"no_show_fee": 300.0},
    })
    db.vcc_cards.docs.append({"id": "c-old", "tenant_id": TENANT, "booking_id": "bk-old"})
    provider = _Provider(behavior="ok")

    summary = _run(db, provider)

    assert summary["scanned"] == 0 and provider.charge_calls == 0
