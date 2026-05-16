// PMS E2E flow helpers — pilot tenant'a karşı gerçek API çağrıları.
// Tüm yardımcılar hata durumunda `{ ok:false, reason }` döner; spec'ler
// REVIEW/SKIP olarak kayıt yapar, asla hard-fail değildir.
// Test verisi E2E_<ts>_ prefix taşır → 20-recap cleanup hedefler.

import { safeGetJson, safePost } from './api.js';

const FAR_OFFSET_DAYS = 30;     // Lifecycle/folio testleri: bugünden uzak tarih → ops çakışmaz
const STAY_NIGHTS = 1;

function isoDateAddDays(days) {
    const d = new Date();
    d.setUTCHours(0, 0, 0, 0);
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
}

export function farFutureDates(offset = FAR_OFFSET_DAYS, nights = STAY_NIGHTS) {
    return { check_in: isoDateAddDays(offset), check_out: isoDateAddDays(offset + nights) };
}

export function todayDates(nights = 1) {
    return { check_in: isoDateAddDays(0), check_out: isoDateAddDays(nights) };
}

/**
 * Pilot'tan müsait bir oda seç. Verilen tarih aralığı için boş bir oda
 * bulunamazsa `{ ok:false }` döner.
 */
export async function pickAvailableRoom(api, { check_in, check_out }) {
    const r = await safeGetJson(api, `/api/pms/available-rooms?check_in=${check_in}&check_out=${check_out}`);
    if (!r.ok || !r.json) return { ok: false, status: r.status, reason: `available-rooms HTTP ${r.status}` };
    const rooms = Array.isArray(r.json.rooms) ? r.json.rooms : [];
    const pick = rooms[0] || (Array.isArray(r.json.all_rooms) ? r.json.all_rooms[0] : null);
    if (!pick || !pick.id) return { ok: false, status: r.status, reason: 'no_available_room' };
    return { ok: true, room: pick };
}

/**
 * Aynı tarih aralığı için N adet farklı müsait oda döndür. Room-move testi için
 * en az 2 farklı oda gerekir (kaynak + hedef).
 */
export async function pickNAvailableRooms(api, { check_in, check_out }, n = 2) {
    const r = await safeGetJson(api, `/api/pms/available-rooms?check_in=${check_in}&check_out=${check_out}`);
    if (!r.ok || !r.json) return { ok: false, status: r.status, reason: `available-rooms HTTP ${r.status}` };
    const rooms = Array.isArray(r.json.rooms) ? r.json.rooms : [];
    const pool = rooms.length >= n ? rooms : (Array.isArray(r.json.all_rooms) ? r.json.all_rooms : rooms);
    const picks = pool.filter((x) => x && x.id).slice(0, n);
    if (picks.length < n) return { ok: false, status: r.status, reason: `only_${picks.length}_available` };
    return { ok: true, rooms: picks };
}

export async function roomMove(api, bookingId, newRoomId, reason = 'E2E assign-room transition') {
    return safePost(api, '/api/pms-core/room-move', { booking_id: bookingId, new_room_id: newRoomId, reason });
}

/**
 * Takvim verisi — ReservationCalendar.jsx aynı endpoint'i tüketir:
 *   GET /api/pms/bookings?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=500
 * Booking calendar'da render'lanıyorsa bu sorgunun sonucunda yer almalı.
 */
export async function fetchCalendarBookings(api, { start_date, end_date }) {
    const r = await safeGetJson(api, `/api/pms/bookings?start_date=${start_date}&end_date=${end_date}&limit=500`);
    if (!r.ok || !r.json) return { ok: false, status: r.status, bookings: [] };
    const items = r.json.bookings || r.json.items || r.json.data || [];
    return { ok: true, status: r.status, bookings: items };
}

/**
 * Hızlı walk-in benzeri rezervasyon oluştur. Pilot guests/bookings koleksiyonu
 * yazılır → registry'e track et. Cleanup 20-recap'te /api/pms-core/cancel ile.
 */
export async function createTestBooking(api, { roomId, guestName, check_in, check_out, totalAmount = 100 }) {
    const r = await safePost(api, '/api/pms/quick-booking', {
        guest_name: guestName,
        room_id: roomId,
        check_in,
        check_out,
        total_amount: totalAmount,
    });
    if (!r.ok || !r.json) return { ok: false, status: r.status, reason: r.body?.slice(0, 200) || `HTTP ${r.status}` };
    // create_reservation_service.create return shape: booking_dict (id, ...).
    // /quick-booking ayrıca guest_name + room_number ekliyor.
    const bookingId = r.json.id || r.json.booking_id;
    if (!bookingId) return { ok: false, status: r.status, reason: 'no_booking_id_in_response' };
    // status = HTTP status (recorder.http alanı için); bookingStatus = business state.
    return { ok: true, bookingId, status: r.status, bookingStatus: r.json.status, raw: r.json };
}

export async function cancelBooking(api, bookingId, reason = 'E2E test cleanup') {
    return safePost(api, '/api/pms-core/cancel', { booking_id: bookingId, reason });
}

export async function checkInBooking(api, bookingId, overrideReason = 'E2E pilot smoke') {
    return safePost(api, '/api/pms-core/check-in', { booking_id: bookingId, override_reason: overrideReason });
}

export async function checkoutBooking(api, bookingId, force = true) {
    return safePost(api, '/api/pms-core/checkout', { booking_id: bookingId, force });
}

export async function addExtraCharge(api, bookingId, { description, amount, category = 'other', quantity = 1 }) {
    return safePost(api, `/api/pms/reservations/${bookingId}/add-extra-charge`, {
        description, amount, category, quantity,
    });
}

export async function voidCharge(api, chargeId, reason = 'E2E test reversal') {
    return safePost(api, '/api/pms-core/folio/void-charge', { charge_id: chargeId, reason });
}

/**
 * Booking'in folio'suna ödeme yaz. Test mock/sandbox değil — gerçek `record-payment`
 * endpoint'i çağrılır; gateway tetiklenmesin diye method='cash' (PCI-DSS sınırı
 * dışı) ya da 'internal' default tutulur.
 */
export async function recordPayment(api, bookingId, { amount, method = 'cash', payment_type = 'interim', reference, notes }) {
    return safePost(api, `/api/pms/reservations/${bookingId}/record-payment`, {
        amount, method, payment_type, reference, notes,
    });
}

/**
 * Ödeme geri al — folio.balance kaydedilen ödeme kadar geri yükselmeli.
 */
export async function voidPayment(api, paymentId, reason = 'E2E payment reversal') {
    return safePost(api, '/api/pms-core/folio/void-payment', { payment_id: paymentId, reason });
}

export async function getBookingDetail(api, bookingId) {
    return safeGetJson(api, `/api/pms/reservations/${bookingId}/full-detail`);
}

/**
 * Walk-in: tek POST ile guest + booking + atomic check-in.
 * Backend: /api/pms-core/walk-in (front_desk.walk_in).
 * Başarılı dönüş: { success:true, booking_id, folio_id, room_number, guest_id }.
 */
export async function walkIn(api, { roomId, guestName, nights = 1, rate = 1, guestPhone = '', guestEmail = '' }) {
    const r = await safePost(api, '/api/pms-core/walk-in', {
        room_id: roomId,
        nights,
        rate,
        guest_name: guestName,
        guest_phone: guestPhone,
        guest_email: guestEmail,
    });
    if (!r.ok || !r.json) return { ok: false, status: r.status, reason: r.body?.slice(0, 200) || `HTTP ${r.status}` };
    const bookingId = r.json.booking_id || r.json.id;
    if (!bookingId) return { ok: false, status: r.status, reason: 'no_booking_id_in_response' };
    return { ok: true, bookingId, status: r.status, raw: r.json };
}

/**
 * No-show: terminal-state işaretler. Pre: booking confirmed/guaranteed.
 * Backend: /api/pms-core/no-show (rsm.handle_no_show).
 * İkinci çağrı 400 + "Cannot mark reservation as no_show in 'no_show' state".
 */
export async function noShowBooking(api, bookingId) {
    return safePost(api, '/api/pms-core/no-show', { booking_id: bookingId });
}

