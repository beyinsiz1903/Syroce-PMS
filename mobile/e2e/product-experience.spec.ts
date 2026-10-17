import { expect, test, type Page } from '@playwright/test';

const user = { id: 'demo-staff', tenant_id: 'demo-hotel', name: 'Ömer Biliş', role: 'admin', email: 'staff@example.invalid' };
const rooms = [
  { id: 'room-201', room_number: '201', room_type: 'Deluxe', floor: 2, status: 'occupied', housekeeping_status: 'inspected' },
  { id: 'room-202', room_number: '202', room_type: 'Standart', floor: 2, status: 'available', housekeeping_status: 'inspected' },
  { id: 'room-204', room_number: '204', room_type: 'Deluxe', floor: 2, status: 'available', housekeeping_status: 'inspection', housekeeping: { task_type: 'inspection', assigned_to_name: 'Elif', elapsed_minutes: 8 } },
  { id: 'room-205', room_number: '205', room_type: 'Suit', floor: 2, status: 'maintenance', housekeeping_status: 'dirty' },
];
const arrival = { id: 'booking-ayse', guest_name: 'Ayşe Yılmaz', booking_number: 'DEMO-001', room_id: 'room-204', room_number: '204', room_type: 'Deluxe', status: 'confirmed', check_in: '2026-10-16', check_out: '2026-10-18', total_amount: 8000, collected_amount: 3000, balance: 5000, currency: 'TRY', adults: 2, children: 0, channel: 'direct' };
const inhouse = { ...arrival, id: 'booking-murat', guest_name: 'Murat Demir', room_id: 'room-201', room_number: '201', status: 'checked_in', check_in: '2026-10-15', check_out: '2026-10-17' };
type World = {
  failArrivals?: boolean; failBlocks?: boolean; malformedBlocks?: boolean; manyBookings?: boolean; currency?: string;
  reservationTotal?: number; collectedAmount?: number; omitCurrency?: boolean;
  userRole?: string;
  separatePayer?: boolean; missingMoney?: boolean; writes: Array<{ path: string; body: unknown; key?: string }>;
  calendarOffsets: number[];
  newPaymentAmount?: number;
  subscriptionStatus?: number;
};

async function installFixtures(page: Page, options: Partial<World> = {}) {
  const world: World = { writes: [], calendarOffsets: [], ...options };
  const sessionUser = { ...user, role: world.userRole || user.role };
  await page.clock.install({ time: new Date('2026-10-16T06:41:00Z') });
  await page.addInitScript(({ user }) => {
    localStorage.setItem('syroce.auth.token', 'isolated-ui-fixture');
    localStorage.setItem('syroce.auth.token_issued_at', String(Date.now()));
    localStorage.setItem('syroce.auth.user', JSON.stringify(user));
    localStorage.setItem('theme_mode', 'light');
  }, { user: sessionUser });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const currency = world.omitCurrency ? undefined : world.currency || 'TRY';
    const totalAmount = world.reservationTotal ?? arrival.total_amount;
    const collectedAmount = world.collectedAmount ?? arrival.collected_amount;
    const balance = Math.round((totalAmount - collectedAmount - (world.newPaymentAmount || 0)) * 100) / 100;
    const currentArrival = { ...arrival, total_amount: totalAmount, collected_amount: collectedAmount, balance, currency };
    const currentInhouse = { ...inhouse, total_amount: totalAmount, collected_amount: collectedAmount, balance, currency };
    const reply = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' },
      body: JSON.stringify(body),
    });
    if (request.method() === 'OPTIONS') return reply({});
    if (!['GET', 'HEAD'].includes(request.method())) {
      world.writes.push({ path, body: request.postDataJSON(), key: request.headers()['idempotency-key'] });
    }
    if (path === '/api/auth/me') return reply(sessionUser);
    if (path === '/api/guest/bookings') return reply({
      active_bookings: [{ ...currentArrival, confirmation_number: 'DEMO-001', hotel: { property_name: 'The Canyon Kartepe' }, room: rooms[2] }],
      past_bookings: [],
    });
    if (path === '/api/subscription/current') return reply(world.subscriptionStatus === 403 ? { detail: 'Fixture access denied' } : {
      modules: { spa: true, mice: false, pos_fnb: true, revenue_management: true }, entitlements: {},
    }, world.subscriptionStatus || 200);
    if (path === '/api/mobile/hub/today') return reply({ date: '2026-10-16', hotel_name: 'The Canyon Kartepe', open_tasks: 3, urgent_tasks: 1, pending_approvals: 0, unread_feed: 0, tasks_preview: [] });
    if (path === '/api/mobile/hub/my-tasks') return reply({ tasks: [], count: 0, by_kind: { housekeeping: 0, maintenance: 0 } });
    if (path === '/api/mobile/hub/feed') return reply({ items: [], count: 0, has_more: false, unread_count: 0 });
    if (path === '/api/messaging/internal/conversations') return reply({ conversations: [], total_count: 0 });
    if (path === '/api/messaging/guest-requests/access') return reply({ can_view: true });
    if (path === '/api/messaging/guest-requests/threads') return reply({ threads: [], total_unread: 0 });
    if (path === '/api/arrivals/today') return reply(world.failArrivals ? { detail: 'fixture outage' } : { arrivals: [currentArrival] }, world.failArrivals ? 503 : 200);
    if (path === '/api/unified/today-departures') return reply({ departures: [currentInhouse] });
    if (path === '/api/unified/in-house') return reply({ in_house: [currentInhouse], count: 1 });
    if (path === '/api/pms/no-show-risk/bulk') return reply({ results: {} });
    if (path === '/api/pms/rooms') return reply(rooms);
    if (path === '/api/pms/rooms/availability') return reply(rooms.map((room) => ({ ...room, available: room.id === 'room-202', occupancy_status: room.id === 'room-202' ? 'free' : 'occupied' })));
    if (path === '/api/pms/room-blocks') return reply(world.failBlocks ? { detail: 'fixture blocks outage' } : world.malformedBlocks ? { incomplete: true } : [], world.failBlocks ? 503 : 200);
    if (path === '/api/housekeeping/mobile/room-tasks') return reply({ tasks: [{ id: 'task-inspect', room_id: 'room-204', task_type: 'inspection', status: 'pending', assigned_to: 'Elif' }] });
    if (path === '/api/housekeeping/mobile/staff') return reply({ staff: [{ id: 'staff-elif', name: 'Elif' }] });
    if (path === '/api/pms/bookings' && request.method() === 'GET') {
      const offset = Number(url.searchParams.get('offset') || 0);
      world.calendarOffsets.push(offset);
      const list = world.manyBookings ? [
        ...Array.from({ length: 200 }, (_, i) => ({ ...currentArrival, id: 'unassigned-' + i, room_id: undefined, room_number: undefined })),
        { ...currentInhouse, id: 'beyond-recent-50' },
      ] : [currentArrival, currentInhouse];
      return reply(list.slice(offset, offset + Number(url.searchParams.get('limit') || 200)));
    }
    if (path === '/api/reservations/search') return reply({ bookings: [currentArrival, currentInhouse], count: 2 });
    if (path.endsWith('/details-enhanced')) return reply({ booking_id: arrival.id, status: 'confirmed', rate_breakdown: { total_amount: totalAmount } });
    if (path.endsWith('/ota-details')) return reply({ booking_id: arrival.id, source_of_booking: 'direct' });
    if (path.endsWith('/full-detail')) {
      const record = path.includes('/booking-murat/') ? currentInhouse : currentArrival;
      return reply({
        booking: { ...record, ...(world.separatePayer ? { agency_id: 'demo-agency', agency_name: 'Atlas Travel' } : {}) },
        guest: { name: record.guest_name }, room: rooms.find((room) => room.id === record.room_id),
        folios: [{ id: 'guest-folio', folio_type: 'guest', payor_type: 'guest', status: 'open', currency }],
        payments: [
          { id: 'demo-payment', folio_id: 'guest-folio', amount: collectedAmount, currency, method: 'card', payment_type: 'interim', status: 'paid', processed_at: '2026-10-16T06:32:00Z' },
          ...(world.newPaymentAmount ? [{ id: 'new-demo-payment', folio_id: 'guest-folio', amount: world.newPaymentAmount, currency, method: 'card', payment_type: 'interim', status: 'paid', processed_at: '2026-10-16T06:41:00Z' }] : []),
        ],
        charges: [],
        summary: world.missingMoney ? {} : { gross_total: totalAmount, reservation_total_due: balance },
        read_only: false,
      });
    }
    if (path === '/api/frontdesk/folio/booking-ayse/payment' && request.method() === 'POST') {
      const body = request.postDataJSON();
      world.newPaymentAmount = body.amount;
      return reply({ id: 'new-demo-payment', folio_id: 'guest-folio', ...body, status: 'paid' });
    }
    if (path === '/api/pms/bookings/' + arrival.id) return reply(currentArrival);
    // Keep unexpected reads visible to the test without hitting any network.
    return reply({ detail: 'Unmocked isolated UI endpoint: ' + path }, 404);
  });
  return world;
}

async function capture(page: Page, name: string) {
  // Let deliberate entry animations settle before evaluating the screenshot.
  await page.waitForTimeout(500);
  await page.screenshot({ path: test.info().outputPath(name + '.png'), fullPage: true });
}

test('Today has honest KPIs and five focused tabs; messages and More remain usable', async ({ page }) => {
  await installFixtures(page);
  await page.goto('/(frontdesk)');
  await expect(page.getByTestId('today-summary-0')).toContainText('1');
  await expect(page.getByRole('tab')).toHaveCount(5);
  await capture(page, '01-today');
  await page.getByTestId('frontdesk-tab-messages').click();
  await expect(page.getByRole('tab')).toHaveCount(5);
  await page.getByRole('tab', { name: /Diğer/ }).click();
  await expect(page.getByTestId('more-reservations')).toBeVisible();
  await expect(page.getByTestId('more-reports')).toBeVisible();
});

test('Today load failure is unavailable, never a successful zero', async ({ page }) => {
  await installFixtures(page, { failArrivals: true });
  await page.goto('/(frontdesk)');
  await expect(page.getByTestId('today-summary-0')).toContainText('—');
  await expect(page.getByTestId('today-summary-0')).not.toContainText('0');
});

test('Calendar renders all overlapping pages and preserves checkout-exclusive cells', async ({ page }) => {
  const world = await installFixtures(page, { manyBookings: true });
  await page.goto('/(frontdesk)/calendar');
  await expect(page.getByTestId('calendar-bar-beyond-recent-50')).toBeVisible();
  // Checked-in reservations must not be green (the legend means available).
  await expect(page.getByTestId('calendar-bar-beyond-recent-50')).toHaveCSS('background-color', 'rgb(37, 99, 235)');
  await expect(page.getByTestId('calendar-bar-beyond-recent-50')).toHaveAttribute('aria-label', /Giriş yaptı/);
  await expect(page.getByTestId('calendar-bar-beyond-recent-50')).toContainText('2 gece');
  expect(world.calendarOffsets).toContain(200);
  await expect(page.getByTestId('calendar-cell-room-201-2026-10-17')).toBeEnabled();
  await capture(page, '02-calendar');
});

test('Calendar block-read failure cannot expose free cells', async ({ page }) => {
  await installFixtures(page, { failBlocks: true });
  await page.goto('/(frontdesk)/calendar');
  await expect(page.getByTestId('calendar-error')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('calendar-grid')).toHaveCount(0);
});

test('A malformed successful block response is not interpreted as empty inventory', async ({ page }) => {
  await installFixtures(page, { malformedBlocks: true });
  await page.goto('/(frontdesk)/calendar');
  await expect(page.getByTestId('calendar-error')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('calendar-grid')).toHaveCount(0);
});

test('Rooms distinguish occupancy, inspection and maintenance', async ({ page }) => {
  await installFixtures(page);
  await page.goto('/(frontdesk)/rooms');
  await expect(page.getByTestId('smoke-rooms-search')).toBeVisible();
  await expect(page.getByText(/Kontrol bekliyor/).first()).toBeVisible();
  await expect(page.getByText(/Bakım/).first()).toBeVisible();
  await capture(page, '03-rooms');
});

test('Reservation uses verified currency and payment history', async ({ page }) => {
  await installFixtures(page, { currency: 'USD' });
  await page.goto('/(frontdesk)/reservation?id=booking-ayse');
  await expect(page.getByText('Ayşe Yılmaz').first()).toBeVisible();
  await expect(page.getByText('Rezervasyon açık bakiyesi')).toBeVisible();
  await expect(page.getByText(/5\.000,00/).first()).toBeVisible();
  await expect(page.getByText('Ödeme hareketleri')).toBeVisible();
  await expect(page.getByText('Kaydedildi')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain('₺');
  await capture(page, '04-reservation-payments');
});

for (const currency of ['USD', 'EUR']) {
  test(`${currency} API amounts survive list → detail → payment → checkout without FX or TRY relabeling`, async ({ page }) => {
    const world = await installFixtures(page, { currency, reservationTotal: 1234.56, collectedAmount: 234.56 });
    const symbol = currency === 'USD' ? /\$|USD/ : /€|EUR/;
    await page.goto('/(frontdesk)');
    await expect(page.getByTestId('today-booking-balance').first()).toContainText(symbol);
    await expect(page.getByTestId('today-booking-balance').first()).toContainText('1.000,00');
    await page.goto('/(frontdesk)/rooms');
    await expect(page.getByTestId('room-booking-balance-room-201')).toContainText(symbol);
    await expect(page.getByTestId('room-booking-balance-room-201')).toContainText('1.000,00');
    await page.goto('/(frontdesk)/reservations');
    const total = page.getByTestId('reservation-total-booking-ayse');
    await expect(total).toContainText('1.234,56');
    await expect(total).toContainText(symbol);
    await expect(total).not.toContainText('₺');
    await page.getByTestId('smoke-reservation-row').filter({ hasText: 'Ayşe Yılmaz' }).click();
    await expect(page.getByTestId('reservation-account-total')).toContainText('1.234,56');
    await expect(page.getByTestId('reservation-account-total')).toContainText(symbol);
    await expect(page.getByTestId('reservation-account-collected')).toContainText('234,56');
    await expect(page.getByTestId('reservation-account-balance')).toContainText('1.000,00');
    expect(await page.locator('body').innerText()).not.toMatch(/₺|\bTRY\b/);
    await capture(page, `reservation-${currency.toLowerCase()}`);

    await page.getByRole('button', { name: 'Ödeme Al', exact: true }).first().click();
    await page.getByRole('textbox', { name: `Tahsil edilecek tutar (${currency})` }).fill('200,12');
    await page.getByTestId('reservation-payment-submit').click();
    await expect(page.getByText('Ödeme kaydedildi')).toBeVisible();
    const payments = world.writes.filter((request) => request.path.endsWith('/payment'));
    expect(payments).toHaveLength(1);
    expect(payments[0].body).toEqual({ amount: 200.12, currency, method: 'card', payment_type: 'interim' });
    expect(payments[0].key).toMatch(/^mobile-payment-/);
    await expect(page.getByTestId('reservation-account-balance')).toContainText('799,88');

    await page.goto('/(frontdesk)/checkout?bookingId=booking-ayse');
    await expect(page.getByTestId('checkout-account-total')).toContainText('1.234,56');
    await expect(page.getByTestId('checkout-account-total')).toContainText(symbol);
    await expect(page.getByTestId('checkout-account-collected')).toContainText('434,68');
    await expect(page.getByTestId('checkout-account-balance')).toContainText('799,88');
    expect(await page.locator('body').innerText()).not.toMatch(/₺|\bTRY\b/);
  });
  test(`Guest ${currency} reservation list and detail keep the API's original 1234.56 price`, async ({ page }) => {
    const world = await installFixtures(page, { currency, reservationTotal: 1234.56, userRole: 'guest_app' });
    const symbol = currency === 'USD' ? /\$|USD/ : /€|EUR/;
    await page.goto('/(guest)');
    const total = page.getByTestId('guest-reservation-total-booking-ayse');
    await expect(total).toContainText('1.234,56');
    await expect(total).toContainText(symbol);
    await expect(total).not.toContainText('₺');
    await total.click();
    const summary = page.getByTestId('guest-reservation-account-summary');
    await expect(summary).toContainText('1.234,56');
    await expect(summary).toContainText(symbol);
    await expect(summary).not.toContainText('₺');
    expect(world.writes).toHaveLength(0);
  });
}

test('Missing reservation currency stays unknown instead of becoming TRY', async ({ page }) => {
  await installFixtures(page, { omitCurrency: true, reservationTotal: 1234.56, collectedAmount: 234.56 });
  await page.goto('/(frontdesk)/reservations');
  const total = page.getByTestId('reservation-total-booking-ayse');
  await expect(total).toContainText('1.234,56');
  await expect(total).toContainText('para birimi belirtilmemiş');
  await expect(total).not.toContainText('₺');
  await page.getByTestId('smoke-reservation-row').filter({ hasText: 'Ayşe Yılmaz' }).click();
  await expect(page.getByTestId('reservation-account-total')).toContainText('para birimi belirtilmemiş');
  await page.getByRole('button', { name: 'Ödeme Al', exact: true }).first().click();
  await expect(page.getByTestId('reservation-payment-submit')).toHaveCount(0);
});

test('Quick creation clearly discloses its actual TRY-only backend contract', async ({ page }) => {
  await installFixtures(page);
  await page.goto('/(frontdesk)/new-reservation');
  await expect(page.getByRole('textbox', { name: 'Toplam konaklama tutarı (TRY)' })).toBeVisible();
  await expect(page.getByText('Hızlı rezervasyonda tutar Türk lirası (TRY) olarak kaydedilir.')).toBeVisible();
  await page.goto('/(frontdesk)/walkin');
  await expect(page.getByRole('textbox', { name: 'Fiyat (TRY)' })).toBeVisible();
  await expect(page.getByText('Walk-in tutarı Türk lirası (TRY) olarak kaydedilir.')).toBeVisible();
});

test('Ambiguous agency debt cannot be posted as guest collection', async ({ page }) => {
  const world = await installFixtures(page, { separatePayer: true });
  await page.goto('/(frontdesk)/reservation?id=booking-ayse&panel=payment');
  await expect(page.getByText(/misafir ve acente \/ şirket tutarları ayrı doğrulanamıyor/).first()).toBeVisible();
  await expect(page.getByTestId('reservation-payment-submit')).toHaveCount(0);
  expect(world.writes.filter((request) => request.path.endsWith('/payment'))).toHaveLength(0);
});

test('Guest collection requires an explicit amount and preserves currency, method and request key', async ({ page }) => {
  const world = await installFixtures(page, { currency: 'USD' });
  await page.goto('/(frontdesk)/reservation?id=booking-ayse&panel=payment');
  const submit = page.getByTestId('reservation-payment-submit');
  await expect(submit).toBeDisabled();
  await page.getByRole('textbox', { name: 'Tahsil edilecek tutar (USD)' }).fill('2000');
  await submit.click();
  await expect(page.getByText('Ödeme kaydedildi')).toBeVisible();
  const payments = world.writes.filter((request) => request.path.endsWith('/payment'));
  expect(payments).toHaveLength(1);
  expect(payments[0].body).toEqual({ amount: 2000, method: 'card', payment_type: 'interim', currency: 'USD' });
  expect(payments[0].key).toMatch(/^mobile-payment-/);
  await expect(page.getByText('Rezervasyon açık bakiyesi').locator('..')).toContainText('3.000,00');
});

test('A newly assigned agency payer blocks collection at the final fresh read', async ({ page }) => {
  const world = await installFixtures(page);
  await page.goto('/(frontdesk)/reservation?id=booking-ayse&panel=payment');
  await page.getByRole('textbox', { name: 'Tahsil edilecek tutar (TRY)' }).fill('2000');
  world.separatePayer = true;
  await page.getByTestId('reservation-payment-submit').click();
  await expect(page.getByText(/misafir ve acente \/ şirket tutarları ayrı doğrulanamıyor/).first()).toBeVisible();
  expect(world.writes.filter((request) => request.path.endsWith('/payment'))).toHaveLength(0);
});

test('Notification utility preserves the operational bottom navigation', async ({ page }) => {
  await installFixtures(page);
  await page.goto('/(frontdesk)');
  await page.getByTestId('frontdesk-header-notifications').click();
  await expect(page.getByRole('tab')).toHaveCount(5);
  await expect(page.getByRole('tab', { name: /Takvim/ })).toBeVisible();
});

test('Demo catalog does not advertise unconnected departments as working modules', async ({ page }) => {
  test.skip(process.env.MOBILE_DEMO_UI !== '1', 'Requires the explicit loopback demo build.');
  await installFixtures(page);
  await page.goto('/(departments)');
  await expect(page.getByTestId('demo-preview-scope')).toBeVisible();
  await expect(page.getByText('Bu önizlemede yer almayanlar')).toBeVisible();
  await expect(page.getByTestId('dept-tile-spa')).toHaveCount(0);
  await page.getByRole('button', { name: 'Takvim · rezervasyonlar' }).click();
  await expect(page.getByTestId('calendar-screen')).toBeVisible();
  await expect(page.getByRole('tab')).toHaveCount(5);
});

test('Departments are grouped and respect verified subscription access', async ({ page }) => {
  test.skip(process.env.MOBILE_DEMO_UI === '1', 'Needs a non-demo bundle to exercise production navigation.');
  await installFixtures(page);
  await page.goto('/(departments)');
  await expect(page.getByTestId('departments-hub')).toBeVisible();
  await expect(page.getByTestId('department-group-operations')).toBeVisible();
  await expect(page.getByTestId('department-group-control')).toHaveCount(1);
  await expect(page.getByTestId('department-group-management')).toHaveCount(1);
  await expect(page.getByTestId('dept-tile-spa')).toBeEnabled();
  await expect(page.getByTestId('dept-tile-pos')).toBeEnabled();
  await expect(page.getByTestId('dept-tile-mice')).toBeDisabled();
  await expect(page.getByTestId('dept-tile-cashier')).toBeEnabled();
  await capture(page, '06-departments-production');
});

test('Subscription 403 does not remove core workflows or grant unknown paid modules', async ({ page }) => {
  test.skip(process.env.MOBILE_DEMO_UI === '1', 'Needs a non-demo bundle to exercise production navigation.');
  await installFixtures(page, { subscriptionStatus: 403 });
  await page.goto('/(departments)');
  await expect(page.getByTestId('department-access-notice')).toBeVisible();
  await expect(page.getByTestId('dept-tile-spa')).toBeDisabled();
  await expect(page.getByTestId('dept-tile-pos')).toBeDisabled();
  await expect(page.getByTestId('dept-tile-cashier')).toBeEnabled();
  await expect(page.getByTestId('dept-tile-maintenance')).toBeEnabled();
  await expect(page.getByTestId('dept-tile-hr')).toBeEnabled();
});

test('Operational reports never invent hotel-wide zeros when RBAC omits those fields', async ({ page }) => {
  await installFixtures(page);
  await page.goto('/(frontdesk)/reports');
  await expect(page.getByTestId('frontdesk-reports')).toBeVisible();
  for (const id of ['report-occupancy', 'report-occupied-rooms', 'report-arrivals', 'report-departures']) {
    await expect(page.getByTestId(id)).toContainText('—');
    await expect(page.getByTestId(id)).not.toContainText('0');
  }
  await expect(page.getByText('Açık görevim').locator('..')).toContainText('3');
  await expect(page.getByText('Öncelikli görevim').locator('..')).toContainText('1');
  await capture(page, '07-reports');
});
