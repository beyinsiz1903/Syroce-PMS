"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials
from typing import Optional
from datetime import datetime, timezone, timedelta
import os
import uuid
import logging

from core.database import db
from core.security import (
    get_current_user, security,
)
from core.helpers import (
    require_module,
)
from models.schemas import User

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["AI / ML"])

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
        from ai_service import get_ai_service
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
                # Search guests by name - try multiple fields
                guests = await db.guests.find({
                    "tenant_id": current_user.tenant_id,
                    "$or": [
                        {"first_name": {"$regex": guest_name_hint, "$options": "i"}},
                        {"last_name": {"$regex": guest_name_hint, "$options": "i"}}
                    ]
                }).to_list(10)
                
                guest_ids = [g['id'] for g in guests]
                
                # Also search folios directly by guest_name field
                folios_by_name = await db.folios.find({
                    "tenant_id": current_user.tenant_id,
                    "guest_name": {"$regex": guest_name_hint, "$options": "i"}
                }).to_list(20)
                
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
            datetime.now(timezone.utc).strftime('%Y-%m-%d')
            
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

        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage as LlmUserMessage
        except ImportError:
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

        session_id = f"chat_{current_user.tenant_id}_{current_user.id}"
        chat = LlmChat(
            api_key=ai_svc.api_key,
            session_id=session_id,
            system_message=system_msg
        )
        chat.with_model("openai", "gpt-4o-mini")

        llm_msg = LlmUserMessage(text=enriched_message)
        response_text = await chat.send_message(llm_msg)

        return {'response': response_text}
    except Exception as exc:
        print(f"AI chat error: {exc}")
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


# ============= AI DYNAMIC PRICING (MARKET LEADER FEATURE) =============



@router.get("/pricing/ai-recommendation")
async def get_ai_pricing_recommendation(
    room_type: Optional[str] = None,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("ai_pricing")),
):
    """AI-powered dynamic pricing recommendation"""
    try:
        # Default values when params not provided
        if not room_type:
            room_type = "standard"
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        from dynamic_pricing_engine import get_pricing_engine
        engine = get_pricing_engine(db)
        recommendation = await engine.recommend_price(
            current_user.tenant_id,
            room_type,
            target_date
        )
        return recommendation
    except Exception:
        # Fallback pricing recommendation
        rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}).to_list(None)
        bookings = await db.bookings.find({
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "checked_in"]}
        }).to_list(None)
        total_rooms = len(rooms) or 1
        occupied = len([b for b in bookings if b.get('status') == 'checked_in'])
        occupancy_rate = occupied / total_rooms

        base_price = 150
        if occupancy_rate > 0.8:
            suggested = base_price * 1.3
        elif occupancy_rate > 0.5:
            suggested = base_price * 1.1
        else:
            suggested = base_price * 0.9

        return {
            "recommended_rate": round(suggested, 2),
            "current_rate": base_price,
            "suggested_price": round(suggested, 2),
            "current_price": base_price,
            "confidence": round(0.7 + occupancy_rate * 0.2, 2),
            "reason": f"Doluluk oranı %{round(occupancy_rate*100)}, talebe göre fiyat önerisi",
            "room_type": room_type,
            "target_date": target_date,
            "source": "heuristic"
        }



@router.get("/pricing/competitor-rates")
async def get_competitor_rates(
    room_type: str,
    target_date: str,
    current_user: User = Depends(get_current_user)
):
    """Rakip otel fiyatları"""
    from dynamic_pricing_engine import get_pricing_engine
    
    engine = get_pricing_engine(db)
    rates = await engine.get_competitor_rates(target_date, room_type)
    
    return rates

# ============= WHATSAPP BUSINESS INTEGRATION =============



@router.get("/reputation/overview")
async def get_reputation_overview(current_user: User = Depends(get_current_user)):
    """Online reputation özeti"""
    from reputation_manager import get_reputation_manager
    
    manager = get_reputation_manager(db)
    overview = await manager.aggregate_reviews(current_user.tenant_id)
    
    return overview



@router.get("/reputation/trends")
async def get_reputation_trends(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Reputation trend analizi"""
    from reputation_manager import get_reputation_manager
    
    manager = get_reputation_manager(db)
    trends = await manager.get_reputation_trends(current_user.tenant_id, days)
    
    return trends



@router.post("/reputation/suggest-response")
async def suggest_review_response(
    review_data: dict,
    current_user: User = Depends(get_current_user)
):
    """AI review yanıt önerisi"""
    from reputation_manager import get_reputation_manager
    
    manager = get_reputation_manager(db)
    response = await manager.suggest_response(
        review_data['review_text'],
        review_data.get('rating', 3)
    )
    
    return {
        'suggested_response': response
    }



@router.get("/reputation/negative-alerts")
async def get_negative_review_alerts(current_user: User = Depends(get_current_user)):
    """Son 24 saatteki negatif review'lar"""
    from reputation_manager import get_reputation_manager
    
    manager = get_reputation_manager(db)
    alerts = await manager.detect_negative_reviews(current_user.tenant_id)
    
    return {
        'negative_reviews': alerts,
        'total': len(alerts),
        'requires_action': len(alerts) > 0
    }


# ============= HOUSEKEEPING AI PREDICTIONS =============



@router.post("/ai-concierge/whatsapp")
async def ai_whatsapp_concierge(
    message_data: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("ai_whatsapp")),
):
    """AI WhatsApp Concierge - Otomatik misafir hizmeti"""
    # Support both phone and guest_phone
    phone = message_data.get('phone') or message_data.get('guest_phone', '+905551234567')
    message = message_data.get('message', '')
    
    # Mock AI response
    result = {
        'response': 'Havuzumuz 08:00-20:00 saatleri arasinda aciktir. Iyi gunler!',
        'action': 'pool_hours_info',
        'confidence': 0.95
    }
    
    # Save conversation
    conversation = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'phone': phone,
        'user_message': message,
        'ai_response': result['response'],
        'action_taken': result.get('action'),
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.ai_conversations.insert_one(conversation)
    
    return result



@router.get("/ai-concierge/conversations")
async def get_ai_conversations(
    phone: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """AI Concierge conversation history"""
    query = {'tenant_id': current_user.tenant_id}
    if phone:
        query['phone'] = phone
    
    conversations = await db.ai_conversations.find(query, {'_id': 0}).sort('created_at', -1).limit(100).to_list(100)
    
    return {
        'conversations': conversations,
        'total': len(conversations)
    }

# ============= PREDICTIVE ANALYTICS (GAME-CHANGER #2) =============



@router.get("/predictions/no-shows")
async def predict_no_shows(
    target_date: str = None,
    current_user: User = Depends(get_current_user)
):
    """No-show risk predictions"""
    # Use today if no date provided
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")
    
    # Mock predictions
    predictions = [
        {'booking_id': 'BK001', 'guest_name': 'John Doe', 'risk_score': 0.75, 'risk_level': 'high'},
        {'booking_id': 'BK002', 'guest_name': 'Jane Smith', 'risk_score': 0.45, 'risk_level': 'medium'}
    ]
    
    return {
        'target_date': target_date,
        'predictions': predictions,
        'high_risk_count': len([p for p in predictions if p['risk_level'] == 'high']),
        'total_at_risk': len(predictions)
    }



@router.get("/predictions/demand-forecast")
async def demand_forecast(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """30 günlük talep tahmini"""
    from predictive_engine import get_predictive_engine
    
    engine = get_predictive_engine(db)
    forecast = await engine.predict_demand(current_user.tenant_id, days)
    
    return {
        'forecast_period': f'{days} days',
        'daily_forecast': forecast,
        'avg_occupancy': round(sum([f['occupancy_forecast'] for f in forecast]) / len(forecast), 1) if forecast else 0,
        'peak_days': [f for f in forecast if f['demand_level'] == 'very_high']
    }



@router.get("/predictions/complaint-risk/{guest_id}")
async def predict_complaint_risk(guest_id: str, current_user: User = Depends(get_current_user)):
    """Predict complaint risk for a guest"""
    # Mock implementation - returns risk score
    return {
        'guest_id': guest_id,
        'risk_score': 0.35,
        'risk_level': 'medium',
        'factors': ['Previous complaint', 'Long wait time'],
        'recommendation': 'Proactive service recovery recommended'
    }

# ============= SOCIAL MEDIA COMMAND CENTER (GAME-CHANGER #3) =============



@router.get("/social-media/mentions")
async def get_social_mentions(hours: int = 24, current_user: User = Depends(get_current_user)):
    """Son 24 saatteki social media mentions"""
    from social_media_radar import get_social_radar
    radar = get_social_radar(db)
    mentions = await radar.scan_mentions(current_user.tenant_id, hours)
    return {'mentions': mentions, 'total': len(mentions)}



@router.get("/social-media/sentiment")
async def get_sentiment_summary(days: int = 7, current_user: User = Depends(get_current_user)):
    """Sentiment özeti"""
    from social_media_radar import get_social_radar
    radar = get_social_radar(db)
    summary = await radar.get_sentiment_summary(current_user.tenant_id, days)
    return summary



@router.get("/social-media/crisis-alerts")
async def get_crisis_alerts(current_user: User = Depends(get_current_user)):
    """Kriz uyarıları"""
    from social_media_radar import get_social_radar
    radar = get_social_radar(db)
    alerts = await radar.detect_crisis(current_user.tenant_id)
    return {'alerts': alerts, 'crisis_detected': len(alerts) > 0}

# ============= REVENUE AUTOPILOT (GAME-CHANGER #4) =============



@router.get("/autopilot/status")
async def get_autopilot_status(current_user: User = Depends(get_current_user)):
    """Autopilot durumu"""
    from revenue_autopilot import get_revenue_autopilot
    autopilot = get_revenue_autopilot(db)
    return {
        'mode': autopilot.mode,
        'active': True,
        'last_cycle': datetime.now(timezone.utc).isoformat()
    }



@router.post("/autopilot/run-cycle")
async def run_autopilot_cycle(current_user: User = Depends(get_current_user)):
    """Autopilot cycle manuel çalıştır"""
    from revenue_autopilot import get_revenue_autopilot
    autopilot = get_revenue_autopilot(db)
    report = await autopilot.daily_optimization_cycle(current_user.tenant_id)
    return report



@router.post("/autopilot/set-mode")
async def set_autopilot_mode(mode_data: dict, current_user: User = Depends(get_current_user)):
    """Autopilot modunu ayarla"""
    from revenue_autopilot import get_revenue_autopilot
    autopilot = get_revenue_autopilot(db)
    autopilot.mode = mode_data.get('mode', 'advisory')  # full_auto, supervised, advisory
    return {'success': True, 'new_mode': autopilot.mode}

# ============= GUEST DNA PROFILE (GAME-CHANGER #5) =============



@router.get("/guest-dna/{guest_id}")
async def get_guest_dna_profile(guest_id: str, current_user: User = Depends(get_current_user)):
    """Get comprehensive guest DNA profile"""
    # Mock implementation
    return {
        'guest_id': guest_id,
        'personality_type': 'Business Traveler',
        'spending_pattern': 'High Value',
        'preferences': {
            'room_type': 'Executive',
            'floor': 'High',
            'amenities': ['Gym', 'Business Center']
        },
        'behavior_score': 8.5,
        'lifetime_value': 15000.0,
        'churn_risk': 'low'
    }

# ============= DYNAMIC STAFFING AI (GAME-CHANGER #6) =============



@router.get("/staffing-ai/optimal")
async def get_optimal_staffing(target_date: str = None, current_user: User = Depends(get_current_user)):
    """Get optimal staffing recommendations"""
    # Mock implementation
    return {
        'target_date': target_date or datetime.now().strftime("%Y-%m-%d"),
        'departments': {
            'front_desk': {'optimal': 4, 'current': 3, 'recommendation': 'hire_1'},
            'housekeeping': {'optimal': 8, 'current': 8, 'recommendation': 'adequate'},
            'fnb': {'optimal': 6, 'current': 5, 'recommendation': 'hire_1'}
        },
        'total_cost_savings': 2500.0,
        'efficiency_gain': '15%'
    }



@router.get("/staffing-ai/schedule")
async def generate_auto_schedule(target_date: str = None, current_user: User = Depends(get_current_user)):
    """Generate AI-optimized staff schedule"""
    # Mock implementation
    return {
        'schedule': [
            {'staff': 'Ahmet', 'shift': '08:00-16:00', 'department': 'Front Desk'},
            {'staff': 'Ayşe', 'shift': '16:00-00:00', 'department': 'Front Desk'}
        ],
        'target_date': target_date or datetime.now().strftime("%Y-%m-%d"),
        'optimization_score': 9.2
    }



@router.post("/ai/solve-overbooking")
async def solve_overbooking(
    date: str,
    current_user: User = Depends(get_current_user)
):
    """AI-powered overbooking resolution suggestions"""
    target_date = datetime.fromisoformat(date).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    # Get all rooms
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    
    # Find overbookings (multiple bookings on same room same date)
    conflicts = []
    for room in rooms:
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'room_id': room['id'],
            'status': {'$in': ['confirmed', 'guaranteed']},
            'check_in': {'$lte': end_of_day.isoformat()},
            'check_out': {'$gte': start_of_day.isoformat()}
        }, {'_id': 0}).to_list(100)
        
        if len(bookings) > 1:
            conflicts.append({
                'room': room,
                'bookings': bookings
            })
    
    # Generate AI solutions
    solutions = []
    for conflict in conflicts:
        room = conflict['room']
        bookings = conflict['bookings']
        
        # Find alternative rooms of same type
        alt_rooms = [r for r in rooms if r['room_type'] == room['room_type'] and r['id'] != room['id']]
        
        for booking in bookings[1:]:  # Keep first booking, move others
            # Find available alternative rooms
            available_alts = []
            for alt_room in alt_rooms:
                # Check if alt room is available
                existing = await db.bookings.count_documents({
                    'tenant_id': current_user.tenant_id,
                    'room_id': alt_room['id'],
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                    'check_in': {'$lte': booking['check_out']},
                    'check_out': {'$gte': booking['check_in']}
                })
                
                if existing == 0:
                    # Calculate guest priority score
                    guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id}, {'_id': 0})
                    loyalty_tier = guest.get('loyalty_tier', 'standard') if guest else 'standard'
                    priority_score = {
                        'vip': 100,
                        'gold': 80,
                        'silver': 60,
                        'standard': 40
                    }.get(loyalty_tier, 40)
                    
                    # Add OTA channel penalty (harder to move OTA bookings)
                    if booking.get('ota_channel'):
                        priority_score -= 20
                    
                    available_alts.append({
                        'room': alt_room,
                        'priority_score': priority_score,
                        'reason': f"Same type ({alt_room['room_type']}), Floor {alt_room['floor']}"
                    })
            
            # Sort by priority score
            available_alts.sort(key=lambda x: x['priority_score'], reverse=True)
            
            if available_alts:
                best_option = available_alts[0]
                solutions.append({
                    'conflict_type': 'overbooking',
                    'severity': 'high',
                    'current_room': room['room_number'],
                    'booking_id': booking['id'],
                    'guest_name': booking.get('guest_name', 'Unknown'),
                    'check_in': booking['check_in'],
                    'check_out': booking['check_out'],
                    'recommended_action': 'move',
                    'recommended_room': best_option['room']['room_number'],
                    'recommended_room_id': best_option['room']['id'],
                    'confidence': 0.85,
                    'reason': best_option['reason'],
                    'impact': 'minimal',
                    'auto_apply': False
                })
    
    return {
        'date': target_date.isoformat(),
        'conflicts_found': len(conflicts),
        'solutions': solutions,
        'summary': f"Found {len(conflicts)} overbooking conflicts with {len(solutions)} AI-powered solutions"
    }



@router.post("/ai/recommend-room-moves")
async def recommend_room_moves(
    date: str,
    current_user: User = Depends(get_current_user)
):
    """AI recommendations for optimal room moves (upgrades, VIP service)"""
    target_date = datetime.fromisoformat(date).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    
    # Get bookings for target date
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed']},
        'check_in': {'$lte': end_of_day.isoformat()},
        'check_out': {'$gte': start_of_day.isoformat()}
    }, {'_id': 0}).to_list(1000)
    
    recommendations = []
    
    for booking in bookings:
        guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id}, {'_id': 0})
        if not guest:
            continue
        
        current_room = next((r for r in rooms if r['id'] == booking['room_id']), None)
        if not current_room:
            continue
        
        loyalty_tier = guest.get('loyalty_tier', 'standard')
        
        # VIP/Gold upgrade opportunities
        if loyalty_tier in ['vip', 'gold']:
            # Find better rooms available
            better_rooms = [r for r in rooms 
                          if r['room_type'] != current_room['room_type'] 
                          and r['base_price'] > current_room['base_price']]
            
            for better_room in better_rooms:
                # Check availability
                existing = await db.bookings.count_documents({
                    'tenant_id': current_user.tenant_id,
                    'room_id': better_room['id'],
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                    'check_in': {'$lte': booking['check_out']},
                    'check_out': {'$gte': booking['check_in']}
                })
                
                if existing == 0:
                    recommendations.append({
                        'type': 'upgrade',
                        'priority': 'high' if loyalty_tier == 'vip' else 'medium',
                        'booking_id': booking['id'],
                        'guest_name': guest.get('name', 'Unknown'),
                        'loyalty_tier': loyalty_tier,
                        'current_room': current_room['room_number'],
                        'recommended_room': better_room['room_number'],
                        'recommended_room_id': better_room['id'],
                        'reason': f"Complimentary upgrade for {loyalty_tier.upper()} guest",
                        'revenue_impact': 0,  # Complimentary
                        'confidence': 0.90
                    })
                    break  # One recommendation per booking
        
        # Room block avoidance
        blocks = await db.room_blocks.find({
            'tenant_id': current_user.tenant_id,
            'room_id': current_room['id'],
            'status': 'active',
            'start_date': {'$lte': booking['check_out']},
            '$or': [
                {'end_date': {'$gte': booking['check_in']}},
                {'end_date': None}
            ]
        }, {'_id': 0}).to_list(10)
        
        if blocks:
            # Find alternative same-type room
            alt_rooms = [r for r in rooms 
                        if r['room_type'] == current_room['room_type'] 
                        and r['id'] != current_room['id']]
            
            for alt_room in alt_rooms:
                existing = await db.bookings.count_documents({
                    'tenant_id': current_user.tenant_id,
                    'room_id': alt_room['id'],
                    'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                    'check_in': {'$lte': booking['check_out']},
                    'check_out': {'$gte': booking['check_in']}
                })
                
                if existing == 0:
                    recommendations.append({
                        'type': 'block_avoidance',
                        'priority': 'urgent',
                        'booking_id': booking['id'],
                        'guest_name': guest.get('name', 'Unknown'),
                        'current_room': current_room['room_number'],
                        'recommended_room': alt_room['room_number'],
                        'recommended_room_id': alt_room['id'],
                        'reason': f"Room {current_room['room_number']} is blocked ({blocks[0]['type']})",
                        'revenue_impact': 0,
                        'confidence': 0.95
                    })
                    break
    
    # Sort by priority
    priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    recommendations.sort(key=lambda x: priority_order.get(x['priority'], 99))
    
    return {
        'date': target_date.isoformat(),
        'recommendations': recommendations,
        'count': len(recommendations),
        'summary': f"Generated {len(recommendations)} AI room move recommendations"
    }



@router.post("/ai/recommend-rates")
async def recommend_rates(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """AI-powered dynamic rate recommendations"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    room_types = list(set(r['room_type'] for r in rooms))
    
    recommendations = []
    
    for rt in room_types:
        rt_rooms = [r for r in rooms if r['room_type'] == rt]
        total_rt_rooms = len(rt_rooms)
        base_rate = rt_rooms[0]['base_price'] if rt_rooms else 0
        
        current_date = start
        while current_date <= end:
            start_of_day = datetime.combine(current_date, datetime.min.time())
            end_of_day = datetime.combine(current_date, datetime.max.time())
            
            # Calculate occupancy
            occupied = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'room_id': {'$in': [r['id'] for r in rt_rooms]},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lte': end_of_day.isoformat()},
                'check_out': {'$gte': start_of_day.isoformat()}
            })
            
            occupancy_pct = (occupied / total_rt_rooms * 100) if total_rt_rooms > 0 else 0
            
            # AI pricing strategy
            if occupancy_pct >= 90:
                # High demand - increase rates
                recommended_rate = base_rate * 1.25
                strategy = 'demand_surge'
                reason = f"High occupancy ({occupancy_pct:.0f}%) - capitalize on demand"
                confidence = 0.88
            elif occupancy_pct >= 75:
                # Good demand - moderate increase
                recommended_rate = base_rate * 1.15
                strategy = 'optimize'
                reason = f"Strong demand ({occupancy_pct:.0f}%) - optimize revenue"
                confidence = 0.82
            elif occupancy_pct >= 50:
                # Moderate - maintain rates
                recommended_rate = base_rate
                strategy = 'maintain'
                reason = f"Normal occupancy ({occupancy_pct:.0f}%) - maintain base rates"
                confidence = 0.75
            else:
                # Low demand - discount to attract
                recommended_rate = base_rate * 0.85
                strategy = 'attract'
                reason = f"Low occupancy ({occupancy_pct:.0f}%) - attract bookings with discount"
                confidence = 0.80
            
            # Check day of week for adjustments
            day_of_week = current_date.weekday()
            if day_of_week in [4, 5]:  # Friday, Saturday
                recommended_rate *= 1.10
                reason += " + Weekend premium"
            
            recommendations.append({
                'date': current_date.isoformat(),
                'day_of_week': current_date.strftime('%A'),
                'room_type': rt,
                'current_rate': round(base_rate, 2),
                'recommended_rate': round(recommended_rate, 2),
                'difference': round(recommended_rate - base_rate, 2),
                'difference_pct': round(((recommended_rate - base_rate) / base_rate * 100), 1),
                'strategy': strategy,
                'reason': reason,
                'occupancy_pct': round(occupancy_pct, 1),
                'confidence': confidence,
                'revenue_impact': round((recommended_rate - base_rate) * (total_rt_rooms - occupied), 2)
            })
            
            current_date += timedelta(days=1)
    
    # Calculate total potential revenue impact
    total_impact = sum(r['revenue_impact'] for r in recommendations if r['revenue_impact'] > 0)
    
    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat()
        },
        'recommendations': recommendations,
        'summary': {
            'total_recommendations': len(recommendations),
            'increase_count': sum(1 for r in recommendations if r['difference'] > 0),
            'decrease_count': sum(1 for r in recommendations if r['difference'] < 0),
            'maintain_count': sum(1 for r in recommendations if r['difference'] == 0),
            'potential_revenue_increase': round(total_impact, 2)
        }
    }



@router.post("/ai/predict-no-shows")
async def predict_no_shows(
    date: str,
    current_user: User = Depends(get_current_user)
):
    """AI prediction of high-risk no-show bookings"""
    target_date = datetime.fromisoformat(date).date()
    
    # Get arrivals for target date
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': target_date.isoformat(),
        'status': {'$in': ['confirmed', 'guaranteed']}
    }, {'_id': 0}).to_list(1000)
    
    predictions = []
    
    for booking in bookings:
        risk_score = 0
        risk_factors = []
        
        # Factor 1: Channel risk (OTA bookings higher risk)
        if booking.get('ota_channel'):
            risk_score += 25
            risk_factors.append(f"OTA booking ({booking.get('ota_channel')})")
        else:
            risk_score += 5
        
        # Factor 2: Payment method
        payment_model = booking.get('payment_model')
        if payment_model == 'agency':
            risk_score += 20
            risk_factors.append("Agency payment (no prepayment)")
        elif payment_model == 'hotel_collect':
            risk_score += 15
            risk_factors.append("Hotel collect (no prepayment)")
        elif payment_model == 'virtual_card':
            risk_score += 5
            risk_factors.append("Virtual card")
        
        # Factor 3: Booking lead time (last-minute bookings higher risk)
        created_at = datetime.fromisoformat(booking.get('created_at', datetime.now(timezone.utc).isoformat()))
        lead_time = (target_date - created_at.date()).days
        if lead_time < 2:
            risk_score += 20
            risk_factors.append(f"Last-minute booking ({lead_time} days)")
        elif lead_time < 7:
            risk_score += 10
            risk_factors.append(f"Short lead time ({lead_time} days)")
        
        # Factor 4: Guest history (if available)
        guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id}, {'_id': 0})
        if guest:
            past_bookings = await db.bookings.count_documents({
                'tenant_id': current_user.tenant_id,
                'guest_id': booking['guest_id'],
                'status': 'checked_in'
            })
            
            if past_bookings == 0:
                risk_score += 15
                risk_factors.append("First-time guest")
            elif past_bookings > 3:
                risk_score -= 10
                risk_factors.append(f"Repeat guest ({past_bookings} stays)")
        
        # Factor 5: Booking amount (lower rates = higher risk)
        if booking.get('total_amount', 0) < 100:
            risk_score += 10
            risk_factors.append("Low booking value")
        
        # Normalize risk score (0-100)
        risk_score = min(100, max(0, risk_score))
        
        # Classify risk level
        if risk_score >= 70:
            risk_level = 'high'
            recommendation = 'Contact guest to confirm + Consider overbook strategy'
        elif risk_score >= 50:
            risk_level = 'medium'
            recommendation = 'Send reminder SMS/email 24h before arrival'
        else:
            risk_level = 'low'
            recommendation = 'Standard arrival preparation'
        
        predictions.append({
            'booking_id': booking['id'],
            'guest_name': booking.get('guest_name', 'Unknown'),
            'room_number': booking.get('room_number', 'TBD'),
            'check_in': booking['check_in'],
            'risk_score': risk_score,
            'risk_level': risk_level,
            'risk_factors': risk_factors,
            'confidence': 0.75,
            'recommendation': recommendation,
            'channel': booking.get('ota_channel') or 'direct',
            'booking_value': booking.get('total_amount', 0)
        })
    
    # Sort by risk score descending
    predictions.sort(key=lambda x: x['risk_score'], reverse=True)
    
    return {
        'date': target_date.isoformat(),
        'total_arrivals': len(bookings),
        'predictions': predictions,
        'summary': {
            'high_risk_count': sum(1 for p in predictions if p['risk_level'] == 'high'),
            'medium_risk_count': sum(1 for p in predictions if p['risk_level'] == 'medium'),
            'low_risk_count': sum(1 for p in predictions if p['risk_level'] == 'low'),
            'avg_risk_score': round(sum(p['risk_score'] for p in predictions) / len(predictions), 1) if predictions else 0
        }
    }

# ============= DELUXE+ ENTERPRISE FEATURES =============



@router.get("/ai/activity-log")
async def get_ai_activity_log(
    limit: int = 50,
    activity_type: Optional[str] = None,
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


# ============= MAINTENANCE WORK ORDERS =============



@router.post("/ai/log-activity")


# ============= IoT SENSOR ALERTS → MAINTENANCE BRIDGE =============



@router.post("/feedback/ai-sentiment-analysis")
async def analyze_review_sentiment_ai(
    review_text: str,
    source: str = "manual",
    current_user: User = Depends(get_current_user)
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




@router.post("/feedback/auto-reply")
async def generate_auto_reply(
    review_id: str,
    template_type: str = "standard",  # standard, apology, thank_you
    current_user: User = Depends(get_current_user)
):
    """
    Generate auto-reply for reviews using templates
    - Thank you for positive reviews
    - Apology for negative reviews
    - Customizable templates
    """
    review = await db.external_reviews.find_one({
        'id': review_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    guest_name = review.get('guest_name', 'Guest')
    sentiment = review.get('sentiment', 'neutral')
    
    # Generate reply based on sentiment
    if sentiment == 'positive' or template_type == 'thank_you':
        reply = f"Dear {guest_name},\n\nThank you for taking the time to share your wonderful feedback! We're thrilled to hear that you enjoyed your stay with us. Your kind words mean a lot to our team, and we look forward to welcoming you back soon.\n\nWarm regards,\n{current_user.name}\nGuest Relations Manager"
    
    elif sentiment == 'negative' or template_type == 'apology':
        reply = f"Dear {guest_name},\n\nThank you for sharing your feedback with us. We sincerely apologize that your experience did not meet your expectations. Your comments are very important to us, and we are taking immediate steps to address the issues you've raised.\n\nWe would appreciate the opportunity to discuss this further and make things right. Please contact me directly at your convenience.\n\nSincerely,\n{current_user.name}\nGuest Relations Manager"
    
    else:
        reply = f"Dear {guest_name},\n\nThank you for your feedback regarding your recent stay. We appreciate you taking the time to share your thoughts with us. Your input helps us continuously improve our services.\n\nWe hope to have the pleasure of welcoming you back in the future.\n\nBest regards,\n{current_user.name}\nGuest Relations Manager"
    
    return {
        'review_id': review_id,
        'generated_reply': reply,
        'template_type': template_type,
        'sentiment': sentiment,
        'can_edit': True,
        'note': 'Review and edit before sending'
    }




@router.get("/feedback/source-filtering")
async def get_reviews_by_source(
    source: str,  # google, booking, tripadvisor, in_house
    days: int = 30,
    sentiment: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Filter reviews by source
    - Google Reviews
    - Booking.com
    - TripAdvisor
    - In-house surveys
    """
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }
    
    # Determine collection based on source
    if source == 'in_house':
        collection = db.survey_responses
        match_criteria.pop('created_at')
        match_criteria['submitted_at'] = {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    else:
        collection = db.external_reviews
        match_criteria['platform'] = source
    
    if sentiment:
        match_criteria['sentiment'] = sentiment
    
    reviews = []
    async for review in collection.find(match_criteria).sort('created_at', -1):
        reviews.append({
            'id': review.get('id'),
            'guest_name': review.get('guest_name'),
            'rating': review.get('rating') or review.get('overall_rating'),
            'review_text': review.get('review_text') or review.get('comments'),
            'sentiment': review.get('sentiment'),
            'date': review.get('created_at') or review.get('submitted_at'),
            'source': source
        })
    
    # Calculate summary
    total_reviews = len(reviews)
    avg_rating = sum(r['rating'] for r in reviews) / total_reviews if total_reviews > 0 else 0
    
    return {
        'source': source,
        'period_days': days,
        'sentiment_filter': sentiment,
        'total_reviews': total_reviews,
        'avg_rating': round(avg_rating, 2),
        'reviews': reviews
    }


# ============= LOYALTY PROGRAM ENHANCEMENTS =============



@router.post("/ai/guest-persona/analyze/{guest_id}")
async def analyze_guest_persona(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    AI Guest Persona Analysis
    - Analyzes booking history, spending patterns, reviews
    - Assigns persona categories
    - Provides actionable recommendations
    """
    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    
    # Get guest's booking history
    bookings = []
    async for booking in db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }).sort('created_at', -1):
        bookings.append(booking)
    
    # Get spending data
    total_spent = 0
    ota_bookings = 0
    direct_bookings = 0
    avg_lead_time = []
    
    for booking in bookings:
        total_spent += booking.get('total_amount', 0)
        if booking.get('channel') in ['booking_com', 'expedia', 'airbnb']:
            ota_bookings += 1
        elif booking.get('channel') == 'direct':
            direct_bookings += 1
        
        # Calculate lead time
        created = datetime.fromisoformat(booking.get('created_at'))
        checkin = datetime.fromisoformat(booking.get('check_in'))
        lead_time = (checkin - created).days
        avg_lead_time.append(lead_time)
    
    # Get reviews/feedback
    reviews = []
    async for review in db.department_feedback.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }):
        reviews.append(review)
    
    negative_reviews = sum(1 for r in reviews if r.get('rating', 0) < 3)
    
    # Get upsell history
    upsells_accepted = 0
    async for charge in db.folio_charges.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id,
        'charge_category': {'$in': ['spa', 'upgrade', 'minibar']}
    }):
        upsells_accepted += 1
    
    # AI Persona Analysis
    personas = []
    
    # 1. Price Sensitive
    if len(bookings) > 0:
        avg_spend = total_spent / len(bookings)
        if avg_spend < 100 and avg_lead_time and sum(avg_lead_time) / len(avg_lead_time) > 30:
            personas.append({
                'type': 'price_sensitive',
                'confidence': 0.85,
                'indicators': [
                    f'Low average spend: ${avg_spend:.2f} per booking',
                    f'Long booking lead time: {sum(avg_lead_time) / len(avg_lead_time):.0f} days',
                    'Likely shops for best rates'
                ],
                'recommendations': [
                    'Offer early bird discounts',
                    'Send promotional emails for off-season',
                    'Avoid premium upsells',
                    'Focus on value packages'
                ]
            })
    
    # 2. Experience Seeker
    if upsells_accepted > 3:
        personas.append({
            'type': 'experience_seeker',
            'confidence': 0.90,
            'indicators': [
                f'Accepted {upsells_accepted} upsells/add-ons',
                'High engagement with hotel services',
                'Values experiences over price'
            ],
            'recommendations': [
                'Offer room upgrade at check-in',
                'Suggest spa packages',
                'Promote exclusive experiences',
                'VIP treatment opportunities'
            ]
        })
    
    # 3. Complainer
    if negative_reviews >= 2:
        personas.append({
            'type': 'complainer',
            'confidence': 0.80,
            'indicators': [
                f'{negative_reviews} negative reviews/feedback',
                'High expectations, difficult to satisfy',
                'Requires extra attention'
            ],
            'recommendations': [
                '⚠️ Assign best available room',
                'Front desk alert on arrival',
                'Proactive service recovery',
                'Senior staff handling',
                'Consider welcome amenity'
            ]
        })
    
    # 4. Upsell Candidate
    if total_spent > 1000 and upsells_accepted > 0:
        personas.append({
            'type': 'upsell_candidate',
            'confidence': 0.88,
            'indicators': [
                f'Total lifetime spend: ${total_spent:.2f}',
                f'Previously accepted {upsells_accepted} upsells',
                'Receptive to premium offerings'
            ],
            'recommendations': [
                '💰 Offer room upgrade ($50-100)',
                'Suggest late checkout',
                'Promote F&B packages',
                'Spa services upsell',
                'Airport transfer service'
            ]
        })
    
    # 5. High LTV (Lifetime Value)
    if total_spent > 2000 or len(bookings) > 5:
        ltv_score = total_spent + (len(bookings) * 200)  # Factor in repeat visits
        personas.append({
            'type': 'high_ltv',
            'confidence': 0.95,
            'indicators': [
                f'Lifetime value: ${ltv_score:.2f}',
                f'{len(bookings)} total stays',
                'Most valuable guest segment'
            ],
            'recommendations': [
                '⭐ VIP treatment',
                'Loyalty program auto-upgrade',
                'Exclusive perks and benefits',
                'Personalized communication',
                'Invitation to special events'
            ]
        })
    
    # 6. OTA → Direct Conversion Candidate
    if ota_bookings > 0 and direct_bookings == 0 and len(bookings) >= 2:
        personas.append({
            'type': 'ota_to_direct_candidate',
            'confidence': 0.75,
            'indicators': [
                f'{ota_bookings} OTA bookings, 0 direct bookings',
                'Repeat customer (familiar with hotel)',
                'High conversion potential'
            ],
            'recommendations': [
                '🎯 Offer direct booking discount (10-15%)',
                'Highlight member benefits',
                'Send personalized email campaign',
                'Loyalty points bonus for direct booking',
                'Best rate guarantee promotion'
            ]
        })
    
    # Store personas
    for persona_data in personas:
        persona = GuestPersona(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            persona_type=persona_data['type'],
            confidence_score=persona_data['confidence'],
            indicators=persona_data['indicators'],
            recommendations=persona_data['recommendations']
        )
        
        # Check if exists
        existing = await db.guest_personas.find_one({
            'guest_id': guest_id,
            'tenant_id': current_user.tenant_id,
            'persona_type': persona_data['type']
        })
        
        persona_dict = persona.model_dump()
        persona_dict['created_at'] = persona_dict['created_at'].isoformat()
        persona_dict['updated_at'] = persona_dict['updated_at'].isoformat()
        
        if existing:
            await db.guest_personas.update_one(
                {'id': existing.get('id')},
                {'$set': persona_dict}
            )
        else:
            await db.guest_personas.insert_one(persona_dict)
    
    return {
        'guest_id': guest_id,
        'guest_name': guest.get('name'),
        'analysis_summary': {
            'total_bookings': len(bookings),
            'lifetime_value': round(total_spent, 2),
            'ota_bookings': ota_bookings,
            'direct_bookings': direct_bookings,
            'upsells_accepted': upsells_accepted,
            'negative_reviews': negative_reviews
        },
        'personas_detected': len(personas),
        'personas': personas,
        'primary_persona': personas[0]['type'] if personas else None
    }




@router.get("/ai/guest-persona/all-insights")
async def get_all_guest_insights(
    persona_type: Optional[str] = None,
    min_confidence: float = 0.7,
    current_user: User = Depends(get_current_user)
):
    """
    Get all guest persona insights
    - Segment guests by persona type
    - Actionable marketing campaigns
    """
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        'confidence_score': {'$gte': min_confidence}
    }
    
    if persona_type:
        match_criteria['persona_type'] = persona_type
    
    insights = []
    async for persona in db.guest_personas.find(match_criteria).sort('confidence_score', -1):
        guest = await db.guests.find_one({'id': persona.get('guest_id')})
        insights.append({
            'guest_id': persona.get('guest_id'),
            'guest_name': guest.get('name') if guest else 'Unknown',
            'persona_type': persona.get('persona_type'),
            'confidence': persona.get('confidence_score'),
            'recommendations': persona.get('recommendations')
        })
    
    # Group by persona type
    by_type = {}
    for insight in insights:
        ptype = insight['persona_type']
        if ptype not in by_type:
            by_type[ptype] = []
        by_type[ptype].append(insight)
    
    return {
        'total_insights': len(insights),
        'persona_filter': persona_type,
        'min_confidence': min_confidence,
        'insights': insights,
        'by_type': {k: len(v) for k, v in by_type.items()},
        'marketing_campaigns': generate_campaign_suggestions(by_type)
    }




@router.post("/ai/predictive-maintenance/analyze")
async def analyze_predictive_maintenance(
    current_user: User = Depends(get_current_user)
):
    """
    Predictive Maintenance Analysis
    - IoT sensor data analysis (simulated)
    - Pattern detection
    - Failure prediction before breakdown
    - Automatic task assignment
    """
    # In production: Integrate with IoT sensors, HVAC controllers, BMS
    # Analyze: Temperature patterns, error codes, usage frequency, vibration data
    
    alerts = []
    
    # Get all rooms
    rooms = []
    async for room in db.rooms.find({'tenant_id': current_user.tenant_id}):
        rooms.append(room)
    
    # Get maintenance history
    for room in rooms[:5]:  # Analyze first 5 rooms for demo
        room_id = room.get('id')
        room_number = room.get('room_number')
        
        # Get past maintenance issues
        issues = []
        async for task in db.maintenance_tasks.find({
            'room_id': room_id,
            'tenant_id': current_user.tenant_id
        }).sort('created_at', -1).limit(10):
            issues.append(task)
        
        # Pattern Analysis (Simulated AI/ML)
        
        # 1. HVAC Analysis
        hvac_issues = [i for i in issues if 'ac' in i.get('description', '').lower() or 'hvac' in i.get('description', '').lower()]
        if len(hvac_issues) >= 2:
            # Recurring AC issues detected
            alert = MaintenanceAlert(
                tenant_id=current_user.tenant_id,
                room_id=room_id,
                equipment_type='hvac',
                severity='high',
                prediction=f'AC unit in room {room_number} showing failure pattern',
                indicators=[
                    f'{len(hvac_issues)} AC service calls in last 90 days',
                    'Same error code reported 3 times',
                    'Temperature fluctuation detected',
                    'Compressor vibration increased by 15%'
                ],
                recommended_action='Schedule preventive maintenance - compressor inspection',
                estimated_failure_days=7
            )
            
            alert_dict = alert.model_dump()
            alert_dict['created_at'] = alert_dict['created_at'].isoformat()
            await db.predictive_maintenance_alerts.insert_one(alert_dict)
            alerts.append(alert_dict)
            
            # Auto-create maintenance task
            await create_predictive_maintenance_task(
                current_user.tenant_id,
                room_id,
                room_number,
                'Preventive HVAC Maintenance',
                'high',
                alert.id
            )
        
        # 2. Plumbing Analysis
        plumbing_issues = [i for i in issues if 'leak' in i.get('description', '').lower() or 'water' in i.get('description', '').lower()]
        if len(plumbing_issues) >= 1:
            alert = MaintenanceAlert(
                tenant_id=current_user.tenant_id,
                room_id=room_id,
                equipment_type='plumbing',
                severity='medium',
                prediction=f'Potential leak risk in room {room_number}',
                indicators=[
                    'Water pressure fluctuation',
                    'Previous leak repair 45 days ago',
                    'Bathroom humidity elevated'
                ],
                recommended_action='Inspect pipes and seals',
                estimated_failure_days=14
            )
            
            alert_dict = alert.model_dump()
            alert_dict['created_at'] = alert_dict['created_at'].isoformat()
            await db.predictive_maintenance_alerts.insert_one(alert_dict)
            alerts.append(alert_dict)
    
    return {
        'analysis_date': datetime.now().date().isoformat(),
        'rooms_analyzed': len(rooms),
        'alerts_generated': len(alerts),
        'high_priority': sum(1 for a in alerts if a.get('severity') == 'high'),
        'medium_priority': sum(1 for a in alerts if a.get('severity') == 'medium'),
        'alerts': alerts,
        'summary': f'{len(alerts)} potential failures predicted - proactive maintenance scheduled',
        'cost_savings_estimate': f'${len(alerts) * 500} (prevented emergency repairs)'
    }




@router.get("/ai/predictive-maintenance/dashboard")
async def get_predictive_maintenance_dashboard(
    current_user: User = Depends(get_current_user)
):
    """Get predictive maintenance dashboard"""
    alerts = []
    async for alert in db.predictive_maintenance_alerts.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending'
    }).sort('severity', -1):
        room = await db.rooms.find_one({'id': alert.get('room_id')})
        alerts.append({
            'alert_id': alert.get('id'),
            'room_number': room.get('room_number') if room else 'Unknown',
            'equipment': alert.get('equipment_type'),
            'severity': alert.get('severity'),
            'prediction': alert.get('prediction'),
            'days_until_failure': alert.get('estimated_failure_days'),
            'recommended_action': alert.get('recommended_action')
        })
    
    return {
        'total_alerts': len(alerts),
        'critical_alerts': sum(1 for a in alerts if a['severity'] == 'critical'),
        'alerts': alerts
    }


# ============= AI HOUSEKEEPING SCHEDULER =============



@router.post("/ai/housekeeping/smart-schedule")
async def ai_housekeeping_smart_scheduler(
    date: str,
    current_user: User = Depends(get_current_user)
):
    """
    AI Housekeeping Scheduler
    - Occupancy forecast analysis
    - Available staff calculation
    - Intelligent task distribution
    - Workload balancing
    """
    datetime.fromisoformat(date)
    
    # 1. Get occupancy forecast
    occupied_rooms = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': date},
        'check_out': {'$gte': date},
        'status': {'$in': ['confirmed', 'checked_in']}
    }):
        occupied_rooms.append(booking.get('room_id'))
    
    # 2. Check-outs today (require deep cleaning)
    checkout_today = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_out': date,
        'status': 'checked_in'
    }):
        checkout_today.append(booking.get('room_id'))
    
    # 3. Get available HK staff
    hk_staff = []
    async for user in db.users.find({
        'tenant_id': current_user.tenant_id,
        'role': 'housekeeping',
        'status': 'active'
    }):
        hk_staff.append(user)
    
    if not hk_staff:
        # Create simulated staff for demo
        hk_staff = [
            {'id': '1', 'name': 'Maria'},
            {'id': '2', 'name': 'Elena'},
            {'id': '3', 'name': 'Sofia'}
        ]
    
    staff_count = len(hk_staff)
    
    # 4. Calculate workload
    total_rooms = len(occupied_rooms) + len(checkout_today)
    
    # Standard cleaning times
    occupied_cleaning_time = 20  # minutes
    checkout_cleaning_time = 45  # minutes (deep clean)
    
    total_minutes = (len(occupied_rooms) * occupied_cleaning_time) + (len(checkout_today) * checkout_cleaning_time)
    
    # Available staff hours (8-hour shift = 480 minutes)
    available_minutes = staff_count * 480
    
    # AI Task Distribution
    tasks_per_staff = total_rooms / staff_count if staff_count > 0 else 0
    
    # Intelligent assignment (balance workload)
    staff_assignments = []
    
    # Priority 1: Checkout rooms (must be done first)
    checkout_assignments = distribute_tasks(checkout_today, hk_staff, 'checkout')
    
    # Priority 2: Occupied rooms
    occupied_assignments = distribute_tasks(occupied_rooms, hk_staff, 'occupied')
    
    # Combine assignments
    combined = {}
    for assignment in checkout_assignments + occupied_assignments:
        staff_name = assignment['staff_name']
        if staff_name not in combined:
            combined[staff_name] = {
                'staff_name': staff_name,
                'staff_id': assignment['staff_id'],
                'tasks': [],
                'total_tasks': 0,
                'estimated_minutes': 0
            }
        combined[staff_name]['tasks'].append(assignment['task'])
        combined[staff_name]['total_tasks'] += 1
        combined[staff_name]['estimated_minutes'] += assignment['estimated_minutes']
    
    staff_assignments = list(combined.values())
    
    # Create tasks in database
    for assignment in staff_assignments:
        for task in assignment['tasks']:
            await db.housekeeping_tasks.insert_one({
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'room_id': task['room_id'],
                'task_type': task['type'],
                'priority': task['priority'],
                'assigned_to': assignment['staff_name'],
                'status': 'pending',
                'scheduled_date': date,
                'estimated_duration': task['estimated_minutes'],
                'created_at': datetime.now(timezone.utc).isoformat(),
                'source': 'ai_scheduler'
            })
    
    # Capacity analysis
    capacity_pct = (total_minutes / available_minutes * 100) if available_minutes > 0 else 0
    
    return {
        'date': date,
        'forecast': {
            'occupied_rooms': len(occupied_rooms),
            'checkout_rooms': len(checkout_today),
            'total_rooms_to_clean': total_rooms
        },
        'staffing': {
            'available_staff': staff_count,
            'total_available_hours': available_minutes / 60,
            'required_hours': total_minutes / 60,
            'capacity_utilization': round(capacity_pct, 1),
            'status': '✅ Adequate' if capacity_pct < 90 else '⚠️ Tight' if capacity_pct < 110 else '🚨 Understaffed'
        },
        'ai_schedule': {
            'tasks_per_staff': round(tasks_per_staff, 1),
            'workload_balanced': True,
            'staff_assignments': staff_assignments
        },
        'recommendations': generate_scheduling_recommendations(capacity_pct, staff_count, total_rooms)
    }




@router.post("/ai/loyalty/auto-tier-upgrade")
async def auto_loyalty_tier_upgrade(
    current_user: User = Depends(get_current_user)
):
    """
    Automatic Loyalty Tier Upgrade
    - Analyzes guest behavior patterns
    - OTA → Direct conversion: bonus points
    - Repeat visits: auto tier upgrade
    - Smart loyalty management
    """
    upgrades = []
    
    # Get all guests
    async for guest in db.guests.find({'tenant_id': current_user.tenant_id}):
        guest_id = guest.get('id')
        guest_name = guest.get('name')
        current_points = guest.get('loyalty_points', 0)
        current_tier = guest.get('loyalty_tier', 'bronze')
        
        # Get booking history
        bookings = []
        async for booking in db.bookings.find({
            'guest_id': guest_id,
            'tenant_id': current_user.tenant_id
        }).sort('created_at', 1):
            bookings.append(booking)
        
        if not bookings:
            continue
        
        # Behavior Analysis
        ota_bookings = [b for b in bookings if b.get('channel') in ['booking_com', 'expedia', 'airbnb']]
        direct_bookings = [b for b in bookings if b.get('channel') == 'direct']
        
        # Rule 1: OTA → Direct Conversion Bonus
        if len(ota_bookings) > 0 and len(direct_bookings) > 0:
            # Check if last booking was direct (conversion!)
            last_booking = bookings[-1]
            if last_booking.get('channel') == 'direct':
                # Previous was OTA?
                if len(bookings) > 1 and bookings[-2].get('channel') in ['booking_com', 'expedia', 'airbnb']:
                    # Conversion detected!
                    bonus_points = 500
                    new_points = current_points + bonus_points
                    
                    await db.guests.update_one(
                        {'id': guest_id},
                        {'$set': {'loyalty_points': new_points}}
                    )
                    
                    upgrades.append({
                        'guest_id': guest_id,
                        'guest_name': guest_name,
                        'action': 'ota_to_direct_bonus',
                        'bonus_points': bonus_points,
                        'reason': 'Switched from OTA to direct booking',
                        'old_points': current_points,
                        'new_points': new_points
                    })
                    
                    current_points = new_points  # Update for tier calculation
        
        # Rule 2: Repeat Visit Auto-Tier Upgrade
        if len(bookings) >= 3:  # 3+ stays
            # Calculate recommended tier
            if current_points >= 10000 and current_tier != 'platinum':
                new_tier = 'platinum'
            elif current_points >= 5000 and current_tier not in ['platinum', 'gold']:
                new_tier = 'gold'
            elif current_points >= 1000 and current_tier not in ['platinum', 'gold', 'silver']:
                new_tier = 'silver'
            else:
                new_tier = current_tier
            
            if new_tier != current_tier:
                await db.guests.update_one(
                    {'id': guest_id},
                    {'$set': {'loyalty_tier': new_tier}}
                )
                
                upgrades.append({
                    'guest_id': guest_id,
                    'guest_name': guest_name,
                    'action': 'tier_upgrade',
                    'old_tier': current_tier,
                    'new_tier': new_tier,
                    'reason': f'{len(bookings)} stays, {current_points} points earned',
                    'benefits_unlocked': get_tier_benefits(new_tier)
                })
        
        # Rule 3: Frequency Bonus (Bookings within 90 days)
        if len(bookings) >= 2:
            last_two = bookings[-2:]
            if len(last_two) == 2:
                date1 = datetime.fromisoformat(last_two[0].get('check_out'))
                date2 = datetime.fromisoformat(last_two[1].get('check_in'))
                days_between = (date2 - date1).days
                
                if days_between <= 90:
                    frequency_bonus = 300
                    new_points = current_points + frequency_bonus
                    
                    await db.guests.update_one(
                        {'id': guest_id},
                        {'$set': {'loyalty_points': new_points}}
                    )
                    
                    upgrades.append({
                        'guest_id': guest_id,
                        'guest_name': guest_name,
                        'action': 'frequency_bonus',
                        'bonus_points': frequency_bonus,
                        'reason': f'Repeat visit within {days_between} days',
                        'old_points': current_points,
                        'new_points': new_points
                    })
    
    # Create notification alerts for upgrades
    for upgrade in upgrades:
        await db.alerts.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'alert_type': 'loyalty_upgrade',
            'priority': 'normal',
            'title': f"Loyalty upgrade: {upgrade['guest_name']}",
            'description': upgrade['reason'],
            'source_module': 'loyalty_ai',
            'status': 'unread',
            'created_at': datetime.now(timezone.utc).isoformat()
        })
    
    return {
        'analysis_date': datetime.now().date().isoformat(),
        'guests_analyzed': await db.guests.count_documents({'tenant_id': current_user.tenant_id}),
        'upgrades_applied': len(upgrades),
        'upgrades': upgrades,
        'summary': {
            'ota_conversions': sum(1 for u in upgrades if u['action'] == 'ota_to_direct_bonus'),
            'tier_upgrades': sum(1 for u in upgrades if u['action'] == 'tier_upgrade'),
            'frequency_bonuses': sum(1 for u in upgrades if u['action'] == 'frequency_bonus')
        }
    }




@router.post("/ml/rms/train")
async def train_rms_model(
    historical_days: int = 730,
    current_user: User = Depends(get_current_user)
):
    """
    Train RMS (Revenue Management System) ML Model
    - Generates 2 years of synthetic training data
    - Trains XGBoost models for occupancy prediction and dynamic pricing
    - Saves models to disk for production use
    """
    try:
        from ml_data_generators import RMSDataGenerator
        from ml_trainers import RMSModelTrainer
        
        # Generate training data
        print(f"Generating {historical_days} days of RMS training data...")
        data_df = RMSDataGenerator.generate(days=historical_days)
        
        # Train models
        trainer = RMSModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)
        
        return {
            'success': True,
            'message': 'RMS models trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_samples': len(data_df),
                'date_range': {
                    'start': data_df['date'].min(),
                    'end': data_df['date'].max()
                },
                'occupancy_range': {
                    'min': float(data_df['occupancy_rate'].min()),
                    'max': float(data_df['occupancy_rate'].max()),
                    'mean': float(data_df['occupancy_rate'].mean())
                },
                'price_range': {
                    'min': float(data_df['optimal_price'].min()),
                    'max': float(data_df['optimal_price'].max()),
                    'mean': float(data_df['optimal_price'].mean())
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")




@router.post("/ml/persona/train")
async def train_persona_model(
    num_guests: int = 400,
    current_user: User = Depends(get_current_user)
):
    """
    Train Guest Persona ML Model
    - Generates 300-500 synthetic guest profiles
    - Trains Random Forest classifier for persona segmentation
    - Saves model to disk for production use
    """
    try:
        from ml_data_generators import PersonaDataGenerator
        from ml_trainers import PersonaModelTrainer
        
        # Generate training data
        print(f"Generating {num_guests} guest persona training samples...")
        data_df = PersonaDataGenerator.generate(num_guests=num_guests)
        
        # Train model
        trainer = PersonaModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)
        
        return {
            'success': True,
            'message': 'Persona model trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_guests': len(data_df),
                'persona_distribution': data_df['persona_type'].value_counts().to_dict(),
                'avg_stays': float(data_df['total_stays'].mean()),
                'avg_spend': float(data_df['avg_spend'].mean())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")




@router.post("/ml/predictive-maintenance/train")
async def train_predictive_maintenance_model(
    num_samples: int = 1000,
    current_user: User = Depends(get_current_user)
):
    """
    Train Predictive Maintenance ML Model
    - Generates IoT sensor simulation data
    - Trains XGBoost classifier for failure risk prediction
    - Trains Gradient Boosting for days-until-failure prediction
    - Saves models to disk for production use
    """
    try:
        from ml_data_generators import PredictiveMaintenanceDataGenerator
        from ml_trainers import PredictiveMaintenanceModelTrainer
        
        # Generate training data
        print(f"Generating {num_samples} predictive maintenance training samples...")
        data_df = PredictiveMaintenanceDataGenerator.generate(num_samples=num_samples)
        
        # Train models
        trainer = PredictiveMaintenanceModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)
        
        return {
            'success': True,
            'message': 'Predictive maintenance models trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_samples': len(data_df),
                'equipment_distribution': data_df['equipment_type'].value_counts().to_dict(),
                'risk_distribution': data_df['failure_risk'].value_counts().to_dict(),
                'avg_days_until_failure': float(data_df['days_until_failure'].mean())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")




@router.post("/ml/hk-scheduler/train")
async def train_hk_scheduler_model(
    num_days: int = 365,
    current_user: User = Depends(get_current_user)
):
    """
    Train Housekeeping Scheduler ML Model
    - Generates occupancy-based staffing data
    - Trains Random Forest regressors for staff and hours prediction
    - Saves models to disk for production use
    """
    try:
        from ml_data_generators import HKSchedulerDataGenerator
        from ml_trainers import HKSchedulerModelTrainer
        
        # Generate training data
        print(f"Generating {num_days} days of HK scheduler training data...")
        data_df = HKSchedulerDataGenerator.generate(num_days=num_days)
        
        # Train models
        trainer = HKSchedulerModelTrainer(model_dir='ml_models')
        metrics = trainer.train(data_df)
        
        return {
            'success': True,
            'message': 'HK scheduler models trained successfully',
            'metrics': metrics,
            'data_summary': {
                'total_days': len(data_df),
                'avg_occupancy': float(data_df['occupancy_rate'].mean()),
                'avg_staff_needed': float(data_df['staff_needed'].mean()),
                'avg_hours': float(data_df['estimated_hours'].mean()),
                'peak_staff_needed': int(data_df['staff_needed'].max())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")




@router.post("/ml/train-all")
async def train_all_models(
    current_user: User = Depends(get_current_user)
):
    """
    Train ALL ML Models in sequence
    - RMS (Revenue Management)
    - Persona (Guest Segmentation)
    - Predictive Maintenance
    - HK Scheduler
    """
    results = {}
    errors = []
    
    try:
        # Import all required modules
        from ml_data_generators import (
            RMSDataGenerator,
            PersonaDataGenerator,
            PredictiveMaintenanceDataGenerator,
            HKSchedulerDataGenerator
        )
        from ml_trainers import (
            RMSModelTrainer,
            PersonaModelTrainer,
            PredictiveMaintenanceModelTrainer,
            HKSchedulerModelTrainer
        )
        
        # 1. Train RMS Model
        try:
            print("\n=== Training RMS Model ===")
            data_df = RMSDataGenerator.generate(days=730)
            trainer = RMSModelTrainer(model_dir='ml_models')
            results['rms'] = trainer.train(data_df)
            results['rms']['status'] = 'success'
        except Exception as e:
            results['rms'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"RMS: {str(e)}")
        
        # 2. Train Persona Model
        try:
            print("\n=== Training Persona Model ===")
            data_df = PersonaDataGenerator.generate(num_guests=400)
            trainer = PersonaModelTrainer(model_dir='ml_models')
            results['persona'] = trainer.train(data_df)
            results['persona']['status'] = 'success'
        except Exception as e:
            results['persona'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"Persona: {str(e)}")
        
        # 3. Train Predictive Maintenance Model
        try:
            print("\n=== Training Predictive Maintenance Model ===")
            data_df = PredictiveMaintenanceDataGenerator.generate(num_samples=1000)
            trainer = PredictiveMaintenanceModelTrainer(model_dir='ml_models')
            results['predictive_maintenance'] = trainer.train(data_df)
            results['predictive_maintenance']['status'] = 'success'
        except Exception as e:
            results['predictive_maintenance'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"Predictive Maintenance: {str(e)}")
        
        # 4. Train HK Scheduler Model
        try:
            print("\n=== Training HK Scheduler Model ===")
            data_df = HKSchedulerDataGenerator.generate(num_days=365)
            trainer = HKSchedulerModelTrainer(model_dir='ml_models')
            results['hk_scheduler'] = trainer.train(data_df)
            results['hk_scheduler']['status'] = 'success'
        except Exception as e:
            results['hk_scheduler'] = {'status': 'failed', 'error': str(e)}
            errors.append(f"HK Scheduler: {str(e)}")
        
        # Summary
        successful = sum(1 for r in results.values() if r.get('status') == 'success')
        total = len(results)
        
        return {
            'success': len(errors) == 0,
            'message': f'Training complete: {successful}/{total} models trained successfully',
            'results': results,
            'errors': errors if errors else None,
            'summary': {
                'total_models': total,
                'successful': successful,
                'failed': len(errors)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk training failed: {str(e)}")




@router.get("/ml/models/status")
async def get_ml_models_status(
    current_user: User = Depends(get_current_user)
):
    """
    Get status of all ML models
    - Check if models are trained and available
    - Return training metrics if available
    """
    import json
    
    model_dir = 'ml_models'
    
    models_status = {
        'rms': {
            'trained': False,
            'files': ['rms_occupancy_model.pkl', 'rms_pricing_model.pkl', 'rms_metrics.json']
        },
        'persona': {
            'trained': False,
            'files': ['persona_model.pkl', 'persona_label_encoder.pkl', 'persona_metrics.json']
        },
        'predictive_maintenance': {
            'trained': False,
            'files': ['maintenance_risk_model.pkl', 'maintenance_days_model.pkl', 'maintenance_label_encoder.pkl', 'maintenance_equipment_encoder.pkl', 'maintenance_metrics.json']
        },
        'hk_scheduler': {
            'trained': False,
            'files': ['hk_staff_model.pkl', 'hk_hours_model.pkl', 'hk_scheduler_metrics.json']
        }
    }
    
    # Check each model
    for model_name, info in models_status.items():
        all_files_exist = all(
            os.path.exists(os.path.join(model_dir, file))
            for file in info['files']
        )
        
        info['trained'] = all_files_exist
        info['files_status'] = {
            file: os.path.exists(os.path.join(model_dir, file))
            for file in info['files']
        }
        
        # Load metrics if available
        metrics_file = [f for f in info['files'] if f.endswith('_metrics.json')]
        if metrics_file and all_files_exist:
            try:
                with open(os.path.join(model_dir, metrics_file[0]), 'r') as f:
                    info['metrics'] = json.load(f)
            except Exception:
                info['metrics'] = None
    
    # Overall summary
    trained_count = sum(1 for info in models_status.values() if info['trained'])
    total_count = len(models_status)
    
    return {
        'models': models_status,
        'summary': {
            'total_models': total_count,
            'trained_models': trained_count,
            'untrained_models': total_count - trained_count,
            'all_ready': trained_count == total_count
        }
    }


# ============= MONITORING & LOGGING ENDPOINTS =============




@router.get("/ai/pms/occupancy-prediction")
@cached(ttl=900, key_prefix="ai_occupancy_pred")
async def get_occupancy_prediction(
    days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get AI-powered occupancy prediction for next N days"""
    current_user = await get_current_user(credentials)
    
    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    
    # Get bookings for next N days
    start_date = datetime.now(timezone.utc)
    start_date + timedelta(days=days)
    
    predictions = []
    for day_offset in range(days):
        pred_date = start_date + timedelta(days=day_offset)
        
        # Count bookings for this date
        bookings_count = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$lte': pred_date},
            'check_out': {'$gt': pred_date},
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        })
        
        occupancy_pct = (bookings_count / total_rooms * 100) if total_rooms > 0 else 0
        
        # Simple prediction model (can be enhanced with ML)
        # Add some variance based on day of week
        day_of_week = pred_date.weekday()
        if day_of_week in [4, 5]:  # Friday, Saturday
            predicted_pct = min(occupancy_pct * 1.15, 100)
        elif day_of_week in [0, 6]:  # Monday, Sunday
            predicted_pct = occupancy_pct * 0.85
        else:
            predicted_pct = occupancy_pct
        
        predictions.append({
            'date': pred_date.strftime('%Y-%m-%d'),
            'day_of_week': pred_date.strftime('%A'),
            'current_bookings': bookings_count,
            'current_occupancy_pct': round(occupancy_pct, 1),
            'predicted_occupancy_pct': round(predicted_pct, 1),
            'confidence': 'high' if day_offset < 7 else 'medium' if day_offset < 14 else 'low'
        })
    
    return {
        'predictions': predictions,
        'total_rooms': total_rooms,
        'prediction_period_days': days
    }

# ============= NEW ENHANCEMENTS: OTA, GUEST PROFILE, HK MOBILE, RMS, MESSAGING, POS =============

# ===== 1. OTA RESERVATION DETAILS ENHANCEMENTS =====

# Extra charges model
# Multi-room reservation tracking


@router.get("/ai/pms/guest-patterns")
@cached(ttl=900, key_prefix="ai_guest_patterns")
async def get_guest_patterns(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """AI-powered guest behavior pattern analysis"""
    current_user = await get_current_user(credentials)
    
    from datetime import datetime, timedelta
    
    # Get recent bookings (last 90 days)
    ninety_days_ago = datetime.now() - timedelta(days=90)
    
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': ninety_days_ago.isoformat()}
    }).to_list(length=5000)
    
    # Analyze patterns
    patterns = {
        'booking_lead_time': {},
        'stay_duration': {},
        'preferred_room_types': {},
        'booking_channels': {},
        'peak_seasons': {},
        'cancellation_rate': 0
    }
    
    total_bookings = len(bookings)
    cancelled = 0
    lead_times = []
    durations = []
    room_types = {}
    channels = {}
    monthly_bookings = {}
    
    for booking in bookings:
        # Lead time
        if booking.get('created_at'):
            created = datetime.fromisoformat(booking['created_at'].replace('Z', '+00:00'))
            check_in = datetime.fromisoformat(booking['check_in'].replace('Z', '+00:00'))
            lead_time = (check_in - created).days
            lead_times.append(lead_time)
        
        # Duration
        check_in = datetime.fromisoformat(booking['check_in'].replace('Z', '+00:00'))
        check_out = datetime.fromisoformat(booking['check_out'].replace('Z', '+00:00'))
        duration = (check_out - check_in).days
        durations.append(duration)
        
        # Room type (get from room)
        room = await db.rooms.find_one({'id': booking.get('room_id')})
        if room:
            room_type = room.get('room_type', 'standard')
            room_types[room_type] = room_types.get(room_type, 0) + 1
        
        # Channel
        channel = booking.get('booking_channel', 'direct')
        channels[channel] = channels.get(channel, 0) + 1
        
        # Month
        month = check_in.strftime('%B')
        monthly_bookings[month] = monthly_bookings.get(month, 0) + 1
        
        # Cancellation
        if booking.get('status') == 'cancelled':
            cancelled += 1
    
    # Calculate averages and patterns
    patterns['booking_lead_time'] = {
        'average_days': round(sum(lead_times) / len(lead_times), 1) if lead_times else 0,
        'distribution': {
            'same_day': len([x for x in lead_times if x == 0]),
            '1-7_days': len([x for x in lead_times if 1 <= x <= 7]),
            '8-30_days': len([x for x in lead_times if 8 <= x <= 30]),
            '30+_days': len([x for x in lead_times if x > 30])
        }
    }
    
    patterns['stay_duration'] = {
        'average_nights': round(sum(durations) / len(durations), 1) if durations else 0,
        'distribution': {
            '1_night': len([x for x in durations if x == 1]),
            '2-3_nights': len([x for x in durations if 2 <= x <= 3]),
            '4-7_nights': len([x for x in durations if 4 <= x <= 7]),
            '7+_nights': len([x for x in durations if x > 7])
        }
    }
    
    patterns['preferred_room_types'] = room_types
    patterns['booking_channels'] = channels
    patterns['peak_seasons'] = monthly_bookings
    patterns['cancellation_rate'] = round((cancelled / total_bookings * 100), 2) if total_bookings > 0 else 0
    
    # AI Insights
    insights = []
    
    avg_lead = patterns['booking_lead_time']['average_days']
    if avg_lead < 7:
        insights.append("Misafirleriniz çoğunlukla son dakika rezervasyonu yapıyor. Esnek iptal politikası düşünün.")
    elif avg_lead > 30:
        insights.append("Misafirleriniz önceden planlama yapıyor. Erken rezervasyon indirimleri sunun.")
    
    if patterns['cancellation_rate'] > 15:
        insights.append(f"İptal oranı yüksek (%{patterns['cancellation_rate']}). İptal koşullarını gözden geçirin.")
    
    avg_stay = patterns['stay_duration']['average_nights']
    if avg_stay < 2:
        insights.append("Kısa süreli konaklamalar yaygın. Transit misafir profili olabilir.")
    elif avg_stay > 5:
        insights.append("Uzun süreli konaklamalar yaygın. Haftalık paket fiyatları sunun.")
    
    return {
        'success': True,
        'total_bookings_analyzed': total_bookings,
        'patterns': patterns,
        'ai_insights': insights,
        'generated_at': datetime.now().isoformat()
    }



