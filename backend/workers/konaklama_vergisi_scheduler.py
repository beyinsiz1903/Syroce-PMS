"""Konaklama Vergisi Auto-Finalize + Email Scheduler.

Ay başında (varsayılan ayın `auto_finalize_day` günü, default 1) önceki
ayın konaklama vergisi beyannamesini otomatik olarak `finalized`
durumuna alır. `auto_email=true` ve `email_recipients` doluysa PDF eki
ile e-posta gönderir.

Tek instance + multi-instance güvenliği:
- `tax_declarations` koleksiyonunda `(tenant_id, period, kind)` UNIQUE
  index var (router._ensure_declaration_indexes); yarış olursa yalnızca
  bir worker kazanır, diğeri DuplicateKeyError alır ve sessiz geçer.
- E-posta tek seferlik: dokümanın `auto_email_sent_at` alanı set edilmiş
  ise tekrar gönderilmez.

Devre dışı bırakmak: `KVB_SCHEDULER_INTERVAL_SECONDS=0`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = int(
    os.environ.get("KVB_SCHEDULER_INTERVAL_SECONDS", "3600"))
_started = False


async def _previous_period_for_tenant(tenant_id: str) -> tuple[int, int]:
    """Tenant TZ'ye göre 'şu an'ın bir önceki ayını döner."""
    from routers.finance.konaklama_vergisi import _tenant_tz
    tz = await _tenant_tz(tenant_id)
    now_local = datetime.now(tz)
    if now_local.month == 1:
        return now_local.year - 1, 12
    return now_local.year, now_local.month - 1


async def _process_tenant(cfg: dict) -> dict:
    """Tek tenant için auto-finalize + opsiyonel auto-email döngüsü.

    `cfg` aktif (tenant_id, auto_finalize=true) bir city_tax_rules
    dökümanıdır. Idempotent: aynı dönem için mevcut finalize'ı asla
    bozmaz; yalnızca eksikse oluşturur.
    """
    tenant_id = cfg.get("tenant_id")
    if not tenant_id:
        return {"tenant_id": None, "skipped": "no_tenant_id"}

    from routers.finance.konaklama_vergisi import (
        _aggregate_period,
        _decl_pdf_bytes,
        _ensure_declaration_indexes,
        _tenant_summary,
        _tenant_tz,
    )
    from core.database import db
    from core.email import _is_valid_email, send_email

    await _ensure_declaration_indexes()

    tz = await _tenant_tz(tenant_id)
    now_local = datetime.now(tz)
    finalize_day = int(cfg.get("auto_finalize_day") or 1)
    if now_local.day < max(1, finalize_day):
        return {"tenant_id": tenant_id, "skipped": "before_finalize_day"}

    year, month = await _previous_period_for_tenant(tenant_id)
    period = f"{year}-{month:02d}"

    existing = await db.tax_declarations.find_one(
        {"tenant_id": tenant_id, "period": period,
         "kind": "konaklama_vergisi"}, {"_id": 0})

    created_new = False
    if not existing or existing.get("status") in (None, "draft"):
        agg = await _aggregate_period(tenant_id, year, month)
        # v95.9: matrah=0 → boş dönem; iz açmayalım, e-posta da yok.
        if (agg.get("total_base") or 0) <= 0 and (
                agg.get("folio_count") or 0) == 0:
            return {"tenant_id": tenant_id, "period": period,
                    "skipped": "empty_period"}
        tenant = await _tenant_summary(tenant_id)
        due_month = month + 1 if month < 12 else 1
        due_year = year if month < 12 else year + 1
        snapshot = {
            "id": (existing or {}).get("id") or str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "kind": "konaklama_vergisi",
            "period": period,
            "year": year,
            "month": month,
            "due_date": f"{due_year}-{due_month:02d}-26",
            "tenant": tenant,
            "rate_percent": agg["rate_percent"],
            "folio_count": agg["folio_count"],
            "total_nights": agg["total_nights"],
            "total_base": agg["total_base"],
            "total_tax": agg["total_tax"],
            "rows": agg["rows"],
            "currency": "TRY",
            "law_reference": "7194 sayılı Kanun — Konaklama Vergisi",
            "status": "finalized",
            "finalized_at": datetime.now(UTC).isoformat(),
            "finalized_by": "system:auto_finalize",
            "submission_ref": None,
            "submitted_at": None,
            "submitted_by": None,
            "payment_ref": None,
            "paid_at": None,
            "paid_by": None,
            "paid_amount": None,
            "auto_finalized": True,
        }
        # Yarış güvenliği: sadece kayıt yoksa veya draft ise yaz.
        res = await db.tax_declarations.update_one(
            {"tenant_id": tenant_id, "period": period,
             "kind": "konaklama_vergisi",
             "$or": [{"status": {"$in": [None, "draft"]}},
                     {"status": {"$exists": False}}]},
            {"$set": snapshot}, upsert=True)
        created_new = bool(res.matched_count or res.upserted_id)
        existing = snapshot if created_new else await db.tax_declarations.find_one(
            {"tenant_id": tenant_id, "period": period,
             "kind": "konaklama_vergisi"}, {"_id": 0})
        if created_new:
            try:
                from core.helpers import create_audit_log
                from models.schemas import User as _User
                sys_user = _User(
                    id="system:auto_finalize",
                    email="system@syroce.local",
                    role="super_admin",
                    tenant_id=tenant_id,
                )
                await create_audit_log(
                    tenant_id=tenant_id, user=sys_user,
                    action="AUTO_FINALIZE_KONAKLAMA_BEYANNAME",
                    entity_type="tax_declaration",
                    entity_id=snapshot["id"],
                    changes={"period": period,
                             "total_tax": snapshot["total_tax"]})
            except Exception as exc:  # pragma: no cover
                logger.debug("audit log skipped: %s", exc)
            logger.info(
                "[kvb-scheduler] auto-finalized tenant=%s period=%s tax=%.2f",
                tenant_id, period, snapshot["total_tax"])

    # E-posta: yalnızca decl finalize edildi VE auto_email aktif VE
    # daha önce bu decl için otomatik mail gönderilmediyse.
    if not existing:
        return {"tenant_id": tenant_id, "period": period,
                "created": created_new, "emailed": False}

    if not cfg.get("auto_email"):
        return {"tenant_id": tenant_id, "period": period,
                "created": created_new, "emailed": False,
                "skipped_email": "disabled"}
    if existing.get("auto_email_sent_at"):
        return {"tenant_id": tenant_id, "period": period,
                "created": created_new, "emailed": False,
                "skipped_email": "already_sent"}

    raw = cfg.get("email_recipients") or []
    seen: set[str] = set()
    targets: list[str] = []
    for r in raw:
        if not isinstance(r, str):
            continue
        rs = r.strip()
        if not rs or not _is_valid_email(rs):
            continue
        k = rs.lower()
        if k in seen:
            continue
        seen.add(k)
        targets.append(rs)
    if not targets:
        return {"tenant_id": tenant_id, "period": period,
                "created": created_new, "emailed": False,
                "skipped_email": "no_recipients"}

    # Atomik claim: gönderim DENENMEDEN ÖNCE auto_email_sent_at'i set
    # ediyoruz. Böylece worker recipient listesinin ortasında crash etse
    # bile bir sonraki tick aynı dökümana DOKUNMAZ — yani aynı dönem için
    # mükerrer e-posta riski sıfır. Trade-off: kısmi başarısızlık kalırsa
    # operatör manuel "E-posta Gönder" butonuyla tekrar tetiklemelidir
    # (manuel akış zaten bu flag'e bakmaz). Operatör görünürlüğü için
    # auto_email_failures'a tüm hedefler "pending" olarak yazılır,
    # gönderim sonrası override edilir.
    now_iso = datetime.now(UTC).isoformat()
    claim = await db.tax_declarations.update_one(
        {"id": existing["id"], "tenant_id": tenant_id,
         "auto_email_sent_at": {"$in": [None, ""]}},
        {"$set": {
            "auto_email_sent_at": now_iso,
            "auto_email_recipients": targets,
            "auto_email_ok": 0,
            "auto_email_failures": [
                {"to": t, "error": "pending"} for t in targets],
        }})
    if claim.matched_count == 0:
        # Başka tick zaten claim etmiş — sessiz geç.
        return {"tenant_id": tenant_id, "period": period,
                "created": created_new, "emailed": False,
                "skipped_email": "already_claimed"}

    try:
        pdf_bytes = _decl_pdf_bytes(existing)
    except Exception as exc:
        logger.warning("[kvb-scheduler] PDF render failed tenant=%s: %s",
                       tenant_id, exc)
        await db.tax_declarations.update_one(
            {"id": existing["id"], "tenant_id": tenant_id},
            {"$set": {"auto_email_failures": [
                {"to": t, "error": f"pdf_render_failed: {exc}"}
                for t in targets]}})
        return {"tenant_id": tenant_id, "period": period,
                "created": created_new, "emailed": False,
                "error": "pdf_render_failed"}

    subject = f"Konaklama Vergisi Beyannamesi — {period}"
    html = (
        "<div style='font-family:Helvetica,Arial,sans-serif;max-width:600px;"
        "margin:0 auto;padding:18px;color:#0f172a;'>"
        f"<h2 style='margin:0 0 8px;'>Konaklama Vergisi Beyannamesi — {period}</h2>"
        f"<p style='color:#64748b;margin:0 0 16px;'>"
        f"Son ödeme tarihi: <b>{existing.get('due_date','-')}</b> &middot; "
        f"Tahakkuk eden vergi: <b>{float(existing.get('total_tax') or 0):.2f} TL</b>"
        "</p>"
        "<p style='margin:0 0 8px;'>Beyanname özeti PDF olarak ekte yer "
        "almaktadır. Bu mesaj otomasyon tarafından üretilmiştir.</p>"
        "<p style='font-size:11px;color:#94a3b8;margin-top:18px;'>"
        "Syroce PMS · Otomatik üretilmiş bildirim"
        "</p></div>"
    )
    attachments = [{
        "filename": f"kvb-{period}.pdf",
        "content": pdf_bytes,
        "content_type": "application/pdf",
    }]
    sent_ok = 0
    failures: list[dict] = []
    for to in targets:
        res = await send_email(
            to=to, subject=subject, html=html, attachments=attachments)
        if res.get("sent"):
            sent_ok += 1
        else:
            failures.append({"to": to,
                             "error": res.get("error") or res.get("provider")})

    await db.tax_declarations.update_one(
        {"id": existing["id"], "tenant_id": tenant_id},
        {"$set": {
            "auto_email_sent_at": datetime.now(UTC).isoformat(),
            "auto_email_recipients": targets,
            "auto_email_ok": sent_ok,
            "auto_email_failures": failures,
            "last_email_at": datetime.now(UTC).isoformat(),
            "last_email_recipients": targets,
            "last_email_ok": sent_ok,
            "last_email_failures": failures,
        }})
    logger.info(
        "[kvb-scheduler] auto-emailed tenant=%s period=%s ok=%d/%d",
        tenant_id, period, sent_ok, len(targets))
    return {"tenant_id": tenant_id, "period": period,
            "created": created_new, "emailed": True,
            "ok": sent_ok, "total": len(targets)}


async def _tick() -> None:
    """Tek tarama: auto_finalize=true olan her tenant için işlem yap."""
    from core.database import db
    cursor = db.city_tax_rules.find(
        {"active": True, "auto_finalize": True}, {"_id": 0})
    processed = 0
    async for cfg in cursor:
        try:
            await _process_tenant(cfg)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[kvb-scheduler] tenant process failed (%s): %s",
                cfg.get("tenant_id"), exc)
    if processed:
        logger.info("[kvb-scheduler] processed_tenants=%d", processed)


async def _loop(interval_seconds: int) -> None:
    logger.info("[kvb-scheduler] loop started interval=%ss", interval_seconds)
    # Boot fazında ağır iş yapmayalım — diğer index/init işleri otursun.
    await asyncio.sleep(60)
    while True:
        try:
            await _tick()
        except Exception as exc:
            logger.warning("[kvb-scheduler] tick error: %s", exc)
        await asyncio.sleep(interval_seconds)


def start() -> bool:
    """Bootstrap çağrısı. False = devre dışı."""
    global _started
    if _started:
        return True
    if DEFAULT_INTERVAL_SECONDS <= 0:
        logger.info("[kvb-scheduler] disabled via env (interval=0)")
        return False
    asyncio.create_task(_loop(DEFAULT_INTERVAL_SECONDS),
                        name="kvb-scheduler")
    _started = True
    return True
