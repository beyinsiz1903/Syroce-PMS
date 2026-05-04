"""Auto-split from misc_router.py — backward-compatible sub-router."""
import html as _html
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

sub_router = APIRouter()

# ── Şikayet/Geri Bildirim Yönetimi ────────────────────────────────────────

ESCALATION_TARGETS = {
    "management": "Yönetim",
    "owner": "Otel Sahibi",
    "duty_manager": "Nöbetçi Müdür",
    "department_head": "Departman Şefi",
}

SLA_HOURS = {
    "critical": 2,
    "high": 6,
    "medium": 12,
    "low": 24,
}

COMPENSATION_LABELS = {
    "free_night": "Bedava Gece",
    "room_upgrade": "Oda Upgrade",
    "fnb_credit": "F&B Kredisi",
    "spa_voucher": "Spa Kuponu",
    "discount": "İndirim",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _history_entry(action: str, user: User, **extra) -> dict:
    entry = {
        "action": action,
        "actor_id": user.id,
        "actor_name": getattr(user, "full_name", None) or getattr(user, "username", None) or user.email,
        "at": _now_iso(),
    }
    entry.update({k: v for k, v in extra.items() if v is not None})
    return entry


async def _push_history(complaint_id: str, tenant_id: str, entry: dict) -> None:
    try:
        await db.service_complaints.update_one(
            {"id": complaint_id, "tenant_id": tenant_id},
            {"$push": {"history": entry}},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("[complaints] history push failed: %s", exc)


async def _notify_managers_of_escalation(complaint: dict, escalated_to: str, notes: str, actor: User) -> None:
    """Send escalation notification e-mail to all managers (admin + supervisor)."""
    try:
        from core.email import send_email
    except Exception as exc:  # pragma: no cover
        logger.warning("[complaints] email module unavailable: %s", exc)
        return

    try:
        managers = await db.users.find(
            {
                "tenant_id": actor.tenant_id,
                "role": {"$in": [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]},
                "is_active": True,
            },
            {"_id": 0, "email": 1, "full_name": 1},
        ).to_list(50)
    except Exception as exc:
        logger.warning("[complaints] manager lookup failed: %s", exc)
        managers = []

    target_label = ESCALATION_TARGETS.get(escalated_to, escalated_to)
    safe_subject = _html.escape(complaint.get("subject") or "-")
    safe_guest = _html.escape(complaint.get("guest_name") or "-")
    safe_room = _html.escape(str(complaint.get("room_number") or "-"))
    safe_desc = _html.escape(complaint.get("description") or "-")
    safe_notes = _html.escape(notes or "(not yok)")
    safe_actor = _html.escape(actor.email or "-")
    safe_target = _html.escape(target_label)
    subject_line = f"[Şikayet] {complaint.get('subject', '-')} ({target_label})"
    severity = complaint.get("severity", "medium")
    severity_label = {"critical": "Kritik", "high": "Yüksek", "medium": "Orta", "low": "Düşük"}.get(severity, severity)
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px">
      <h2 style="color:#7c3aed">Şikayet Eskalasyonu</h2>
      <p><strong>{safe_actor}</strong> bir şikayeti <strong>{safe_target}</strong>'e havale etti.</p>
      <table style="border-collapse:collapse;margin-top:12px">
        <tr><td style="padding:4px 12px 4px 0;color:#6b7280">Konu</td><td><strong>{safe_subject}</strong></td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#6b7280">Misafir</td><td>{safe_guest}</td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#6b7280">Oda</td><td>{safe_room}</td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#6b7280">Önem</td><td>{severity_label}</td></tr>
      </table>
      <p style="margin-top:16px"><em>Eskalasyon notu:</em><br>{safe_notes}</p>
      <p style="margin-top:16px;color:#6b7280;font-size:12px">Açıklama: {safe_desc}</p>
    </div>
    """
    for m in managers:
        if not m.get("email"):
            continue
        try:
            await send_email(m["email"], subject_line, html)
        except Exception as exc:
            logger.warning("[complaints] escalation email to %s failed: %s", m.get("email"), exc)


async def _notify_guest_resolved(complaint: dict, resolution_notes: str, actor: User) -> None:
    """E-mail the guest when their complaint is resolved (best-effort)."""
    guest_id = complaint.get("guest_id")
    if not guest_id:
        return
    try:
        from core.email import send_email
        guest = await db.guests.find_one(
            {"id": guest_id, "tenant_id": actor.tenant_id},
            {"_id": 0, "name": 1, "email": 1},
        )
    except Exception as exc:
        logger.warning("[complaints] guest lookup failed: %s", exc)
        return
    if not guest or not guest.get("email"):
        return

    safe_name = _html.escape(guest.get("name") or "Misafirimiz")
    safe_subject = _html.escape(complaint.get("subject") or "-")
    safe_resolution = _html.escape(resolution_notes or "(not yok)")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px">
      <h2 style="color:#16a34a">Şikayetiniz Çözüldü</h2>
      <p>Sayın <strong>{safe_name}</strong>,</p>
      <p>Bize ilettiğiniz <em>"{safe_subject}"</em> konulu geri bildiriminiz çözüme kavuşturuldu.</p>
      <p style="background:#f0fdf4;border:1px solid #bbf7d0;padding:12px;border-radius:8px">
        <strong>Çözüm:</strong><br>{safe_resolution}
      </p>
      <p>Güvenliğiniz ve memnuniyetiniz bizim için önceliklidir. Yaşanan duruma ilişkin yaşadığınız rahatsızlık için özür dileriz.</p>
      <p style="color:#6b7280;font-size:12px;margin-top:24px">Bu mesaj otomatik olarak gönderilmiştir.</p>
    </div>
    """
    try:
        await send_email(guest["email"], f"Şikayetiniz çözüldü: {complaint.get('subject', '')}", html)
    except Exception as exc:
        logger.warning("[complaints] guest resolution email failed: %s", exc)


# Tazminat tipi → folio ledger charge_code haritası.
# Negatif "adjustment" entry'si yazıldığı için misafir lehine kredit/indirim olur.
_COMPENSATION_CODE_MAP = {
    "discount": "MISC",
    "free_night": "ROOM",
    "fnb_credit": "FB",
    "spa_voucher": "SPA",
    "room_upgrade": "ROOM",
    "other": "MISC",
    "none": "MISC",
}


async def _post_compensation_to_folio(complaint: dict, actor: User) -> dict:
    """
    Şikayet çözümünde verilen tazminatı misafirin aktif folyosuna kredit
    olarak işler. Best-effort — folio bulunamazsa sessizce skip eder.

    Returns: {folio_adjusted, folio_id?, entry_id?, new_balance?, reason?}
    """
    booking_id = complaint.get("booking_id")
    raw_amount = complaint.get("compensation_amount") or 0
    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        amount = 0.0
    comp_type = (complaint.get("compensation_offered") or "").strip()

    if not booking_id:
        return {"folio_adjusted": False, "reason": "Rezervasyon bağlantısı yok"}
    if amount <= 0:
        return {"folio_adjusted": False, "reason": "Tazminat tutarı sıfır"}
    if not comp_type or comp_type == "none":
        return {"folio_adjusted": False, "reason": "Tazminat tipi seçilmedi"}

    try:
        folio = await db.folios.find_one(
            {
                "tenant_id": actor.tenant_id,
                "booking_id": booking_id,
                "status": "open",
            },
            {"_id": 0, "id": 1, "folio_number": 1, "balance": 1},
        )
    except Exception as exc:
        logger.warning("[complaints] folio lookup failed: %s", exc)
        return {"folio_adjusted": False, "reason": "Folyo sorgusu hata verdi"}

    if not folio:
        return {"folio_adjusted": False, "reason": "Açık folyo bulunamadı"}

    folio_id = folio["id"]
    charge_code = _COMPENSATION_CODE_MAP.get(comp_type, "MISC")
    comp_label = COMPENSATION_LABELS.get(comp_type, comp_type)
    short_id = (complaint.get("id") or "")[:8]
    description = f"Şikayet tazminatı: {comp_label} (Şikayet #{short_id})"

    try:
        from core.folio_ledger_service import FolioLedgerService
        svc = FolioLedgerService()
        # Tenant-scope idempotency key: aynı şikayet 2 kez resolve edilirse
        # ledger'da ikinci entry oluşmaz; cross-tenant çakışma riski yok.
        idem_key = f"complaint-comp:{actor.tenant_id}:{complaint.get('id')}"
        result = await svc.post_adjustment(
            tenant_id=actor.tenant_id,
            folio_id=folio_id,
            booking_id=booking_id,
            amount=-round(amount, 2),  # negatif → misafir lehine kredit
            description=description,
            charge_code=charge_code,
            reference_id=complaint.get("id"),
            idempotency_key=idem_key,
            posted_by=actor.id,
            metadata={
                "source": "complaint_compensation",
                "complaint_id": complaint.get("id"),
                "compensation_type": comp_type,
            },
        )
        new_balance = result["new_balance"]

        # folios.balance snapshot'ını da senkron tut (raporlama için).
        try:
            await db.folios.update_one(
                {"id": folio_id, "tenant_id": actor.tenant_id},
                {"$set": {"balance": new_balance, "updated_at": _now_iso()}},
            )
        except Exception as exc:
            logger.warning("[complaints] folio balance snapshot failed: %s", exc)

        return {
            "folio_adjusted": True,
            "folio_id": folio_id,
            "folio_number": folio.get("folio_number"),
            "entry_id": result.get("entry_id"),
            "amount_credited": round(amount, 2),
            "new_balance": new_balance,
        }
    except Exception as exc:
        logger.exception("[complaints] folio adjustment failed: %s", exc)
        return {"folio_adjusted": False, "reason": f"Folyo işleme hatası: {exc}"}


def _enrich_with_sla(complaint: dict) -> dict:
    """Add SLA fields (age_hours, sla_hours, is_overdue) for active complaints."""
    if complaint.get("status") in ("resolved",):
        return complaint
    created = complaint.get("created_at")
    if not created:
        return complaint
    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=UTC)
        age = datetime.now(UTC) - created_dt
        age_hours = age.total_seconds() / 3600
        sla_hours = SLA_HOURS.get(complaint.get("severity", "medium"), 12)
        complaint = {
            **complaint,
            "age_hours": round(age_hours, 1),
            "sla_hours": sla_hours,
            "is_overdue": age_hours > sla_hours,
        }
    except Exception:
        pass
    return complaint


@sub_router.get("/service/complaints")
async def get_complaints(
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    room_number: str | None = None,
    current_user: User = Depends(get_current_user)
):
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    if category:
        query['category'] = category
    if severity:
        query['severity'] = severity
    if room_number:
        query['room_number'] = room_number

    raw = await db.service_complaints.find(query, {'_id': 0}).sort('created_at', -1).to_list(200)
    complaints = [_enrich_with_sla(c) for c in raw]

    stats = {
        "total": len(complaints),
        "open": sum(1 for c in complaints if c.get("status") == "open"),
        "in_progress": sum(1 for c in complaints if c.get("status") == "in_progress"),
        "escalated": sum(1 for c in complaints if c.get("status") == "escalated"),
        "resolved": sum(1 for c in complaints if c.get("status") == "resolved"),
        "critical": sum(1 for c in complaints if c.get("severity") == "critical"),
        "high": sum(1 for c in complaints if c.get("severity") == "high"),
        "overdue": sum(1 for c in complaints if c.get("is_overdue")),
    }

    return {'complaints': complaints, 'total': len(complaints), 'stats': stats}


@sub_router.get("/service/complaints/compensation-report")
async def complaint_compensation_report(
    current_user: User = Depends(get_current_user),
):
    """Tazminat raporu — çözülmüş şikayetlerde verilen tazminatların özeti."""
    pipeline = [
        {"$match": {
            "tenant_id": current_user.tenant_id,
            "status": "resolved",
            "compensation_offered": {"$nin": [None, "", "none"]},
        }},
        {"$group": {
            "_id": "$compensation_offered",
            "count": {"$sum": 1},
            "total_amount": {"$sum": {"$ifNull": ["$compensation_amount", 0]}},
        }},
    ]
    items = await db.service_complaints.aggregate(pipeline).to_list(50)
    breakdown = [
        {
            "type": it["_id"],
            "label": COMPENSATION_LABELS.get(it["_id"], it["_id"]),
            "count": it["count"],
            "total_amount": it.get("total_amount", 0),
        }
        for it in items
    ]
    return {
        "breakdown": breakdown,
        "totals": {
            "count": sum(b["count"] for b in breakdown),
            "amount": sum(b["total_amount"] for b in breakdown),
        },
    }


@sub_router.get("/service/complaints/{complaint_id}")
async def get_complaint_detail(
    complaint_id: str,
    current_user: User = Depends(get_current_user)
):
    complaint = await db.service_complaints.find_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not complaint:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")

    tid = current_user.tenant_id
    result = _enrich_with_sla({**complaint})
    if complaint.get("room_id"):
        room = await db.rooms.find_one({"id": complaint["room_id"], "tenant_id": tid}, {"_id": 0})
        if room:
            result["room_detail"] = {"room_number": room.get("room_number"), "room_type": room.get("room_type"), "floor": room.get("floor")}
    if complaint.get("guest_id"):
        guest = await db.guests.find_one({"id": complaint["guest_id"], "tenant_id": tid}, {"_id": 0})
        if guest:
            result["guest_detail"] = {"name": guest.get("name"), "email": guest.get("email"), "phone": guest.get("phone"), "vip_status": guest.get("vip_status")}
    if complaint.get("booking_id"):
        booking = await db.bookings.find_one({"id": complaint["booking_id"], "tenant_id": tid}, {"_id": 0})
        if booking:
            result["booking_detail"] = {"check_in": booking.get("check_in"), "check_out": booking.get("check_out"), "room_type": booking.get("room_type"), "status": booking.get("status")}

    return result


@sub_router.put("/service/complaints/{complaint_id}")
async def update_complaint(
    complaint_id: str,
    update_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    update_data.pop("id", None)
    update_data.pop("tenant_id", None)
    update_data.pop("history", None)
    now = _now_iso()
    update_data["updated_at"] = now
    update_data["updated_by"] = current_user.id

    existing = await db.service_complaints.find_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")

    changed = {k: v for k, v in update_data.items() if k in ("status", "severity", "category", "assigned_department", "subject", "description") and existing.get(k) != v}

    await db.service_complaints.update_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id},
        {"$set": update_data}
    )
    if changed:
        if "status" in changed and changed["status"] == "in_progress" and existing.get("status") == "escalated":
            await _push_history(complaint_id, current_user.tenant_id, _history_entry("de_escalated", current_user, to_status="in_progress"))
        else:
            await _push_history(complaint_id, current_user.tenant_id, _history_entry("updated", current_user, changes=changed))
    return {"success": True, "message": "Şikayet güncellendi"}


@sub_router.post("/service/complaints/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: str,
    resolve_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    now = _now_iso()
    resolution_notes = resolve_data.get("resolution_notes", "")
    update = {
        "status": "resolved",
        "resolution_notes": resolution_notes,
        "compensation_offered": resolve_data.get("compensation_offered"),
        "compensation_amount": resolve_data.get("compensation_amount", 0),
        "resolved_at": now,
        "resolved_by": current_user.id,
        "updated_at": now,
    }
    existing = await db.service_complaints.find_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")

    await db.service_complaints.update_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id},
        {"$set": update}
    )
    merged = {**existing, **update, "id": complaint_id}
    await _push_history(
        complaint_id, current_user.tenant_id,
        _history_entry(
            "resolved", current_user,
            notes=resolution_notes,
            compensation=resolve_data.get("compensation_offered"),
            amount=resolve_data.get("compensation_amount", 0),
        ),
    )

    # Tazminatı misafirin folyosuna kredit olarak işle (best-effort)
    folio_result = await _post_compensation_to_folio(merged, current_user)
    if folio_result.get("folio_adjusted"):
        await _push_history(
            complaint_id, current_user.tenant_id,
            _history_entry(
                "folio_credited", current_user,
                folio_id=folio_result.get("folio_id"),
                folio_number=folio_result.get("folio_number"),
                amount=folio_result.get("amount_credited"),
                entry_id=folio_result.get("entry_id"),
            ),
        )
    elif resolve_data.get("compensation_offered") and resolve_data.get("compensation_amount", 0) > 0:
        # Tazminat seçilmiş ama folyoya işlenememiş — operasyonel iz bırak
        await _push_history(
            complaint_id, current_user.tenant_id,
            _history_entry(
                "folio_credit_failed", current_user,
                reason=folio_result.get("reason"),
            ),
        )

    await _notify_guest_resolved(merged, resolution_notes, current_user)
    return {
        "success": True,
        "message": "Şikayet çözüldü",
        "folio": folio_result,
    }


@sub_router.post("/service/complaints/{complaint_id}/escalate")
async def escalate_complaint(
    complaint_id: str,
    escalate_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    now = _now_iso()
    escalated_to = escalate_data.get("escalated_to", "management")
    notes = escalate_data.get("notes", "")
    update = {
        "status": "escalated",
        "escalated_to": escalated_to,
        "escalation_notes": notes,
        "escalated_at": now,
        "escalated_by": current_user.id,
        "updated_at": now,
    }
    existing = await db.service_complaints.find_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")

    await db.service_complaints.update_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id},
        {"$set": update}
    )
    await _push_history(
        complaint_id, current_user.tenant_id,
        _history_entry("escalated", current_user, escalated_to=escalated_to, notes=notes),
    )
    await _notify_managers_of_escalation({**existing, **update}, escalated_to, notes, current_user)
    return {
        "success": True,
        "message": "Şikayet eskalasyon edildi ve yöneticilere bildirim gönderildi",
        "notified_role": escalated_to,
    }


@sub_router.post("/service/complaints/{complaint_id}/de-escalate")
async def deescalate_complaint(
    complaint_id: str,
    body: dict | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Eskalasyondan geri al — şikayeti tekrar 'işlemde' durumuna döndür."""
    body = body or {}
    now = _now_iso()
    notes = body.get("notes", "")
    update = {
        "status": "in_progress",
        "de_escalated_at": now,
        "de_escalated_by": current_user.id,
        "de_escalation_notes": notes,
        "updated_at": now,
    }
    existing = await db.service_complaints.find_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")
    if existing.get("status") != "escalated":
        raise HTTPException(status_code=400, detail="Sadece eskalasyondaki şikayetler geri alınabilir")

    await db.service_complaints.update_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id},
        {"$set": update},
    )
    await _push_history(
        complaint_id, current_user.tenant_id,
        _history_entry("de_escalated", current_user, notes=notes),
    )
    return {"success": True, "message": "Şikayet eskalasyondan geri alındı"}


@sub_router.post("/service/complaints/auto-escalate")
async def auto_escalate_overdue(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """SLA süresini aşmış (open/in_progress) şikayetleri toplu eskalasyon eder."""
    raw = await db.service_complaints.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["open", "in_progress"]},
        },
        {"_id": 0},
    ).to_list(500)

    escalated_count = 0
    for c in raw:
        enriched = _enrich_with_sla(c)
        if not enriched.get("is_overdue"):
            continue
        now = _now_iso()
        update = {
            "status": "escalated",
            "escalated_to": "management",
            "escalation_notes": f"Otomatik: SLA aşıldı ({enriched.get('age_hours')} saat)",
            "escalated_at": now,
            "escalated_by": current_user.id,
            "updated_at": now,
        }
        await db.service_complaints.update_one(
            {"id": c["id"], "tenant_id": current_user.tenant_id},
            {"$set": update},
        )
        await _push_history(
            c["id"], current_user.tenant_id,
            _history_entry(
                "escalated", current_user,
                escalated_to="management",
                notes=update["escalation_notes"],
                auto=True,
            ),
        )
        await _notify_managers_of_escalation({**c, **update}, "management", update["escalation_notes"], current_user)
        escalated_count += 1

    return {"success": True, "escalated_count": escalated_count}


@sub_router.delete("/service/complaints/{complaint_id}")
async def delete_complaint(
    complaint_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    result = await db.service_complaints.delete_one(
        {"id": complaint_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Şikayet bulunamadı")
    return {"success": True, "message": "Şikayet silindi"}


@sub_router.get("/service/complaints-rooms")
async def get_rooms_for_complaints(
    current_user: User = Depends(get_current_user)
):
    rooms = await db.rooms.find(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1, "status": 1}
    ).sort("room_number", 1).to_list(500)
    return {"rooms": rooms}


@sub_router.get("/service/complaints-guests")
async def get_guests_for_complaints(
    q: str | None = None,
    current_user: User = Depends(get_current_user)
):
    from security.query_safety import safe_search_term
    query = {"tenant_id": current_user.tenant_id}
    if (s := safe_search_term(q)):
        query["name"] = {"$regex": s, "$options": "i"}
    guests = await db.guests.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "vip_status": 1}
    ).sort("name", 1).to_list(100)
    return {"guests": guests}


@sub_router.get("/service/complaints-bookings")
async def get_active_bookings_for_complaints(
    current_user: User = Depends(get_current_user)
):
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "status": {"$in": ["checked_in", "confirmed"]}},
        {"_id": 0, "id": 1, "guest_name": 1, "guest_id": 1, "room_number": 1, "room_id": 1,
         "room_type": 1, "check_in": 1, "check_out": 1, "status": 1}
    ).sort("check_in", -1).to_list(200)
    return {"bookings": bookings}


# ============= MULTI-PROPERTY MANAGEMENT =============

