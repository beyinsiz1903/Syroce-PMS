const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { webcrypto } = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../police-agent.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
const binding = { tenantId: 'tenant-a', userId: 'user-a', consent: true };
const stamp = '2026-11-04T09:00:00+00:00';
const job = id => ({ id, created_at: stamp, tenant_id: 'tenant-a', action: 'checkin', payload: {
  id_number: '10000000146', guest_name: 'Synthetic Guest', room_number: '101', check_in: '2026-11-04',
} });

function harness(options = {}) {
  const saved = options.saved || {};
  const alarms = options.alarms || new Map();
  const calls = [], sent = [], writes = [];
  const chrome = {
    storage: { session: {
      get: async key => ({ [key]: saved[key] }),
      set: async values => { writes.push(plain(values)); Object.assign(saved, plain(values)); },
    } },
    alarms: { create: async (key, value) => {
      if (options.alarmError) throw new Error('alarm unavailable');
      alarms.set(key, value);
    }, clear: async key => alarms.delete(key) },
  };
  const context = { crypto: webcrypto, AbortController, setTimeout, clearTimeout };
  context.globalThis = context;
  vm.createContext(context); vm.runInContext(source, context);
  const fetch = async (url, init) => {
    const route = url.replace('https://pms.syroce.com/api/kbs', '');
    calls.push({ route, ...init });
    const special = await options.api?.(route, init);
    if (special) return special;
    let data = {};
    if (route === '/background/context') data = { tenant_id: binding.tenantId, user_id: binding.userId };
    if (route.startsWith('/background/jobs')) data = { jobs: (options.jobs || [job('one'), job('two')]).map(j => ({ id: j.id, created_at: j.created_at })) };
    if (route.endsWith('/claim')) data = { job: job(route.split('/')[2]) };
    return new Response(JSON.stringify(data), { status: 200 });
  };
  const agent = context.SyrocePoliceAgent.create({ chrome, fetch,
    profile: async () => ({ mode: options.mode || 'egm-session' }), installId: async () => 'install-a',
    send: async body => { sent.push(plain(body)); return options.send ? options.send(body) : { ok: true, reference: 'EGM-local', officialReference: false }; },
  });
  return { agent, calls, saved, alarms, sent, writes };
}

test('no opt-in means no PMS/authority traffic; start never accepts secrets or URLs', async () => {
  const h = harness();
  await h.agent.restore(); await h.agent.run();
  assert.equal(h.calls.length, 0); assert.equal(h.sent.length, 0);
  assert.equal((await h.agent.start({ ...binding, consent: false })).ok, false);
  assert.equal((await h.agent.start({ ...binding, tenantId: '../other' })).ok, false);
  assert.equal((await h.agent.start({ ...binding, url: 'https://evil.example', token: 'NEVER_SAVE' })).ok, true);
  assert.equal(JSON.stringify(h.saved).includes('NEVER_SAVE'), false);
  assert.equal(h.calls.every(c => c.credentials === 'include' && !('Authorization' in c.headers)), true);
});

test('alarm worker sends and completes without any tab/window; keeps no guest data', async () => {
  const h = harness(); await h.agent.start(binding); await h.agent.run();
  assert.equal(h.sent.length, 2);
  assert.equal(h.calls.filter(c => c.route.endsWith('/complete')).length, 2);
  assert.equal(h.calls.filter(c => c.route === '/background/context').length, 4); // start, run, before each send
  const stored = JSON.stringify(h.writes);
  assert.equal(/10000000146|Synthetic Guest|check_in|access_token|password/.test(stored), false);
  assert.equal((await h.agent.status()).sent, 2);
  for (const call of h.calls) {
    assert.equal(call.headers['X-KBS-Tenant'], 'tenant-a'); assert.equal(call.headers['X-KBS-User'], 'user-a');
    assert.equal(call.redirect, 'error');
  }
});

test('MV3 suspension restores alarm, browser restart does not restore consent', async () => {
  const first = harness(); await first.agent.start(binding);
  first.alarms.clear();
  const restored = harness({ saved: first.saved, alarms: first.alarms }); await restored.agent.restore();
  assert.equal(restored.alarms.size, 1);
  const restarted = harness({ alarms: first.alarms }); await restarted.agent.restore(); await restarted.agent.run();
  assert.equal(restarted.alarms.size, 0); assert.equal(restarted.calls.length, 0);
});

test('an enabled account cannot be silently retargeted even by another start command', async () => {
  const h = harness(); await h.agent.start(binding);
  const result = await h.agent.start({ ...binding, tenantId: 'tenant-b', userId: 'user-b' });
  assert.equal(result.ok, false); assert.equal(result.error, 'existing_sender_must_stop');
  assert.equal((await h.agent.status()).tenantId, 'tenant-a');
});

test('failed alarm creation is not displayed or stored as active', async () => {
  const h = harness({ alarmError: true });
  assert.equal((await h.agent.start(binding)).ok, false);
  assert.equal((await h.agent.status()).enabled, false);
  assert.equal((await h.agent.status()).reason, 'alarm_unavailable');
});

test('failed alarm restoration disables an otherwise stale active flag', async () => {
  const first = harness(); await first.agent.start(binding);
  const h = harness({ saved: first.saved, alarmError: true });
  await h.agent.restore(); await h.agent.run();
  assert.equal((await h.agent.status()).enabled, false);
  assert.equal(h.sent.length, 0);
});

for (const status of [401, 403, 409, 423]) test(`PMS status ${status} stops without authority traffic`, async () => {
  let changed = false;
  const h = harness({ api: route => changed && route === '/background/context' ? new Response('{}', { status }) : null });
  await h.agent.start(binding); changed = true; await h.agent.run();
  assert.equal(h.sent.length, 0); assert.equal((await h.agent.status()).enabled, false); assert.equal(h.alarms.size, 0);
});

test('account change between feed/claim and authority call is checked again', async () => {
  let claimed = false;
  const h = harness({ api: route => {
    if (route.endsWith('/claim')) claimed = true;
    if (claimed && route === '/background/context') return new Response('{}', { status: 403 });
  } });
  await h.agent.start(binding); await h.agent.run();
  assert.equal(h.sent.length, 0); assert.equal((await h.agent.status()).enabled, false);
});

test('test/custom transport modes cannot enable police background sending', async () => {
  for (const mode of ['test', 'token', 'cookie', 'jandarma-soap']) {
    const h = harness({ mode });
    assert.equal((await h.agent.start(binding)).ok, false); assert.equal(h.calls.length, 0);
  }
});

test('bad/missing-data/blocked claim does not starve the next job and cursor advances', async () => {
  const h = harness({ api: route => route === '/queue/one/claim' ? new Response('{}', { status: 422 }) : null });
  await h.agent.start(binding); await h.agent.run(); await h.agent.run();
  assert.equal(h.sent.length, 2); // only second job each mocked feed
  assert.equal(h.calls.some(c => c.route.includes('after_id=two')), true);
});

test('empty fair page wraps to see newly eligible older jobs', async () => {
  let empty = false;
  const h = harness({ api: route => empty && route.startsWith('/background/jobs') ? new Response('{"jobs":[]}', { status: 200 }) : null });
  await h.agent.start(binding); await h.agent.run(); empty = true; await h.agent.run();
  assert.equal(h.saved.kbsPoliceAgent.cursor, null);
});

test('uncertain delivery holds that job, then continues with following job', async () => {
  let count = 0;
  const h = harness({ send: () => ++count === 1 ? { ok: false, deliveryUncertain: true, error: 'network: timeout' } : { ok: true, reference: 'accepted' } });
  await h.agent.start(binding); await h.agent.run();
  const failure = h.calls.find(c => c.route === '/queue/one/fail');
  assert.equal(JSON.parse(failure.body).delivery_uncertain, true); assert.equal(JSON.parse(failure.body).retry, false);
  assert.equal(h.calls.some(c => c.route === '/queue/two/complete'), true);
});

test('lost PMS completion never repeats the authority write; expired lease remains safe', async () => {
  const h = harness({ jobs: [job('one')], api: route => route.endsWith('/complete') ? new Response('{}', { status: 503 }) : null });
  await h.agent.start(binding); await h.agent.run();
  assert.equal(h.sent.length, 1);
  assert.equal(JSON.parse(h.calls.find(c => c.route.endsWith('/fail')).body).delivery_uncertain, true);
});

test('EGM login expiry pauses; explicit authority rejection of one record does not', async () => {
  for (const error of ['egm_login_required', 'identity_rejected']) {
    const h = harness({ send: () => ({ ok: false, error }) });
    await h.agent.start(binding); await h.agent.run();
    assert.equal(h.sent.length, error === 'egm_login_required' ? 1 : 2);
    assert.equal((await h.agent.status()).enabled, error !== 'egm_login_required');
  }
});

test('overlapping alarms run once and stop during send never rearms stored opt-in', async () => {
  let release, entered;
  const waiting = new Promise(resolve => { entered = resolve; });
  const h = harness({ send: async () => { entered(); await new Promise(resolve => { release = resolve; }); return { ok: true, reference: 'accepted' }; } });
  await h.agent.start(binding);
  const running = h.agent.run(); await waiting; await h.agent.run();
  await h.agent.stop(); release(); await running;
  assert.equal(h.sent.length, 1); assert.equal((await h.agent.status()).enabled, false); assert.equal(h.alarms.size, 0);
});
