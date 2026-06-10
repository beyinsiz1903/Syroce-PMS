"""
Night Audit Engine - Business date roll, room charge posting, pending arrival/departure control,
unbalanced folio detection, tax consistency, daily snapshot, exceptions queue.
"""
import uuid
from datetime import UTC, date, datetime, timedelta

from core.database import db

# A night audit completes in well under 5s even at 500 rooms; 900s (the same
# stale threshold the hardened engine uses) is a very safe window after which a
# lock abandoned by a SIGKILL'd run is considered stale and may be taken over,
# so the nightly-critical path can never deadlock permanently.
NIGHT_AUDIT_LOCK_STALE_SECONDS = 900


class NightAuditEngine:
    """Executes nightly audit operations for a hotel property."""

    _LOCK_COLLECTION = "night_audit_locks"

    async def _acquire_lock(self, tenant_id: str, business_date: str) -> str | None:
        """Acquire an exclusive run-level lock for (tenant_id, business_date).

        Returns a fresh lock_id on success, or None when another run already
        holds the lock. Atomicity depends on the unique partial index
        idx_na_locks_active_unique (night_audit_locks: tenant_id+business_date
        WHERE released=False) built by ensure_night_audit_indexes(): two
        concurrent upserts can only ever insert ONE document. The loser either
        raises DuplicateKeyError or is retried by the driver as a plain update
        (matched=1, upserted_id=None); both paths return None below.
        """
        lock_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        lock_doc = {
            "id": lock_id,
            "tenant_id": tenant_id,
            "business_date": business_date,
            "acquired_at": now.isoformat(),
            "released": False,
        }
        try:
            result = await db[self._LOCK_COLLECTION].update_one(
                {"tenant_id": tenant_id, "business_date": business_date, "released": False},
                {"$setOnInsert": lock_doc},
                upsert=True,
            )
            if result.upserted_id is not None:
                return lock_id
        except Exception:
            # DuplicateKeyError (lost the race) or a transient error: fall
            # through to the stale-takeover check.
            pass

        # An active lock already exists. Take it over ONLY if it is stale (a
        # previous run was killed before its finally released it). The
        # conditional release (acquired_at < cutoff) guarantees a FRESH lock is
        # never stolen, and the unique index makes concurrent takeovers safe
        # (only one re-acquire can win).
        cutoff = (now - timedelta(seconds=NIGHT_AUDIT_LOCK_STALE_SECONDS)).isoformat()
        takeover = await db[self._LOCK_COLLECTION].update_one(
            {
                "tenant_id": tenant_id,
                "business_date": business_date,
                "released": False,
                "acquired_at": {"$lt": cutoff},
            },
            {"$set": {"released": True, "released_at": now.isoformat(), "stale_takeover": True}},
        )
        if takeover.modified_count:
            try:
                result = await db[self._LOCK_COLLECTION].update_one(
                    {"tenant_id": tenant_id, "business_date": business_date, "released": False},
                    {"$setOnInsert": lock_doc},
                    upsert=True,
                )
                if result.upserted_id is not None:
                    return lock_id
            except Exception:
                return None
        return None

    async def _release_lock(self, lock_id: str):
        """Release the lock held by THIS run, addressed by its lock id.

        Releasing by (tenant_id, business_date) would be unsafe once
        stale-takeover exists: it could match an older released doc and leave
        the active lock held, or (after a takeover) release the NEW owner's
        lock and reopen the double-post window. Always release the exact lock
        this run acquired.
        """
        await db[self._LOCK_COLLECTION].update_one(
            {"id": lock_id, "released": False},
            {"$set": {"released": True, "released_at": datetime.now(UTC).isoformat()}},
        )

    async def run_night_audit(self, tenant_id: str, business_date: str, started_by: str) -> dict:
        """Execute complete night audit for a business date.

        Concurrency guard: at most one in-flight audit per (tenant_id,
        business_date). A second concurrent run returns
        {"success": False, "code": "already_running"} which the route maps to
        HTTP 409. The unique dedup index on folio_charges is the DB-level
        backstop that keeps room charges / folio.balance posted exactly once
        even if the lock is ever bypassed.
        """
        lock_id = await self._acquire_lock(tenant_id, business_date)
        if not lock_id:
            return {
                "success": False,
                "code": "already_running",
                "tenant_id": tenant_id,
                "audit_date": business_date,
                "message": f"Night audit already running for {business_date}",
            }

        try:
            audit_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            audit_record = {
                "id": audit_id,
                "tenant_id": tenant_id,
                "audit_date": business_date,
                "started_at": now.isoformat(),
                "started_by": started_by,
                "status": "in_progress",
                "steps": [],
                "exceptions": [],
                "warnings": [],
            }

            try:
                # Step 1: Pending arrivals control
                arrivals = await self._check_pending_arrivals(tenant_id, business_date)
                audit_record["steps"].append({"step": "pending_arrivals", "result": arrivals})
                audit_record["exceptions"].extend(arrivals.get("exceptions", []))

                # Step 2: Pending departures control
                departures = await self._check_pending_departures(tenant_id, business_date)
                audit_record["steps"].append({"step": "pending_departures", "result": departures})
                audit_record["exceptions"].extend(departures.get("exceptions", []))

                # Step 3: No-show processing
                no_shows = await self._process_no_shows(tenant_id, business_date, started_by)
                audit_record["steps"].append({"step": "no_show_processing", "result": no_shows})

                # Step 4: Room charge posting
                room_charges = await self._post_room_charges(tenant_id, business_date, started_by)
                audit_record["steps"].append({"step": "room_charge_posting", "result": room_charges})
                audit_record["exceptions"].extend(room_charges.get("exceptions", []))

                # Step 5: Unbalanced folio detection
                unbalanced = await self._detect_unbalanced_folios(tenant_id)
                audit_record["steps"].append({"step": "unbalanced_folios", "result": unbalanced})
                audit_record["warnings"].extend(unbalanced.get("warnings", []))

                # Step 6: Tax consistency check
                tax_check = await self._check_tax_consistency(tenant_id, business_date)
                audit_record["steps"].append({"step": "tax_consistency", "result": tax_check})
                audit_record["warnings"].extend(tax_check.get("warnings", []))

                # Step 7: Daily snapshot
                snapshot = await self._create_daily_snapshot(tenant_id, business_date, room_charges)
                audit_record["steps"].append({"step": "daily_snapshot", "result": {"snapshot_id": snapshot["id"]}})

                # Step 8: Business date roll
                await self._roll_business_date(tenant_id, business_date)
                audit_record["steps"].append({"step": "business_date_roll", "result": {"new_business_date": self._next_date(business_date)}})

                audit_record["status"] = "completed"
                audit_record["completed_at"] = datetime.now(UTC).isoformat()

            except Exception as e:
                audit_record["status"] = "failed"
                audit_record["error"] = str(e)
                audit_record["completed_at"] = datetime.now(UTC).isoformat()

            await db.night_audit_records.insert_one(audit_record)

            # Store exceptions in queue
            for exc in audit_record["exceptions"]:
                await db.audit_exceptions.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "audit_id": audit_id,
                    "audit_date": business_date,
                    "exception_type": exc.get("type"),
                    "description": exc.get("description"),
                    "entity_type": exc.get("entity_type"),
                    "entity_id": exc.get("entity_id"),
                    "status": "open",
                    "created_at": datetime.now(UTC).isoformat(),
                })

            audit_record.pop("_id", None)
            return audit_record
        finally:
            await self._release_lock(lock_id)

    async def _check_pending_arrivals(self, tenant_id: str, business_date: str) -> dict:
        """Check for expected arrivals that haven't checked in."""
        arrivals = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$lte": business_date + "T23:59:59"},
        }, {"_id": 0, "id": 1, "guest_id": 1, "room_id": 1, "check_in": 1, "status": 1}).to_list(500)

        # Filter to today's arrivals
        today_arrivals = [a for a in arrivals if a["check_in"][:10] <= business_date]
        exceptions = [
            {"type": "pending_arrival", "description": f"Booking {a['id']} not checked in (arrival: {a['check_in'][:10]})",
             "entity_type": "booking", "entity_id": a["id"]}
            for a in today_arrivals
        ]

        return {"count": len(today_arrivals), "bookings": today_arrivals, "exceptions": exceptions}

    async def _check_pending_departures(self, tenant_id: str, business_date: str) -> dict:
        """Check for guests who should have checked out but haven't."""
        overdue = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": "checked_in",
            "check_out": {"$lte": business_date + "T23:59:59"},
        }, {"_id": 0, "id": 1, "guest_id": 1, "room_id": 1, "check_out": 1}).to_list(500)

        today_departures = [d for d in overdue if d["check_out"][:10] <= business_date]
        exceptions = [
            {"type": "pending_departure", "description": f"Booking {d['id']} not checked out (departure: {d['check_out'][:10]})",
             "entity_type": "booking", "entity_id": d["id"]}
            for d in today_departures
        ]

        return {"count": len(today_departures), "bookings": today_departures, "exceptions": exceptions}

    async def _process_no_shows(self, tenant_id: str, business_date: str, user_id: str) -> dict:
        """Mark confirmed/guaranteed bookings with arrival <= business_date as no-show."""
        from modules.pms_core.reservation_state_machine import ReservationStateMachine
        rsm = ReservationStateMachine()

        candidates = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$lte": business_date + "T18:00:00"},  # 6 PM cutoff
        }, {"_id": 0}).to_list(500)

        # Only process arrivals from before today
        to_process = [c for c in candidates if c["check_in"][:10] < business_date]

        processed = 0
        for booking in to_process:
            result = await rsm.handle_no_show(tenant_id, booking, user_id)
            if result.get("success"):
                processed += 1

        return {"candidates": len(to_process), "processed": processed}

    async def _post_room_charges(self, tenant_id: str, business_date: str, user_id: str) -> dict:
        """Post nightly room charges for all checked-in guests.

        tur-33 (CI #51 P2 perf finding fix): 500-oda stress tenant'ta bu
        fonksiyon 180s+ sürüyordu. Kök neden: klasik N+1 query — her
        booking için 4 sıralı DB query (folios.find_one + folio_charges
        duplicate-check + rooms.find_one + folio_charges insert_one).
        500 booking × 4 query × ~30ms Atlas latency = ~60s minimum, 120s+
        kolayca. Fix: bulk pre-fetch (folios + rooms + existing charges)
        tek query'lere indirildi, loop in-memory dict lookup + insert_many.
        Beklenen perf: 4 query + 1 insert_many → < 5 saniye 500-oda için.
        """
        checked_in = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": "checked_in",
        }, {"_id": 0}).to_list(2000)  # 1000 → 2000 (büyük tenant kapasitesi)

        if not checked_in:
            return {"posted": 0, "failed": 0, "total_revenue": 0.0, "total_tax": 0.0, "exceptions": []}

        booking_ids = [b["id"] for b in checked_in]
        room_ids = [b["room_id"] for b in checked_in if b.get("room_id")]

        # Bulk pre-fetch #1: tüm açık folio'lar tek query'de
        folio_cursor = db.folios.find({
            "tenant_id": tenant_id,
            "booking_id": {"$in": booking_ids},
            "status": "open",
        }, {"_id": 0})
        folios_by_booking = {}
        async for f in folio_cursor:
            folios_by_booking[f["booking_id"]] = f

        # Bulk pre-fetch #2: tüm room number'lar tek query'de
        rooms_by_id = {}
        if room_ids:
            room_cursor = db.rooms.find({
                "tenant_id": tenant_id,
                "id": {"$in": room_ids},
            }, {"_id": 0, "id": 1, "room_number": 1})
            async for r in room_cursor:
                rooms_by_id[r["id"]] = r.get("room_number", "N/A")

        # Bulk pre-fetch #3: bu business_date için zaten posted charge'lar
        # (duplicate guard) — tek query, folio_id set'i.
        folio_ids = [f["id"] for f in folios_by_booking.values()]
        already_posted_folio_ids: set[str] = set()
        if folio_ids:
            existing_cursor = db.folio_charges.find({
                "tenant_id": tenant_id,
                "folio_id": {"$in": folio_ids},
                "charge_category": "room",
                "voided": False,
                "night_audit_date": business_date,
            }, {"_id": 0, "folio_id": 1})
            async for c in existing_cursor:
                already_posted_folio_ids.add(c["folio_id"])

        # Loop artık in-memory — DB hit YOK.
        posted = 0
        failed = 0
        total_revenue = 0.0
        total_tax = 0.0
        exceptions: list[dict] = []
        charges_to_insert: list[dict] = []
        now_iso = datetime.now(UTC).isoformat()
        tax_rate = 10  # default tax rate

        # Architect review fix #1: intra-run duplicate guard. Eski kod
        # per-booking find_one ile aynı folio'ya iki booking map'lendiğinde
        # ikinci insert sırasında zaten posted'i görebiliyordu. Yeni bulk
        # kodda snapshot başta alındığı için aynı run içinde iki kez
        # enqueue olabilir. `scheduled_folio_ids` set'iyle in-loop dedupe.
        scheduled_folio_ids: set[str] = set()
        # Charge meta'sını da sakla → bulk insert partial failure halinde
        # reconcile için (architect fix #2).
        charge_meta: list[dict] = []  # [{folio_id, amount, tax_amount}]

        for booking in checked_in:
            try:
                folio = folios_by_booking.get(booking["id"])
                if not folio:
                    exceptions.append({
                        "type": "no_open_folio",
                        "description": f"Booking {booking['id']} has no open folio",
                        "entity_type": "booking", "entity_id": booking["id"],
                    })
                    failed += 1
                    continue

                fid = folio["id"]
                if fid in already_posted_folio_ids or fid in scheduled_folio_ids:
                    continue  # idempotency (DB-level OR intra-run dedupe)

                # Calculate nightly rate
                check_in_dt = datetime.fromisoformat(booking["check_in"].replace("Z", "+00:00"))
                check_out_dt = datetime.fromisoformat(booking["check_out"].replace("Z", "+00:00"))
                total_nights = max((check_out_dt - check_in_dt).days, 1)
                nightly_rate = round(booking.get("total_amount", 0) / total_nights, 2)

                tax_amount = round(nightly_rate * tax_rate / 100, 2)
                total = round(nightly_rate + tax_amount, 2)
                room_number = rooms_by_id.get(booking.get("room_id"), "N/A")

                charge_id = str(uuid.uuid4())
                charges_to_insert.append({
                    "id": charge_id,
                    "tenant_id": tenant_id,
                    "folio_id": fid,
                    "booking_id": booking["id"],
                    "charge_category": "room",
                    "description": f"Room {room_number} - Night {business_date}",
                    "unit_price": nightly_rate,
                    "quantity": 1.0,
                    "amount": nightly_rate,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amount,
                    "total": total,
                    "posted_by": "night_audit",
                    "date": now_iso,
                    "night_audit_date": business_date,
                    # Standardized fields so the hardened unique dedup index
                    # idx_folio_charges_na_dedup (tenant_id, booking_id,
                    # business_date, charge_type) covers these room charges and
                    # blocks double-posting under concurrent runs at the DB level.
                    "business_date": business_date,
                    "charge_type": "room_charge",
                    "voided": False,
                })
                charge_meta.append({
                    "id": charge_id,
                    "folio_id": fid,
                    "booking_id": booking["id"],
                    "amount": nightly_rate,
                    "tax_amount": tax_amount,
                })
                scheduled_folio_ids.add(fid)

            except Exception as e:
                failed += 1
                exceptions.append({
                    "type": "room_charge_failure",
                    "description": f"Failed to prepare charge for booking {booking['id']}: {str(e)}",
                    "entity_type": "booking", "entity_id": booking["id"],
                })

        # Architect review fix #2: BulkWriteError reconcile. Counts'u sadece
        # gerçekten persist edilmiş charge'lardan hesapla; partial failure'da
        # snapshot abartmasın.
        if charges_to_insert:
            inserted_ids: set[str] = set()
            try:
                await db.folio_charges.insert_many(charges_to_insert, ordered=False)
                # Success path: exception yok → hepsi insert edildi
                inserted_ids = {m["id"] for m in charge_meta}
            except Exception as e:
                # Architect review #2 fix v2: BulkWriteError ile generic
                # exception ayrı muamele. Sadece BulkWriteError'da
                # nInserted/writeErrors güvenilir.
                try:
                    from pymongo.errors import BulkWriteError as _BWE
                    is_bulk_err = isinstance(e, _BWE)
                except Exception:
                    is_bulk_err = False

                if is_bulk_err:
                    details = getattr(e, "details", None) or {}
                    write_errors = details.get("writeErrors", []) or []
                    n_inserted = int(details.get("nInserted", 0) or 0)
                    failed_indices = {we.get("index") for we in write_errors if we.get("index") is not None}
                    # Index'e dayalı inferred set
                    inferred_inserted = [
                        meta for idx, meta in enumerate(charge_meta)
                        if idx not in failed_indices
                    ]
                    # nInserted cap — eğer driver daha az insert raporladıysa
                    # konservatif şekilde set'i kıs (atipik write-concern
                    # senaryolarında overstate olmasın).
                    if n_inserted < len(inferred_inserted):
                        inferred_inserted = inferred_inserted[:n_inserted]
                    inserted_ids = {m["id"] for m in inferred_inserted}
                else:
                    # BulkWriteError olmayan exception (örn. network, timeout,
                    # write-concern fail) — insertion evidence yok, hepsini
                    # fail say.
                    inserted_ids = set()

                exceptions.append({
                    "type": "bulk_insert_partial_failure",
                    "description": (f"insert_many failure ({'bulk' if is_bulk_err else 'generic'}): "
                                    f"attempted={len(charges_to_insert)} "
                                    f"inserted={len(inserted_ids)} "
                                    f"err={str(e)[:200]}"),
                    "entity_type": "folio_charge", "entity_id": None,
                })

            # Counts'u sadece gerçekten insert edilen charge'lardan hesapla
            for meta in charge_meta:
                if meta["id"] in inserted_ids:
                    posted += 1
                    total_revenue += meta["amount"]
                    total_tax += meta["tax_amount"]
                else:
                    failed += 1

            # Gelir zinciri: charge -> folio.balance. Eski kod charge'ı
            # folio_charges'a yazıyor ama folio.balance'ı HIC artmiyordu →
            # otomatik oda geliri folyo bakiyesine (ve checkout bakiye
            # guard'ina) hic yansimiyordu. Hardened engine ($inc total)
            # semantigini birebir uygula: yalnizca gercekten insert edilmis
            # charge'larin toplami kadar artir (idempotency guard'lari ayni
            # business_date'te tekrar insert'i zaten engelliyor).
            balance_inc_by_folio: dict[str, float] = {}
            for meta in charge_meta:
                if meta["id"] not in inserted_ids:
                    continue
                line_total = round(meta["amount"] + meta["tax_amount"], 2)
                balance_inc_by_folio[meta["folio_id"]] = round(
                    balance_inc_by_folio.get(meta["folio_id"], 0.0) + line_total, 2
                )
            for fid, inc in balance_inc_by_folio.items():
                if inc:
                    await db.folios.update_one(
                        {"id": fid, "tenant_id": tenant_id},
                        {"$inc": {"balance": inc}},
                    )

        return {
            "posted": posted,
            "failed": failed,
            "total_revenue": round(total_revenue, 2),
            "total_tax": round(total_tax, 2),
            "exceptions": exceptions,
        }

    async def _detect_unbalanced_folios(self, tenant_id: str) -> dict:
        """Find open folios with unusual balances.

        tur-33 (perf fix): aynı N+1 darboğazı — 1000 folio × 2 query =
        2000 sıralı roundtrip. Bulk pre-fetch + in-memory aggregation'a
        çevrildi. MongoDB aggregate kullanmak yerine basit pre-fetch
        yeterli (folio sayısı tipik tenant'ta 1000'in çok altında).
        """
        open_folios = await db.folios.find({"tenant_id": tenant_id, "status": "open"}, {"_id": 0}).to_list(2000)
        warnings: list = []
        if not open_folios:
            return {"checked": 0, "warnings": warnings}

        folio_ids = [f["id"] for f in open_folios]

        # Bulk pre-fetch: tüm charges + tüm payments tek query'de, folio_id'ye göre grupla
        charges_by_folio: dict[str, float] = {}
        payments_by_folio: dict[str, float] = {}

        charges_cursor = db.folio_charges.find({
            "tenant_id": tenant_id,
            "folio_id": {"$in": folio_ids},
            "voided": False,
        }, {"_id": 0, "folio_id": 1, "total": 1, "amount": 1})
        async for c in charges_cursor:
            fid = c.get("folio_id")
            if fid:
                charges_by_folio[fid] = charges_by_folio.get(fid, 0) + (c.get("total") or c.get("amount") or 0)

        payments_cursor = db.payments.find({
            "tenant_id": tenant_id,
            "folio_id": {"$in": folio_ids},
            "voided": False,
        }, {"_id": 0, "folio_id": 1, "amount": 1})
        async for p in payments_cursor:
            fid = p.get("folio_id")
            if fid:
                payments_by_folio[fid] = payments_by_folio.get(fid, 0) + (p.get("amount") or 0)

        for folio in open_folios:
            total_charges = charges_by_folio.get(folio["id"], 0)
            total_payments = payments_by_folio.get(folio["id"], 0)
            balance = round(total_charges - total_payments, 2)

            if total_payments > total_charges + 0.01:
                warnings.append({
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "type": "overpayment",
                    "balance": balance,
                    "message": f"Folio {folio.get('folio_number')} has overpayment of {abs(balance)}",
                })
            elif balance > 10000:
                warnings.append({
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "type": "high_balance",
                    "balance": balance,
                    "message": f"Folio {folio.get('folio_number')} has high outstanding balance: {balance}",
                })

        return {"checked": len(open_folios), "warnings": warnings}

    async def _check_tax_consistency(self, tenant_id: str, business_date: str) -> dict:
        """Check tax calculations for consistency."""
        charges = await db.folio_charges.find({
            "tenant_id": tenant_id,
            "voided": False,
            "date": {"$gte": business_date + "T00:00:00", "$lte": business_date + "T23:59:59"},
        }, {"_id": 0}).to_list(5000)

        warnings = []
        for charge in charges:
            amount = charge.get("amount", 0)
            tax_rate = charge.get("tax_rate", 0)
            tax_amount = charge.get("tax_amount", 0)
            expected_tax = round(amount * tax_rate / 100, 2) if tax_rate else 0

            if abs(tax_amount - expected_tax) > 0.02:
                warnings.append({
                    "charge_id": charge["id"],
                    "type": "tax_mismatch",
                    "expected_tax": expected_tax,
                    "actual_tax": tax_amount,
                    "message": f"Charge {charge['id']}: tax {tax_amount} != expected {expected_tax}",
                })

        return {"checked": len(charges), "warnings": warnings}

    async def _create_daily_snapshot(self, tenant_id: str, business_date: str, room_charges_result: dict) -> dict:
        """Create a daily audit snapshot for reporting."""
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0, "status": 1}).to_list(2000)
        total_rooms = len(rooms)
        occupied = sum(1 for r in rooms if r.get("status") == "occupied")

        checked_in_count = await db.bookings.count_documents({"tenant_id": tenant_id, "status": "checked_in"})

        snapshot = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "business_date": business_date,
            "total_rooms": total_rooms,
            "occupied_rooms": occupied,
            "occupancy_rate": round(occupied / total_rooms * 100, 2) if total_rooms else 0,
            "room_revenue": room_charges_result.get("total_revenue", 0),
            "tax_revenue": room_charges_result.get("total_tax", 0),
            "total_revenue": room_charges_result.get("total_revenue", 0) + room_charges_result.get("total_tax", 0),
            "room_postings": room_charges_result.get("posted", 0),
            "failed_postings": room_charges_result.get("failed", 0),
            "in_house_guests": checked_in_count,
            "created_at": datetime.now(UTC).isoformat(),
        }

        await db.daily_audit_snapshots.insert_one(snapshot)
        snapshot.pop("_id", None)
        return snapshot

    async def _roll_business_date(self, tenant_id: str, current_date: str):
        """Advance the business date to the next day."""
        next_date = self._next_date(current_date)
        await db.tenant_settings.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"business_date": next_date, "last_audit_date": current_date}},
            upsert=True,
        )

    def _next_date(self, date_str: str) -> str:
        d = date.fromisoformat(date_str)
        return (d + timedelta(days=1)).isoformat()

    async def get_business_date(self, tenant_id: str) -> str:
        """Get current business date for tenant."""
        settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
        if settings and settings.get("business_date"):
            return settings["business_date"]
        return datetime.now(UTC).date().isoformat()

    async def get_audit_exceptions(self, tenant_id: str, status: str = "open") -> list[dict]:
        """Get audit exceptions queue."""
        return await db.audit_exceptions.find(
            {"tenant_id": tenant_id, "status": status}, {"_id": 0}
        ).sort("created_at", -1).to_list(200)

    async def resolve_exception(self, tenant_id: str, exception_id: str, resolved_by: str, resolution: str) -> dict:
        """Resolve an audit exception."""
        now = datetime.now(UTC)
        result = await db.audit_exceptions.update_one(
            {"id": exception_id, "tenant_id": tenant_id},
            {"$set": {"status": "resolved", "resolved_by": resolved_by, "resolution": resolution, "resolved_at": now.isoformat()}}
        )
        if result.modified_count == 0:
            return {"success": False, "error": "Exception not found"}
        return {"success": True, "exception_id": exception_id}

    async def get_daily_snapshot(self, tenant_id: str, business_date: str) -> dict | None:
        """Get daily snapshot for a specific date."""
        snapshot = await db.daily_audit_snapshots.find_one(
            {"tenant_id": tenant_id, "business_date": business_date}, {"_id": 0}
        )
        return snapshot
