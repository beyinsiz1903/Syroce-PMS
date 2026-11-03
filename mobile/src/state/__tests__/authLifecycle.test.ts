import assert from 'node:assert/strict';
import test from 'node:test';
import { authHarness, deferred, reply, tick } from './authHarness';

test('a final protected 401 drops the open session, Keychain identity and cached account data', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  const before = h.cache.clears;
  h.setFetch(async () => reply({ detail: 'revoked' }, 401));
  await assert.rejects(h.client.api.get('/api/pms/bookings'), { status: 401 });
  assert.equal(h.store.getState().user, null);
  assert.equal(h.store.getState().loading, false);
  assert.equal(h.storage.has('syroce.auth.token'), false);
  assert.equal(h.storage.has('syroce.auth.refresh_token'), false);
  assert.equal(h.storage.has('syroce.auth.user'), false);
  assert.ok(h.cache.clears > before);
});

test('ordinary forbidden operations and temporary network outages do not log a valid operator out', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  h.setFetch(async () => reply({ detail: 'operation forbidden' }, 403));
  await assert.rejects(h.client.api.get('/api/pms/bookings'), { status: 403 });
  assert.equal(h.store.getState().user.id, 'a');
  h.setFetch(async () => { throw new TypeError('offline'); });
  await assert.rejects(h.client.api.get('/api/pms/bookings'), { status: 0 });
  assert.equal(h.store.getState().user.id, 'a');
  await h.store.getState().hydrate();
  assert.equal(h.store.getState().user.id, 'a');
});

test('a revoked /auth/me is not treated as an offline permission grant', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  h.setFetch(async () => reply({ detail: 'disabled' }, 403));
  await h.store.getState().hydrate();
  assert.equal(h.store.getState().user, null);
  assert.equal(h.storage.has('syroce.auth.token'), false);
});

test('late hydration cannot resurrect a logged-out account or replace a new operator', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  const waiting = deferred<Response>();
  const entered = deferred();
  h.setFetch(async (url, init) => {
    const path = new URL(url).pathname;
    if (path === '/api/auth/me') { entered.resolve(null); return waiting.promise; }
    if (path === '/api/auth/login') {
      const { email } = JSON.parse(String(init?.body));
      return reply({ access_token: `access-${email}`, user: { id: email, tenant_id: 'local-b', role: 'housekeeping' } });
    }
    return reply({ ok: true });
  });
  const old = h.store.getState().hydrate();
  await entered.promise;
  await h.store.getState().logout();
  await h.store.getState().login('b', 'synthetic');
  waiting.resolve(reply({ id: 'a', tenant_id: 'local-a', role: 'super_admin' }));
  await old;
  assert.equal(h.store.getState().user.id, 'b');
  assert.equal(h.store.getState().role, 'housekeeping');
  assert.equal(await h.client.getToken(), 'access-b');
  assert.equal(JSON.parse(h.storage.get('syroce.auth.user')!).id, 'b');
});

test('late refresh from the old account cannot overwrite new tokens or replay its request as the new user', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  h.storage.set('syroce.auth.token_issued_at', '1');
  const waiting = deferred<Response>();
  const entered = deferred();
  h.setFetch(async (url, init) => {
    const path = new URL(url).pathname;
    if (path === '/api/auth/refresh-token') { entered.resolve(null); return waiting.promise; }
    if (path === '/api/auth/login') return reply({ access_token: 'access-b', refresh_token: 'refresh-b', user: { id: 'b', role: 'housekeeping' } });
    return reply({ ok: true });
  });
  const old = h.client.api.get('/api/private-old-account');
  const rejected = assert.rejects(old, /Oturum değişti/);
  await entered.promise;
  await h.store.getState().login('b', 'synthetic');
  waiting.resolve(reply({ access_token: 'late-access-a', refresh_token: 'late-refresh-a' }));
  await rejected;
  assert.equal(await h.client.getToken(), 'access-b');
  assert.equal(await h.client.getRefreshToken(), 'refresh-b');
  assert.equal(h.calls.some(c => c.path === '/api/private-old-account'), false);
});

test('concurrent refresh callers share one rotation even during async Keychain reads', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  h.storage.set('syroce.auth.token_issued_at', '1');
  const waiting = deferred<Response>();
  let rotations = 0;
  h.setFetch(async url => {
    if (new URL(url).pathname === '/api/auth/refresh-token') { rotations++; return waiting.promise; }
    return reply({ ok: true });
  });
  const pending = Promise.all([h.client.api.get('/api/one'), h.client.api.get('/api/two')]);
  await tick();
  assert.equal(rotations, 1);
  waiting.resolve(reply({ access_token: 'rotated', refresh_token: 'rotated-refresh' }));
  await pending;
  assert.equal(await h.client.getToken(), 'rotated');
});

test('cancelled 2FA cannot sign the user back in when an accepted response arrives late', async () => {
  const h = authHarness();
  const waiting = deferred<Response>();
  const entered = deferred();
  h.setFetch(async url => {
    if (new URL(url).pathname === '/api/auth/login') return reply({ requires_2fa: true, challenge_token: 'synthetic-challenge' });
    entered.resolve(null); return waiting.promise;
  });
  await h.store.getState().login('a', 'synthetic');
  const verify = h.store.getState().verifyTwoFactor('000000');
  await entered.promise;
  h.store.getState().cancelTwoFactor();
  await tick();
  waiting.resolve(reply({ access_token: 'late-2fa', user: { id: 'a', role: 'admin' } }));
  await verify;
  assert.equal(h.store.getState().user, null);
  assert.equal(await h.client.getToken(), null);
  assert.equal(h.store.getState().pendingTwoFactorToken, null);
});

test('session revalidation adopts revoked page permissions and clears previous report cache', async () => {
  const h = authHarness();
  await h.store.getState().login('a', 'synthetic');
  const before = h.cache.clears;
  h.setFetch(async () => reply({ id: 'a', tenant_id: 'local-hotel', role: 'admin',
    effective_permissions: ['view_procurement'], module_scopes: ['procurement'], page_access: { procurement: true } }));
  await h.store.getState().hydrate();
  assert.equal(h.store.getState().frontdeskAccess, false);
  assert.equal(h.store.getState().financeReports, false);
  assert.equal(h.store.getState().procurementAccess, true);
  assert.ok(h.cache.clears > before);
});
