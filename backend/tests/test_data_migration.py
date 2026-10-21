"""Vendor-neutral migration acceptance against isolated, LOCAL Mongo only."""

import asyncio
import io
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Response
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from openpyxl import Workbook

from modules.data_migration import service
from modules.data_migration.formats import MigrationError, parse_file
from modules.data_migration.schema import money, normalize, suggest_mapping


@pytest.fixture
async def migration_db():
    uri = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    parsed = urlsplit(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.port not in {27017, 27987} or "," in parsed.netloc:
        pytest.fail("Migration tests require an isolated local MongoDB")
    client = AsyncIOMotorClient(uri, directConnection=True, serverSelectionTimeoutMS=2000)
    db = client["migration_acceptance_" + uuid4().hex]
    try:
        await client.admin.command("ping")
        yield db
    finally:
        await client.drop_database(db.name)
        client.close()


async def batch(db, *, tenant="A", publish=False, namespace="legacy-2026"):
    return await service.create_batch(db, tenant, "admin", source="Synthetic PMS export", namespace=namespace, publish_guests=publish)


async def add(db, b, entity, rows, **options):
    headers = list(dict.fromkeys(key for row in rows for key in row))
    b = await service.add_dataset(db, b, "admin", entity=entity, headers=headers, rows=rows)
    datasets = b["datasets"]
    datasets[-1].update(options)
    return await service.change_batch(db, b, "admin", {"datasets": datasets})


async def finish(db, b):
    b = await service.review(db, b, "admin")
    assert not b["report"]["error_count"], b["report"]
    while b["state"] != "complete":
        b = await service.namespace_guard(db, b, lambda: service.commit_chunk(db, b, "admin", b["review_token"]))
    return b


def guest(source_id="g1", **extra):
    return {"source_id": source_id, "name": "Synthetic Guest", **extra}


def reservation(source_id="r1", **extra):
    return {"source_id": source_id, "guest_source_id": "g1", "check_in": "2025-01-01", "check_out": "2025-01-03", "status": "checked_out", "total_amount": "100.10", "currency": "EUR", **extra}


@pytest.mark.parametrize(
    "extension, content",
    [
        ("csv", b"source_id;name\ng1;Synthetic Guest\n"),
        ("tsv", b"source_id\tname\ng1\tSynthetic Guest\n"),
        ("json", b'[{"source_id":"g1","name":"Synthetic Guest"}]'),
        ("xml", b"<records><record><source_id>g1</source_id><name>Synthetic Guest</name></record></records>"),
    ],
)
def test_formats_preserve_the_same_canonical_row(extension, content):
    headers, rows = parse_file("export." + extension, content)
    assert headers == ["source_id", "name"]
    assert rows == [guest()]


def test_excel_sheet_selection_and_formula_rejection():
    book = Workbook()
    book.active.append(["source_id", "name"])
    book.active.append(["001", "Synthetic Guest"])
    output = io.BytesIO()
    book.save(output)
    assert parse_file("export.xlsx", output.getvalue())[1][0]["source_id"] == "001"
    book.create_sheet("Other")
    output = io.BytesIO()
    book.save(output)
    with pytest.raises(MigrationError, match="sayfa"):
        parse_file("export.xlsx", output.getvalue())
    assert parse_file("export.xlsx", output.getvalue(), sheet="Sheet")[1][0]["source_id"] == "001"
    book["Sheet"]["B2"] = '=HYPERLINK("https://invalid.example", "bad")'
    output = io.BytesIO()
    book.save(output)
    with pytest.raises(MigrationError, match="formül"):
        parse_file("export.xlsx", output.getvalue(), sheet="Sheet")


@pytest.mark.parametrize(
    "name, content",
    [
        ("a.csv", b"source_id,source id\n1,2"),
        ("a.csv", b"source_id,name\n1,x,extra"),
        ("a.csv", b"source_id,password\n1,secret"),
        ("a.json", b'[{"name":"a","name":"b"}]'),
        ("a.json", b'[{"name":{"nested":"secret"}}]'),
        ("a.xml", b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x><r><name>&e;</name></r></x>'),
        ("a.xml", b"<x><r><name>a</name><name>b</name></r></x>"),
        ("a.xml", b"<x><r><name><value>a</value></name></r></x>"),
        ("a.xls", b"legacy binary"),
        ("a.csv", b""),
    ],
)
def test_malformed_or_unsafe_files_fail_closed(name, content):
    with pytest.raises(MigrationError):
        parse_file(name, content)


def test_row_limit_is_not_silent_truncation_and_turkish_encoding_is_explicit():
    with pytest.raises(MigrationError, match="10.000"):
        parse_file("a.csv", ("source_id,name\n" + "1,Synthetic\n" * 10001).encode())
    content = "source_id,Ad Soyad\n1,Çağrı Örnek".encode("cp1254")
    with pytest.raises(MigrationError):
        parse_file("a.csv", content)
    assert parse_file("a.csv", content, encoding="cp1254")[1][0]["Ad Soyad"] == "Çağrı Örnek"
    assert suggest_mapping("guests", ["Eski ID", "Ad Soyad", "E-posta"]) == {"source_id": "Eski ID", "name": "Ad Soyad", "email": "E-posta"}


@pytest.mark.parametrize("raw, currency, separator, expected", [("100.10", "EUR", ".", "100.10"), ("100,10", "TRY", ",", "100.10"), ("123", "JPY", ".", "123"), ("1.234", "KWD", ".", "1.234")])
def test_money_never_guesses_or_uses_binary_float(raw, currency, separator, expected):
    assert money(raw, currency, separator) == expected


@pytest.mark.parametrize("raw,currency", [("1,234.56", "EUR"), ("NaN", "EUR"), ("Infinity", "EUR"), ("1.001", "TRY"), ("1.5", "JPY"), ("1e5", "EUR")])
def test_ambiguous_precision_and_non_finite_amounts_are_rejected(raw, currency):
    with pytest.raises(MigrationError):
        money(raw, currency)


def test_consent_dates_statuses_and_unknown_fields_require_explicit_mapping():
    with pytest.raises(MigrationError, match="kanıt"):
        normalize("guests", guest(marketing_consent="true"), {k: k for k in guest(marketing_consent="true")})
    assert normalize("guests", guest(), {k: k for k in guest()})["marketing_consent"] is False
    with pytest.raises(MigrationError, match="Çıkış"):
        normalize("reservations", reservation(check_out="2024-01-01"), {k: k for k in reservation()})
    with pytest.raises(MigrationError):
        normalize("guests", guest(), {"source_id": "source_id", "name": "name", "$set": "name"})


async def test_linked_historical_and_financial_data_are_encrypted_and_have_no_operational_side_effects(migration_db):
    db = migration_db
    b = await add(db, await batch(db, publish=True), "guests", [guest(email="synthetic@example.invalid", phone="+900000000000")])
    b = await add(db, b, "reservations", [reservation(), reservation("r2", status="confirmed", currency="USD", total_amount="20.00")])
    b = await add(db, b, "folios", [{"source_id": "f1", "reservation_source_id": "r1", "currency": "EUR", "balance": "80.10"}], folio_transactions_complete=True)
    b = await add(
        db,
        b,
        "transactions",
        [
            {"source_id": "t1", "folio_source_id": "f1", "transaction_date": "2025-01-01", "kind": "charge", "amount": "100.10", "currency": "EUR"},
            {"source_id": "t2", "folio_source_id": "f1", "transaction_date": "2025-01-01", "kind": "payment", "amount": "20.00", "currency": "EUR"},
        ],
    )
    b = await finish(db, b)
    assert b["report"]["active_reservations_archive_only"] == 1
    assert await db.migration_archive.count_documents({}) == 6
    assert await db.guests.count_documents({}) == 1
    profile = await db.guests.find_one({})
    assert profile["email"].startswith(("SYR1:", "aes256gcm:"))
    assert profile["kvkk_consent"] is False and profile["marketing_consent"] is False
    staged = await db.migration_staging.find({}).to_list(None)
    assert all("Synthetic Guest" not in json.dumps(r, default=str) for r in staged)
    for collection in ("bookings", "payments", "folio_charges", "cash_flow", "gl_journal_entries", "kbs_queue", "outbox", "messages"):
        assert await db[collection].count_documents({}) == 0
    archive = await service.archive_rows(db, "A", guest_id=profile["id"])
    assert {r["entity"] for r in archive["items"]} == {"guests", "reservations"}
    assert (await service.archive_rows(db, "B"))["total"] == 0
    with pytest.raises(MigrationError):
        await service.get_batch(db, "B", b["id"])
    with pytest.raises(MigrationError, match="yayınlanmış"):
        await service.rollback(db, b, "admin")


async def test_missing_links_duplicate_ids_and_source_counts_block_commit(migration_db):
    db = migration_db
    b = await add(db, await batch(db), "reservations", [reservation()], expected_count=2, expected_totals={"total:EUR": "100.11"})
    b = await service.review(db, b, "admin")
    assert b["report"]["error_count"] == 3
    with pytest.raises(MigrationError):
        await service.commit_chunk(db, b, "admin", b["review_token"])
    assert await db.migration_archive.count_documents({}) == 0
    b = await add(db, b, "guests", [guest(), guest()])
    b = await service.review(db, b, "admin")
    assert any("tekrar" in e["message"] for e in b["report"]["errors"])


async def test_repeated_files_are_idempotent_changed_sources_conflict_and_tenants_remain_separate(migration_db):
    db = migration_db
    first = await finish(db, await add(db, await batch(db), "guests", [guest()]))
    repeated = await finish(db, await add(db, await batch(db), "guests", [guest()]))
    assert repeated["report"]["datasets"][0]["reuse"] == 1
    assert await db.migration_archive.count_documents({"tenant_id": "A"}) == 1
    changed = await add(db, await batch(db), "guests", [guest(name="Changed Name")])
    changed = await service.review(db, changed, "admin")
    assert changed["report"]["error_count"] == 1
    await finish(db, await add(db, await batch(db, tenant="B"), "guests", [guest()]))
    assert await db.migration_archive.count_documents({}) == 2
    with pytest.raises(MigrationError):
        await service.rollback(db, first, "admin")


async def test_review_token_is_invalidated_by_mapping_or_destination_changes(migration_db):
    db = migration_db
    b = await add(db, await batch(db), "guests", [guest()])
    b = await service.review(db, b, "admin")
    old = b["review_token"]
    b = await service.change_batch(db, b, "admin", {"datasets": b["datasets"]})
    with pytest.raises(MigrationError):
        await service.commit_chunk(db, b, "admin", old)
    b = await service.review(db, b, "admin")
    another = await finish(db, await add(db, await batch(db), "guests", [guest()]))
    assert another["state"] == "complete"
    with pytest.raises(MigrationError):
        await service.commit_chunk(db, b, "admin", b["review_token"])


async def test_failed_chunk_resumes_after_an_ambiguous_write_without_duplicates(migration_db, monkeypatch):
    db = migration_db
    b = await service.review(db, await add(db, await batch(db, publish=True), "guests", [guest("g1"), guest("g2")]), "admin")
    real = service._publish_guest
    failures = 0

    async def lost_response(database, job, row):
        nonlocal failures
        await real(database, job, row)
        if failures == 0:
            failures += 1
            raise TimeoutError("synthetic lost response")

    monkeypatch.setattr(service, "_publish_guest", lost_response)
    with pytest.raises(TimeoutError):
        await service.namespace_guard(db, b, lambda: service.commit_chunk(db, b, "admin", b["review_token"]))
    b = await service.get_batch(db, "A", b["id"])
    assert b["state"] == "failed"
    monkeypatch.setattr(service, "_publish_guest", real)
    b = await service.namespace_guard(db, b, lambda: service.commit_chunk(db, b, "admin", b["review_token"]))
    assert b["state"] == "complete"
    assert await db.guests.count_documents({}) == 2
    assert await db.migration_archive.count_documents({}) == 2


async def test_same_names_are_not_merged_and_strong_matches_require_explicit_link(migration_db):
    db = migration_db
    await db.guests.insert_one({"tenant_id": "A", "id": "live", "name": "Synthetic Guest", "email": "synthetic@example.invalid"})
    b = await add(db, await batch(db, publish=True), "guests", [guest(email="synthetic@example.invalid")])
    reviewed = await service.review(db, b, "admin")
    assert reviewed["report"]["error_count"] == 1
    b["datasets"][0]["guest_links"] = {"g1": "live"}
    b = await service.change_batch(db, reviewed, "admin", {"datasets": b["datasets"]})
    await finish(db, b)
    assert await db.guests.count_documents({}) == 1
    assert (await db.guests.find_one({"id": "live"}))["email"] == "synthetic@example.invalid"
    await finish(db, await add(db, await batch(db, publish=True, namespace="other-source"), "guests", [guest("g2"), guest("g3")]))
    assert await db.guests.count_documents({}) == 3


async def test_foreign_guest_links_are_rejected(migration_db):
    db = migration_db
    await db.guests.insert_one({"tenant_id": "B", "id": "foreign", "name": "Foreign Guest"})
    b = await add(db, await batch(db, publish=True), "guests", [guest()], guest_links={"g1": "foreign"})
    b = await service.review(db, b, "admin")
    assert b["report"]["error_count"] == 1


async def test_archive_only_rollback_is_scoped_and_never_touches_live_data(migration_db):
    db = migration_db
    await db.guests.insert_one({"tenant_id": "A", "id": "live", "name": "Existing Guest"})
    b = await finish(db, await add(db, await batch(db), "guests", [guest()]))
    other = await finish(db, await add(db, await batch(db, tenant="B"), "guests", [guest()]))
    result = await service.namespace_guard(db, b, lambda: service.rollback(db, b, "admin"))
    assert result["state"] == "rolled_back"
    assert await db.migration_archive.count_documents({"tenant_id": "A"}) == 0
    assert await db.migration_archive.count_documents({"tenant_id": "B"}) == 1
    assert await db.guests.count_documents({}) == 1
    assert other["state"] == "complete"


async def test_parallel_namespace_writes_are_serialized(migration_db):
    db = migration_db
    b = await batch(db)
    gate, started = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        await gate.wait()
        return "done"

    task = asyncio.create_task(service.namespace_guard(db, b, work))
    await started.wait()
    with pytest.raises(MigrationError, match="başka"):
        await service.namespace_guard(db, b, AsyncMock())
    gate.set()
    assert await task == "done"


async def test_full_folio_history_reconciles_and_wrong_currency_or_balance_blocks(migration_db):
    db = migration_db
    b = await add(db, await batch(db), "guests", [guest()])
    b = await add(db, b, "reservations", [reservation()])
    b = await add(db, b, "folios", [{"source_id": "f1", "reservation_source_id": "r1", "currency": "EUR", "balance": "100.00"}], folio_transactions_complete=True)
    b = await add(db, b, "transactions", [{"source_id": "t1", "folio_source_id": "f1", "transaction_date": "2025-01-01", "kind": "charge", "amount": "100.00", "currency": "USD"}])
    b = await service.review(db, b, "admin")
    assert any("para birimi" in e["message"] for e in b["report"]["errors"])


async def test_staging_expiry_and_disabled_encryption_fail_closed(migration_db, monkeypatch):
    db = migration_db
    b = await add(db, await batch(db), "guests", [guest()])
    await db.migration_staging.delete_many({})
    with pytest.raises(MigrationError, match="eksik"):
        await service.review(db, b, "admin")
    from core.crypto import service as crypto

    monkeypatch.setattr(crypto, "get_crypto_service", lambda: SimpleNamespace(encrypt=lambda text: text))
    with pytest.raises(MigrationError, match="Şifreleme"):
        service.seal([guest()], "A")


async def test_api_mapping_templates_auth_and_tenant_scope(migration_db, monkeypatch):
    from core.security import get_current_user
    from routers import data_migration as api

    db = migration_db
    monkeypatch.setattr(api, "get_system_db", lambda: db)
    app = FastAPI()
    app.include_router(api.router)
    user = SimpleNamespace(tenant_id="A", role="admin", id="admin", roles=["admin"])
    app.dependency_overrides[get_current_user] = lambda: user
    # Keep the actual migration role/PII checks; only unrelated licence and RBAC storage is isolated.
    for dependency in api.router.dependencies:
        app.dependency_overrides[dependency.dependency] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local.test") as client:
        response = await client.post("/api/data-migration/batches", json={"source": "Synthetic", "namespace": "legacy", "tenant_id": "B"})
        assert response.status_code == 201
        b = response.json()
        assert b["tenant_id"] == "A"
        response = await client.post(f"/api/data-migration/batches/{b['id']}/files", data={"entity": "guests"}, files={"file": ("guests.csv", b"source_id,name\ng1,Synthetic Guest", "text/csv")})
        assert response.status_code == 200
        b = response.json()
        dataset = b["datasets"][0]
        bad_mapping = {"mapping": {"$set": "name"}}
        assert (await client.put(f"/api/data-migration/batches/{b['id']}/datasets/{dataset['id']}", json=bad_mapping)).status_code == 422
        response = await client.post("/api/data-migration/mapping-templates", json={"name": "Synthetic layout", "batch_id": b["id"], "dataset_id": dataset["id"]})
        assert response.status_code == 200
        assert "guest_links" not in response.json()
        assert (await client.get("/api/data-migration/mapping-templates")).json()["items"][0]["entity"] == "guests"
        response = await client.post(f"/api/data-migration/batches/{b['id']}/review")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        approved = response.json()
        assert (await client.post(f"/api/data-migration/batches/{b['id']}/commit", json={"review_token": approved["review_token"], "archive_only_ack": False, "warnings_ack": True})).status_code == 422
        response = await client.post(f"/api/data-migration/batches/{b['id']}/commit", json={"review_token": approved["review_token"], "archive_only_ack": True, "warnings_ack": True})
        assert response.status_code == 200 and response.json()["state"] == "complete"
        response = await client.get("/api/data-migration/archive")
        assert response.status_code == 200 and response.json()["total"] == 1
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get("/api/data-migration/templates/guests.csv")).status_code == 200
        user.tenant_id = "B"
        assert (await client.get(f"/api/data-migration/batches/{b['id']}")).status_code == 422
        assert (await client.get("/api/data-migration/mapping-templates")).json()["items"] == []
        user.role = "receptionist"
        assert (await client.get("/api/data-migration/schema")).status_code == 403
        user.role = "admin"
        user.guest_data_visibility = {"identity": "hidden"}
        assert (await client.get("/api/data-migration/archive")).status_code == 403
        user.guest_data_visibility = None
        user.tenant_id = ""
        with pytest.raises(HTTPException):
            api.require_migration_admin(Response(), user)


async def test_all_eight_entities_keep_their_relationships_and_currency_totals(migration_db):
    db = migration_db
    b = await batch(db)
    for entity in ("companies", "agencies"):
        b = await add(db, b, entity, [{"source_id": entity + "1", "name": "Synthetic organisation"}])
    b = await add(db, b, "rooms", [{"source_id": "room1", "room_number": "001", "room_type": "Suite"}])
    b = await add(db, b, "guests", [guest(company_source_id="companies1", agency_source_id="agencies1")])
    b = await add(db, b, "reservations", [reservation(room_source_id="room1", company_source_id="companies1", agency_source_id="agencies1")], expected_count=1, expected_totals={"total:EUR": "100.10"})
    b = await add(db, b, "folios", [{"source_id": "f1", "reservation_source_id": "r1", "currency": "EUR", "balance": "80.10"}], folio_transactions_complete=True)
    b = await add(
        db,
        b,
        "transactions",
        [
            {"source_id": "charge", "folio_source_id": "f1", "transaction_date": "2025-01-01", "kind": "charge", "amount": "100.10", "currency": "EUR"},
            {"source_id": "payment", "folio_source_id": "f1", "transaction_date": "2025-01-01", "kind": "payment", "amount": "20.00", "currency": "EUR"},
        ],
    )
    b = await add(db, b, "balances", [{"source_id": "balance1", "company_source_id": "companies1", "balance_date": "2025-01-03", "kind": "receivable", "amount": "80.10", "currency": "EUR"}])
    b = await finish(db, b)
    archived = await service.archive_rows(db, "A")
    assert len(archived["items"]) == 9
    reservation_row = next(r for r in archived["items"] if r["entity"] == "reservations")
    assert len(reservation_row["refs"]) == 4
    children = await service.archive_rows(db, "A", parent_key=reservation_row["id"])
    assert [row["entity"] for row in children["items"]] == ["folios"]
    assert await db.bookings.count_documents({}) == await db.payments.count_documents({}) == 0
    stat = next(d for d in b["report"]["datasets"] if d["entity"] == "reservations")
    assert stat["source_reconciled"] is True and stat["totals"] == {"total:EUR": "100.10"}


async def test_full_folio_wrong_balance_is_not_accepted_as_a_reconciled_history(migration_db):
    db = migration_db
    b = await add(db, await batch(db), "guests", [guest()])
    b = await add(db, b, "reservations", [reservation()])
    b = await add(db, b, "folios", [{"source_id": "f1", "reservation_source_id": "r1", "currency": "EUR", "balance": "1.00"}], folio_transactions_complete=True)
    b = await add(db, b, "transactions", [{"source_id": "t1", "folio_source_id": "f1", "transaction_date": "2025-01-01", "kind": "charge", "amount": "100.10", "currency": "EUR"}])
    b = await service.review(db, b, "admin")
    assert any("bakiye uyuşmuyor" in error["message"] for error in b["report"]["errors"])


async def test_large_batch_is_bounded_and_resumes_multiple_chunks(migration_db):
    db = migration_db
    b = await service.review(db, await add(db, await batch(db), "guests", [guest(f"g{i}") for i in range(251)]), "admin")
    positions = []
    while b["state"] != "complete":
        b = await service.namespace_guard(db, b, lambda: service.commit_chunk(db, b, "admin", b["review_token"]))
        positions.append(b["cursor"])
    assert positions == [100, 200, 251]
    assert await db.migration_archive.count_documents({}) == 251


async def test_bulk_identity_lookup_uses_bounded_queries_and_same_name_alone_is_not_identity(migration_db):
    db = migration_db
    await db.guests.insert_one({"tenant_id": "A", "id": "existing", "name": "Synthetic Guest", "email": "synthetic-100@example.invalid"})
    query_count = 0

    class CountingGuests:
        def find(self, *args, **kwargs):
            nonlocal query_count
            query_count += 1
            return db.guests.find(*args, **kwargs)

    records = [(str(i), guest(str(i), email=f"synthetic-{i}@example.invalid")) for i in range(251)]
    matches = await service.existing_guest_matches(SimpleNamespace(guests=CountingGuests()), "A", records)
    assert query_count == 3
    assert matches["100"] == {"existing"} and not matches["101"]


async def test_existing_guest_link_configuration_is_encrypted_at_rest(migration_db):
    db = migration_db
    b = await add(db, await batch(db, publish=True), "guests", [guest()], guest_links={"private-old-id": "private-current-id"})
    raw = await db.migration_batches.find_one({"id": b["id"]})
    assert "private-old-id" not in json.dumps(raw, default=str)
    assert (await service.get_batch(db, "A", b["id"]))["datasets"][0]["guest_links"] == {"private-old-id": "private-current-id"}


async def test_old_review_plan_parts_do_not_poison_a_new_approved_plan(migration_db):
    db = migration_db
    b = await service.review(db, await add(db, await batch(db), "guests", [guest()]), "admin")
    await db.migration_staging.insert_one({"tenant_id": "A", "batch_id": b["id"], "dataset_id": "plan:" + b["id"] + ":" + "0" * 64, "part": 99, "payload": service.seal([], "A")})
    b = await service.namespace_guard(db, b, lambda: service.commit_chunk(db, b, "admin", b["review_token"]))
    assert b["state"] == "complete"


async def test_profile_encryption_failure_never_falls_back_to_plaintext(migration_db, monkeypatch):
    from security import guest_write

    db = migration_db
    b = await service.review(db, await add(db, await batch(db, publish=True), "guests", [guest(email="synthetic@example.invalid")]), "admin")
    monkeypatch.setattr(guest_write, "encrypt_guest_insert", lambda doc: doc)
    with pytest.raises(MigrationError, match="şifrelemesi"):
        await service.namespace_guard(db, b, lambda: service.commit_chunk(db, b, "admin", b["review_token"]))
    assert await db.guests.count_documents({}) == 0
    assert (await service.get_batch(db, "A", b["id"]))["state"] == "failed"


def test_private_fingerprints_preserve_case_sensitive_source_identifiers():
    from modules.data_migration.schema import private_fingerprint, record_id

    assert record_id("A", "legacy", "guests", "ABC") != record_id("A", "legacy", "guests", "abc")
    assert private_fingerprint({"name": "Synthetic"}) != private_fingerprint({"name": "synthetic"})


async def test_vendor_specific_columns_can_be_preserved_without_becoming_database_fields(migration_db):
    db = migration_db
    b = await add(db, await batch(db), "guests", [guest(**{"legacy.vip": "Example level", "$source_note": "Synthetic private note"})], preserve_extra_fields=True)
    b = await finish(db, b)
    stat = b["report"]["datasets"][0]
    assert stat["unmapped_preserved"] and set(stat["unmapped_columns"]) == {"legacy.vip", "$source_note"}
    raw = await db.migration_archive.find_one({})
    assert "Synthetic private note" not in json.dumps(raw, default=str)
    assert "$source_note" not in raw
    archive = await service.archive_rows(db, "A")
    assert archive["items"][0]["data"]["source_fields"] == {"legacy.vip": "Example level", "$source_note": "Synthetic private note"}
