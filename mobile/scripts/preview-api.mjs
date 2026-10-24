import { createServer } from 'node:http';
import { pathToFileURL } from 'node:url';

// Isolated fixture service. It has no database, file writes, proxy, external
// fetch, or request logging. The dummy tokens are invalid on the live service.
export const DEMO_TOKEN = 'syroce-local-preview-only-v1';
const DEMO_REFRESH = 'syroce-local-preview-refresh-only-v1';
const READ_ONLY = 'Salt okunur demo; canlı veri değişmez';
const DEMO_LOGIN = 'Bu yerel önizleme yalnızca demo@syroce.local / demo-mobile hesabını kabul eder. Gerçek hesap bilgileri kullanmayın.';
const ORIGINS = new Set(['http://localhost:8086', 'http://127.0.0.1:8086']);

function fixtures(now = new Date()) {
  const day = (offset = 0) => {
    const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  };
  const user = { id: 'demo-staff', tenant_id: 'demo-hotel', hotel_id: 'demo-hotel', name: 'Demo Kullanıcı', username: 'demo', role: 'admin', email: 'demo@syroce.local' };
  const rooms = [
    { id: 'room-201', room_number: '201', room_type: 'Deluxe', floor: 2, status: 'occupied', housekeeping_status: 'inspected' },
    { id: 'room-202', room_number: '202', room_type: 'Standart', floor: 2, status: 'available', housekeeping_status: 'inspected' },
    { id: 'room-204', room_number: '204', room_type: 'Deluxe', floor: 2, status: 'available', housekeeping_status: 'inspection', housekeeping: { state: 'waiting', task_type: 'inspection', assigned_to_name: 'Elif', elapsed_minutes: null } },
    { id: 'room-205', room_number: '205', room_type: 'Suit', floor: 2, status: 'maintenance', housekeeping_status: 'dirty' },
  ];
  const arrival = { id: 'booking-ayse', guest_id: 'guest-ayse', guest_name: 'Ayşe Yılmaz', booking_number: 'DEMO-001', room_id: 'room-204', room_number: '204', room_type: 'Deluxe', status: 'confirmed', check_in: day(), check_out: day(2), total_amount: 8000, collected_amount: 3000, paid_amount: 3000, balance: 5000, currency: 'TRY', adults: 2, children: 0, channel: 'direct' };
  const inhouse = { ...arrival, id: 'booking-murat', guest_id: 'guest-murat', booking_number: 'DEMO-002', guest_name: 'Murat Demir', room_id: 'room-201', room_number: '201', status: 'checked_in', check_in: day(-1), check_out: day(1) };
  const bookings = [arrival, inhouse];
  const payments = [{ id: 'demo-payment', folio_id: 'guest-folio', amount: 3000, currency: 'TRY', method: 'card', payment_type: 'interim', status: 'paid', processed_at: now.toISOString() }];
  const folio = { id: 'guest-folio', folio_number: 'DEMO-F001', folio_type: 'guest', payor_type: 'guest', status: 'open', currency: 'TRY', balance: 5000, charges: [], payments };
  const task = { id: 'task-inspect', kind: 'housekeeping', title: '204 numaralı odanın kontrolü', room_id: 'room-204', room_number: '204', task_type: 'inspection', status: 'pending', assigned_to: 'Elif', priority: 'high', created_at: new Date(now.getTime() - 8 * 60000).toISOString() };
  const guests = bookings.map((booking) => ({ id: booking.guest_id, full_name: booking.guest_name, name: booking.guest_name, vip_status: false }));
  return { day, user, rooms, arrival, inhouse, bookings, payments, folio, task, guests };
}

// Export the dispatcher for validation without starting the interactive server.
export function previewResponse({ method = 'GET', path = '/', authorization, body, now }) {
  const url = new URL(path, 'http://127.0.0.1:18999');
  const pathname = url.pathname;
  const data = fixtures(now);
  const ok = (value) => ({ status: 200, body: value });
  const fail = (status, detail) => ({ status, body: { detail } });
  if (method === 'POST' && pathname === '/api/auth/login') {
    if (body?.email !== 'demo@syroce.local' || body?.password !== 'demo-mobile') return fail(401, DEMO_LOGIN);
    return ok({ access_token: DEMO_TOKEN, refresh_token: DEMO_REFRESH, token_type: 'bearer', expires_in: 86400, user: data.user });
  }
  if (method === 'POST' && pathname === '/api/auth/refresh-token') {
    if (body?.refresh_token !== DEMO_REFRESH && authorization !== `Bearer ${DEMO_TOKEN}`) return fail(401, DEMO_LOGIN);
    return ok({ access_token: DEMO_TOKEN, refresh_token: DEMO_REFRESH, token_type: 'bearer', expires_in: 86400 });
  }
  if (authorization !== `Bearer ${DEMO_TOKEN}`) return fail(401, DEMO_LOGIN);
  if (method === 'POST' && pathname === '/api/auth/logout') return ok({ message: 'Demo oturumu kapatıldı.' });
  // The production risk API uses POST for a read-only calculation. This one
  // allowlisted fixture read never changes a booking or stores its body.
  if (method === 'POST' && pathname === '/api/pms/no-show-risk/bulk') return ok({ results: {} });
  if (!['GET', 'HEAD'].includes(method)) return fail(409, READ_ONLY);
  if (pathname === '/api/auth/me') return ok(data.user);
  if (pathname === '/api/mobile/hub/today') return ok({ date: data.day(), hotel_name: 'Demo Otel · Yerel Önizleme', open_tasks: 1, urgent_tasks: 1, pending_approvals: 0, unread_feed: 0, tasks_preview: [data.task], occupancy_pct: 25, occupied_rooms: 1, total_rooms: 4, check_ins: 1, check_outs: 0, open_faults: 1 });
  if (pathname === '/api/mobile/hub/my-tasks') return ok({ tasks: [data.task], count: 1, by_kind: { housekeeping: 1, maintenance: 0 } });
  if (pathname === '/api/mobile/hub/feed') return ok({ items: [], count: 0, offset: 0, limit: 50, has_more: false, unread_count: 0 });
  if (pathname === '/api/mobile/hub/approvals') return ok({ categories: [], total: 0 });
  if (pathname === '/api/mobile/hub/search') return ok({ query: url.searchParams.get('q') || '', guests: data.guests, reservations: data.bookings, rooms: data.rooms, total: 8 });
  if (pathname === '/api/messaging/internal/conversations') return ok({ conversations: [], total_count: 0 });
  if (pathname.startsWith('/api/messaging/internal/thread/')) return ok({ messages: [], count: 0 });
  if (pathname === '/api/arrivals/today') return ok({ arrivals: [data.arrival] });
  if (pathname === '/api/unified/today-departures') return ok({ departures: [] });
  if (pathname === '/api/unified/in-house') return ok({ in_house: [data.inhouse], count: 1 });
  if (pathname === '/api/pms/rooms') return ok(data.rooms);
  if (pathname === '/api/pms/room-blocks') return ok([]);
  if (pathname === '/api/housekeeping/mobile/room-tasks') return ok({ tasks: [data.task] });
  if (pathname === '/api/housekeeping/mobile/staff') return ok({ staff: [{ id: 'staff-elif', name: 'Elif', role: 'housekeeping' }] });
  if (pathname === '/api/pms/bookings' || pathname === '/api/reservations/search') {
    let records = data.bookings;
    const start = url.searchParams.get('start_date');
    const end = url.searchParams.get('end_date');
    if (start) records = records.filter((record) => record.check_out > start);
    if (end) records = records.filter((record) => record.check_in < end);
    if (url.searchParams.get('id')) records = records.filter((record) => record.id === url.searchParams.get('id'));
    if (url.searchParams.get('status')) records = records.filter((record) => record.status === url.searchParams.get('status'));
    if (url.searchParams.get('room_number')) records = records.filter((record) => record.room_number === url.searchParams.get('room_number'));
    const query = (url.searchParams.get('query') || '').toLocaleLowerCase('tr-TR');
    if (query) records = records.filter((record) => `${record.guest_name} ${record.booking_number} ${record.room_number}`.toLocaleLowerCase('tr-TR').includes(query));
    const offset = Math.max(0, Number(url.searchParams.get('offset')) || 0);
    const limit = Math.min(1000, Math.max(1, Number(url.searchParams.get('limit')) || 200));
    const page = records.slice(offset, offset + limit);
    return ok(pathname === '/api/reservations/search' ? { bookings: page, count: records.length } : page);
  }
  if (pathname === '/api/pms/guests/search' || pathname === '/api/pms/guests') return ok({ guests: data.guests });
  if (pathname === '/api/pms/rooms/availability') {
    const checkIn = url.searchParams.get('check_in') || data.day();
    const checkOut = url.searchParams.get('check_out') || data.day(1);
    return ok(data.rooms.map((room) => {
      const occupied = data.bookings.some((booking) => booking.room_id === room.id && booking.check_out > checkIn && booking.check_in < checkOut);
      const blocked = room.status === 'maintenance';
      return { ...room, available: !occupied && !blocked, occupancy_status: occupied ? 'occupied' : blocked ? 'blocked' : 'free', blocks: [] };
    }));
  }
  const reservationMatch = pathname.match(/^\/api\/pms\/reservations\/([^/]+)\/(full-detail)$/)
    || pathname.match(/^\/api\/reservations\/([^/]+)\/(details-enhanced|ota-details)$/);
  if (reservationMatch) {
    const booking = data.bookings.find((record) => record.id === decodeURIComponent(reservationMatch[1]));
    if (!booking) return fail(404, 'Demo rezervasyonu bulunamadı.');
    if (reservationMatch[2] === 'details-enhanced') return ok({ booking_id: booking.id, status: booking.status, rate_breakdown: { total_amount: booking.total_amount } });
    if (reservationMatch[2] === 'ota-details') return ok({ booking_id: booking.id, source_of_booking: 'direct' });
    return ok({ booking, guest: { name: booking.guest_name }, room: data.rooms.find((room) => room.id === booking.room_id), folios: [data.folio], payments: data.payments, charges: [], summary: { gross_total: 8000, reservation_total_due: 5000 }, read_only: false });
  }
  if (pathname.startsWith('/api/frontdesk/folio/') || pathname === '/api/folio/guest-folio') return ok(data.folio);
  if (pathname === '/api/folio/list') return ok({ folios: [{ ...data.folio, guest_name: data.arrival.guest_name, room_number: '204' }], total: 1 });
  const bookingMatch = pathname.match(/^\/api\/pms\/bookings\/([^/]+)$/);
  if (bookingMatch) return data.bookings.find((booking) => booking.id === bookingMatch[1]) ? ok(data.bookings.find((booking) => booking.id === bookingMatch[1])) : fail(404, 'Demo rezervasyonu bulunamadı.');
  if (pathname === '/api/reports/finance-snapshot') return ok({ report_date: data.day(), business_date: data.day(), pending_ar: { total: 5000, by_currency: { TRY: { total: 5000, '0-30_days': 5000, '30-60_days': 0, '60_plus_days': 0, overdue_invoices_count: 0 } }, overdue_breakdown: { '0-30_days': 5000, '30-60_days': 0, '60_plus_days': 0 }, overdue_invoices_count: 0 }, todays_collections: { currency: 'TRY', amount: 3000, payment_count: 1 }, mtd_collections: { currency: 'TRY', amount: 3000, collection_rate_percentage: 37.5 }, accounting_invoices: { pending_count: 0, pending_total: 0 } });
  return fail(404, 'Bu ekran için yerel demo verisi bulunmuyor.');
}

export function createPreviewServer() {
  return createServer(async (request, response) => {
    const origin = request.headers.origin;
    const localPort = request.socket.localPort;
    const allowedHosts = new Set([`localhost:${localPort}`, `127.0.0.1:${localPort}`]);
    const headers = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', Vary: 'Origin' };
    if (ORIGINS.has(origin)) {
      headers['Access-Control-Allow-Origin'] = origin;
      headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Idempotency-Key';
      headers['Access-Control-Allow-Methods'] = 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS';
    }
    const send = (status, body) => { response.writeHead(status, headers); response.end(request.method === 'HEAD' ? undefined : JSON.stringify(body)); };
    if (!allowedHosts.has(request.headers.host) || (origin && !ORIGINS.has(origin))) {
      request.resume();
      send(403, { detail: 'Yalnızca yerel önizleme bağlantısına izin verilir.' });
      return;
    }
    if (request.method === 'OPTIONS') { request.resume(); send(200, {}); return; }
    let body;
    if (request.method === 'POST' && request.url?.startsWith('/api/auth/')) {
      try {
        let size = 0;
        const chunks = [];
        for await (const chunk of request) {
          size += chunk.length;
          if (size > 4096) { send(413, { detail: 'Demo isteği çok büyük.' }); return; }
          chunks.push(chunk);
        }
        body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : undefined;
      } catch { send(400, { detail: 'Geçersiz demo isteği.' }); return; }
    } else request.resume();
    try {
      const result = previewResponse({ method: request.method, path: request.url, authorization: request.headers.authorization, body });
      send(result.status, result.body);
    } catch { send(400, { detail: 'Geçersiz demo isteği.' }); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = createPreviewServer();
  server.on('error', () => { console.error('Yerel demo API başlatılamadı; 18999 bağlantı noktasını kontrol edin.'); process.exitCode = 1; });
  server.listen(18999, '127.0.0.1', () => {
    console.log('Salt okunur demo API: http://127.0.0.1:18999');
    console.log('Demo giriş: demo@syroce.local / demo-mobile');
    console.log('Canlı sunucuya bağlanılmaz; işlemler gerçek verileri değiştirmez.');
  });
}
