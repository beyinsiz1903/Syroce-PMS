"""Synthetic-only live-cutover acceptance, using the real atomic booking core."""

import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from modules.data_migration import api_source, cutover, service
from modules.data_migration.formats import MigrationError
from tests.test_data_migration import add, batch, finish, guest, reservation
from tests.test_data_migration import migration_db as migration_db_fixture

migration_db = migration_db_fixture


@pytest.fixture
async def ready(migration_db, monkeypatch):
    from core import atomic_booking

    db = migration_db
    monkeypatch.setattr(atomic_booking, "db", db)
    monkeypatch.setattr(atomic_booking, "get_system_db", lambda: db)
    monkeypatch.setattr(atomic_booking, "_timeline_event", AsyncMock())
    monkeypatch.setattr(atomic_booking, "_emit_overbooking_alert", AsyncMock())
    # Use today's real date so frozen-at validation is deterministic in any CI year.
    today = datetime.now(UTC).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Istanbul")).date()
    day = today.isoformat()
    await db.tenant_settings.insert_one({"tenant_id": "A", "business_date": day})
    await db.rooms.insert_one({"id": "room-a", "tenant_id": "A", "room_number": "101", "room_type": "standard", "capacity": 3})
    await db.gl_setup_profiles.insert_one({"tenant_id": "A", "currency": "TRY"})
    for code, kind in (("120", "asset"), ("320", "liability"), ("340", "liability"), ("500", "equity")):
        await db.gl_accounts.insert_one({"tenant_id": "A", "code": code, "active": True, "type": kind})
    b = await batch(db, publish=True)
    b = await add(db, b, "guests", [guest()], expected_count=1)
    b = await add(db, b, "rooms", [{"source_id": "room-old", "room_number": "101", "room_type": "standard"}], expected_count=1)
    b = await add(
        db,
        b,
        "reservations",
        [reservation(status="confirmed", room_source_id="room-old", check_in=day, check_out=(today + timedelta(days=2)).isoformat(), currency="TRY", total_amount="200.00")],
        expected_count=1,
        expected_totals={"total:TRY": "200.00"},
    )
    b = await add(
        db,
        b,
        "folios",
        [{"source_id": "f1", "reservation_source_id": "r1", "currency": "TRY", "balance": "0.00", "charged_amount": "0.00", "paid_amount": "0.00"}],
        expected_count=1,
        expected_totals={"total:TRY": "0.00"},
    )
    b = await add(
        db,
        b,
        "daily_rates",
        [{"source_id": f"rate-{i}", "reservation_source_id": "r1", "rate_date": (today + timedelta(days=i)).isoformat(), "amount": "100.00", "currency": "TRY"} for i in range(2)],
        expected_count=2,
        expected_totals={"total:TRY": "200.00"},
    )
    b = await finish(db, b)
    config = {
        "cutover_date": day,
        "source_frozen_at": datetime.now(UTC).isoformat(),
        "target_links": {"rooms": {"room-old": "room-a"}},
        "accounts": {"receivable": "120", "payable": "320", "deposit": "340", "clearing": "500"},
        "exchange_rates": {"TRY": "1"},
        "source_writes_stopped": True,
    }
    return db, b, config


async def reviewed(db, b, config):
    await cutover.configure(db, b, "admin", config)
    return await cutover.review(db, b, "admin")


async def test_future_reservation_activation_is_atomic_idempotent_and_silent(ready):
    db, b, config = ready
    job = await reviewed(db, b, config)
    assert job["report"]["error_count"] == 0, job
    job = await service.namespace_guard(db, b, lambda: cutover.activate(db, b, "admin", job["review_token"]))
    assert job["state"] == "complete"
    await cutover.activate(db, b, "admin", job["review_token"])
    assert await db.bookings.count_documents({"tenant_id": "A"}) == 1
    assert await db.room_night_locks.count_documents({"tenant_id": "A"}) == 2
    assert await db.folios.count_documents({"tenant_id": "A"}) == 1
    saved = await db.bookings.find_one({"tenant_id": "A"})
    assert saved["origin"] == "import" and saved["messaging_pending"] == {}
    assert saved["kbs_migration_review_required"] is False  # Future arrivals use normal new check-in reporting.
    for collection in ("payments", "folio_charges", "outbox_events", "kbs_jobs", "gl_journal_entries"):
        assert await db[collection].count_documents({}) == 0
    other = await service.create_batch(db, "A", "admin", source="delta", namespace=b["namespace"])
    other = await add(db, other, "guests", [guest("g-new")])
    other = await service.review(db, other, "admin")
    with pytest.raises(MigrationError, match="donduruldu"):
        await service.commit_chunk(db, other, "admin", other["review_token"])


@pytest.mark.parametrize("problem", ["foreign_room", "room_missing", "overlap", "block", "pending", "rate_missing", "unreconciled", "business_date", "stale_stay"])
async def test_cutover_blocks_unsafe_target_and_incomplete_source(ready, problem):
    db, b, config = ready
    if problem == "foreign_room":
        await db.rooms.update_one({"id": "room-a"}, {"$set": {"tenant_id": "B"}})
    elif problem == "room_missing":
        config["target_links"] = {}
    elif problem == "overlap":
        await db.bookings.insert_one(
            {
                "id": "other",
                "tenant_id": "A",
                "room_id": "room-a",
                "status": "confirmed",
                "check_in": config["cutover_date"],
                "check_out": (date.fromisoformat(config["cutover_date"]) + timedelta(days=2)).isoformat(),
            }
        )
    elif problem == "block":
        await db.room_night_locks.insert_one({"tenant_id": "A", "room_id": "room-a", "night_date": config["cutover_date"], "booking_id": "OOO:test"})
    elif problem in {"pending", "stale_stay"}:
        row = await db.migration_archive.find_one({"entity": "reservations"})
        data = service.unseal(row["payload"], "A")
        data.update({"status": "pending"} if problem == "pending" else {"check_out": config["cutover_date"]})
        await db.migration_archive.update_one({"_id": row["_id"]}, {"$set": {"payload": service.seal(data, "A")}})
    elif problem == "rate_missing":
        await db.migration_archive.delete_one({"entity": "daily_rates"})
    elif problem == "unreconciled":
        await db.migration_batches.update_one({"id": b["id"]}, {"$set": {"report.all_source_reconciled": False}})
    else:
        config["cutover_date"] = "2000-01-01"
    try:
        job = await reviewed(db, b, config)
    except MigrationError:
        pass
    else:
        assert job["report"]["error_count"] > 0, job
        with pytest.raises(MigrationError):
            await cutover.activate(db, b, "admin", job["review_token"])
    assert await db.folios.count_documents({}) == 0


async def test_target_conflict_arriving_after_review_is_still_rejected(ready):
    db, b, config = ready
    job = await reviewed(db, b, config)
    await db.bookings.insert_one(
        {
            "id": "new-booking",
            "tenant_id": "A",
            "room_id": "room-a",
            "status": "confirmed",
            "check_in": config["cutover_date"],
            "check_out": (date.fromisoformat(config["cutover_date"]) + timedelta(days=2)).isoformat(),
        }
    )
    from core.atomic_booking import BookingConflictError

    with pytest.raises(BookingConflictError):
        await cutover.activate(db, b, "admin", job["review_token"])
    assert (await cutover.get_job(db, b))["state"] == "failed"
    assert await db.room_night_locks.count_documents({}) == 0


async def test_financial_cutover_requires_exact_posted_voucher_and_never_replays_cash(ready):
    db, b, config = ready
    folio = await db.migration_archive.find_one({"entity": "folios"})
    data = service.unseal(folio["payload"], "A")
    data.update({"paid_amount": "50.00", "balance": "-50.00"})
    await db.migration_archive.update_one({"_id": folio["_id"]}, {"$set": {"payload": service.seal(data, "A"), "content_hash": service.private_fingerprint(data)}})
    job = await reviewed(db, b, config)
    assert not job["report"]["error_count"], job
    assert job["report"]["totals"] == {"deposit:TRY": "50.00"}
    with pytest.raises(MigrationError, match="muhasebede"):
        await cutover.activate(db, b, "admin", job["review_token"])
    _, plan = await cutover.activation_plan(db, b, job["review_token"])
    from shared_kernel.gl_posting import normalize_journal_lines

    voucher = {"id": "v1", "tenant_id": "A", "date": config["cutover_date"], "status": "draft", "lines": normalize_journal_lines(plan["lines"])[0]}
    await db.gl_vouchers.insert_one(voucher)
    await cutover.record_voucher(db, b, job["review_token"], voucher)
    with pytest.raises(MigrationError):
        await cutover.activate(db, b, "admin", job["review_token"])
    await db.gl_vouchers.update_one({"id": "v1"}, {"$set": {"status": "posted"}})
    job = await cutover.activate(db, b, "admin", job["review_token"])
    assert job["state"] == "complete"
    from modules.pms_core.receivable_reporting import folio_snapshots

    saved = await db.folios.find_one({"tenant_id": "A"})
    snapshots = await folio_snapshots(db, "A", [saved], fallback_currency="TRY")
    assert snapshots[saved["id"]]["balance_by_currency"] == {"TRY": -50.0}
    assert snapshots[saved["id"]]["charges_by_currency"] == {}
    assert snapshots[saved["id"]]["payments_by_currency"] == {}


async def test_in_house_cutover_balances_night_audit_and_checkout_remain_consistent(ready, monkeypatch):
    db, b, config = ready
    today = date.fromisoformat(config["cutover_date"])
    async for row in db.migration_archive.find({"tenant_id": "A", "entity": {"$in": ["reservations", "folios", "daily_rates"]}}):
        data = service.unseal(row["payload"], "A")
        if row["entity"] == "reservations":
            data.update({"status": "checked_in", "check_in": (today - timedelta(days=1)).isoformat(), "check_out": (today + timedelta(days=1)).isoformat()})
        elif row["entity"] == "daily_rates":
            data["rate_date"] = (today - timedelta(days=1) if data["source_id"] == "rate-0" else today).isoformat()
        else:
            data.update({"charged_amount": "100.00", "paid_amount": "50.00", "balance": "50.00"})
        await db.migration_archive.update_one({"_id": row["_id"]}, {"$set": {"payload": service.seal(data, "A"), "content_hash": service.private_fingerprint(data)}})
    job = await reviewed(db, b, config)
    assert not job["report"]["error_count"], job
    _, plan = await cutover.activation_plan(db, b, job["review_token"])
    from shared_kernel.gl_posting import normalize_journal_lines

    voucher = {"id": "opening", "tenant_id": "A", "status": "posted", "date": config["cutover_date"], "lines": normalize_journal_lines(plan["lines"])[0]}
    await db.gl_vouchers.insert_one(voucher)
    await cutover.record_voucher(db, b, job["review_token"], voucher)
    job = await cutover.activate(db, b, "admin", job["review_token"])
    assert job["state"] == "complete"
    saved = await db.bookings.find_one({"tenant_id": "A"})
    assert saved["status"] == "checked_in" and saved["kbs_migration_review_required"]
    assert (await db.rooms.find_one({"id": "room-a"}))["current_booking_id"] == saved["id"]
    from core.channel_room_charge_pricing import calculate_room_charge
    from core.folio_checkout_reconciliation import reconcile_unposted_room_charge
    from routers import reservation_detail

    monkeypatch.setattr(reservation_detail, "db", db)
    assert await reservation_detail._reservation_outstanding_balance("A", saved) == 150
    assert calculate_room_charge(saved, (today - timedelta(days=1)).isoformat(), explicit_daily_rate=100)["total"] == 0
    posted = await reconcile_unposted_room_charge(db, tenant_id="A", booking=saved, posted_by="synthetic-checkout")
    assert posted["amount"] == 100  # Not 200: the source night was already accrued.
    await db.payments.insert_one({"tenant_id": "A", "booking_id": saved["id"], "folio_id": saved["folio_id"], "amount": 150, "status": "paid", "method": "cash"})
    assert await reservation_detail._reservation_outstanding_balance("A", saved) == 0


async def test_archival_deltas_preserve_encrypted_prior_version_and_never_rewrite_profile(migration_db):
    db = migration_db
    b = await add(db, await batch(db, publish=True), "guests", [guest()])
    b = await finish(db, b)
    old = await db.migration_archive.find_one({"entity": "guests"})
    new = await service.create_batch(db, "A", "admin", source="Final delta", namespace=b["namespace"], allow_archive_updates=True)
    new = await add(db, new, "guests", [guest(name="Changed source name")])
    new = await finish(db, new)
    archive = await db.migration_archive.find_one({"id": old["id"]})
    assert service.unseal(archive["payload"], "A")["name"] == "Changed source name"
    assert archive["guest_id"] == old["guest_id"]
    version = await db.migration_versions.find_one({"record_id": old["id"]})
    assert service.unseal(version["previous"]["payload"], "A")["name"] == "Synthetic Guest"
    assert (await db.guests.find_one({"id": old["guest_id"]}))["name"] == "Synthetic Guest"
    with pytest.raises(MigrationError, match="Sürümlü"):
        await service.rollback(db, new, "admin")


async def test_resume_after_lost_checkpoint_never_overwrites_operator_edit(ready, monkeypatch):
    from core import atomic_booking

    db, b, config = ready
    job = await reviewed(db, b, config)
    original = atomic_booking.create_booking_atomic
    calls = 0

    async def fail_checkpoint(*args, **kwargs):
        nonlocal calls
        result = await original(*args, **kwargs)
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic lost checkpoint")
        return result

    monkeypatch.setattr(atomic_booking, "create_booking_atomic", fail_checkpoint)
    with pytest.raises(RuntimeError):
        await cutover.activate(db, b, "admin", job["review_token"])
    await db.bookings.update_one({"tenant_id": "A"}, {"$set": {"special_requests": "Operator edit after interruption"}})
    job = await cutover.activate(db, b, "admin", job["review_token"])
    assert job["state"] == "complete"
    assert await db.bookings.count_documents({}) == 1
    assert (await db.bookings.find_one({}))["special_requests"] == "Operator edit after interruption"


async def test_source_cutover_claim_prevents_second_batch_opening(ready):
    db, b, _ = ready
    await cutover.claim_source(db, b)
    other = await service.create_batch(db, "A", "admin", source="Second", namespace=b["namespace"])
    with pytest.raises(MigrationError, match="başka canlı"):
        await cutover.claim_source(db, other)


async def test_commercial_party_reservations_do_not_invent_target_default_commissions(ready):
    db, b, config = ready
    record = await db.migration_archive.find_one({"entity": "reservations"})
    await db.migration_archive.update_one({"_id": record["_id"]}, {"$set": {"refs.agency_source_id": "opaque-source-agency"}})
    job = await reviewed(db, b, config)
    assert any("komisyon" in error["message"] for error in job["report"]["errors"])
    with pytest.raises(MigrationError):
        await cutover.activate(db, b, "admin", job["review_token"])
    assert await db.bookings.count_documents({}) == 0


async def test_encrypted_source_attachments_are_idempotent_and_tenant_scoped(ready):
    import io

    from PIL import Image

    from modules.data_migration import attachments

    db, _, _ = ready
    record = await db.migration_archive.find_one({"entity": "guests"})
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="PNG")
    content = output.getvalue()
    first = await attachments.upload(db, "A", record["id"], "doc-1", "synthetic.png", content)
    second = await attachments.upload(db, "A", record["id"], "doc-1", "synthetic.png", content)
    assert first["id"] == second["id"]
    stored = await db.migration_attachments.find_one({"id": first["id"]})
    assert "synthetic.png" not in str(stored)
    assert await attachments.download(db, "A", first["id"]) == (content, "image/png", ".png")
    with pytest.raises(MigrationError):
        await attachments.download(db, "B", first["id"])
    with pytest.raises(MigrationError):
        await attachments.upload(db, "A", record["id"], "doc-2", "fake.pdf", b"<script>not a PDF</script>")


async def test_foreign_opening_is_balanced_per_currency_and_rejects_revenue_accounts(ready):
    db, b, config = ready
    g = await db.migration_archive.find_one({"entity": "guests"})
    key = service.record_id("A", b["namespace"], "balances", "bal-1")
    data = {"source_id": "bal-1", "guest_source_id": "g1", "balance_date": config["cutover_date"], "kind": "receivable", "amount": "10.00", "currency": "EUR"}
    await db.migration_archive.insert_one(
        {
            "id": key,
            "tenant_id": "A",
            "namespace": b["namespace"],
            "owner_batch_id": b["id"],
            "entity": "balances",
            "content_hash": service.private_fingerprint(data),
            "payload": service.seal(data, "A"),
            "refs": {"guest_source_id": g["id"]},
        }
    )
    config.update({"exchange_rates": {"TRY": "1", "EUR": "40.123456"}, "balances_exclude_folios": True})
    job = await reviewed(db, b, config)
    assert not job["report"]["error_count"], job
    _, plan = await cutover.activation_plan(db, b, job["review_token"])
    assert sum(float(l["debit"]) for l in plan["lines"]) == sum(float(l["credit"]) for l in plan["lines"]) == 401.23
    assert job["report"]["totals"] == {"receivable:EUR": "10.00"}
    await db.gl_accounts.update_one({"code": "120"}, {"$set": {"type": "revenue"}})
    job = await cutover.review(db, b, "admin")
    assert any("bilanço" in e["message"] for e in job["report"]["errors"])


@pytest.mark.parametrize("problem", [None, "cursor_loop", "changed_snapshot", "wrong_count", "secret_column", "unauthorized"])
async def test_configured_json_api_snapshots_are_bounded_and_tenant_authorized(migration_db, monkeypatch, problem):
    db = migration_db
    b = await batch(db)
    monkeypatch.setenv(
        "DATA_MIGRATION_API_SOURCES",
        json.dumps([{"id": "legacy-guests", "label": "Synthetic", "url": "https://legacy.example/export/guests", "token_env": "MIGRATION_SOURCE_TEST_TOKEN", "tenant_ids": ["A"], "entity": "guests"}]),
    )
    monkeypatch.setenv("MIGRATION_SOURCE_TEST_TOKEN", "synthetic-source-token-not-real")
    calls = []

    async def download(url, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic-source-token-not-real"
        page = len(calls)
        row = guest(str(page)) if problem != "secret_column" else {"source_id": str(page), "password": "do-not-retain"}
        return json.dumps(
            {
                "snapshot_id": "changed" if problem == "changed_snapshot" and page == 2 else "snapshot-1",
                "total_count": 3 if problem == "wrong_count" else 2,
                "records": [row],
                "next_cursor": "page2" if page == 1 or problem == "cursor_loop" else None,
            }
        ).encode()

    monkeypatch.setattr("integrations.xchange.safety.safe_download_async", download)
    if problem == "unauthorized":
        b = await batch(db, tenant="B")
    if problem:
        with pytest.raises(MigrationError):
            await api_source.import_snapshot(db, b, "admin", "legacy-guests")
        assert await db.migration_staging.count_documents({}) == 0
    else:
        result = await api_source.import_snapshot(db, b, "admin", "legacy-guests")
        assert result["datasets"][0]["expected_count"] == 2
        assert "synthetic-source-token" not in str(result)
        calls.clear()
        replay = await api_source.import_snapshot(db, result, "admin", "legacy-guests")
        assert len(replay["datasets"]) == 1


def test_imported_room_pricing_never_charges_pre_cutover_dates():
    from core.channel_room_charge_pricing import calculate_room_charge

    booking = {"check_in": "2026-01-01", "check_out": "2026-01-04", "total_amount": 300, "migration_cutover_date": "2026-01-03"}
    assert calculate_room_charge(booking, "2026-01-02", explicit_daily_rate=100)["total"] == 0
    assert calculate_room_charge(booking, "2026-01-03", explicit_daily_rate=100)["total"] == 100


async def test_nightly_kbs_sweep_cannot_replay_imported_in_house_checkin(migration_db, monkeypatch):
    from core import kbs_auto_enqueue

    db = migration_db
    monkeypatch.setattr(kbs_auto_enqueue, "db", db)
    monkeypatch.setattr(kbs_auto_enqueue, "_build_payload_snapshot", AsyncMock(return_value={"guest_name": "Synthetic"}))
    await db.bookings.insert_one({"tenant_id": "A", "id": "migrated", "guest_id": "g1", "status": "checked_in", "kbs_migration_review_required": True})
    for _ in range(2):
        assert await kbs_auto_enqueue.auto_enqueue_kbs("A", "migrated", "checkin", target_guest_id="g1") is None
    assert await db.kbs_reports.count_documents({}) == 0
    assert await db.kbs_alerts.count_documents({"kind": "migration_review_required"}) == 1


def test_imported_reservation_summary_preserves_past_amounts_without_cash_rows():
    from routers.reservation_detail import _build_financial_summary

    booking = {
        "check_in": "2026-01-01",
        "check_out": "2026-01-04",
        "total_amount": 300,
        "migration_cutover_date": "2026-01-03",
        "migration_financial_snapshot": {"charged": "220", "paid": "250", "accommodation": "200"},
    }
    summary = _build_financial_summary(booking, [], [], [], [])
    assert summary["folio_balance"] == -30
    assert summary["reservation_total_due"] == 70
    assert summary["unposted_room_amount"] == 100
    assert summary["source_paid_amount"] == 250
    assert summary["additional_charge_total"] == 20
    assert summary["gross_total"] == 320
