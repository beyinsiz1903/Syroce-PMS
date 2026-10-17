import { expect, test, type Page } from '@playwright/test';

const BASE = '/api/messaging/guest-requests';
type World = { denied?: boolean; listFailure?: boolean; malformed?: boolean; threadFailure?: boolean; sendFailure?: boolean;
  role?: string; reads: string[]; writes: { path: string; body: any }[]; replies: Record<string, any[]>; readRooms: Set<string> };

async function install(page: Page, options: Partial<World> = {}) {
  const world: World = { reads: [], writes: [], replies: {}, readRooms: new Set(), ...options };
  const user = { id: 'request-staff', tenant_id: 'request-hotel', name: 'Ömer', role: world.role || 'admin' };
  await page.clock.install({ time: new Date('2026-10-17T10:00:00Z') });
  await page.addInitScript(user => {
    localStorage.setItem('syroce.auth.token', 'isolated-request-test');
    localStorage.setItem('syroce.auth.token_issued_at', String(Date.now()));
    localStorage.setItem('syroce.auth.user', JSON.stringify(user));
    localStorage.setItem('theme_mode', 'light');
  }, user);
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' }, body: JSON.stringify(data) });
    if (request.method() === 'OPTIONS') return reply({});
    if (request.method() === 'GET') world.reads.push(path);
    else world.writes.push({ path, body: request.postDataJSON() });
    if (path === '/api/auth/me') return reply(user);
    if (path === '/api/subscription/current') return reply({ modules: {}, entitlements: {} });
    if (path === BASE + '/access') return reply({ can_view: !world.denied });
    if (path === BASE + '/threads') {
      if (world.listFailure) return reply({ detail: 'Talep servisine ulaşılamadı.' }, 500);
      if (world.malformed) return reply({ conversations: [] });
      return reply({ threads: ['201', '202', 'WA'].map((number, i) => ({
        room_id: number === 'WA' ? 'wa_905000000000' : 'room-' + number, room_number: number,
        last_body: i === 0 ? 'İki ilave havlu rica ediyoruz.' : 'Klima kontrolü', last_category: i === 0 ? 'rooms' : 'technical',
        last_created_at: '2026-10-17T09:00:00Z', last_sender_type: 'guest', total: 1,
        unread: number === '201' && !world.readRooms.has('room-201') ? 1 : number === 'WA' ? 9 : 0,
      })), total_unread: 10 });
    }
    const thread = path.match(/\/threads\/(room-20[12])(?:\/(reply|mark-read))?$/);
    if (thread) {
      const [, roomId, action] = thread;
      if (action === 'mark-read') { world.readRooms.add(roomId); return reply({ success: true, modified: 1 }); }
      if (action === 'reply') {
        if (world.sendFailure) return reply({ detail: 'Yanıt gönderilemedi; yeniden deneyin.' }, 500);
        const message = { id: 'reply-' + world.writes.length, room_id: roomId, sender_type: 'staff', sender_name: 'Ömer',
          body: request.postDataJSON().message, created_at: '2026-10-17T10:01:00Z', read: true };
        (world.replies[roomId] ||= []).push(message);
        return reply({ success: true, message });
      }
      if (world.threadFailure) return reply({ detail: 'Erişim reddedildi.' }, 403);
      return reply({ room_id: roomId, room_number: roomId.slice(-3), messages: [
        { id: 'qr-' + roomId, room_id: roomId, body: roomId === 'room-201' ? 'İki ilave havlu rica ediyoruz.' : 'Klima çalışmıyor.',
          sender_type: 'guest', created_at: '2026-10-17T09:00:00Z', category: roomId === 'room-201' ? 'rooms' : 'technical',
          request_id: 'request-' + roomId, read: world.readRooms.has(roomId) }, ...(world.replies[roomId] || []),
      ] });
    }
    if (path === '/api/mobile/hub/today') return reply({ open_tasks: 0, unread_feed: 0, tasks_preview: [] });
    if (path === '/api/mobile/hub/feed') return reply({ items: [], count: 0, unread_count: 0 });
    return reply({}); // All traffic intercepted; never touch a real hotel.
  });
  return world;
}

async function open(page: Page) {
  await page.goto('/(frontdesk)/messages');
  await expect(page.getByTestId('smoke-home-messages')).toBeVisible();
}

test('room QR requests replace personnel chat; room counts and search exclude WhatsApp', async ({ page }) => {
  const world = await install(page);
  await open(page);
  await expect(page.getByTestId('guest-request-room-room-201')).toContainText('İki ilave havlu');
  await expect(page.getByText('2 oda görüşmesi')).toBeVisible();
  await expect(page.getByText('1 okunmamış', { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('guest-request-inbox.png'), fullPage: true });
  await expect(page.getByText('WA', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Okunmamış', exact: true }).click();
  await expect(page.getByTestId('guest-request-room-room-202')).toHaveCount(0);
  await page.getByRole('button', { name: 'Tümü', exact: true }).click();
  await page.getByLabel('Oda veya talep ara').fill('202');
  await expect(page.getByTestId('guest-request-room-room-201')).toHaveCount(0);
  await expect(page.getByTestId('guest-request-room-room-202')).toBeVisible();
  expect(world.reads.some(path => path.includes('/messaging/internal'))).toBe(false);
});

test('opening a room marks only its requests read and replies into the same guest stream', async ({ page }) => {
  const world = await install(page);
  await open(page);
  await page.getByTestId('guest-request-room-room-201').click();
  await expect(page.getByTestId('guest-request-thread')).toContainText('Oda 201');
  await expect.poll(() => world.writes.some(row => row.path.endsWith('/room-201/mark-read'))).toBe(true);
  await page.getByTestId('guest-request-reply').fill('Havlularınız birazdan odanıza getirilecek.');
  await page.getByTestId('guest-request-send').click();
  await expect(page.getByTestId('guest-request-reply')).toHaveValue('');
  await expect(page.getByText('Havlularınız birazdan odanıza getirilecek.', { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('guest-request-thread.png'), fullPage: true });
  expect(world.writes.filter(row => row.path.endsWith('/reply'))).toEqual([{ path: BASE + '/threads/room-201/reply', body: { message: 'Havlularınız birazdan odanıza getirilecek.' } }]);
  await expect(page.getByTestId('guest-request-reply')).toHaveValue('');
});

test('denied roles never fetch guest content', async ({ page }) => {
  const world = await install(page, { denied: true });
  await open(page);
  await expect(page.getByTestId('guest-requests-no-access')).toBeVisible();
  expect(world.reads.includes(BASE + '/threads')).toBe(false);
  expect(world.writes).toHaveLength(0);
});

for (const condition of ['listFailure', 'malformed'] as const) {
  test(`${condition}: a failed or invalid response is not an empty inbox`, async ({ page }) => {
    await install(page, { [condition]: true });
    await open(page);
    await expect(page.getByTestId('guest-requests-error')).toBeVisible();
    await expect(page.getByText('Henüz misafir talebi yok')).toHaveCount(0);
  });
}

test('failed room fetch cannot mark messages read or permit a reply', async ({ page }) => {
  const world = await install(page, { threadFailure: true });
  await open(page);
  await page.getByTestId('guest-request-room-room-201').click();
  await expect(page.getByTestId('guest-requests-error')).toBeVisible();
  await expect(page.getByTestId('guest-request-send')).toBeDisabled();
  expect(world.writes).toHaveLength(0);
});

test('failed replies retain the draft and are not automatically resent', async ({ page }) => {
  const world = await install(page, { sendFailure: true });
  await open(page);
  await page.getByTestId('guest-request-room-room-201').click();
  const input = page.getByTestId('guest-request-reply');
  await expect(input).toBeEnabled();
  await input.fill('Talebinizi aldık.');
  await page.getByTestId('guest-request-send').click();
  await expect(page.getByTestId('guest-request-send-error')).toBeVisible();
  await expect(input).toHaveValue('Talebinizi aldık.');
  expect(world.writes.filter(row => row.path.endsWith('/reply'))).toHaveLength(1);
  world.sendFailure = false;
  await page.getByTestId('guest-request-send').click();
  await expect(input).toHaveValue('');
});

test('switching rooms cannot send a draft to the next guest', async ({ page }) => {
  const world = await install(page);
  await open(page);
  await page.getByTestId('guest-request-room-room-201').click();
  await expect(page.getByTestId('guest-request-reply')).toBeEnabled();
  await page.getByTestId('guest-request-reply').fill('201 odasına özel taslak');
  await page.getByRole('button', { name: '← Misafir talepleri' }).click();
  await page.getByTestId('guest-request-room-room-202').click();
  await expect(page.getByTestId('guest-request-reply')).toHaveValue('');
  await expect(page.getByTestId('guest-request-thread')).toContainText('Klima çalışmıyor.');
  expect(world.writes.filter(row => row.path.endsWith('/reply'))).toHaveLength(0);
});

test('home shell also uses room requests, not personnel conversations', async ({ page }) => {
  const world = await install(page, { role: 'finance' });
  await page.goto('/(home)/messages');
  await expect(page.getByTestId('guest-request-room-room-201')).toBeVisible();
  await expect(page.getByTestId('smoke-tab-messages')).toContainText('Talepler');
  expect(world.reads.some(path => path.includes('/messaging/internal'))).toBe(false);
});

test('permission revocation hides cached guest content and disables further replies', async ({ page }) => {
  const world = await install(page);
  await open(page);
  await page.getByTestId('guest-request-room-room-201').click();
  await expect(page.getByTestId('guest-request-reply')).toBeEnabled();
  world.denied = true;
  await page.clock.fastForward(31000);
  await expect(page.getByTestId('guest-requests-no-access')).toBeVisible();
  await expect(page.getByTestId('guest-request-thread')).toHaveCount(0);
  await expect(page.getByTestId('guest-request-reply')).toHaveCount(0);
});
