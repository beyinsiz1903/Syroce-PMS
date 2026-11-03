import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { notificationTarget } from '../notificationRoutes';
import { mobileTargetAllowed } from '../routeAccess';
import { authHarness, deferred, reply, tick } from '../../state/__tests__/authHarness';

const hk = { id: 'hk', tenant_id: 'local-hotel', role: 'housekeeping', effective_permissions: ['view_hk_board'], page_access: { housekeeping: true } };
const restricted = { id: 'staff', tenant_id: 'local-hotel', role: 'admin', effective_permissions: ['view_procurement'], page_access: { procurement: true } };

test('push routing uses current page/operation permissions instead of broad role names', () => {
  assert.equal(notificationTarget({ type: 'no_show_risk', booking_id: 'synthetic-booking' }, restricted), '/(home)');
  assert.equal(notificationTarget({ type: 'housekeeping_task' }, hk), '/(home)/tasks');
  assert.equal(notificationTarget({ type: 'damage_report' }, restricted), '/(home)');
  assert.equal(notificationTarget({ type: 'guest_message' }, hk), '/(home)/messages');
  assert.deepEqual(notificationTarget({ type: 'no_show_risk', booking_id: 'synthetic-booking' }, {
    ...restricted, effective_permissions: ['view_bookings', 'checkin'], page_access: { bookings: true },
  }), { pathname: '/(frontdesk)/checkin', params: { bookingId: 'synthetic-booking' } });
});

test('old or cross-tenant OS notifications cannot route a new logged-in account', () => {
  const payload = { type: 'housekeeping_task', user_id: 'hk', tenant_id: 'local-hotel' };
  assert.equal(notificationTarget(payload, hk, true), '/(home)/tasks');
  assert.equal(notificationTarget({ ...payload, tenant_id: 'another-hotel' }, hk), null);
  assert.equal(notificationTarget({ ...payload, user_id: 'previous-user' }, hk), null);
  assert.equal(notificationTarget({ type: 'housekeeping_task' }, hk, true), null);
  assert.equal(notificationTarget(payload, null), null);
});

test('guest push never opens staff flows and unknown routes are not navigation grants', () => {
  assert.equal(notificationTarget({ type: 'maintenance_task' }, { role: 'guest' }), '/(guest)');
  assert.equal(mobileTargetAllowed(hk, '/(home)/typo'), false);
  assert.equal(mobileTargetAllowed(hk, 'https://outside.example/(home)/tasks'), false);
  assert.equal(mobileTargetAllowed(hk, '/(home)/tasks?filter=open#top'), true);
  assert.equal(mobileTargetAllowed(hk, '/(frontdesk)/reservation/unsupported-id'), false);
});

test('background registration never requests an OS permission; approved devices register normally', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  h.notifications.permission = 'undetermined';
  const push = h.load('notifications/push');
  assert.equal(await push.registerForPush({ requestPermission: false }), null);
  assert.equal(h.notifications.requested, 0);
  assert.equal(h.calls.some(c => c.path === '/api/notifications/push/register'), false);
  h.notifications.permission = 'granted';
  assert.ok(await push.registerForPush({ requestPermission: false }));
  assert.equal(h.calls.filter(c => c.path === '/api/notifications/push/register').length, 1);
  assert.equal(push.getLastPushStatus(), 'registered');
});

test('unmounted or replaced notification listeners cannot replay late cold-start navigation', async () => {
  const h = authHarness();
  const push = h.load('notifications/push');
  const waiting = deferred();
  h.notifications.getLastNotificationResponseAsync = () => waiting.promise;
  const routes: unknown[] = [];
  const detach = push.attachPushListeners({ push: (route: unknown) => routes.push(route) }, hk);
  detach();
  waiting.resolve({ actionIdentifier: 'default', notification: { request: { identifier: 'synthetic-notification', content: {
    data: { type: 'housekeeping_task', user_id: hk.id, tenant_id: hk.tenant_id },
  } } } });
  await tick();
  assert.deepEqual(routes, []);
});

test('a foreground 401 from an old listener cannot direct the replacement account', async () => {
  const h = authHarness();
  const push = h.load('notifications/push');
  const routes: unknown[] = [];
  const detach = push.attachPushListeners({ push: (route: unknown) => routes.push(route) }, hk);
  h.session.beginAuthSession();
  h.notifications.listener({ actionIdentifier: 'default', notification: { request: { identifier: 'synthetic', content: { data: { type: 'housekeeping_task' } } } } });
  await tick();
  assert.deepEqual(routes, []);
  detach();
});

test('root wires registration, listeners and foreground identity revalidation, without prompting on sign-in', () => {
  const root = readFileSync('app/_layout.tsx', 'utf8');
  assert.match(root, /attachPushListeners\(router, user\)/);
  assert.match(root, /registerForPush\(\{ requestPermission: false \}\)/);
  assert.match(root, /resumed && auth.user && !auth.loading/);
  assert.match(root, /void auth.hydrate\(\)/);
});
