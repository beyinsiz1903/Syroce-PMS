from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import marketplace_b2b


class Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def insert_one(self, document):
        self.rows.append(dict(document))

    async def find_one(self, query, _projection=None):
        return next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)

    async def update_one(self, query, update):
        def matches(row):
            for key, expected in query.items():
                if isinstance(expected, dict) and "$gt" in expected:
                    if not row.get(key) or row[key] <= expected["$gt"]:
                        return False
                elif row.get(key) != expected:
                    return False
            return True

        row = next((item for item in self.rows if matches(item)), None)
        if row:
            row.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1 if row else 0, modified_count=1 if row else 0)

    async def update_many(self, query, update):
        modified = 0
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                row.update(update.get("$set", {}))
                modified += 1
        return SimpleNamespace(modified_count=modified)


def fake_db():
    return SimpleNamespace(
        agency_connect_codes=Collection(),
        marketplace_api_keys=Collection(),
        marketplace_audit_logs=Collection(),
    )


def connect_request(verifier="v" * 48):
    return marketplace_b2b.AgencyConnectAuthorize(
        client_id="syroce_agency",
        redirect_uri="https://agency.syroce.com/auth/syroce/callback",
        code_challenge=marketplace_b2b._pkce_s256(verifier),
        state="state-value-123",
    )


def test_account_connect_rejects_unregistered_redirect():
    with pytest.raises(HTTPException) as error:
        marketplace_b2b._registered_agency_connect_client("syroce_agency", "https://attacker.example/callback")
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_account_connect_code_is_short_lived_and_stored_only_as_hash(monkeypatch):
    database = fake_db()
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: database)
    result = await marketplace_b2b.marketplace_connect_authorize(
        connect_request(),
        {"agency_id": "agency-1", "user": {"id": "user-1"}},
    )

    stored = database.agency_connect_codes.rows[0]
    assert result["expires_in"] == 300
    assert stored["code_hash"] == marketplace_b2b._hash_key(result["code"])
    assert result["code"] not in str(stored)
    assert stored["used_at"] is None


@pytest.mark.asyncio
async def test_account_connect_exchange_is_pkce_protected_single_use_and_rotates_key(monkeypatch):
    database = fake_db()
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: database)
    verifier = "secure-verifier-" + "x" * 40
    authorization = await marketplace_b2b.marketplace_connect_authorize(
        connect_request(verifier),
        {"agency_id": "agency-1", "user": {"id": "user-1"}},
    )
    exchange = marketplace_b2b.AgencyConnectExchange(
        client_id="syroce_agency",
        redirect_uri="https://agency.syroce.com/auth/syroce/callback",
        code=authorization["code"],
        code_verifier=verifier,
    )

    result = await marketplace_b2b.marketplace_connect_token(exchange)
    assert result["access_token"].startswith("syroce_mkt_")
    assert database.marketplace_api_keys.rows[0]["key_hash"] == marketplace_b2b._hash_key(result["access_token"])
    assert result["access_token"] not in str(database.marketplace_api_keys.rows[0])
    assert database.marketplace_api_keys.rows[0]["client_id"] == "syroce_agency"

    with pytest.raises(HTTPException) as replay:
        await marketplace_b2b.marketplace_connect_token(exchange)
    assert replay.value.status_code == 400


@pytest.mark.asyncio
async def test_account_connect_exchange_rejects_wrong_verifier(monkeypatch):
    database = fake_db()
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: database)
    authorization = await marketplace_b2b.marketplace_connect_authorize(
        connect_request(),
        {"agency_id": "agency-1", "user": {"id": "user-1"}},
    )
    with pytest.raises(HTTPException) as error:
        await marketplace_b2b.marketplace_connect_token(
            marketplace_b2b.AgencyConnectExchange(
                client_id="syroce_agency",
                redirect_uri="https://agency.syroce.com/auth/syroce/callback",
                code=authorization["code"],
                code_verifier="wrong-verifier-" + "z" * 40,
            )
        )
    assert error.value.status_code == 400
