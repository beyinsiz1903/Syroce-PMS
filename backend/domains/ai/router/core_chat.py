"""
core_chat

Auto-split sub-router (shared imports/classes inlined).
"""
"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic import Field as _PydField

from core.database import db
from core.helpers import (
    require_module,
)
from core.security import (
    get_current_user,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)


class GuestPersona(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    guest_id: str
    persona_type: str
    confidence_score: float
    indicators: list[str] = []
    recommendations: list[str] = []
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


class MaintenanceAlert(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    room_id: str
    equipment_type: str
    severity: str
    prediction: str
    indicators: list[str] = []
    recommended_action: str
    estimated_failure_days: int = 0
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


async def create_predictive_maintenance_task(
    tenant_id: str, room_id: str, room_number: str, title: str, severity: str, alert_id: str
) -> None:
    try:
        await db.maintenance_tasks.insert_one({
            'id': uuid.uuid4().hex,
            'tenant_id': tenant_id,
            'room_id': room_id,
            'room_number': room_number,
            'title': title,
            'severity': severity,
            'source_alert_id': alert_id,
            'status': 'pending',
            'source': 'predictive_ai',
            'created_at': datetime.now(UTC).isoformat(),
        })
    except Exception:
        logger.exception('[ai] failed to create predictive maintenance task')


def distribute_tasks(rooms: list[dict], staff: list[dict], task_type: str) -> list[dict]:
    """Round-robin task distribution across staff members."""
    if not staff:
        return []
    minutes_per_task = 30 if task_type == 'checkout' else 20
    out = []
    for idx, room in enumerate(rooms):
        member = staff[idx % len(staff)]
        out.append({
            'staff_id': member.get('id') or member.get('staff_id'),
            'staff_name': member.get('name') or member.get('staff_name') or 'Staff',
            'task': {
                'room_id': room.get('id') or room.get('room_id'),
                'type': task_type,
                'priority': 'high' if task_type == 'checkout' else 'normal',
                'estimated_minutes': minutes_per_task,
            },
            'estimated_minutes': minutes_per_task,
        })
    return out


def generate_scheduling_recommendations(capacity_pct: float, staff_count: int, total_rooms: int) -> list[str]:
    recs = []
    if capacity_pct >= 110:
        recs.append('Schedule additional housekeeping staff or extend shifts.')
    elif capacity_pct >= 90:
        recs.append('Capacity is tight — monitor task completion closely.')
    else:
        recs.append('Workload is healthy.')
    if staff_count and total_rooms / max(staff_count, 1) > 18:
        recs.append('Consider rebalancing room-to-staff ratio.')
    return recs


def get_tier_benefits(tier: str) -> list[str]:
    matrix = {
        'silver': ['Welcome drink', 'Late checkout 1h'],
        'gold': ['Room upgrade subject to availability', 'Late checkout 2h', '10% F&B discount'],
        'platinum': ['Guaranteed upgrade', 'Late checkout 4h', '20% F&B discount', 'Lounge access'],
    }
    return matrix.get((tier or '').lower(), [])


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator








# ============= AI DYNAMIC PRICING (MARKET LEADER FEATURE) =============







# ============= WHATSAPP BUSINESS INTEGRATION =============














# ============= HOUSEKEEPING AI PREDICTIONS =============







# ============= PREDICTIVE ANALYTICS (GAME-CHANGER #2) =============










# ============= SOCIAL MEDIA COMMAND CENTER (GAME-CHANGER #3) =============










# ============= REVENUE AUTOPILOT (GAME-CHANGER #4) =============










# ============= GUEST DNA PROFILE (GAME-CHANGER #5) =============




# ============= DYNAMIC STAFFING AI (GAME-CHANGER #6) =============



















# ============= DELUXE+ ENTERPRISE FEATURES =============





# ============= MAINTENANCE WORK ORDERS =============













# ============= LOYALTY PROGRAM ENHANCEMENTS =============

















# ============= AI HOUSEKEEPING SCHEDULER =============

































# ============= MONITORING & LOGGING ENDPOINTS =============





# ============= NEW ENHANCEMENTS: OTA, GUEST PROFILE, HK MOBILE, RMS, MESSAGING, POS =============

# ===== 1. OTA RESERVATION DETAILS ENHANCEMENTS =====

# Extra charges model
# Multi-room reservation tracking

router = APIRouter(prefix="/api", tags=["AI / ML"])


# ── POST /ai/chat ──
@router.post("/ai/chat")
async def ai_chat(
    message_data: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("ai_chatbot")),
):
    """AI-powered hotel assistant chatbot with real data access"""
    user_message = message_data.get('message', '').strip()
    if not user_message:
        return {'response': 'Lütfen bir mesaj yazın.'}

    try:
        from domains.ai.service import get_ai_service
        ai_svc = get_ai_service()

        if not ai_svc.llm_enabled:
            raise RuntimeError("LLM backend not available")

        # Gather hotel context
        tenant = await db.tenants.find_one({"id": current_user.tenant_id})
        hotel_name = tenant.get('property_name', 'Otel') if tenant else 'Otel'

        rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}).to_list(None)
        all_bookings = await db.bookings.find({
            "tenant_id": current_user.tenant_id
        }).to_list(None)
        total_rooms = len(rooms)
        occupied = len([b for b in all_bookings if b.get('status') == 'checked_in'])
        occupancy = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0

        # ── Detect intent and gather relevant data ──
        msg_lower = user_message.lower()
        data_context = ""

        # Helper: format date safely
        def fmt_date(val):
            if not val:
                return "-"
            if isinstance(val, str):
                return val[:10]
            if hasattr(val, 'strftime'):
                return val.strftime('%Y-%m-%d')
            return str(val)

        # ── FOLIO INTENT ──
        if any(w in msg_lower for w in ['folio', 'folyo', 'folyosu', 'hesap', 'hesabı', 'harcama', 'harcamaları']):
            # Try to extract guest name from message
            guest_name_hint = None
            words = user_message.split()
            # Look for capitalized words that could be names
            for i, w in enumerate(words):
                if w[0].isupper() and w.lower() not in ['folio', 'folyo', 'hesap', 'getir', 'göster', 'bak', 'listele', 'misafir', 'müşteri']:
                    if guest_name_hint:
                        guest_name_hint += " " + w
                    else:
                        guest_name_hint = w

            folios_found = []
            if guest_name_hint:
                from security.query_safety import safe_search_term
                _gnh = safe_search_term(guest_name_hint)
                # Search guests by name - try multiple fields
                guests = await db.guests.find({
                    "tenant_id": current_user.tenant_id,
                    "$or": [
                        {"first_name": {"$regex": _gnh or "", "$options": "i"}},
                        {"last_name": {"$regex": _gnh or "", "$options": "i"}}
                    ]
                }).to_list(10) if _gnh else []

                guest_ids = [g['id'] for g in guests]

                # Also search folios directly by guest_name field
                folios_by_name = await db.folios.find({
                    "tenant_id": current_user.tenant_id,
                    "guest_name": {"$regex": _gnh or "", "$options": "i"}
                }).to_list(20) if _gnh else []

                # Search folios by guest_id
                folios_by_id = []
                if guest_ids:
                    folios_by_id = await db.folios.find({
                        "tenant_id": current_user.tenant_id,
                        "guest_id": {"$in": guest_ids}
                    }).to_list(20)

                # Merge and deduplicate
                seen_ids = set()
                all_folios = []
                for f in folios_by_id + folios_by_name:
                    if f['id'] not in seen_ids:
                        seen_ids.add(f['id'])
                        all_folios.append(f)

                for f in all_folios:
                    charges = await db.folio_charges.find({
                        "folio_id": f['id'], "voided": {"$ne": True}
                    }).to_list(50)

                    charge_lines = []
                    total = 0
                    for ch in charges:
                        amt = ch.get('total', ch.get('amount', 0))
                        total += amt
                        charge_lines.append(f"  - {ch.get('description','')}: {amt:.2f} TL")

                    # Get booking info
                    booking = await db.bookings.find_one({"id": f.get('booking_id')})
                    guest = next((g for g in guests if g['id'] == f.get('guest_id')), None)
                    guest_full = f"{guest.get('first_name','')} {guest.get('last_name','')}" if guest else f.get('guest_name', 'Bilinmiyor')

                    folio_info = (
                        f"Folio #{f.get('folio_number','')}\n"
                        f"  Misafir: {guest_full}\n"
                        f"  Durum: {'Açık (aktif)' if f.get('status') == 'open' else 'Kapalı (geçmiş)'}\n"
                    )
                    if booking:
                        folio_info += (
                            f"  Oda: {booking.get('room_number','')}\n"
                            f"  Giriş: {fmt_date(booking.get('check_in'))}\n"
                            f"  Çıkış: {fmt_date(booking.get('check_out'))}\n"
                        )
                    folio_info += "  Harcamalar:\n" + "\n".join(charge_lines) if charge_lines else "  Harcama yok"
                    folio_info += f"\n  TOPLAM: {total:.2f} TL"
                    folios_found.append(folio_info)

            if not folios_found:
                # If no name provided or no match, list all open folios
                open_folios = await db.folios.find({
                    "tenant_id": current_user.tenant_id,
                    "status": "open"
                }).to_list(10)

                for f in open_folios:
                    charges = await db.folio_charges.find({
                        "folio_id": f['id'], "voided": {"$ne": True}
                    }).to_list(50)
                    total = sum(ch.get('total', ch.get('amount', 0)) for ch in charges)
                    charge_summary = ", ".join(ch.get('description','') for ch in charges[:5])

                    booking = await db.bookings.find_one({"id": f.get('booking_id')})
                    folios_found.append(
                        f"Folio #{f.get('folio_number','')} | {f.get('guest_name','Bilinmiyor')} | "
                        f"Oda {booking.get('room_number','') if booking else '-'} | "
                        f"Toplam: {total:.2f} TL | Kalemler: {charge_summary}"
                    )

            if folios_found:
                count_label = f"({len(folios_found)} adet bulundu - KULLANICIYA HANGİSİNİ İSTEDİĞİNİ SOR)" if len(folios_found) > 1 else "(1 adet)"
                data_context = f"\n\n## VERİTABANINDAN GELEN FOLİO VERİLERİ {count_label}:\n" + "\n\n".join(folios_found)
            else:
                data_context = "\n\nVeritabanında eşleşen folio bulunamadı."

        # ── RESERVATION INTENT ──
        elif any(w in msg_lower for w in ['rezervasyon', 'booking', 'geçmiş', 'gelecek', 'bugün', 'yarın', 'misafir listesi', 'kimler var', 'kimler gelecek']):
            datetime.now(UTC).strftime('%Y-%m-%d')

            if any(w in msg_lower for w in ['geçmiş', 'önceki', 'eski', 'tamamlanan']):
                # Past reservations
                past = [b for b in all_bookings if b.get('status') == 'checked_out']
                past.sort(key=lambda x: x.get('check_out', ''), reverse=True)
                lines = []
                for b in past[:10]:
                    lines.append(
                        f"- {b.get('guest_name','?')} | Oda {b.get('room_number','-')} | "
                        f"{fmt_date(b.get('check_in'))} → {fmt_date(b.get('check_out'))} | "
                        f"Tutar: {b.get('total_amount',0):.0f} TL | Durum: Çıkış yapıldı"
                    )
                data_context = f"\n\n## GEÇMİŞ REZERVASYONLAR ({len(past)} adet):\n" + "\n".join(lines) if lines else "\nGeçmiş rezervasyon bulunamadı."

            elif any(w in msg_lower for w in ['gelecek', 'yaklaşan', 'planlanan', 'gelecek hafta', 'kimler gelecek']):
                # Future reservations
                future = [b for b in all_bookings if b.get('status') == 'confirmed']
                future.sort(key=lambda x: x.get('check_in', ''))
                lines = []
                for b in future[:10]:
                    lines.append(
                        f"- {b.get('guest_name','?')} | Oda {b.get('room_number','-')} ({b.get('room_type','')}) | "
                        f"{fmt_date(b.get('check_in'))} → {fmt_date(b.get('check_out'))} | "
                        f"Gecelik: {b.get('rate_per_night',0):.0f} TL | Toplam: {b.get('total_amount',0):.0f} TL"
                    )
                data_context = f"\n\n## GELECEK REZERVASYONLAR ({len(future)} adet):\n" + "\n".join(lines) if lines else "\nGelecek rezervasyon bulunamadı."

            elif any(w in msg_lower for w in ['bugün', 'şu an', 'aktif', 'mevcut', 'kimler var', 'otelde kim']):
                # Current guests (checked in)
                current = [b for b in all_bookings if b.get('status') == 'checked_in']
                lines = []
                for b in current:
                    lines.append(
                        f"- {b.get('guest_name','?')} | Oda {b.get('room_number','-')} ({b.get('room_type','')}) | "
                        f"{fmt_date(b.get('check_in'))} → {fmt_date(b.get('check_out'))} | "
                        f"Gecelik: {b.get('rate_per_night',0):.0f} TL"
                    )
                data_context = f"\n\n## ŞU AN OTELDE OLAN MİSAFİRLER ({len(current)} kişi):\n" + "\n".join(lines) if lines else "\nŞu an otelde misafir yok."

            else:
                # Search by guest name if mentioned
                guest_name_hint = None
                words = user_message.split()
                for w in words:
                    if w[0].isupper() and w.lower() not in ['rezervasyon', 'booking', 'getir', 'göster', 'bak', 'listele', 'misafir']:
                        guest_name_hint = w
                        break

                if guest_name_hint:
                    matched = [b for b in all_bookings if guest_name_hint.lower() in (b.get('guest_name','') or '').lower()]
                    lines = []
                    for b in matched:
                        lines.append(
                            f"- {b.get('guest_name','?')} | Oda {b.get('room_number','-')} | "
                            f"{fmt_date(b.get('check_in'))} → {fmt_date(b.get('check_out'))} | "
                            f"Durum: {b.get('status','')} | Tutar: {b.get('total_amount',0):.0f} TL"
                        )
                    count_note = f" ({len(matched)} adet - BİRDEN FAZLA VARSA KULLANICIYA HANGİSİNİ İSTEDİĞİNİ SOR)" if len(matched) > 1 else ""
                    data_context = f"\n\n## '{guest_name_hint}' İÇİN REZERVASYONLAR{count_note}:\n" + "\n".join(lines) if lines else f"\n'{guest_name_hint}' adına rezervasyon bulunamadı."
                else:
                    # Show summary of all
                    checked_in = len([b for b in all_bookings if b.get('status') == 'checked_in'])
                    confirmed = len([b for b in all_bookings if b.get('status') == 'confirmed'])
                    checked_out = len([b for b in all_bookings if b.get('status') == 'checked_out'])
                    data_context = (
                        f"\n\n## REZERVASYON ÖZETİ:\n"
                        f"- Otelde: {checked_in} misafir\n"
                        f"- Gelecek: {confirmed} onaylı rezervasyon\n"
                        f"- Geçmiş: {checked_out} tamamlanan\n"
                        f"- Toplam: {len(all_bookings)} rezervasyon"
                    )

        # ── GUEST SEARCH INTENT ──
        elif any(w in msg_lower for w in ['misafir', 'müşteri', 'konuk', 'guest']):
            all_guests = await db.guests.find({"tenant_id": current_user.tenant_id}).to_list(50)

            # Check if specific name is asked
            guest_name_hint = None
            words = user_message.split()
            for w in words:
                if len(w) > 2 and w[0].isupper() and w.lower() not in ['misafir', 'müşteri', 'konuk', 'guest', 'bilgi', 'göster', 'getir', 'listele', 'kimdir']:
                    guest_name_hint = w
                    break

            if guest_name_hint:
                matched = [g for g in all_guests if guest_name_hint.lower() in f"{g.get('first_name','')} {g.get('last_name','')}".lower()]
                if matched:
                    lines = []
                    for g in matched:
                        name = f"{g.get('first_name','')} {g.get('last_name','')}"
                        lines.append(
                            f"- {name} | {g.get('email','')} | {g.get('phone','')}\n"
                            f"  Uyruk: {g.get('nationality','-')} | Sadakat: {g.get('loyalty_tier','-')} | "
                            f"Toplam konaklama: {g.get('total_stays',0)} | Harcama: {g.get('total_spend',0):.0f} TL"
                        )
                    data_context = "\n\n## MİSAFİR BİLGİLERİ:\n" + "\n".join(lines)
                else:
                    data_context = f"\n'{guest_name_hint}' adında misafir bulunamadı."
            else:
                lines = []
                for g in all_guests[:10]:
                    name = f"{g.get('first_name','')} {g.get('last_name','')}"
                    lines.append(f"- {name} | {g.get('loyalty_tier','-')} | {g.get('total_stays',0)} konaklama | {g.get('total_spend',0):.0f} TL")
                data_context = f"\n\n## MİSAFİR LİSTESİ ({len(all_guests)} toplam):\n" + "\n".join(lines)

        if not ai_svc.llm_enabled:
            raise HTTPException(status_code=503, detail="AI servisi şu anda kullanılamıyor")

        system_msg = (
            f"Sen {hotel_name} otelinin Syroce PMS AI asistanısın. Otel yöneticilerine Türkçe olarak yardımcı oluyorsun. "
            f"Otel bilgileri: {total_rooms} oda, şu an doluluk %{occupancy}, "
            f"{len(all_bookings)} toplam rezervasyon var. "
            "Sorulara kısa, net ve profesyonel yanıtlar ver. "
            "Veritabanından gelen gerçek verileri olduğu gibi kullanıcıya sun. "
            "Folio, rezervasyon, misafir verileri sorulduğunda aşağıdaki VERİTABANI VERİLERİ bölümünden yanıtla. "
            "Uygulama içi navigasyon sorularına kesin ve doğru yanıt ver. "
            "Yanıtlarını 300 kelimeyi geçmeyecek şekilde tut.\n\n"
            "## ÇOKLU SONUÇ KURALI (ÇOK ÖNEMLİ):\n"
            "Bir misafir adına birden fazla folio, rezervasyon veya kayıt bulunduğunda:\n"
            "1. Tüm sonuçları KISA bir özet halinde listele (folio no, oda, tarih, durum, tutar).\n"
            "2. Ardından kullanıcıya 'Hangisinin detayını görmek istersiniz?' diye sor.\n"
            "3. Ayırt edici bilgiler sun: tarih aralığı, oda numarası, folio numarası, açık/kapalı durumu.\n"
            "4. Eğer biri 'açık' (aktif) diğeri 'kapalı' (geçmiş) ise bunu özellikle vurgula.\n"
            "5. Kullanıcı spesifik bir tarih, oda veya folio numarası belirtmişse direkt o sonucu göster.\n"
            "Örnek: 'Ahmet Yılmaz adına 2 folio bulundu:\n"
            "1. F-2026-00005 | Oda 101 | 13-16 Ocak | Kapalı | 1,593 TL\n"
            "2. F-2026-00008 | Oda 108 | 12-15 Şubat | Açık | 1,805 TL\n"
            "Hangisinin detayını görmek istersiniz?'\n\n"
            "## UYGULAMA YAPISI VE NAVIGASYON HARITASI\n"
            "Syroce PMS uygulamasının menü yapısı (üst navigasyon çubuğundaki sıralama):\n\n"
            "### TEMEL MODÜLLER (Basic Plan):\n"
            "- **Dashboard** → Ana sayfa, günlük brifing, doluluk özeti, grafikler\n"
            "- **Takvim** → Rezervasyon takvimi, oda müsaitlik görünümü\n"
            "- **PMS** → Oda yönetimi, misafir listesi, check-in/check-out, ön büro işlemleri\n"
            "- **Raporlar** → Temel raporlar (doluluk, gelir, misafir istatistikleri)\n"
            "- **Ayarlar** → Otel bilgileri, kullanıcı yönetimi, abonelik, ekip yönetimi\n\n"
            "### PROFESYONEL MODÜLLER (Professional Plan):\n"
            "- **Fatura & Finans** → Fatura oluşturma, ödeme takibi, folio yönetimi\n"
            "- **Maliyet** → Maliyet analizi, departman bazlı harcamalar\n"
            "- **Channel Manager** → OTA kanal yönetimi (Booking.com, Expedia vb.), fiyat senkronizasyonu\n"
            "- **Gelişmiş Raporlar** → Detaylı analitik raporlar, departman performansı, RevPAR, ADR, gelir analizi\n\n"
            "### KURUMSAL MODÜLLER (Enterprise Plan):\n"
            "- **Revenue (RMS)** → Gelir yönetimi, dinamik fiyatlandırma, talep tahmini\n"
            "- **AI Modülleri** → AI Hub sayfası. İçinde 8 AI alt modülü var:\n"
            "  - AI Overview → AI brifing, metrikler, fiyat önerisi\n"
            "  - AI Chatbot → Bu asistan (şu an konuştuğumuz)\n"
            "  - AI Modüller sekmesi → Aşağıdaki 8 modülü içerir, tıklandığında aynı sayfa içinde açılır:\n"
            "    1. AI-Powered PMS: Yapay zeka destekli mülk yönetim sistemi\n"
            "    2. AI Chatbot: 24/7 AI destekli misafir asistanı\n"
            "    3. WhatsApp Concierge: AI destekli WhatsApp misafir hizmetleri\n"
            "    4. Dynamic Pricing: AI fiyatlandırma optimizasyonu, rakip analizi\n"
            "    5. Predictive Analytics: No-show risk tahmini, 30 günlük talep tahmini\n"
            "    6. Reputation Center: Online itibar yönetimi (Tripadvisor, Google, Booking.com, Expedia puanları)\n"
            "    7. Revenue Autopilot: Otomatik gelir yönetimi (Full Auto/Supervised/Advisory modları)\n"
            "    8. Social Media Radar: Sosyal medya takibi, mention analizi, kriz uyarıları\n\n"
            "### DİĞER ÖZEL SAYFALAR:\n"
            "- **Housekeeping** → Kat hizmetleri, oda temizlik durumu\n"
            "- **Grup Rezervasyonlar** → Grup satışları ve blok rezervasyonlar\n"
            "- **E-Fatura** → Elektronik fatura yönetimi\n"
            "- **VIP Yönetimi** → VIP misafir takibi\n"
            "- **Sadakat Programı** → Misafir sadakat sistemi\n"
            "- **Spa & Wellness** → Spa randevu ve hizmet yönetimi\n"
            "- **F&B (Yiyecek İçecek)** → Restoran, bar, oda servisi yönetimi\n"
            "- **İK (İnsan Kaynakları)** → Personel yönetimi\n"
            "- **Bakım** → Teknik bakım ve arıza takibi\n"
            "- **Night Audit** → Gece denetimi\n"
            "- **Mobil** → /mobile altında tüm departmanlar için mobil arayüzler\n\n"
            "### ÖNEMLİ KURALLAR:\n"
            "- 'Nerede?' türü sorularda, modülün tam konumunu ve nasıl erişileceğini açıkça belirt.\n"
            "- AI modülleri AI Hub (AI Modülleri) sayfası içindeki AI Modüller sekmesinde yer alır.\n"
            "- Gelişmiş Raporlar üst menüde ayrı bir buton olarak bulunur.\n"
            "- Abonelik planına göre bazı modüller görünmeyebilir.\n"
        )

        # Append data context to the user message so LLM can use real data
        enriched_message = user_message
        if data_context:
            enriched_message = user_message + data_context

        chat = ai_svc._create_chat(system_message=system_msg)
        response_text = await chat.send_message(enriched_message)

        return {'response': response_text}
    except Exception as exc:
        logger.info(f"AI chat error: {exc}")
        # Fallback to keyword-based responses with accurate app navigation info
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ['merhaba', 'selam', 'hey']):
            return {'response': 'Merhaba! Ben Syroce AI asistanınızım. Uygulama navigasyonu, otel operasyonları, doluluk, rezervasyon gibi konularda size yardımcı olabilirim. Ne sormak istersiniz?'}
        elif any(w in msg_lower for w in ['nerede', 'nasıl bulurum', 'nasıl giderim', 'hangi menü', 'hangi sayfa']):
            if any(w in msg_lower for w in ['ai', 'yapay zeka', 'chatbot', 'asistan']):
                return {'response': 'AI modülleri üst menüdeki "AI Modülleri" butonundan erişebilirsiniz. AI Hub sayfasında 3 sekme var: AI Overview (brifing ve metrikler), AI Chatbot (bu asistan), AI Modüller (8 AI alt modülü: AI-Powered PMS, AI Chatbot, WhatsApp Concierge, Dynamic Pricing, Predictive Analytics, Reputation Center, Revenue Autopilot, Social Media Radar). Tüm modüller aynı sayfa içinde inline açılır.'}
            elif any(w in msg_lower for w in ['rapor', 'report', 'gelişmiş']):
                return {'response': 'Raporlar iki yerde bulunur:\n1. **Raporlar** (üst menü) → Temel raporlar: doluluk, gelir, misafir istatistikleri\n2. **Gelişmiş Raporlar** (üst menü, ayrı buton) → Detaylı analitik: departman performansı, RevPAR, ADR, gelir analizi\n\nGelişmiş Raporlar Professional ve Enterprise planlarda kullanılabilir.'}
            elif any(w in msg_lower for w in ['fatura', 'finans', 'ödeme']):
                return {'response': 'Fatura ve finans işlemleri üst menüdeki "Fatura & Finans" butonundan erişebilirsiniz. Bu modülde fatura oluşturma, ödeme takibi ve folio yönetimi yapabilirsiniz. E-Fatura için ayrıca /efatura sayfası mevcuttur.'}
            elif any(w in msg_lower for w in ['kanal', 'channel', 'ota', 'booking.com', 'expedia']):
                return {'response': 'OTA kanal yönetimi üst menüdeki "Channel Manager" butonundan erişebilirsiniz. Bu modülde Booking.com, Expedia gibi kanallara fiyat ve müsaitlik senkronizasyonu yapabilirsiniz.'}
            elif any(w in msg_lower for w in ['revenue', 'rms', 'gelir yönetimi']):
                return {'response': 'Gelir yönetimi (RMS) üst menüdeki "Revenue (RMS)" butonundan erişebilirsiniz. Dinamik fiyatlandırma ve talep tahmini bu modüldedir. AI destekli fiyatlandırma için AI Modülleri → Dynamic Pricing alt modülünü kullanabilirsiniz.'}
            elif any(w in msg_lower for w in ['pms', 'oda', 'check-in', 'check-out', 'ön büro']):
                return {'response': 'PMS modülüne üst menüdeki "PMS" butonundan erişebilirsiniz. Oda yönetimi, misafir listesi, check-in/check-out ve ön büro işlemleri bu modüldedir. Takvim görünümü için "Takvim" butonunu kullanın.'}
            elif any(w in msg_lower for w in ['maliyet', 'cost', 'harcama']):
                return {'response': 'Maliyet yönetimi üst menüdeki "Maliyet" butonundan erişebilirsiniz. Departman bazlı harcama analizi ve maliyet takibi bu modüldedir.'}
            elif any(w in msg_lower for w in ['ayar', 'setting', 'profil', 'ekip', 'kullanıcı']):
                return {'response': 'Ayarlar üst menüdeki "Ayarlar" butonundan erişebilirsiniz. Otel bilgileri, kullanıcı yönetimi, ekip üyeleri, abonelik planı ve genel tercihler bu sayfadadır.'}
            else:
                return {'response': 'Uygulamada başlıca menüler: Dashboard, Takvim, PMS, Raporlar, Ayarlar (Temel). Fatura & Finans, Maliyet, Channel Manager, Gelişmiş Raporlar (Profesyonel). Revenue (RMS), AI Modülleri (Enterprise). Hangi sayfayı arıyorsunuz?'}
        elif any(w in msg_lower for w in ['rezervasyon', 'booking', 'oda ayırt']):
            return {'response': 'Rezervasyon işlemleri için:\n- **Takvim** → Oda müsaitlik görünümü ve yeni rezervasyon oluşturma\n- **PMS** → Mevcut rezervasyonları yönetme, check-in/check-out\nHer iki modüle de üst menüden erişebilirsiniz.'}
        elif any(w in msg_lower for w in ['doluluk', 'occupancy', 'oda durumu']):
            return {'response': 'Anlık doluluk bilgisi **Dashboard** sayfasında görünür. Detaylı doluluk raporları **Raporlar** ve **Gelişmiş Raporlar** bölümlerinde mevcuttur. AI destekli doluluk tahmini için AI Modülleri → Predictive Analytics kullanabilirsiniz.'}
        elif any(w in msg_lower for w in ['fiyat', 'pricing', 'ücret', 'tarife']):
            return {'response': 'Fiyat yönetimi için:\n- **Revenue (RMS)** → Gelir yönetimi ve fiyatlandırma stratejileri\n- **AI Modülleri → Dynamic Pricing** → AI destekli fiyat önerileri ve rakip analizi\n- **Channel Manager** → Kanallara fiyat senkronizasyonu'}
        elif any(w in msg_lower for w in ['housekeeping', 'temizlik', 'kat hizmet']):
            return {'response': 'Kat hizmetleri için **PMS** modülü altında housekeeping bölümünü kullanabilirsiniz. Mobil erişim için /mobile/housekeeping adresini kullanın. AI destekli housekeeping planlaması AI Modülleri → AI-Powered PMS içindedir.'}
        else:
            return {'response': 'Bu konuda yardımcı olabilirim. Uygulama içi navigasyon (hangi modül nerede), otel operasyonları (doluluk, fiyat, rezervasyon) veya AI özellikleri hakkında sorabilirsiniz. Daha spesifik bir soru sormayı deneyin.'}
# ── GET /ai/sentiment/{guest_id} ──
@router.get("/ai/sentiment/{guest_id}")
async def get_sentiment(guest_id: str, current_user: User = Depends(get_current_user)):
    reviews = await db.reviews.find({'guest_id': guest_id}, {'_id': 0, 'rating': 1}).to_list(100)
    avg = sum([r.get('rating', 3) for r in reviews]) / len(reviews) if reviews else 3
    return {
        'guest_id': guest_id,
        'sentiment': 'positive' if avg >= 4 else 'neutral' if avg >= 3 else 'negative',
        'avg_rating': round(avg, 2),
        'total_reviews': len(reviews)
    }
# ── GET /ai/activity-log ──
@router.get("/ai/activity-log")
async def get_ai_activity_log(
    limit: int = 50,
    activity_type: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get AI activity log for dashboard visualization"""
    query = {'tenant_id': current_user.tenant_id}
    if activity_type:
        query['type'] = activity_type

    activities = await db.ai_activity_log.find(
        query,
        {'_id': 0}
    ).sort('timestamp', -1).limit(limit).to_list(limit)

    # Calculate stats
    total = await db.ai_activity_log.count_documents({'tenant_id': current_user.tenant_id})
    successful = await db.ai_activity_log.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'success'
    })

    return {
        'activities': activities,
        'stats': {
            'total': total,
            'successful': successful,
            'failed': total - successful
        }
    }
# ── POST /ai/log-activity + POST /feedback/ai-sentiment-analysis ──
@router.post("/ai/log-activity")


# ============= IoT SENSOR ALERTS → MAINTENANCE BRIDGE =============



@router.post("/feedback/ai-sentiment-analysis")
async def analyze_review_sentiment_ai(
    review_text: str,
    source: str = "manual",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """
    AI-powered sentiment analysis for reviews
    - Overall sentiment (positive/neutral/negative)
    - Department-specific insights
    - Key topics extraction
    """
    # In production, integrate with:
    # - OpenAI GPT-4
    # - Google Cloud Natural Language API
    # - Azure Text Analytics

    # Simulated AI analysis
    review_lower = review_text.lower()

    # Simple sentiment detection
    positive_words = ['great', 'excellent', 'amazing', 'wonderful', 'perfect', 'love', 'best', 'fantastic']
    negative_words = ['bad', 'terrible', 'awful', 'poor', 'worst', 'dirty', 'rude', 'disappointed']

    positive_count = sum(1 for word in positive_words if word in review_lower)
    negative_count = sum(1 for word in negative_words if word in review_lower)

    if positive_count > negative_count:
        sentiment = 'positive'
        sentiment_score = 0.8
    elif negative_count > positive_count:
        sentiment = 'negative'
        sentiment_score = 0.2
    else:
        sentiment = 'neutral'
        sentiment_score = 0.5

    # Department detection
    departments_mentioned = []
    if any(word in review_lower for word in ['room', 'bed', 'clean', 'housekeeping']):
        departments_mentioned.append('housekeeping')
    if any(word in review_lower for word in ['reception', 'check-in', 'front desk', 'staff']):
        departments_mentioned.append('front_desk')
    if any(word in review_lower for word in ['food', 'restaurant', 'breakfast', 'dinner']):
        departments_mentioned.append('fnb')
    if any(word in review_lower for word in ['spa', 'massage', 'wellness']):
        departments_mentioned.append('spa')

    # Key topics (simulated)
    topics = ['service', 'cleanliness'] if sentiment == 'positive' else ['maintenance', 'noise']

    return {
        'review_text': review_text,
        'sentiment': sentiment,
        'sentiment_score': sentiment_score,
        'departments_mentioned': departments_mentioned,
        'key_topics': topics,
        'ai_summary': f"Review expresses {sentiment} sentiment about {', '.join(departments_mentioned) if departments_mentioned else 'general experience'}",
        'note': 'In production, use OpenAI GPT-4 or Google NLP for advanced analysis'
    }
