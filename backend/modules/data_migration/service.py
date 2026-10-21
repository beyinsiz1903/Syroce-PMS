"""Encrypted staging + immutable archive + optional, explicit guest publication.

Never calls booking creation, cashier, GL, KBS, channel or messaging code.
Live reservation/balance activation is deliberately NOT an archive import.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pymongo import ReturnDocument, UpdateOne

from .formats import MigrationError
from .schema import FIELDS, REFERENCES, digest, normalize, private_fingerprint, record_id, suggest_mapping

MAX_BATCH_ROWS = 50000
CHUNK_SIZE = 100
ORDER = {name: index for index, name in enumerate(FIELDS)}


def now():
    return datetime.now(UTC)


def seal(data, tenant_id):
    from core.crypto.service import get_crypto_service

    service = get_crypto_service()
    value = service.encrypt(json.dumps({"tenant_id": tenant_id, "data": data}, ensure_ascii=False))
    if not value.startswith(("SYR1:", "aes256gcm:")):
        raise MigrationError("Şifreleme devre dışı; veri aktarımı güvenli biçimde durduruldu.")
    return value


def unseal(value, tenant_id):
    from core.crypto.service import get_crypto_service

    content = json.loads(get_crypto_service().decrypt(value))
    if content.get("tenant_id") != tenant_id:
        raise MigrationError("Şifreli kayıt tesis bağlamı uyuşmuyor.")
    return content["data"]


async def indexes(db):
    # Do not cache globally: tests and per-loop databases must get the same guarantees.
    await db.migration_batches.create_index([("tenant_id", 1), ("id", 1)], unique=True)
    await db.migration_archive.create_index([("tenant_id", 1), ("id", 1)], unique=True)
    await db.migration_archive.create_index([("tenant_id", 1), ("namespace", 1), ("entity", 1)])
    await db.migration_archive.create_index([("tenant_id", 1), ("guest_id", 1), ("entity", 1)])
    for field in REFERENCES:
        await db.migration_archive.create_index([("tenant_id", 1), (f"refs.{field}", 1)])
    await db.migration_staging.create_index("expires_at", expireAfterSeconds=0)
    await db.migration_staging.create_index([("tenant_id", 1), ("dataset_id", 1), ("part", 1)], unique=True)


def decoded_batch(batch):
    result = deepcopy(batch)
    for dataset in result.get("datasets", []):
        encrypted_links = dataset.pop("guest_links_payload", None)
        if encrypted_links:
            dataset["guest_links"] = unseal(encrypted_links, batch["tenant_id"])
    return result


def public_batch(batch):
    return {key: value for key, value in decoded_batch(batch).items() if key not in {"_id", "lease", "lease_until", "plan"}}


async def get_batch(db, tenant_id, batch_id):
    batch = await db.migration_batches.find_one({"tenant_id": tenant_id, "id": batch_id})
    if not batch:
        raise MigrationError("Aktarım bulunamadı.")
    return decoded_batch(batch)


async def audit(db, batch, actor_id, action):
    event_id = digest([batch["tenant_id"], batch["id"], batch["revision"], action, batch.get("cursor", 0)])
    await db.audit_logs.update_one(
        {"_id": event_id, "tenant_id": batch["tenant_id"]},
        {
            "$setOnInsert": {
                "tenant_id": batch["tenant_id"],
                "actor_id": actor_id,
                "action": action,
                "target_id": batch["id"],
                "entity_type": "data_migration",
                "created_at": now(),
                "details": {"revision": batch["revision"], "state": batch["state"]},
            }
        },
        upsert=True,
    )


async def create_batch(db, tenant_id, actor_id, *, source, namespace, publish_guests=False, allow_archive_updates=False):
    await indexes(db)
    batch = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "source": source,
        "namespace": namespace,
        "publish_guests": publish_guests,
        "allow_archive_updates": allow_archive_updates,
        "state": "draft",
        "revision": 1,
        "datasets": [],
        "created_at": now(),
        "created_by": actor_id,
        "cursor": 0,
        "history": [],
    }
    await db.migration_batches.insert_one(batch)
    await audit(db, batch, actor_id, "migration_created")
    return public_batch(batch)


async def change_batch(db, batch, actor_id, changes):
    if batch["state"] not in {"draft", "reviewed"}:
        raise MigrationError("Başlatılmış aktarım değiştirilemez; yeni bir aktarım açın.")
    changes = deepcopy(changes)
    if "datasets" in changes:
        for dataset in changes["datasets"]:
            links = dataset.pop("guest_links", {})
            dataset["guest_links_payload"] = seal(links, batch["tenant_id"]) if links else None
        if len(json.dumps(changes["datasets"], ensure_ascii=False).encode()) > 2 * 1024 * 1024:
            raise MigrationError("Eşleştirme ayarları çok büyük; aktarımı daha küçük parçalara ayırın.")
    result = await db.migration_batches.find_one_and_update(
        {"id": batch["id"], "tenant_id": batch["tenant_id"], "revision": batch["revision"], "state": batch["state"]},
        {"$set": {**changes, "state": "draft", "report": None, "review_token": None, "updated_at": now()}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise MigrationError("Aktarım başka bir işlemde değişti; yenileyin.")
    await audit(db, result, actor_id, "migration_mapping_changed")
    return public_batch(result)


async def add_dataset(db, batch, actor_id, *, entity, headers, rows, source_metadata=None):
    if len(batch["datasets"]) >= 20 or sum(d["row_count"] for d in batch["datasets"]) + len(rows) > MAX_BATCH_ROWS:
        raise MigrationError("Aktarım başına 20 dosya / 50.000 satır sınırı.")
    if batch["state"] not in {"draft", "reviewed"}:
        raise MigrationError("Aktarım başlatılmış; dosya eklenemez.")
    dataset_id = str(uuid.uuid4())
    for part, offset in enumerate(range(0, len(rows), 250)):
        await db.migration_staging.insert_one(
            {
                "tenant_id": batch["tenant_id"],
                "batch_id": batch["id"],
                "dataset_id": dataset_id,
                "part": part,
                "payload": seal(rows[offset : offset + 250], batch["tenant_id"]),
                "expires_at": now() + timedelta(days=30),
            }
        )
    item = {
        "id": dataset_id,
        "entity": entity,
        "headers": headers,
        "row_count": len(rows),
        "parts": (len(rows) + 249) // 250,
        "mapping": suggest_mapping(entity, headers),
        "date_format": "%Y-%m-%d",
        "decimal_separator": ".",
        "value_mapping": {},
        "expected_count": None,
        "expected_totals": None,
        "guest_links": {},
        **(source_metadata or {}),
    }
    return await change_batch(db, batch, actor_id, {"datasets": [*batch["datasets"], item]})


async def load_rows(db, batch):
    result = []
    for dataset in sorted(batch["datasets"], key=lambda d: ORDER[d["entity"]]):
        chunks = await db.migration_staging.find({"tenant_id": batch["tenant_id"], "batch_id": batch["id"], "dataset_id": dataset["id"]}).sort("part", 1).to_list(201)
        if len(chunks) != dataset["parts"] or [c["part"] for c in chunks] != list(range(dataset["parts"])):
            raise MigrationError("Hazırlık dosyası eksik veya süresi dolmuş; aktarımı yeniden hazırlayın.")
        rows = [row for chunk in chunks for row in unseal(chunk["payload"], batch["tenant_id"])]
        if len(rows) != dataset["row_count"]:
            raise MigrationError("Hazırlık dosyasının satır sayısı uyuşmuyor.")
        for index, row in enumerate(rows, 2):
            result.append((dataset, index, row))
    return result


def _money_key(entity, data):
    if entity not in {"reservations", "folios", "transactions", "balances", "daily_rates"}:
        return None
    return f"{data.get('kind', 'total')}:{data['currency']}"


async def existing_guest_matches(db, tenant_id, candidates):
    """Bounded bulk queries with the same identity rules as ordinary guest creation."""
    from modules.pms_core.guest_identity import guest_identity_conditions, guest_identity_tokens
    from security.encrypted_lookup import decrypt_guest_doc

    result = {}
    for offset in range(0, len(candidates), 100):
        group = candidates[offset : offset + 100]
        branches = [condition for _, data in group for condition in guest_identity_conditions(data)]
        if not branches:
            continue
        records = await db.guests.find({"tenant_id": tenant_id, "archived": {"$ne": True}, "status": {"$ne": "deleted"}, "$or": branches}, {"_id": 0}).limit(2001).to_list(2001)
        if len(records) > 2000:
            raise MigrationError("Çok fazla ortak kimlik eşleşmesi; yalnız arşiv veya daha küçük bir dosyayla inceleyin.")
        tokens = defaultdict(set)
        for record in records:
            for identity in guest_identity_tokens(decrypt_guest_doc(record)):
                tokens[identity].add(record["id"])
        for key, data in group:
            matches = set()
            for identity in guest_identity_tokens(data):
                matches.update(tokens.get(identity, ()))
            result[key] = matches
    return result


async def build_plan(db, batch):
    from modules.pms_core.guest_identity import guest_identity_tokens

    tenant_id, namespace = batch["tenant_id"], batch["namespace"]
    raw_rows = await load_rows(db, batch)
    # Indexed, bounded lookups rather than scanning/truncating a hotel's history.
    # A multi-year migration can be split into many batches without a global row cap.
    candidate_keys = set()
    for dataset, _line, raw in raw_rows:
        for field in ("source_id", *REFERENCES):
            source_value = str(raw.get(dataset["mapping"].get(field), "")).strip()
            if source_value:
                target = dataset["entity"] if field == "source_id" else REFERENCES[field]
                candidate_keys.add(record_id(tenant_id, namespace, target, source_value))
    candidate_keys = list(candidate_keys)
    existing = {}
    for offset in range(0, len(candidate_keys), 1000):
        documents = await db.migration_archive.find({"tenant_id": tenant_id, "namespace": namespace, "id": {"$in": candidate_keys[offset : offset + 1000]}}, {"payload": 0}).to_list(1000)
        existing.update({row["id"]: row for row in documents})
    guest_candidates = []
    if batch["publish_guests"]:
        for dataset, _line, raw in raw_rows:
            if dataset["entity"] != "guests":
                continue
            try:
                data = normalize("guests", raw, dataset["mapping"], date_format=dataset["date_format"], decimal_separator=dataset["decimal_separator"], value_mapping=dataset["value_mapping"])
                if not dataset.get("guest_links", {}).get(data["source_id"]):
                    guest_candidates.append((record_id(tenant_id, namespace, "guests", data["source_id"]), data))
            except MigrationError:
                pass  # The main validation loop reports the exact row error.
    guest_matches = await existing_guest_matches(db, tenant_id, guest_candidates)
    rows, errors, warnings, seen, identity_seen = [], [], [], set(), set()
    error_count = 0
    totals = defaultdict(lambda: defaultdict(Decimal))
    stats = {
        d["id"]: {
            "dataset_id": d["id"],
            "entity": d["entity"],
            "rows": d["row_count"],
            "create": 0,
            "reuse": 0,
            "update": 0,
            "unmapped_columns": [h for h in d["headers"] if h not in d["mapping"].values()],
        }
        for d in batch["datasets"]
    }

    def error(dataset, line, message):
        nonlocal error_count
        error_count += 1
        if len(errors) < 200:
            errors.append({"dataset_id": dataset["id"], "row": line, "message": message})

    if not batch["datasets"]:
        error_count += 1
        errors.append({"dataset_id": "", "row": 0, "message": "Önce dosya ekleyin."})
    for dataset, line, raw in raw_rows:
        try:
            data = normalize(dataset["entity"], raw, dataset["mapping"], date_format=dataset["date_format"], decimal_separator=dataset["decimal_separator"], value_mapping=dataset["value_mapping"])
            if dataset.get("preserve_extra_fields"):
                extras = {key: value for key, value in raw.items() if key not in dataset["mapping"].values()}
                if extras:
                    data["source_fields"] = extras
            key = record_id(tenant_id, namespace, dataset["entity"], data["source_id"])
            if key in seen:
                raise MigrationError("Aynı tür/kaynak kayıt numarası dosyalarda tekrar ediyor.")
            seen.add(key)
            content_hash = private_fingerprint(data)
            changed = key in existing and existing[key]["content_hash"] != content_hash
            if changed:
                if not batch.get("allow_archive_updates"):
                    raise MigrationError("Bu kaynak kayıt daha önce farklı içerikle aktarıldı; değişiklik incelemesi gerekli.")
                origin = await db.migration_batches.find_one({"tenant_id": tenant_id, "id": existing[key]["owner_batch_id"], "state": "complete"})
                if not origin:
                    raise MigrationError("Yarım kalmış kaynak kayıt değiştirilemez; önce önceki aktarımı tamamlayın.")
            guest_id = None
            if dataset["entity"] == "guests" and batch["publish_guests"]:
                linked = dataset.get("guest_links", {}).get(data["source_id"])
                if linked:
                    guest = await db.guests.find_one({"tenant_id": tenant_id, "id": linked, "archived": {"$ne": True}, "status": {"$ne": "deleted"}})
                    if not guest:
                        raise MigrationError("Bağlanacak mevcut misafir bu tesiste bulunamadı.")
                    guest_id = linked
                else:
                    guest_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "migration-guest:" + key))
                    if guest_matches.get(key, set()) - {guest_id}:
                        raise MigrationError("Mevcut misafirle güçlü kimlik eşleşmesi var; Syroce misafir ID'sini açıkça bağlayın veya yalnız arşiv aktarın.")
                    tokens = guest_identity_tokens(data)
                    if tokens & identity_seen:
                        raise MigrationError("Dosyalarda güçlü kimliği tekrarlanan misafir var; kaynak kayıtlarını inceleyin.")
                    identity_seen.update(tokens)
                if key in existing and existing[key].get("guest_id") not in {None, guest_id}:
                    raise MigrationError("Arşiv kaydı başka bir Syroce misafirine bağlı; bağlantı incelemesi gerekli.")
            refs = {field: record_id(tenant_id, namespace, target, data[field]) for field, target in REFERENCES.items() if data.get(field)}
            action = "update" if changed else "reuse" if key in existing else "create"
            stats[dataset["id"]][action] += 1
            row = {
                "id": key,
                "entity": dataset["entity"],
                "content_hash": content_hash,
                "data": data,
                "refs": refs,
                "dataset_id": dataset["id"],
                "row": line,
                "guest_id": guest_id,
                "linked_guest": bool(dataset.get("guest_links", {}).get(data["source_id"])),
                "previous_hash": existing[key]["content_hash"] if changed else None,
            }
            rows.append(row)
            money_key = _money_key(dataset["entity"], data)
            if money_key:
                totals[dataset["id"]][money_key] += Decimal(data.get("amount", data.get("total_amount", data.get("balance", "0"))))
        except MigrationError as exc:
            error(dataset, line, str(exc))
    by_id = {row["id"]: row for row in rows}
    known = set(existing) | set(by_id)
    datasets_by_id = {d["id"]: d for d in batch["datasets"]}
    for row in rows:
        for field, key in row["refs"].items():
            if key not in known:
                error(datasets_by_id[row["dataset_id"]], row["row"], f"Bağlantılı kaynak kayıt eksik: {field}")
        if row["entity"] == "transactions" and row["refs"].get("folio_source_id") in known:
            folio_key = row["refs"]["folio_source_id"]
            folio = by_id[folio_key]["data"] if folio_key in by_id else unseal(existing[folio_key]["payload"], tenant_id) if "payload" in existing[folio_key] else None
            if folio is None:
                stored = await db.migration_archive.find_one({"tenant_id": tenant_id, "id": folio_key})
                folio = unseal(stored["payload"], tenant_id)
            if folio["currency"] != row["data"]["currency"]:
                error(datasets_by_id[row["dataset_id"]], row["row"], "Folyo ve hareket para birimi farklı; açık kur dönüşümü olmadan aktarılmaz.")
    complete_folios = {r["id"]: r for r in rows if r["entity"] == "folios" and datasets_by_id[r["dataset_id"]].get("folio_transactions_complete")}
    folio_nets = defaultdict(Decimal)
    for row in rows:
        if row["entity"] == "transactions" and row["refs"]["folio_source_id"] in complete_folios:
            data = row["data"]
            folio_nets[row["refs"]["folio_source_id"]] += Decimal(data["amount"]) * (-1 if data["kind"] == "payment" else 1)
    if complete_folios:
        async for archived in db.migration_archive.find({"tenant_id": tenant_id, "namespace": namespace, "entity": "transactions", "refs.folio_source_id": {"$in": list(complete_folios)}}):
            if archived["id"] not in by_id:
                data = unseal(archived["payload"], tenant_id)
                folio_nets[archived["refs"]["folio_source_id"]] += Decimal(data["amount"]) * (-1 if data["kind"] == "payment" else 1)
        for key, row in complete_folios.items():
            if folio_nets[key] != Decimal(row["data"]["balance"]):
                error(datasets_by_id[row["dataset_id"]], row["row"], "Tam folyo hareketleri ile bakiye uyuşmuyor (borç + iade + düzeltme − ödeme).")
    for dataset in batch["datasets"]:
        stat = stats[dataset["id"]]
        stat["totals"] = {key: format(amount, "f") for key, amount in totals[dataset["id"]].items()}
        stat["source_reconciled"] = False
        if dataset.get("expected_count") is not None and dataset["expected_count"] != dataset["row_count"]:
            error(dataset, 0, "Kaynak kayıt sayısı dosyayla uyuşmuyor.")
        expected = dataset.get("expected_totals")
        if expected is not None:
            try:
                if set(expected) != set(stat["totals"]) or any(not Decimal(str(value)).is_finite() or Decimal(str(value)) != Decimal(stat["totals"][key]) for key, value in expected.items()):
                    error(dataset, 0, "Kaynak para birimi/tür toplamları dosyayla uyuşmuyor.")
                else:
                    stat["source_reconciled"] = dataset.get("expected_count") == dataset["row_count"]
            except (ValueError, ArithmeticError):
                error(dataset, 0, "Kaynak kontrol toplamı geçersiz.")
        elif dataset.get("expected_count") == dataset["row_count"] and not stat["totals"]:
            stat["source_reconciled"] = True
        if not stat["source_reconciled"]:
            warnings.append({"dataset_id": dataset["id"], "message": "Bağımsız kaynak sayısı/toplamı ile mutabakat tamamlanmadı."})
        if dataset["entity"] == "folios" and not dataset.get("folio_transactions_complete"):
            warnings.append({"dataset_id": dataset["id"], "message": "Tam hareket dökümü onaylanmadı; folyo bakiyesi hareketlerle doğrulanmadı."})
        if stat["unmapped_columns"]:
            stat["unmapped_preserved"] = dataset.get("preserve_extra_fields", False)
            warnings.append(
                {
                    "dataset_id": dataset["id"],
                    "message": "Ek sütunlar kaynak alanları olarak şifreli arşivde korunacak; canlı profil alanı değildir."
                    if stat["unmapped_preserved"]
                    else "Eşleştirilmemiş sütunlar nihai arşive taşınmayacak.",
                }
            )
    active = sum(row["entity"] == "reservations" and row["data"]["status"] in {"confirmed", "checked_in", "pending"} for row in rows)
    report = {
        "rows": len(rows),
        "error_count": error_count,
        "errors": errors,
        "errors_truncated": error_count > len(errors),
        "warnings": warnings,
        "datasets": list(stats.values()),
        "active_reservations_archive_only": active,
        "financial_activation": "not_supported",
        "archive_only": True,
        "all_source_reconciled": bool(stats) and all(s["source_reconciled"] for s in stats.values()),
    }
    token = digest({"revision": batch["revision"], "report": report, "rows": [{k: v for k, v in r.items() if k != "data"} for r in rows]})
    return rows, {**report, "review_token": token}


async def review(db, batch, actor_id):
    if batch["state"] not in {"draft", "reviewed"}:
        raise MigrationError("Başlatılmış aktarım yeniden eşleştirilemez.")
    _, report = await build_plan(db, batch)
    result = await db.migration_batches.find_one_and_update(
        {"tenant_id": batch["tenant_id"], "id": batch["id"], "state": batch["state"], "revision": batch["revision"]},
        {"$set": {"state": "reviewed", "report": report, "review_token": report["review_token"], "reviewed_at": now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise MigrationError("İnceleme sırasında aktarım değişti; tekrar deneyin.")
    await audit(db, result, actor_id, "migration_reviewed")
    return public_batch(result)


async def _publish_guest(db, batch, row):
    if not row["guest_id"]:
        return
    if row["linked_guest"]:
        if not await db.guests.find_one({"tenant_id": batch["tenant_id"], "id": row["guest_id"], "archived": {"$ne": True}, "status": {"$ne": "deleted"}}):
            raise MigrationError("Bağlı misafir artık kullanılamıyor; işlem durduruldu.")
        return
    matched = await existing_guest_matches(db, batch["tenant_id"], [(row["id"], row["data"])])
    if matched.get(row["id"], set()) - {row["guest_id"]}:
        raise MigrationError("Aktarım sırasında yeni kimlik eşleşmesi oluştu; işlem durduruldu.")
    from models.schemas.guests import Guest
    from security.guest_write import encrypt_guest_insert

    data = row["data"]
    guest = Guest(id=row["guest_id"], tenant_id=batch["tenant_id"], **{k: v for k, v in data.items() if k in Guest.model_fields and k not in {"id", "tenant_id"}}).model_dump(mode="json")
    guest.update(
        {
            "migration_record_id": row["id"],
            "migration_batch_id": batch["id"],
            "marketing_consent": data.get("marketing_consent", False),
            "consent_date": data.get("consent_date"),
            "consent_reference": data.get("consent_reference"),
            "kvkk_consent": False,
        }
    )
    # Fail closed here, even though normal interactive guest creation is fail-open.
    protected = encrypt_guest_insert(guest.copy())
    for field in ("email", "phone", "id_number", "address", "birth_date"):
        if guest.get(field) and not str(protected.get(field, "")).startswith(("SYR1:", "aes256gcm:")):
            raise MigrationError("Misafir alan şifrelemesi kullanılamıyor; yayınlama durduruldu.")
    await db.guests.update_one({"tenant_id": batch["tenant_id"], "id": row["guest_id"]}, {"$setOnInsert": protected}, upsert=True)


async def commit_chunk(db, batch, actor_id, token):
    """Bounded synchronous chunk, resumable after a crash. Never a fire-and-forget job."""
    if batch["state"] == "complete":
        return public_batch(batch)
    if await db.migration_cutover_sources.find_one({"tenant_id": batch["tenant_id"], "namespace": batch["namespace"]}):
        raise MigrationError("Kaynak canlı devir için donduruldu; arşiv farkı otomatik uygulanamaz.")
    if batch["state"] not in {"reviewed", "importing", "failed"} or token != batch.get("review_token"):
        raise MigrationError("Güncel deneme aktarımını onaylayın.")
    if batch["state"] == "reviewed":
        rows, report = await build_plan(db, batch)
        if report["error_count"] or report["review_token"] != token:
            raise MigrationError("İnceleme artık geçerli değil veya hata var; deneme aktarımını yenileyin.")
        # Freeze the normalized plan in encrypted chunks; subsequent resume does not reclassify created rows.
        writes = []
        for part, offset in enumerate(range(0, len(rows), 250)):
            writes.append(
                UpdateOne(
                    {"tenant_id": batch["tenant_id"], "dataset_id": "plan:" + batch["id"] + ":" + token, "part": part},
                    {"$set": {"batch_id": batch["id"], "payload": seal(rows[offset : offset + 250], batch["tenant_id"]), "expires_at": now() + timedelta(days=30)}},
                    upsert=True,
                )
            )
            if len(writes) == 20:
                await db.migration_staging.bulk_write(writes)
                writes = []
        if writes:
            await db.migration_staging.bulk_write(writes)
        plan_parts = (len(rows) + 249) // 250
    else:
        plan_parts = batch["plan_parts"]
    lease = str(uuid.uuid4())
    locked = await db.migration_batches.find_one_and_update(
        {
            "tenant_id": batch["tenant_id"],
            "id": batch["id"],
            "revision": batch["revision"],
            "state": batch["state"],
            "review_token": token,
            "$or": [{"lease_until": {"$lt": now()}}, {"lease_until": None}],
        },
        {"$set": {"state": "importing", "lease": lease, "lease_until": now() + timedelta(minutes=5), "plan_parts": plan_parts}},
        return_document=ReturnDocument.AFTER,
    )
    if not locked:
        raise MigrationError("Aktarım başka bir işlemde çalışıyor; kısa süre sonra yenileyin.")
    try:
        start = locked["cursor"]
        cursor = min(start + CHUNK_SIZE, locked["report"]["rows"])
        first_part, last_part = start // 250, max(start, cursor - 1) // 250
        chunks = (
            await db.migration_staging.find({"tenant_id": batch["tenant_id"], "dataset_id": "plan:" + batch["id"] + ":" + token, "part": {"$gte": first_part, "$lte": last_part}})
            .sort("part", 1)
            .to_list(2)
        )
        if [c["part"] for c in chunks] != list(range(first_part, last_part + 1)):
            raise MigrationError("Onaylı plan eksik veya süresi dolmuş; destek incelemesi gerekli.")
        rows = [r for chunk in chunks for r in unseal(chunk["payload"], batch["tenant_id"])]
        selected = rows[start % 250 : start % 250 + cursor - start]
        if len(selected) != cursor - start:
            raise MigrationError("Onaylı planın satır sayısı uyuşmuyor.")
        for row in selected:
            doc = {
                "id": row["id"],
                "tenant_id": batch["tenant_id"],
                "namespace": batch["namespace"],
                "entity": row["entity"],
                "content_hash": row["content_hash"],
                "payload": seal(row["data"], batch["tenant_id"]),
                "refs": row["refs"],
                "guest_id": row["guest_id"],
                "owner_batch_id": batch["id"],
                "created_at": now(),
            }
            if row.get("previous_hash"):
                prior = await db.migration_archive.find_one({"tenant_id": batch["tenant_id"], "id": row["id"]})
                if prior and prior["content_hash"] == row["previous_hash"]:
                    version_key = digest([batch["tenant_id"], row["id"], batch["id"]])
                    await db.migration_versions.update_one(
                        {"_id": version_key, "tenant_id": batch["tenant_id"]},
                        {
                            "$setOnInsert": {
                                "record_id": row["id"],
                                "tenant_id": batch["tenant_id"],
                                "replaced_by_batch": batch["id"],
                                "archived_at": now(),
                                "previous": {k: v for k, v in prior.items() if k != "_id"},
                            }
                        },
                        upsert=True,
                    )
                    # Preserve a previous live guest link; delta never overwrites
                    # that guest's operational profile fields.
                    doc["guest_id"] = row.get("guest_id") or prior.get("guest_id")
                    await db.migration_archive.update_one({"tenant_id": batch["tenant_id"], "id": row["id"], "content_hash": row["previous_hash"]}, {"$set": doc})
            else:
                await db.migration_archive.update_one({"tenant_id": batch["tenant_id"], "id": row["id"]}, {"$setOnInsert": doc}, upsert=True)
            actual = await db.migration_archive.find_one({"tenant_id": batch["tenant_id"], "id": row["id"]}, {"content_hash": 1})
            if actual["content_hash"] != row["content_hash"]:
                raise MigrationError("Eşzamanlı kaynak kayıt değişikliği; aktarım durduruldu.")
            await _publish_guest(db, batch, row)
            if row["guest_id"]:
                await db.migration_archive.update_one({"tenant_id": batch["tenant_id"], "id": row["id"]}, {"$set": {"guest_id": row["guest_id"]}})
        state = "complete" if cursor == locked["report"]["rows"] else "importing"
        await audit(db, {**locked, "cursor": cursor, "state": state}, actor_id, "migration_completed" if state == "complete" else "migration_chunk_imported")
        result = await db.migration_batches.find_one_and_update(
            {"tenant_id": batch["tenant_id"], "id": batch["id"], "lease": lease},
            {"$set": {"cursor": cursor, "state": state, "lease_until": None, "updated_at": now(), "last_error": None}},
            return_document=ReturnDocument.AFTER,
        )
        return public_batch(result)
    except (Exception, asyncio.CancelledError):
        await db.migration_batches.update_one(
            {"tenant_id": batch["tenant_id"], "id": batch["id"], "lease": lease},
            {"$set": {"state": "failed", "lease_until": None, "last_error": "İşlem durdu; aynı onay ile kaldığı yerden sürdürülebilir."}},
        )
        raise


async def archive_rows(db, tenant_id, *, namespace=None, entity=None, guest_id=None, record_key=None, parent_key=None, offset=0, limit=50):
    query = {"tenant_id": tenant_id}
    if namespace:
        query["namespace"] = namespace
    if entity:
        query["entity"] = entity
    if record_key:
        query["id"] = record_key
    if parent_key:
        query["$and"] = [{"$or": [{f"refs.{field}": parent_key} for field in REFERENCES]}]
    if guest_id:
        profiles = await db.migration_archive.find({"tenant_id": tenant_id, "entity": "guests", "guest_id": guest_id}, {"id": 1}).to_list(1001)
        if len(profiles) > 1000:
            raise MigrationError("Misafir bağlantı sınırı; kaynak alanıyla daraltın.")
        keys = [p["id"] for p in profiles]
        query["$or"] = [{"id": {"$in": keys}}, {"refs.guest_source_id": {"$in": keys}}]
    documents = await db.migration_archive.find(query).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
    states = {b["id"]: b["state"] for b in await db.migration_batches.find({"tenant_id": tenant_id, "id": {"$in": [d["owner_batch_id"] for d in documents]}}, {"id": 1, "state": 1}).to_list(limit)}
    return {
        "total": await db.migration_archive.count_documents(query),
        "items": [
            {
                "id": d["id"],
                "entity": d["entity"],
                "namespace": d["namespace"],
                "guest_id": d.get("guest_id"),
                "refs": d["refs"],
                "data": unseal(d["payload"], tenant_id),
                "owner_batch_id": d["owner_batch_id"],
                "batch_state": states.get(d["owner_batch_id"], "unknown"),
            }
            for d in documents
        ],
        "offset": offset,
        "limit": limit,
    }


async def rollback(db, batch, actor_id):
    """Archive reversal only. Published profiles are retained, never delete a live guest."""
    if batch.get("allow_archive_updates") or await db.migration_cutover_sources.find_one({"tenant_id": batch["tenant_id"], "namespace": batch["namespace"]}):
        raise MigrationError("Sürümlü fark veya canlı devir otomatik silinmez; kontrollü ters kayıt/mutabakat gerekli.")
    if batch["publish_guests"]:
        raise MigrationError("Misafir listesine yayınlanmış aktarım otomatik geri alınamaz; canlı profiller korunur. Destek incelemesi gerekli.")
    if batch["state"] not in {"complete", "failed", "rolling_back"}:
        raise MigrationError("Bu durumda aktarım geri alınamaz.")
    # A tenant-wide durable lock excludes another commit while dependencies are checked/deleted.
    # Import and rollback share this lock (router/service caller uses namespace_guard).
    owned = await db.migration_archive.find({"tenant_id": batch["tenant_id"], "owner_batch_id": batch["id"]}, {"id": 1}).to_list(MAX_BATCH_ROWS)
    keys = {r["id"] for r in owned}
    if await db.migration_attachments.find_one({"tenant_id": batch["tenant_id"], "record_id": {"$in": list(keys)}}):
        raise MigrationError("Arşivde ek belgeler var; saklama/silme politikası kapsamında kontrollü inceleme gerekli.")
    others = await db.migration_archive.find({"tenant_id": batch["tenant_id"], "namespace": batch["namespace"], "owner_batch_id": {"$ne": batch["id"]}}, {"refs": 1}).to_list(200001)
    if any(keys & set(r.get("refs", {}).values()) for r in others):
        raise MigrationError("Başka aktarım bu kayıtlara bağlı; önce bağımlı aktarımı geri alın.")
    batches = await db.migration_batches.find(
        {"tenant_id": batch["tenant_id"], "namespace": batch["namespace"], "id": {"$ne": batch["id"]}, "state": {"$in": ["importing", "failed", "complete"]}}, {"datasets": 1}
    ).to_list(10001)
    if batches:
        # Conservative: no destructive dependency inference from incomplete/reused chunks.
        raise MigrationError("Aynı kaynaktan başka aktarım var; güvenli geri alma için destek incelemesi gerekli.")
    await db.migration_batches.update_one({"tenant_id": batch["tenant_id"], "id": batch["id"]}, {"$set": {"state": "rolling_back"}})
    await db.migration_archive.delete_many({"tenant_id": batch["tenant_id"], "owner_batch_id": batch["id"]})
    await db.migration_batches.update_one({"tenant_id": batch["tenant_id"], "id": batch["id"]}, {"$set": {"state": "rolled_back", "updated_at": now()}})
    batch = await get_batch(db, batch["tenant_id"], batch["id"])
    await audit(db, batch, actor_id, "migration_rolled_back")
    return public_batch(batch)


async def namespace_guard(db, batch, callback):
    """Serialize migration writes in a tenant, including cross-source publication."""
    key = digest([batch["tenant_id"], "data-migration"])
    await db.migration_locks.update_one({"_id": key}, {"$setOnInsert": {"tenant_id": batch["tenant_id"], "until": now()}}, upsert=True)
    lease = str(uuid.uuid4())
    acquired = await db.migration_locks.find_one_and_update(
        {"_id": key, "tenant_id": batch["tenant_id"], "until": {"$lte": now()}}, {"$set": {"lease": lease, "until": now() + timedelta(minutes=10)}}, return_document=ReturnDocument.AFTER
    )
    if not acquired:
        raise MigrationError("Bu tesis için başka aktarım çalışıyor; yenileyin.")
    try:
        async with asyncio.timeout(90):
            return await callback()
    finally:
        await db.migration_locks.update_one({"_id": key, "tenant_id": batch["tenant_id"], "lease": lease}, {"$set": {"until": now()}})
