"""Operator-configured, read-only JSON snapshot connector, not vendor magic.

Registry and tokens live ONLY in server configuration. A tenant request cannot
choose an arbitrary URL, credential or target tenant. Remote pages are never
executed as instructions and still pass the ordinary upload validators.
"""

import asyncio
import json
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .formats import MAX_BYTES, MigrationError, parse_file
from .schema import FIELDS, private_fingerprint
from .service import add_dataset, get_batch


def registry(tenant):
    try:
        entries = json.loads(os.getenv("DATA_MIGRATION_API_SOURCES", "[]"))
        if not isinstance(entries, list):
            raise ValueError()
        result = {}
        for item in entries:
            if not isinstance(item, dict) or tenant not in item.get("tenant_ids", []):
                continue
            name, url, env = item["id"], item["url"], item["token_env"]
            parts = urlsplit(url)
            if not re.fullmatch(r"[a-z0-9_-]{3,60}", name) or parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment or parts.query:
                raise ValueError()
            if not re.fullmatch(r"MIGRATION_SOURCE_[A-Z0-9_]+_TOKEN", env) or item["entity"] not in FIELDS:
                raise ValueError()
            result[name] = item
        return result
    except (ValueError, KeyError, TypeError):
        raise MigrationError("API kaynak yapılandırması geçersiz; sistem yöneticisi incelemeli.") from None


def public_sources(tenant):
    return [{"id": k, "entity": v["entity"], "label": str(v.get("label") or k)[:80]} for k, v in registry(tenant).items()]


async def import_snapshot(db, batch, actor, source_id):
    if batch["state"] not in {"draft", "reviewed"}:
        raise MigrationError("API içe aktarımı yalnız hazırlık aşamasında kullanılabilir.")
    source = registry(batch["tenant_id"]).get(source_id)
    if not source:
        raise MigrationError("Bu tesis için yetkilendirilmiş API kaynağı yok.")
    token = os.getenv(source["token_env"], "").strip()
    if not token:
        raise MigrationError("Kaynak API kimlik bilgisi sunucuda tanımlı değil.")
    from integrations.xchange.safety import safe_download_async

    rows, cursors = [], set()
    cursor, snapshot, expected_count, expected_totals = None, None, None, None
    consumed = 0
    try:
        async with asyncio.timeout(80):
            for page in range(40):
                parts = urlsplit(source["url"])
                query = dict(parse_qsl(parts.query))
                query.update({"limit": "250"})
                if cursor:
                    query["cursor"] = cursor
                url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
                body = await safe_download_async(url, max_bytes=MAX_BYTES, timeout=10, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
                consumed += len(body)
                if consumed > MAX_BYTES:
                    raise MigrationError("API anlık görüntüsü 5 MB sınırını aşıyor; kaynak kapsamını bölün.")
                payload = json.loads(body)
                if not isinstance(payload, dict) or not isinstance(payload.get("snapshot_id"), str) or not 1 <= len(payload["snapshot_id"]) <= 160:
                    raise MigrationError("Kaynak API sabit snapshot_id vermeli.")
                if page == 0:
                    snapshot, expected_count, expected_totals = payload["snapshot_id"], payload.get("total_count"), payload.get("totals")
                    if type(expected_count) is not int or not 0 <= expected_count <= 10000:
                        raise MigrationError("Kaynak API bağımsız total_count (0–10.000) vermeli.")
                    if expected_totals is not None and (
                        not isinstance(expected_totals, dict)
                        or len(expected_totals) > 100
                        or any(not isinstance(k, str) or len(k) > 160 or not isinstance(v, str) or len(v) > 40 for k, v in expected_totals.items())
                    ):
                        raise MigrationError("Kaynak API toplamları geçersiz.")
                elif payload["snapshot_id"] != snapshot or payload.get("total_count") != expected_count or payload.get("totals") != expected_totals:
                    raise MigrationError("Kaynak API sayfalar arasında değişti; sabit anlık görüntü gerekli.")
                records = payload.get("records")
                if not isinstance(records, list) or len(records) > 250 or len(rows) + len(records) > expected_count:
                    raise MigrationError("Kaynak API sayfa satırları / kontrol sayısı geçersiz.")
                rows.extend(records)
                cursor = payload.get("next_cursor")
                if cursor is None:
                    break
                if not records or not isinstance(cursor, str) or not 1 <= len(cursor) <= 500 or cursor in cursors:
                    raise MigrationError("Kaynak API sayfalama döngüsü veya geçersiz imleç.")
                cursors.add(cursor)
            else:
                raise MigrationError("Kaynak API 40 sayfa sınırını aştı; veri kesilmedi.")
    except MigrationError:
        raise
    except (Exception, TimeoutError):
        # Never surface URLs, authorization headers, raw source errors or PII.
        raise MigrationError("Kaynak API okunamadı; kimlik, izin ve bağlantıyı kontrol edin. Otomatik tekrar yapılmadı.") from None
    if len(rows) != expected_count:
        raise MigrationError("Kaynak API toplamı ile alınan satır sayısı farklı.")
    headers, validated = parse_file("snapshot.json", json.dumps(rows, ensure_ascii=False).encode())
    fingerprint = private_fingerprint([source_id, snapshot, validated, expected_count, expected_totals])
    batch = await get_batch(db, batch["tenant_id"], batch["id"])
    prior = next((d for d in batch["datasets"] if d.get("api_snapshot") == private_fingerprint([source_id, snapshot])), None)
    if prior:
        if prior.get("api_content_hash") != fingerprint:
            raise MigrationError("Aynı API anlık görüntü kimliği değişmiş içerikle geldi; kaynak uyarlamasını inceleyin.")
        return batch
    return await add_dataset(
        db,
        batch,
        actor,
        entity=source["entity"],
        headers=headers,
        rows=validated,
        source_metadata={"expected_count": expected_count, "expected_totals": expected_totals, "api_snapshot": private_fingerprint([source_id, snapshot]), "api_content_hash": fingerprint},
    )
