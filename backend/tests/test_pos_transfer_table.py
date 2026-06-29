"""Test suite for POS transfer_table endpoint.
Covers full transfer, partial transfer, quantity-aware transfer, duplicate-item merge,
tenant scoping and consistency guard.
"""
from types import SimpleNamespace
from datetime import datetime, UTC
import uuid
import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import pos_core

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n=None):
        return self._docs

class InMemoryCollection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    @staticmethod
    def _match(doc, flt):
        for k, v in flt.items():
            dv = doc.get(k)
            if isinstance(v, dict):
                for op, ov in v.items():
                    if op == "$gte":
                        if dv is None or dv < ov:
                            return False
                    elif op == "$gt":
                        if dv is None or dv <= ov:
                            return False
                    elif op == "$ne":
                        if dv == ov:
                            return False
            elif dv != v:
                return False
        return True

    async def find_one(self, flt, _proj=None, session=None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    def find(self, flt, _proj=None, session=None):
        return _Cursor([dict(d) for d in self.docs if self._match(d, flt)])

    async def insert_one(self, doc, session=None):
        doc["_id"] = "fake_mongo_id"
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, flt, update, session=None, upsert=False):
        for d in self.docs:
            if self._match(d, flt):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$inc", {}).items():
                    d[k] = (d.get(k) or 0) + v
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def delete_one(self, flt, session=None):
        for idx, d in enumerate(self.docs):
            if self._match(d, flt):
                self.docs.pop(idx)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

from pymongo.errors import OperationFailure

class _FakeClient:
    async def start_session(self):
        raise OperationFailure("Transaction numbers are only allowed on a replica set member or mongos")

class _FakeDB:
    def __init__(self, docs):
        self.pos_transactions = InMemoryCollection(docs)
        self.client = _FakeClient()

@pytest.fixture
def fake_db():
    docs = [
        {
            "_id": "src_1",
            "id": "src_uuid_1",
            "tenant_id": "tenant1",
            "outlet_id": "out1",
            "table_number": "T1",
            "status": "open",
            "items": [
                {"item_id": "i1", "name": "Burger", "price": 100, "quantity": 2, "tax_amount": 18},
                {"item_id": "i2", "name": "Coke", "price": 50, "quantity": 1, "tax_amount": 9},
            ],
            "total_amount": 286,
        },
        {
            "_id": "cross_tenant",
            "id": "cross_uuid_1",
            "tenant_id": "tenant2",
            "outlet_id": "out1",
            "table_number": "T2",
            "status": "open",
            "items": [],
            "total_amount": 0,
        }
    ]
    return _FakeDB(docs)

async def _fake_user():
    return SimpleNamespace(tenant_id="tenant1", username="testuser", user_id="u1")

@pytest.mark.asyncio
async def test_full_transfer(fake_db, monkeypatch):
    monkeypatch.setattr(pos_core, "db", fake_db)
    
    res = await pos_core.transfer_table(
        from_table="T1",
        to_table="T2",
        outlet_id="out1",
        transfer_all=True,
        current_user=await _fake_user(),
        _perm=None
    )
    
    assert res["success"] is True
    
    # Check if table number is updated
    updated_tx = await fake_db.pos_transactions.find_one({"id": "src_uuid_1"})
    assert updated_tx["table_number"] == "T2"

@pytest.mark.asyncio
async def test_partial_transfer_index_based(fake_db, monkeypatch):
    monkeypatch.setattr(pos_core, "db", fake_db)
    
    # Transfer only the second item (Coke)
    res = await pos_core.transfer_table(
        from_table="T1",
        to_table="T2",
        outlet_id="out1",
        transfer_all=False,
        items_to_transfer=[1],
        current_user=await _fake_user(),
        _perm=None
    )
    
    assert res["success"] is True
    assert res["items_transferred"] == 1
    
    # Source table check
    src_tx = await fake_db.pos_transactions.find_one({"id": "src_uuid_1"})
    assert len(src_tx["items"]) == 1
    assert src_tx["items"][0]["name"] == "Burger"
    
    # Target table check (newly created)
    target_tx = await fake_db.pos_transactions.find_one({"table_number": "T2", "status": "open", "tenant_id": "tenant1"})
    assert target_tx is not None
    assert len(target_tx["items"]) == 1
    assert target_tx["items"][0]["name"] == "Coke"

@pytest.mark.asyncio
async def test_partial_transfer_quantity_aware_and_duplicate_merge(fake_db, monkeypatch):
    # Pre-create a target transaction to test merging
    await fake_db.pos_transactions.insert_one({
        "_id": "target_1",
        "id": "target_uuid_1",
        "tenant_id": "tenant1",
        "outlet_id": "out1",
        "table_number": "T2",
        "status": "open",
        "items": [
            {"item_id": "i1", "name": "Burger", "price": 100, "quantity": 1, "tax_amount": 9},
            {"item_id": "i3", "name": "Fries", "price": 30, "quantity": 1, "tax_amount": 5}
        ],
        "total_amount": 144,
    })
    
    monkeypatch.setattr(pos_core, "db", fake_db)
    
    # Transfer 1 Burger (partial quantity) and 1 Coke (full) from T1 to T2
    res = await pos_core.transfer_table(
        from_table="T1",
        to_table="T2",
        outlet_id="out1",
        transfer_all=False,
        items_to_transfer=[
            {"index": 0, "quantity": 1},  # Burger
            {"index": 1} # Coke (null qty = all)
        ],
        current_user=await _fake_user(),
        _perm=None
    )
    
    assert res["success"] is True
    
    src_tx = await fake_db.pos_transactions.find_one({"id": "src_uuid_1"})
    # Burger should have 1 qty remaining, Coke is gone
    assert len(src_tx["items"]) == 1
    assert src_tx["items"][0]["quantity"] == 1
    assert src_tx["items"][0]["name"] == "Burger"
    
    target_tx = await fake_db.pos_transactions.find_one({"id": "target_uuid_1"})
    # Target originally had 1 Burger and 1 Fries. Now it should have 2 Burgers, 1 Fries, 1 Coke
    assert len(target_tx["items"]) == 3
    burger = next(i for i in target_tx["items"] if i["item_id"] == "i1")
    assert burger["quantity"] == 2
    
@pytest.mark.asyncio
async def test_cross_tenant_transfer_defense(fake_db, monkeypatch):
    monkeypatch.setattr(pos_core, "db", fake_db)
    # T2 exists for tenant2, try to transfer from tenant2's table but our user is tenant1
    with pytest.raises(HTTPException) as exc:
        await pos_core.transfer_table(
            from_table="T2",
            to_table="T3",
            outlet_id="out1",
            transfer_all=True,
            current_user=await _fake_user(),
            _perm=None
        )
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_invalid_quantity_transfer(fake_db, monkeypatch):
    monkeypatch.setattr(pos_core, "db", fake_db)
    # Try to transfer more than exists (Burger has 2 qty, trying to transfer 3)
    with pytest.raises(HTTPException) as exc:
        await pos_core.transfer_table(
            from_table="T1",
            to_table="T2",
            outlet_id="out1",
            transfer_all=False,
            items_to_transfer=[
                {"index": 0, "quantity": 3},
            ],
            current_user=await _fake_user(),
            _perm=None
        )
    assert exc.value.status_code == 400
    assert "exceeds source item quantity" in exc.value.detail

@pytest.mark.asyncio
async def test_negative_quantity_transfer(fake_db, monkeypatch):
    monkeypatch.setattr(pos_core, "db", fake_db)
    with pytest.raises(HTTPException) as exc:
        await pos_core.transfer_table(
            from_table="T1",
            to_table="T2",
            outlet_id="out1",
            transfer_all=False,
            items_to_transfer=[
                {"index": 0, "quantity": -1},
            ],
            current_user=await _fake_user(),
            _perm=None
        )
    assert exc.value.status_code == 400
    assert "quantity must be > 0" in exc.value.detail


@pytest.mark.asyncio
async def test_partial_transfer_compensation(fake_db, monkeypatch):
    monkeypatch.setattr(pos_core, "db", fake_db)
    
    # Target (T2) will be created as a new document, then source (T1) update will fail.
    original_update_one = fake_db.pos_transactions.update_one
    original_insert_one = fake_db.pos_transactions.insert_one
    
    # We want source update to fail. Source update is the update_one call.
    # Target creation is insert_one.
    # We can mock update_one to return modified_count=0 when updating T1.
    async def mock_update_one(flt, update, session=None, upsert=False):
        if flt.get("table_number") == "T1" or flt.get("_id") == "src_1":
            return SimpleNamespace(modified_count=0, matched_count=0)
        return await original_update_one(flt, update, session, upsert)
        
    monkeypatch.setattr(fake_db.pos_transactions, "update_one", mock_update_one)
    
    with pytest.raises(HTTPException) as exc:
        await pos_core.transfer_table(
            from_table="T1",
            to_table="T2",
            outlet_id="out1",
            transfer_all=False,
            items_to_transfer=[1],
            current_user=await _fake_user(),
            _perm=None
        )
    assert exc.value.status_code == 409
    assert "Operation aborted and compensated" in exc.value.detail
    
    # Check that T2 is not in db (it got deleted during compensation)
    t2_tx = await fake_db.pos_transactions.find_one({"table_number": "T2", "tenant_id": "tenant1"})
    assert t2_tx is None

