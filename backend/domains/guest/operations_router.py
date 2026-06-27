"""
Guest / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import (
    generate_time_based_qr_token,
    get_current_user,
    security,
)
from models.enums import UserRole
from models.schemas import LoyaltyProgram, LoyaltyProgramCreate, LoyaltyTransaction, LoyaltyTransactionCreate, RoomService, RoomServiceCreate, User
from modules.guest_journey import feedback_reporting_service as feedback_report
from modules.pms_core.role_permission_service import require_module as require_module_v100  # v100 DW
from modules.pms_core.role_permission_service import (
    require_op,  # v96 DW
    require_role,
)

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["Guest / Operations"])


from domains.guest.schemas import (  # noqa: E402
    CleaningRequestCreate,
    GuestPreference,
    GuestTag,
    MinimumStockAlertRequest,
    RedeemPointsRequest,
)


@router.post("/loyalty/points")
async def add_points(data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    await db.loyalty_transactions.insert_one({
        'id': str(uuid.uuid4()), 'guest_id': data['guest_id'],
        'points': data['points'], 'created_at': datetime.now(UTC).isoformat()
    })
    return {'success': True}


# ============= MULTI-PROPERTY MANAGEMENT =============



@router.post("/journey/log-event")
async def log_journey_event(event_data: dict, current_user: User = Depends(get_current_user)):
    """Misafir yolculuğu olayı kaydet"""
    # Flexible field mapping
    guest_id = event_data.get('guest_id') or event_data.get('user_id')
    booking_id = event_data.get('booking_id') or event_data.get('reservation_id')

    event = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'booking_id': booking_id,
        'touchpoint': event_data.get('touchpoint', 'check_in'),
        'event_type': event_data.get('event_type', 'general'),
        'description': event_data.get('description', ''),
        'occurred_at': datetime.now(UTC).isoformat()
    }
    await db.guest_journey_events.insert_one(event)
    return {'success': True, 'event_id': event['id']}



def _nps_category(score: int) -> str:
    # Tek doğruluk kaynağı: birleşik raporlama servisi.
    return feedback_report.nps_category(score)


@router.post("/nps/survey")
async def submit_nps_survey(survey_data: dict, current_user: User = Depends(get_current_user)):
    """Misafir yorumu/puanı kaydet (NPS anketi).

    Müşteri ilişkileri ekibi resepsiyon/telefon/e-posta yoluyla aldığı
    misafir geri bildirimini bu endpoint ile sisteme girer. Oda ve serbest
    metin yorum desteklenir; oda bazlı raporlama (`/nps/by-room`) bu
    veriyi kullanır.
    """
    # ÖNEMLİ: `or` kullanmak nps_score=0 değerini düşürür (falsy).
    # Anahtar varlığını kontrol et, yoksa fallback uygula.
    if 'nps_score' in survey_data and survey_data['nps_score'] is not None:
        raw_score = survey_data['nps_score']
    elif 'score' in survey_data and survey_data['score'] is not None:
        raw_score = survey_data['score']
    else:
        raise HTTPException(status_code=400, detail="Puan zorunlu (0-10)")
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Puan 0-10 arası bir tam sayı olmalı")
    if score < 0 or score > 10:
        raise HTTPException(status_code=400, detail="Puan 0-10 arası olmalı")

    guest_id = survey_data.get('guest_id') or survey_data.get('user_id')
    booking_id = survey_data.get('booking_id') or survey_data.get('reservation_id')
    room_number = (survey_data.get('room_number') or '').strip() or None
    guest_name = (survey_data.get('guest_name') or '').strip() or None
    feedback = (survey_data.get('feedback') or survey_data.get('comment') or '').strip() or None
    source = survey_data.get('source') or 'manual'  # manual | email | qr | api

    survey = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'booking_id': booking_id,
        'room_number': room_number,
        'guest_name': guest_name,
        'nps_score': score,
        'category': _nps_category(score),
        'feedback': feedback,
        'source': source,
        'recorded_by': current_user.name,
        'recorded_by_id': current_user.id,
        'responded_at': datetime.now(UTC).isoformat(),
    }
    await db.nps_surveys.insert_one(survey)
    # Kanonik modele dual-write (idempotent, en-iyi-çaba): cutover sonrası
    # /nps/* okuma yolu feedback_entries'ten beslenir.
    await feedback_report.dualwrite_canonical(feedback_report.SOURCE_NPS_SURVEY, survey)
    return {'success': True, 'survey_id': survey['id'], 'category': survey['category']}


@router.delete("/nps/survey/{survey_id}")
async def delete_nps_survey(survey_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Yanlış girilmiş bir yorumu sil (yalnızca aynı tenant)."""
    res = await db.nps_surveys.delete_one(
        {'id': survey_id, 'tenant_id': current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    # Kanonik modelden de sil (dual-delete, en-iyi-çaba) → cutover sonrası
    # silinen yorum NPS skorundan da düşer.
    await feedback_report.dualdelete_canonical(
        current_user.tenant_id, feedback_report.SOURCE_NPS_SURVEY, survey_id
    )
    return {'success': True}


def _bounded_days(days: int) -> int:
    """Anormal aralıkları engelle (1..730 gün). Tek doğruluk kaynağı: servis."""
    return feedback_report.bounded_days(days)


@router.get("/nps/score")
async def get_nps_score(days: int = 30, current_user: User = Depends(get_current_user)):
    """NPS skoru hesapla.

    Birleşik raporlama servisinin ince adaptörü. Yanıt biçimi ve hesaplanan
    sayılar legacy davranışla birebir aynıdır (yalnız NPS-uygun 0-10 kaynak).
    """
    return await feedback_report.compute_nps_score(current_user.tenant_id, days)


@router.get("/nps/recent")
async def get_recent_nps(
    days: int = 30,
    limit: int = 50,
    category: str | None = None,
    room_number: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Son misafir yorumları (kategori/oda filtreli) — servisin ince adaptörü."""
    return await feedback_report.recent_feedback(
        current_user.tenant_id, days, limit, category, room_number
    )


@router.get("/nps/by-room")
async def get_nps_by_room(
    days: int = 30,
    current_user: User = Depends(get_current_user),
):
    """Oda bazlı ortalama puan + yanıt sayısı (en kötüden iyiye sıralı).

    Müşteri ilişkilerinin "hangi odalar tekrarlanan şikayet alıyor"
    sorusuna cevap verir. Oda numarası girilmemiş yanıtlar atlanır.
    Birleşik raporlama servisinin ince adaptörü (çıktı legacy ile birebir).
    """
    return await feedback_report.by_room(current_user.tenant_id, days)


@router.post("/loyalty/earn-points")
async def earn_points(points_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
    await db.loyalty_points_transactions.insert_one({
        'id': str(uuid.uuid4()), 'guest_id': points_data['guest_id'],
        'points': points_data['points'], 'type': 'earn',
        'created_at': datetime.now(UTC).isoformat()
    })
    return {'success': True, 'message': f'{points_data["points"]} puan kazanıldı'}



@router.get("/loyalty/member/{guest_id}")
async def get_loyalty_member(guest_id: str, current_user: User = Depends(get_current_user)):
    # Bug DZ — tenant scoping (cross-tenant IDOR fix)
    member = await db.loyalty_members.find_one(
        {'guest_id': guest_id, 'tenant_id': current_user.tenant_id}, {'_id': 0}
    )
    if not member:
        member = {'guest_id': guest_id, 'total_points': 0, 'tier': 'bronze'}
    return {'member': member}



@router.get("/celebrations/upcoming")
async def get_upcoming_celebrations(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Yaklaşan kutlamalar (30 gün içinde)"""
    celebrations = await db.celebration_tracking.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    upcoming = []
    today = date.today()

    # N+1 fix: tum guest bilgilerini tek $in sorgusuyla topla
    guest_ids = list({c['guest_id'] for c in celebrations if c.get('guest_id')})
    guests_map = {}
    if guest_ids:
        # Decrypt PII — guest_email is surfaced in the celebration payload.
        from security.encrypted_lookup import decrypt_guest_doc
        async for g in db.guests.find(
            {'id': {'$in': guest_ids}},
            {'_id': 0, 'id': 1, 'name': 1, 'email': 1, 'phone': 1},
        ):
            guests_map[g['id']] = decrypt_guest_doc(g)

    for celeb in celebrations:
        # Check birthday
        if celeb.get('birthday'):
            bday = celeb['birthday']
            if isinstance(bday, str):
                bday = datetime.fromisoformat(bday).date()
            this_year_bday = bday.replace(year=today.year)
            days_until = (this_year_bday - today).days

            if 0 <= days_until <= days:
                guest = guests_map.get(celeb['guest_id'])
                if guest:
                    upcoming.append({
                        'type': 'birthday',
                        'guest_id': celeb['guest_id'],
                        'guest_name': guest.get('name'),
                        'guest_email': guest.get('email'),
                        'date': this_year_bday.isoformat(),
                        'days_until': days_until,
                        'age': today.year - bday.year
                    })

        # Check anniversary
        if celeb.get('anniversary'):
            anniv = celeb['anniversary']
            if isinstance(anniv, str):
                anniv = datetime.fromisoformat(anniv).date()
            this_year_anniv = anniv.replace(year=today.year)
            days_until = (this_year_anniv - today).days

            if 0 <= days_until <= days:
                guest = guests_map.get(celeb['guest_id'])
                if guest:
                    upcoming.append({
                        'type': 'anniversary',
                        'guest_id': celeb['guest_id'],
                        'guest_name': guest.get('name'),
                        'guest_email': guest.get('email'),
                        'date': this_year_anniv.isoformat(),
                        'days_until': days_until,
                        'years': today.year - anniv.year
                    })

    # Sort by days_until
    upcoming.sort(key=lambda x: x['days_until'])

    return {
        'upcoming_celebrations': upcoming,
        'total': len(upcoming),
        'days_range': days
    }



@router.post("/pre-arrival/send-welcome")
async def send_pre_arrival_welcome(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Pre-arrival hoşgeldin e-postası gönder"""
    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    # Get guest (decrypt PII — email is used as the welcome-email recipient).
    from security.encrypted_lookup import decrypt_guest_doc
    guest = decrypt_guest_doc(await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0}))
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")

    # Create welcome email content
    check_in_date = booking['check_in']
    if isinstance(check_in_date, str):
        check_in_date = datetime.fromisoformat(check_in_date.replace('Z', '+00:00'))

    from modules.messaging.email_service import email_service

    # Generate 6-digit confirmation code for express check-in
    confirmation_code = email_service.generate_verification_code()

    # Send email (this will use AWS SES in production)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                      color: white; padding: 30px; text-align: center; }}
            .content {{ padding: 30px; background: #f9f9f9; }}
            .code-box {{ background: white; border: 2px solid #667eea; padding: 15px;
                       text-align: center; font-size: 24px; font-weight: bold;
                       margin: 20px 0; border-radius: 8px; }}
            .info-box {{ background: white; padding: 15px; margin: 10px 0; border-left: 4px solid #667eea; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Syroce'ye Hoş Geldiniz!</h1>
                <p>Rezervasyon Onayı</p>
            </div>
            <div class="content">
                <p>Sayın {__import__('html').escape(str(guest['name'] or ''), quote=True)},</p>
                <p>Rezervasyonunuz için teşekkür ederiz. Sizi ağırlamak için sabırsızlanıyoruz!</p>

                <div class="info-box">
                    <strong>📅 Check-in Tarihi:</strong> {check_in_date.strftime('%d.%m.%Y')}<br>
                    <strong>⏰ Check-in Saati:</strong> 14:00<br>
                    <strong>🏨 Rezervasyon Kodu:</strong> {booking['id'][:8].upper()}
                </div>

                <h3>🚀 Hızlı Check-in Kodunuz:</h3>
                <div class="code-box">{confirmation_code}</div>
                <p style="color: #666; font-size: 14px;">Bu kodu resepsiyonda göstererek anında check-in yapabilirsiniz.</p>

                <h3>✅ Online Check-in Yapın</h3>
                <p>Gelişinizden önce online check-in yaparak zamandan tasarruf edin:</p>
                <ul>
                    <li>Oda tercihlerinizi belirleyin</li>
                    <li>Özel isteklerinizi iletin</li>
                    <li>Pasaport bilgilerinizi gönderin</li>
                </ul>
                <p style="text-align: center;">
                    <a href="https://syroce.com/online-checkin/{booking['id']}"
                       style="background: #667eea; color: white; padding: 15px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Online Check-in Yap
                    </a>
                </p>

                <h3>🎁 Özel Teklifler</h3>
                <p>Konaklamanızı daha özel hale getirin:</p>
                <ul>
                    <li>🛏️ Deluxe Oda Upgrade - Sadece €75</li>
                    <li>⏰ Erken Check-in (12:00) - Sadece €35</li>
                    <li>💆 Spa Paketi - %20 İndirimli</li>
                </ul>

                <p>Görüşmek üzere!<br>
                <strong>Syroce Ekibi</strong></p>
            </div>
        </div>
    </body>
    </html>
    """

    # In production, this would send via AWS SES
    logger.info(f"📧 Sending pre-arrival email to {guest['email']}")

    # Save communication record
    comm_record = {
        'id': str(uuid.uuid4()),
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id,
        'guest_id': booking['guest_id'],
        'communication_type': 'welcome_email',
        'sent_at': datetime.now(UTC).isoformat(),
        'subject': 'Syroce\'ye Hoş Geldiniz - Rezervasyon Onayı',
        'message': html_content,
        'opened': False,
        'clicked': False
    }

    await db.pre_arrival_communications.insert_one(comm_record)

    # Update booking with confirmation code
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {'express_checkin_code': confirmation_code}}
    )

    return {
        'success': True,
        'message': 'Pre-arrival hoşgeldin e-postası gönderildi',
        'email_sent_to': guest['email'],
        'confirmation_code': confirmation_code
    }



@router.get("/upsell/offers/{booking_id}")
async def get_upsell_offers(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Rezervasyon için upsell tekliflerini getir"""
    offers = await db.upsell_offers.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'pending'
    }, {'_id': 0}).to_list(100)

    return {
        'booking_id': booking_id,
        'offers': offers,
        'total': len(offers)
    }

# ============= FLASH REPORT & DAILY ANALYTICS =============

# ============= GROUP SALES MANAGEMENT =============



@router.get("/guest/bookings-old")
@cached(ttl=600, key_prefix="guest_bookings_old")  # Cache for 10 min
async def get_guest_bookings_old(
    current_user: User = Depends(get_current_user),
    _role: None = Depends(require_role(UserRole.GUEST)),
):
    if current_user.role != UserRole.GUEST:
        raise HTTPException(status_code=403, detail="Only guests can access this endpoint")

    # Dual-read: encrypted _hash_email OR legacy plaintext; tenant-scoped (IDOR).
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = await db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)},
        {'_id': 0},
    ).to_list(1000)
    guest_ids = [g['id'] for g in guest_records]

    if not guest_ids:
        return {'active_bookings': [], 'past_bookings': []}

    all_bookings = await db.bookings.find({'guest_id': {'$in': guest_ids}}, {'_id': 0}).to_list(1000)

    now = datetime.now(UTC)
    active_bookings = []
    past_bookings = []

    # N+1 fix: tum tenant + room bilgilerini tek seferde getir
    tenant_ids = list({b.get('tenant_id') for b in all_bookings if b.get('tenant_id')})
    room_ids = list({b.get('room_id') for b in all_bookings if b.get('room_id')})
    tenants_map = {}
    if tenant_ids:
        async for t in db.tenants.find({'id': {'$in': tenant_ids}}, {'_id': 0}):
            tenants_map[t['id']] = t
    rooms_map = {}
    if room_ids:
        async for r in db.rooms.find({'id': {'$in': room_ids}}, {'_id': 0}):
            rooms_map[r['id']] = r

    for booking in all_bookings:
        tenant = tenants_map.get(booking.get('tenant_id'))
        room = rooms_map.get(booking.get('room_id'))

        booking_data = {**booking, 'hotel': tenant, 'room': room}

        checkout_date = datetime.fromisoformat(booking['check_out'].replace('Z', '+00:00')) if isinstance(booking['check_out'], str) else booking['check_out']

        if checkout_date >= now and booking['status'] not in ['cancelled', 'checked_out']:
            active_bookings.append(booking_data)
        else:
            past_bookings.append(booking_data)

    return {'active_bookings': active_bookings, 'past_bookings': past_bookings}



@router.get("/guest/loyalty-old")
@cached(ttl=600, key_prefix="guest_loyalty_old")  # Cache for 10 min
async def get_guest_loyalty_old(
    current_user: User = Depends(get_current_user),
    _role: None = Depends(require_role(UserRole.GUEST)),
):
    if current_user.role != UserRole.GUEST:
        raise HTTPException(status_code=403, detail="Only guests can access this endpoint")

    # Dual-read: encrypted _hash_email OR legacy plaintext; tenant-scoped (IDOR).
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = await db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)},
        {'_id': 0},
    ).to_list(1000)
    guest_ids = [g['id'] for g in guest_records]

    if not guest_ids:
        return {'loyalty_programs': [], 'total_points': 0}

    loyalty_programs = await db.loyalty_programs.find({'guest_id': {'$in': guest_ids}}, {'_id': 0}).to_list(1000)

    enriched_programs = []
    total_points = 0

    # N+1 fix: tum tenants tek $in
    p_tenant_ids = list({p.get('tenant_id') for p in loyalty_programs if p.get('tenant_id')})
    p_tenants_map = {}
    if p_tenant_ids:
        async for t in db.tenants.find({'id': {'$in': p_tenant_ids}}, {'_id': 0}):
            p_tenants_map[t['id']] = t

    for program in loyalty_programs:
        tenant = p_tenants_map.get(program.get('tenant_id'))
        enriched_programs.append({**program, 'hotel': tenant})
        total_points += program['points']

    return {'loyalty_programs': enriched_programs, 'total_points': total_points}



@router.post("/guest/room-service")
async def create_room_service_request(request: RoomServiceCreate, current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.GUEST:
        raise HTTPException(status_code=403, detail="Only guests can create room service requests")

    booking = await db.bookings.find_one({'id': request.booking_id}, {'_id': 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Dual-read ownership guard: id must match AND email (encrypted or plaintext).
    from security.encrypted_lookup import build_guest_pii_query
    guest = await db.guests.find_one(
        {'id': booking['guest_id'], **build_guest_pii_query('email', current_user.email)}, {'_id': 0}
    )
    if not guest:
        raise HTTPException(status_code=403, detail="This booking does not belong to you")

    room_service = RoomService(
        tenant_id=booking['tenant_id'],
        booking_id=request.booking_id,
        guest_id=booking['guest_id'],
        service_type=request.service_type,
        description=request.description,
        notes=request.notes
    )

    service_dict = room_service.model_dump()
    service_dict['created_at'] = service_dict['created_at'].isoformat()
    await db.room_services.insert_one(service_dict)

    return room_service



# rbac-allow: cache-rbac — GUEST portal — oda servis isteği
@router.get("/guest/room-service/{booking_id}")
@cached(ttl=300, key_prefix="guest_room_service")  # Cache for 5 min
async def get_room_service_requests(booking_id: str, current_user: User = Depends(get_current_user)):
    services = await db.room_services.find({'booking_id': booking_id}, {'_id': 0}).to_list(1000)
    return services



# rbac-allow: cache-rbac — GUEST portal — otel listesi
@router.get("/guest/hotels")
@cached(ttl=600, key_prefix="guest_hotels")  # Cache for 10 min
async def browse_hotels(current_user: User = Depends(get_current_user)):
    hotels = await db.tenants.find({}, {'_id': 0}).to_list(1000)
    return hotels

# Continue in next message due to length...
# ============= PMS - ROOMS MANAGEMENT =============

# ============= PMS - GUESTS MANAGEMENT =============

# ============= COMPANY MANAGEMENT =============



@router.post("/loyalty/programs", response_model=LoyaltyProgram)
async def create_loyalty_program(program_data: LoyaltyProgramCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    program = LoyaltyProgram(tenant_id=current_user.tenant_id, **program_data.model_dump())
    program_dict = program.model_dump()
    program_dict['last_activity'] = program_dict['last_activity'].isoformat()
    await db.loyalty_programs.insert_one(program_dict)
    return program



# rbac-allow: cache-rbac — GUEST portal — loyalty programları
@router.get("/loyalty/programs")
@cached(ttl=600, key_prefix="loyalty_programs")  # Cache for 10 min
async def get_loyalty_programs(current_user: User = Depends(get_current_user)):
    """Get loyalty program definitions (not guest memberships)"""
    programs = await db.loyalty_programs.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return programs



@router.post("/loyalty/transactions", response_model=LoyaltyTransaction)
async def create_loyalty_transaction(transaction_data: LoyaltyTransactionCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
    transaction = LoyaltyTransaction(tenant_id=current_user.tenant_id, **transaction_data.model_dump())
    transaction_dict = transaction.model_dump()
    transaction_dict['created_at'] = transaction_dict['created_at'].isoformat()
    await db.loyalty_transactions.insert_one(transaction_dict)

    if transaction.transaction_type == 'earned':
        await db.loyalty_programs.update_one({'guest_id': transaction.guest_id, 'tenant_id': current_user.tenant_id},
                                            {'$inc': {'points': transaction.points, 'lifetime_points': transaction.points}})
    else:
        await db.loyalty_programs.update_one({'guest_id': transaction.guest_id, 'tenant_id': current_user.tenant_id},
                                            {'$inc': {'points': -transaction.points}})
    return transaction



# rbac-allow: cache-rbac — GUEST portal — guest loyalty
@router.get("/loyalty/guest/{guest_id}")
@cached(ttl=600, key_prefix="loyalty_guest")  # Cache for 10 min
async def get_guest_loyalty_by_id(guest_id: str, current_user: User = Depends(get_current_user)):
    program = await db.loyalty_programs.find_one({'guest_id': guest_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    transactions = await db.loyalty_transactions.find({'guest_id': guest_id, 'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return {'program': program, 'transactions': transactions}


@router.get("/guest/bookings/{booking_id}")
async def get_guest_booking_detail(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Tek bir rezervasyonun detayı (SelfCheckin / DigitalKey sayfaları için).

    Multi-tenant guest scope: kullanıcının e-postasıyla eşleşen TÜM tenant'lardaki
    guest kayıtları taranır; talep edilen booking bunlardan birine aitse döner.
    Aksi halde 404. Misafir başkasının rezervasyonunu okuyamaz.

    Yanıt SelfCheckin.jsx'in beklediği şekildedir:
    {id, check_in, check_out, room_type, room_number, guests_count,
     status, hotel:{...}, guest:{email, phone, name}}
    """
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = []
    async for guest in db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ):
        guest_records.append(guest)

    guest_ids = [g['id'] for g in guest_records]

    booking = await db.bookings.find_one({
        'id': booking_id,
        'guest_id': {'$in': guest_ids}
    }, {'_id': 0}) if guest_ids else None

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    from security.encrypted_lookup import decrypt_guest_doc
    room = await db.rooms.find_one({'id': booking.get('room_id')}, {'_id': 0}) or {}
    guest = decrypt_guest_doc(await db.guests.find_one({'id': booking.get('guest_id')}, {'_id': 0})) or {}
    tenant = await db.tenants.find_one({'id': booking.get('tenant_id')}, {'_id': 0}) or {}

    return {
        'id': booking.get('id'),
        'tenant_id': booking.get('tenant_id'),
        'confirmation_number': booking.get('confirmation_number') or (booking.get('id') or '')[:8].upper(),
        'check_in': booking.get('check_in'),
        'check_out': booking.get('check_out'),
        'status': booking.get('status'),
        'guests_count': (booking.get('adults') or 1) + (booking.get('children') or 0),
        'adults': booking.get('adults', 1),
        'children': booking.get('children', 0),
        'total_amount': booking.get('total_amount', 0),
        'paid_amount': booking.get('paid_amount', 0),
        'room_number': room.get('room_number') or booking.get('room_number'),
        'room_type': room.get('room_type') or booking.get('room_type') or 'Standard',
        'floor': room.get('floor'),
        'hotel': {
            'id': tenant.get('id'),
            'property_name': tenant.get('property_name') or tenant.get('hotel_name') or 'Hotel',
            'hotel_name': tenant.get('hotel_name') or tenant.get('property_name') or 'Hotel',
            'address': tenant.get('address') or '',
        },
        'guest': {
            'name': guest.get('name') or current_user.name,
            'email': guest.get('email') or current_user.email,
            'phone': guest.get('phone'),
        },
    }


@router.post("/guest/self-checkin/{booking_id}")
async def guest_self_checkin(
    booking_id: str,
    checkin_data: dict = {},
    current_user: User = Depends(get_current_user)
):
    """Complete self check-in process for guest"""
    # Find booking by guest email (multi-tenant support)
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = []
    async for guest in db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ):
        guest_records.append(guest)

    guest_ids = [g['id'] for g in guest_records]

    booking = await db.bookings.find_one({
        'id': booking_id,
        'guest_id': {'$in': guest_ids}
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Update booking status
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'checked_in',
            'actual_check_in': datetime.now(UTC).isoformat(),
            'guest_info': checkin_data.get('guest_info'),
            'preferences': checkin_data.get('preferences')
        }}
    )

    # Update room status
    if booking.get('room_id'):
        await db.rooms.update_one(
            {'id': booking['room_id']},
            {'$set': {
                'status': 'occupied',
                'current_booking_id': booking_id
            }}
        )

    # Generate digital key (bound + signed token; mirrors the get/refresh path).
    digital_key = _build_digital_key({**booking, 'id': booking_id, 'tenant_id': current_user.tenant_id})

    await db.digital_keys.insert_one(digital_key)

    return {
        'message': 'Check-in successful',
        'booking_id': booking_id,
        'room_number': booking.get('room_number'),
        'digital_key': {
            'key_id': digital_key['key_id'],
            'expires_at': digital_key['expires_at']
        }
    }



# ── Digital key helpers ───────────────────────────────────────────────────────
def _parse_dt(value):
    """Best-effort parse of an ISO timestamp / datetime into an aware datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


async def _resolve_guest_owned_booking(booking_id: str, current_user: User) -> dict:
    """Resolve a booking the caller owns, tenant-scoped.

    Mirrors the ownership contract used by the self-checkin and booking-detail
    endpoints: the booking's ``guest_id`` must belong to a tenant-scoped guest
    record matching the caller's e-mail. Raises 404 (not 403) so a caller cannot
    probe for the existence of another guest's booking. Fail-closed: an empty
    guest set yields 404 rather than a global lookup.
    """
    from security.encrypted_lookup import build_guest_pii_query
    guest_ids: list[str] = []
    async for g in db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)},
        {'_id': 0, 'id': 1},
    ):
        gid = g.get('id')
        if gid:
            guest_ids.append(gid)

    booking = await db.bookings.find_one(
        {'id': booking_id, 'guest_id': {'$in': guest_ids}}, {'_id': 0}
    ) if guest_ids else None

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _key_is_usable(booking: dict) -> bool:
    """A digital key may exist only for an in-house stay that has not ended.

    Enforced server-side so a key is never returned/minted past checkout or for
    a cancelled / checked-out booking, regardless of any stale ``active`` row.
    """
    if booking.get('status') != 'checked_in':
        return False
    checkout = _parse_dt(booking.get('check_out'))
    if checkout and datetime.now(UTC) > checkout:
        return False
    return True


def _token_expiry_hours(booking: dict) -> float:
    """Cap the signed QR token lifetime to the remaining stay (<= 72h).

    A door reader that trusts the JWT ``exp`` alone must never accept a token
    past checkout, so we bind the token expiry to the time left until checkout
    (clamped to a 72h ceiling for very long stays, and a small positive floor).
    """
    checkout = _parse_dt(booking.get('check_out'))
    if not checkout:
        return 72.0
    remaining = (checkout - datetime.now(UTC)).total_seconds() / 3600.0
    return max(0.1, min(72.0, remaining))


def _build_digital_key(booking: dict) -> dict:
    """Build a fresh digital-key document bound to the booking.

    ``token`` is a JWT (signed with JWT_SECRET) embedding the booking id and an
    expiry, mirroring the mobile QR contract so a door reader can verify
    authenticity server-side instead of trusting a forgeable plaintext payload.
    The token expiry is bound to checkout so it cannot outlive the stay.
    """
    return {
        'id': str(uuid.uuid4()),
        'key_id': str(uuid.uuid4())[:8].upper(),
        'tenant_id': booking.get('tenant_id'),
        'booking_id': booking.get('id'),
        'guest_id': booking.get('guest_id'),
        'room_number': booking.get('room_number'),
        'token': generate_time_based_qr_token(
            booking.get('id'), expiry_hours=_token_expiry_hours(booking)
        ),
        'status': 'active',
        'created_at': datetime.now(UTC).isoformat(),
        'expires_at': booking.get('check_out'),
        'last_used': None,
    }


def _key_response(key: dict) -> dict:
    """Trim a stored key to the guest-facing contract the web/mobile UI needs."""
    return {
        'key_id': key.get('key_id'),
        'room_number': key.get('room_number'),
        'guest_id': key.get('guest_id'),
        'token': key.get('token'),
        'status': key.get('status'),
        'expires_at': key.get('expires_at'),
    }


@router.get("/guest/digital-key/{booking_id}")
async def get_digital_key(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get digital room key for guest (ownership + tenant + expiry enforced)."""
    booking = await _resolve_guest_owned_booking(booking_id, current_user)
    tenant_id = booking.get('tenant_id')

    key = await db.digital_keys.find_one(
        {'booking_id': booking_id, 'tenant_id': tenant_id, 'status': 'active'},
        {'_id': 0},
    )

    # Expire any stale active key once the stay has ended (checkout / cancel).
    if key and not _key_is_usable(booking):
        await db.digital_keys.update_many(
            {'booking_id': booking_id, 'tenant_id': tenant_id, 'status': 'active'},
            {'$set': {'status': 'expired'}},
        )
        key = None

    if not key:
        if not _key_is_usable(booking):
            raise HTTPException(
                status_code=404, detail="Digital key not available - booking not checked in"
            )
        key = _build_digital_key(booking)
        await db.digital_keys.insert_one(key)
    elif not key.get('token'):
        # Backfill a signed token on keys minted before token binding existed.
        token = generate_time_based_qr_token(booking_id)
        await db.digital_keys.update_one(
            {'booking_id': booking_id, 'tenant_id': tenant_id, 'status': 'active'},
            {'$set': {'token': token}},
        )
        key['token'] = token

    return _key_response(key)


@router.post("/guest/digital-key/{booking_id}/refresh")
async def refresh_digital_key(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Refresh digital key (ownership + tenant enforced; refuses ended stays)."""
    booking = await _resolve_guest_owned_booking(booking_id, current_user)
    tenant_id = booking.get('tenant_id')

    if not _key_is_usable(booking):
        raise HTTPException(
            status_code=404, detail="Digital key not available - booking not checked in"
        )

    # Deactivate previous keys for this booking (tenant-scoped).
    await db.digital_keys.update_many(
        {'booking_id': booking_id, 'tenant_id': tenant_id},
        {'$set': {'status': 'expired'}},
    )

    key = _build_digital_key(booking)
    await db.digital_keys.insert_one(key)
    return _key_response(key)



@router.get("/guest/upsell-offers/{booking_id}")
async def get_upsell_offers_v2(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get personalized upsell offers for guest"""
    # Get AI predictions
    predictions = await db.ai_upsell_predictions.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('confidence', -1).limit(10).to_list(10)

    # Get already purchased items — Bug DZ: tenant scoping
    purchased = await db.purchased_upsells.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(100)

    return {
        'offers': predictions,
        'purchased': purchased
    }



@router.post("/guest/purchase-upsell/{booking_id}")
async def purchase_upsell(
    booking_id: str,
    purchase_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Purchase an upsell offer for guest"""
    # Find booking by guest email (multi-tenant support)
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = []
    async for guest in db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ):
        guest_records.append(guest)

    guest_ids = [g['id'] for g in guest_records]

    booking = await db.bookings.find_one({
        'id': booking_id,
        'guest_id': {'$in': guest_ids}
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    purchase = {
        'id': str(uuid.uuid4()),
        'tenant_id': booking.get('tenant_id'),
        'booking_id': booking_id,
        'offer_id': purchase_data.get('offer_id'),
        'offer_name': purchase_data.get('offer_name', 'Upsell'),
        'amount': purchase_data.get('price', 0),
        'purchased_at': datetime.now(UTC).isoformat(),
        'status': 'confirmed'
    }

    await db.purchased_upsells.insert_one(purchase)

    # Post to folio if exists
    folio = await db.folios.find_one({'booking_id': booking_id, 'status': 'open'})
    if folio:
        charge = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'folio_id': folio['id'],
            'charge_type': 'upsell',
            'description': f"Upsell: {purchase_data.get('offer_type')}",
            'amount': purchase_data.get('amount'),
            'quantity': 1,
            'total': purchase_data.get('amount'),
            'posted_at': datetime.now(UTC).isoformat(),
            'voided': False
        }
        await db.folio_charges.insert_one(charge)

    return {'message': 'Purchase successful', 'purchase_id': purchase['id']}



@router.get("/guest/purchased-upsells/{booking_id}")
async def get_purchased_upsells(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get purchased upsells for a booking"""
    items = await db.purchased_upsells.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(100)

    return {'items': items}


# rbac-allow: cache-rbac — GUEST portal — guest profili
@router.get("/guests/{guest_id}/profile-enhanced")
@cached(ttl=300, key_prefix="guest_profile_enhanced")  # Cache for 5 min
async def get_guest_profile_enhanced(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get enhanced guest profile with:
    - Stay history
    - Preferences
    - Tags (VIP, Honeymoon, etc)
    - Spending pattern
    """
    from security.encrypted_lookup import decrypt_guest_doc
    guest = decrypt_guest_doc(await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    }))

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # Stay history — N+1 fix: rooms + folios tek $in sorgusuyla
    stay_history = []
    total_spent_all_time = 0
    bookings_list = await db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_out', 'checked_in']}
    }).sort('check_in', -1).limit(10).to_list(10)

    sh_room_ids = list({b.get('room_id') for b in bookings_list if b.get('room_id')})
    sh_booking_ids = [b.get('id') for b in bookings_list if b.get('id')]
    sh_rooms_map = {}
    if sh_room_ids:
        async for r in db.rooms.find({'id': {'$in': sh_room_ids}}):
            sh_rooms_map[r['id']] = r
    sh_folios_map = {}
    if sh_booking_ids:
        async for f in db.folios.find({
            'booking_id': {'$in': sh_booking_ids},
            'tenant_id': current_user.tenant_id,
            'folio_type': 'guest',
        }):
            sh_folios_map[f['booking_id']] = f

    for booking in bookings_list:
        room = sh_rooms_map.get(booking.get('room_id'))

        check_in = booking.get('check_in')
        check_out = booking.get('check_out')

        if isinstance(check_in, str):
            check_in_dt = datetime.fromisoformat(check_in[:10])
        else:
            check_in_dt = check_in

        if isinstance(check_out, str):
            check_out_dt = datetime.fromisoformat(check_out[:10])
        else:
            check_out_dt = check_out

        nights = (check_out_dt - check_in_dt).days

        folio = sh_folios_map.get(booking.get('id'))
        total_spent = folio.get('balance', 0) if folio else booking.get('total_amount', 0)
        total_spent_all_time += abs(total_spent) if folio else booking.get('total_amount', 0)

        stay_history.append({
            'booking_id': booking.get('id'),
            'check_in': check_in_dt.date().isoformat() if hasattr(check_in_dt, 'date') else str(check_in_dt),
            'check_out': check_out_dt.date().isoformat() if hasattr(check_out_dt, 'date') else str(check_out_dt),
            'room_number': room.get('room_number') if room else 'N/A',
            'nights': nights,
            'total_spent': abs(total_spent) if folio else booking.get('total_amount', 0),
            'status': booking.get('status')
        })

    # Preferences
    preferences = await db.guest_preferences.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    if not preferences:
        preferences = {
            'pillow_type': None,
            'room_temperature': None,
            'smoking': False,
            'floor_preference': None,
            'room_view': None,
            'newspaper': None,
            'extra_requests': [],
            'dietary_restrictions': [],
            'allergies': []
        }

    # Tags
    tags = []
    async for tag in db.guest_tags.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }):
        tags.append({
            'tag': tag.get('tag'),
            'color': tag.get('color'),
            'notes': tag.get('notes'),
            'added_by': tag.get('added_by'),
            'created_at': tag.get('created_at')
        })

    # Calculate lifetime value
    ltv = total_spent_all_time
    avg_spend_per_stay = ltv / len(stay_history) if stay_history else 0

    return {
        'guest_id': guest_id,
        'name': guest.get('name'),
        'email': guest.get('email'),
        'phone': guest.get('phone'),
        'vip_status': guest.get('vip_status', False),
        'loyalty_points': guest.get('loyalty_points', 0),
        'total_stays': len(stay_history),
        'lifetime_value': round(ltv, 2),
        'avg_spend_per_stay': round(avg_spend_per_stay, 2),
        'stay_history': stay_history,
        'preferences': preferences,
        'tags': tags,
        'profile_completion': _calculate_profile_completion(guest, preferences, tags)
    }


def _calculate_profile_completion(guest: dict, preferences: list | None, tags: list | None) -> int:
    """Return guest profile completion percentage (0-100)."""
    fields = ['name', 'email', 'phone', 'birth_date', 'nationality', 'preferred_language']
    filled = sum(1 for f in fields if guest.get(f))
    score = (filled / len(fields)) * 70
    if preferences:
        score += 20
    if tags:
        score += 10
    return min(100, int(round(score)))




@router.post("/guests/{guest_id}/preferences")
async def update_guest_preferences(
    guest_id: str,
    pillow_type: str | None = None,
    room_temperature: int | None = None,
    smoking: bool = False,
    floor_preference: str | None = None,
    room_view: str | None = None,
    newspaper: str | None = None,
    extra_requests: list[str] = [],
    dietary_restrictions: list[str] = [],
    allergies: list[str] = [],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
    """Update or create guest preferences"""
    pref_data = {
        'pillow_type': pillow_type,
        'room_temperature': room_temperature,
        'smoking': smoking,
        'floor_preference': floor_preference,
        'room_view': room_view,
        'newspaper': newspaper,
        'extra_requests': extra_requests,
        'dietary_restrictions': dietary_restrictions,
        'allergies': allergies,
        'updated_at': datetime.now(UTC).isoformat()
    }

    existing = await db.guest_preferences.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    if existing:
        await db.guest_preferences.update_one(
            {'guest_id': guest_id, 'tenant_id': current_user.tenant_id},
            {'$set': pref_data}
        )
    else:
        pref = GuestPreference(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            **pref_data
        )
        pref_dict = pref.model_dump()
        pref_dict['created_at'] = pref_dict['created_at'].isoformat()
        pref_dict['updated_at'] = pref_dict['updated_at'].isoformat()
        await db.guest_preferences.insert_one(pref_dict)

    return {'success': True, 'message': 'Guest preferences updated'}




@router.post("/guests/{guest_id}/tags")
async def add_guest_tag(
    guest_id: str,
    tag: str,
    color: str = "blue",
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Add a tag to guest (VIP, Honeymoon, Complainer, etc)"""
    guest_tag = GuestTag(
        tenant_id=current_user.tenant_id,
        guest_id=guest_id,
        tag=tag,
        color=color,
        added_by=current_user.name,
        notes=notes
    )

    tag_dict = guest_tag.model_dump()
    tag_dict['created_at'] = tag_dict['created_at'].isoformat()
    await db.guest_tags.insert_one(tag_dict)

    return {'success': True, 'tag_id': guest_tag.id, 'message': f'Tag "{tag}" added to guest'}


# ============= RESERVATION ENHANCEMENTS =============



@router.get("/loyalty/{guest_id}/benefits")
async def get_loyalty_benefits(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get loyalty perks and benefits
    - Late checkout
    - Free breakfast
    - Upgrade priority
    - Points balance and expiration
    """
    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    points = guest.get('loyalty_points', 0)
    total_stays = guest.get('total_stays', 0)
    total_spend = guest.get('total_spend', 0)

    # Determine tier
    if points >= 10000:
        tier = 'Platinum'
        tier_benefits = ['Late checkout (2pm)', 'Free breakfast', 'Priority upgrade', 'Welcome amenity', 'Free Wi-Fi', 'Room upgrade (subject to availability)']
    elif points >= 5000:
        tier = 'Gold'
        tier_benefits = ['Late checkout (1pm)', 'Free breakfast', 'Priority upgrade', 'Welcome amenity', 'Free Wi-Fi']
    elif points >= 1000:
        tier = 'Silver'
        tier_benefits = ['Late checkout (12pm)', 'Free breakfast', 'Free Wi-Fi']
    else:
        tier = 'Bronze'
        tier_benefits = ['Free Wi-Fi', 'Welcome drink']

    # Points to next tier
    if tier == 'Bronze':
        next_tier = 'Silver'
        points_needed = 1000 - points
    elif tier == 'Silver':
        next_tier = 'Gold'
        points_needed = 5000 - points
    elif tier == 'Gold':
        next_tier = 'Platinum'
        points_needed = 10000 - points
    else:
        next_tier = None
        points_needed = 0

    # Points expiration (1 year from last activity)
    points_expiry = (datetime.now(UTC) + timedelta(days=365)).date().isoformat()

    # Calculate Lifetime Value
    ltv = total_spend

    return {
        'guest_id': guest_id,
        'guest_name': guest.get('name'),
        'loyalty_tier': tier,
        'points_balance': points,
        'points_expiry_date': points_expiry,
        'next_tier': next_tier,
        'points_to_next_tier': points_needed if next_tier else None,
        'tier_benefits': tier_benefits,
        'total_stays': total_stays,
        'lifetime_value': round(ltv, 2),
        'member_since': guest.get('created_at')
    }




@router.post("/loyalty/{guest_id}/redeem-points")
async def redeem_loyalty_points(
    guest_id: str,
    request: RedeemPointsRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v100("frontdesk")),  # v100 DW
):
    """Redeem loyalty points"""
    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    current_points = guest.get('loyalty_points', 0)

    if current_points < request.points_to_redeem:
        raise HTTPException(status_code=400, detail="Insufficient points")

    # Update points
    new_balance = current_points - request.points_to_redeem
    await db.guests.update_one(
        {'id': guest_id},
        {'$set': {'loyalty_points': new_balance}}
    )

    # Create redemption record
    redemption = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'points_redeemed': request.points_to_redeem,
        'redemption_type': request.reward_type,
        'processed_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.loyalty_redemptions.insert_one(redemption)

    return {
        'success': True,
        'points_redeemed': request.points_to_redeem,
        'redemption_type': request.reward_type,
        'new_points_balance': new_balance,
        'redemption_id': redemption['id']
    }


# ============= PROCUREMENT ENHANCEMENTS =============



@router.get("/procurement/auto-purchase-suggestions")
async def get_auto_purchase_suggestions(
    current_user: User = Depends(get_current_user)
):
    """
    Automatic purchase suggestions based on consumption rate analysis
    - Items below reorder level
    - Predicted stock-out date
    - Recommended order quantity
    """
    suggestions = []

    # Get all inventory items
    async for item in db.inventory.find({
        'tenant_id': current_user.tenant_id
    }):
        current_stock = item.get('quantity', 0)
        reorder_level = item.get('reorder_level', 50)

        if current_stock <= reorder_level:
            # Calculate consumption rate (last 30 days)
            # In production, analyze actual usage data
            avg_daily_consumption = 5  # Simulated

            days_until_stockout = current_stock / avg_daily_consumption if avg_daily_consumption > 0 else 999

            # Recommended order quantity (30 days supply)
            recommended_qty = int(avg_daily_consumption * 30)

            suggestions.append({
                'item_id': item.get('id'),
                'item_name': item.get('name'),
                'category': item.get('category'),
                'current_stock': current_stock,
                'reorder_level': reorder_level,
                'avg_daily_consumption': avg_daily_consumption,
                'days_until_stockout': int(days_until_stockout),
                'recommended_order_qty': recommended_qty,
                'unit_cost': item.get('unit_cost', 0),
                'estimated_cost': round(recommended_qty * item.get('unit_cost', 0), 2),
                'priority': 'urgent' if days_until_stockout < 7 else 'high' if days_until_stockout < 14 else 'normal',
                'supplier': item.get('preferred_supplier')
            })

    # Sort by priority
    suggestions.sort(key=lambda x: x['days_until_stockout'])

    return {
        'total_suggestions': len(suggestions),
        'urgent_count': sum(1 for s in suggestions if s['priority'] == 'urgent'),
        'total_estimated_cost': round(sum(s['estimated_cost'] for s in suggestions), 2),
        'suggestions': suggestions
    }




@router.post("/procurement/minimum-stock-alert")
async def set_minimum_stock_alert(
    request: MinimumStockAlertRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Set minimum stock alert for an item"""
    item = await db.inventory.find_one({
        'id': request.item_id,
        'tenant_id': current_user.tenant_id
    })

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.inventory.update_one(
        {'id': request.item_id},
        {'$set': {
            'reorder_level': request.min_stock_level,
            'alert_recipients': request.alert_recipients
        }}
    )

    return {
        'success': True,
        'item_id': request.item_id,
        'min_stock_level': request.min_stock_level,
        'message': 'Minimum stock alert configured'
    }


@router.get("/guests/{guest_id}/profile-complete")
async def get_complete_guest_profile(
    guest_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get complete guest profile including history, preferences, and tags"""
    current_user = await get_current_user(credentials)

    # Get guest
    from security.encrypted_lookup import decrypt_guest_doc
    guest = decrypt_guest_doc(await db.guests.find_one({'id': guest_id, 'tenant_id': current_user.tenant_id}))
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # Get stay history (all bookings) — N+1 fix: rooms tek $in
    stay_history = []
    sh_bookings = await db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_out', 'checked_in']}
    }).sort('check_in', -1).to_list(5000)
    full_room_ids = list({b.get('room_id') for b in sh_bookings if b.get('room_id')})
    full_rooms_map = {}
    if full_room_ids:
        async for r in db.rooms.find(
            {'tenant_id': current_user.tenant_id, 'id': {'$in': full_room_ids}}
        ):
            full_rooms_map[r['id']] = r

    for booking in sh_bookings:
        try:
            room = full_rooms_map.get(booking.get('room_id'))

            # Calculate nights - handle both datetime and string
            check_in = booking.get('check_in')
            check_out = booking.get('check_out')
            nights = 0

            if isinstance(check_in, datetime) and isinstance(check_out, datetime):
                nights = (check_out - check_in).days
            elif isinstance(check_in, str) and isinstance(check_out, str):
                try:
                    check_in_dt = datetime.fromisoformat(check_in.replace('Z', '+00:00'))
                    check_out_dt = datetime.fromisoformat(check_out.replace('Z', '+00:00'))
                    nights = (check_out_dt - check_in_dt).days
                except Exception:
                    nights = 0

            stay_history.append({
                'booking_id': booking['id'],
                'check_in': check_in.isoformat() if isinstance(check_in, datetime) else str(check_in),
                'check_out': check_out.isoformat() if isinstance(check_out, datetime) else str(check_out),
                'room_number': room.get('room_number') if room else 'N/A',
                'room_type': room.get('room_type') if room else 'N/A',
                'nights': nights,
                'total_amount': booking.get('total_amount', 0),
                'status': booking['status']
            })
        except Exception as e:
            # Skip bookings that cause errors
            logger.info(f"Error processing booking {booking.get('id')}: {e}")
            continue

    # Get preferences
    preferences = await db.guest_preferences.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    # Get tags
    guest_tags_doc = await db.guest_tags.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    tags = guest_tags_doc.get('tags', []) if guest_tags_doc else []

    # Clean guest data to remove ObjectId fields
    guest_clean = {k: v for k, v in guest.items() if k != '_id'}
    preferences_clean = {k: v for k, v in (preferences or {}).items() if k != '_id'}

    return {
        'guest_id': guest_id,
        'guest': guest_clean,
        'stay_history': stay_history,
        'total_stays': len(stay_history),
        'preferences': preferences_clean,
        'tags': tags,
        'vip_status': 'vip' in tags or guest.get('vip_status', False),
        'blacklist_status': 'blacklist' in tags
    }


@router.post("/guest/request-cleaning")
async def guest_request_cleaning(
    request: CleaningRequestCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Guest requests room cleaning
    Types: regular, urgent, turndown, do_not_disturb
    """
    try:
        # Find booking - either by booking_id or current user's active booking
        if request.booking_id:
            booking = await db.bookings.find_one({
                'id': request.booking_id,
                'tenant_id': current_user.tenant_id
            }, {'_id': 0})
        else:
            booking = await db.bookings.find_one({
                'guest_id': current_user.id,
                'status': 'checked_in',
                'tenant_id': current_user.tenant_id
            }, {'_id': 0})

        if not booking:
            raise HTTPException(status_code=404, detail="No active booking found")

        # Get room info
        room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
        room_number = room.get('room_number') if room else request.room_number

        # Get guest info
        guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
        guest_name = guest.get('name') if guest else current_user.name

        # Create cleaning request
        cleaning_request_id = str(uuid.uuid4())
        cleaning_request = {
            'id': cleaning_request_id,
            'tenant_id': current_user.tenant_id,
            'booking_id': booking['id'],
            'room_id': booking['room_id'],
            'room_number': room_number,
            'guest_id': booking['guest_id'],
            'guest_name': guest_name,
            'request_type': request.type,
            'notes': request.notes or "",
            'status': 'pending',  # pending, in_progress, completed, cancelled
            'priority': 'urgent' if request.type == 'urgent' else 'normal',
            'requested_at': datetime.now(UTC).isoformat(),
            'completed_at': None,
            'assigned_to': None,
            'completed_by': None
        }

        await db.cleaning_requests.insert_one(cleaning_request)

        # Create notification for housekeeping
        await db.notifications.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'user_role': 'housekeeping',
            'title': f'Yeni Temizlik Talebi - Oda {cleaning_request["room_number"]}',
            'message': f'{cleaning_request["guest_name"]} oda temizliği talep etti',
            'type': 'cleaning_request',
            'priority': cleaning_request['priority'],
            'related_id': cleaning_request_id,
            'read': False,
            'created_at': datetime.now(UTC).isoformat()
        })

        return {
            'message': 'Temizlik talebiniz alındı',
            'request_id': cleaning_request_id,
            'room_number': cleaning_request['room_number'],
            'request_type': request.type,
            'estimated_time': 30 if request.type == 'urgent' else 120,
            'status': 'pending'
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create cleaning request: {str(e)}")


@router.get("/guest/my-cleaning-requests")
async def get_my_cleaning_requests(
    current_user: User = Depends(get_current_user)
):
    """
    Get current guest's cleaning requests
    """
    try:
        requests = await db.cleaning_requests.find({
            'guest_id': current_user.id,
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).sort('requested_at', -1).limit(10).to_list(10)

        return {
            'requests': requests,
            'count': len(requests),
            'pending_count': len([r for r in requests if r['status'] == 'pending']),
            'in_progress_count': len([r for r in requests if r['status'] == 'in_progress'])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve your cleaning requests: {str(e)}")


# ============================================================================
# FINANCIAL OVERVIEW EXPANSION - EXPENSE CATEGORIES
# ============================================================================

# ============================================================================
# 7-DAY TREND ANALYTICS
# ============================================================================


