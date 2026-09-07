"""Transaction-scoped workflow serialization. No unsafe standalone fallback.

The stable _id lock is created before starting the transaction. Incrementing
it inside the transaction makes concurrent readers retry with a fresh snapshot.
All callback data operations must use the supplied SessionDatabase.
"""
import hashlib
import json

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern


class SessionCollection:
    def __init__(self, collection, session):
        self.collection, self.session = collection, session

    def __getattr__(self, name):
        method = getattr(self.collection, name)
        # Index creation is schema work, never part of a data transaction.
        if name in {"create_index", "create_indexes", "index_information", "list_indexes"}:
            return method
        if name in {"find", "find_one", "insert_one", "insert_many", "update_one",
                    "update_many", "find_one_and_update", "delete_one", "count_documents", "aggregate",
                    "replace_one", "find_one_and_delete", "find_one_and_replace", "delete_many",
                    "bulk_write", "distinct"}:
            def invoke(*args, **kwargs):
                return method(*args, **{**kwargs, "session": self.session})
            return invoke
        if callable(method):
            raise AttributeError(f"Collection operation {name} is not transaction-scoped")
        return method


class SessionDatabase:
    def __init__(self, database, session):
        self.database, self.session = database, session

    def __getitem__(self, name):
        return SessionCollection(self.database[name], self.session)

    def __getattr__(self, name):
        return SessionCollection(getattr(self.database, name), self.session)


async def run_atomic(database, client, tenant_id, resource, callback):
    lock_id = hashlib.sha256(json.dumps([tenant_id, resource]).encode()).hexdigest()
    query = {"_id": lock_id, "tenant_id": tenant_id}
    try:
        await database.workflow_locks.update_one(
            query, {"$setOnInsert": {"resource": resource, "revision": 0}}, upsert=True)
    except DuplicateKeyError:
        # Another worker initialized the same lock; never steal another tenant's.
        if not await database.workflow_locks.find_one(query):
            raise
    try:
        async with await client.start_session() as session:
            async def transact(s):
                scoped = SessionDatabase(database, s)
                await scoped.workflow_locks.update_one(query, {"$inc": {"revision": 1}})
                return await callback(scoped)
            return await session.with_transaction(
                transact, read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority"))
    except OperationFailure as exc:
        if exc.code in {20, 303}:
            raise HTTPException(503, "Güvenli işlem için MongoDB replica set/transaction desteği gerekli") from exc
        raise
