const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { webcrypto } = require("node:crypto");

function loadWorker(fetchImpl, overrides = {}) {
  let listener;
  let alarmListener;
  const extensionDir = path.join(__dirname, "..");
  const local = {
    kbsConfig: overrides.kbsConfig || { polis: { mode: "egm-session" }, jandarma: { mode: "test" } },
    ...(overrides.local || {}),
  };
  const session = overrides.session || {};
  const context = {
    AbortController, URL, URLSearchParams, Response, Headers, crypto: webcrypto,
    setTimeout, clearTimeout, fetch: fetchImpl,
    chrome: {
      storage: {
        local: {
          get: async (key) => ({ [key]: local[key] }),
          set: async (values) => Object.assign(local, values),
          remove: async (key) => { delete local[key]; },
        },
        session: { get: async (key) => ({ [key]: session[key] }), ...(overrides.agent ? {
          set: async values => Object.assign(session, JSON.parse(JSON.stringify(values))),
        } : {}) },
      },
      ...(overrides.agent ? { alarms: { create: async () => {}, get: async () => null, clear: async () => {},
        onAlarm: { addListener: fn => { alarmListener = fn; } } } } : {}),
      runtime: {
        id: "test-extension",
        getManifest: () => ({ version: "1.3.0" }),
        getURL: (file) => `chrome-extension://test-extension/${file}`,
        onMessage: { addListener: (fn) => { listener = fn; } },
      },
    },
  };
  context.globalThis = context;
  context.importScripts = (...files) => {
    for (const file of files) {
      vm.runInContext(fs.readFileSync(path.join(extensionDir, file), "utf8"), context);
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(extensionDir, "background.js"), "utf8"), context);
  const send = (message, sender = { id: "test-extension", tab: { id: 1 } }) => new Promise((resolve) => {
    const keepOpen = listener(message, sender, resolve);
    assert.equal(typeof keepOpen, 'boolean');
  });
  send.alarm = () => alarmListener({ name: 'syroce-kbs-police' });
  return send;
}

test("EGM session mode posts Turkish check-in without opening a tab", async () => {
  const calls = [];
  const send = loadWorker(async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ isSuccess: true, data: {} }), {
      status: 200, headers: { "content-type": "application/json" },
    });
  });
  const result = await send({
    type: "KBS_SEND", authority: "polis",
    body: { action: "checkin", guest_name: "Ali Veli", nationality: "TR", id_number: "10000000146", room_number: "101", check_in: "2026-08-23", check_out: "2026-08-24" },
  });
  assert.equal(result.ok, true);
  assert.match(result.reference, /^EGM-CHECKIN-/);
  assert.equal(result.officialReference, false);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /Konaklayan\/KonaklayanTurkVatandasiEkle$/);
  assert.equal(calls[0].init.credentials, "include");
});

test("EGM session mode fails closed when the portal session expired", async () => {
  const send = loadWorker(async () => new Response("<html>login</html>", {
    status: 200, headers: { "content-type": "text/html" },
  }));
  const result = await send({
    type: "KBS_SEND", authority: "polis",
    body: { action: "checkin", guest_name: "Ali Veli", nationality: "TR", id_number: "10000000146", room_number: "101", check_in: "2026-08-23", check_out: "2026-08-24" },
  });
  assert.deepEqual(JSON.parse(JSON.stringify(result)), { ok: false, error: "egm_login_required", deliveryUncertain: true });
});

for (const mode of ['network', 'invalid-json', 'unknown-acceptance', 'http-500']) test(`EGM write ${mode} is uncertain, never a retryable rejection`, async () => {
  const send = loadWorker(async () => {
    if (mode === 'network') throw new TypeError('Failed to fetch');
    return new Response(mode === 'invalid-json' ? 'incomplete {' : '{}', {
      status: mode === 'http-500' ? 500 : 200, headers: { 'content-type': 'application/json' },
    });
  });
  const result = await send({ type: 'KBS_SEND', authority: 'polis', body: {
    action: 'checkin', nationality: 'TR', id_number: '10000000146', room_number: '101', check_in: '2026-11-04',
  } });
  assert.equal(result.ok, false); assert.equal(result.deliveryUncertain, true); assert.equal(result.reference, undefined);
});

test('only the exact PMS top-level content script may control the background agent', async () => {
  const send = loadWorker(async () => { throw new Error('no network allowed'); });
  for (const sender of [
    { id: 'other-extension', tab: { id: 1 }, url: 'https://pms.syroce.com/app/pms', frameId: 0 },
    { id: 'test-extension', tab: { id: 1 }, url: 'https://other.syroce.com/', frameId: 0 },
    { id: 'test-extension', tab: { id: 1 }, url: 'https://pms.syroce.com.evil.test/', frameId: 0 },
    { id: 'test-extension', tab: { id: 1 }, url: 'https://pms.syroce.com/app/pms', frameId: 1 },
    { id: 'test-extension', url: 'chrome-extension://test-extension/options.html' },
  ]) {
    const result = await send({ type: 'KBS_AGENT_START', binding: { tenantId: 't', userId: 'u', consent: true } }, sender);
    assert.equal(result.error, 'forbidden');
  }
});

test('real worker wiring claims and reports check-in/check-out on alarms without a page', async () => {
  const calls = [], session = {};
  const sender = { id: 'test-extension', tab: { id: 1 }, frameId: 0, url: 'https://pms.syroce.com/app/pms' };
  const send = loadWorker(async (url, init) => {
    calls.push({ url, init });
    let data = { isSuccess: true };
    if (url.endsWith('/background/context')) data = { tenant_id: 'hotel-a', user_id: 'user-a' };
    else if (url.endsWith('/background/jobs')) data = { jobs: ['in', 'out'].map(id => ({ id, created_at: '2026-11-04T09:00:00+00:00' })) };
    else if (url.endsWith('/claim')) {
      const id = url.split('/').at(-2);
      data = { job: { id, tenant_id: 'hotel-a', action: id === 'in' ? 'checkin' : 'checkout', payload: {
        nationality: 'TR', id_number: '10000000146', room_number: '101', check_in: '2026-11-04', check_out: '2026-11-05',
      } } };
    } else if (url.endsWith('/AktifKonaklayanGetir')) data = { isSuccess: true, data: { items: [
      { konaklayanId: 'official-guest', kimlikNo: 10000000146, verilenOda: '101' },
    ] } };
    return new Response(JSON.stringify(data), { status: 200, headers: { 'content-type': 'application/json' } });
  }, { agent: true, session });
  assert.equal((await send({ type: 'KBS_STATE' }, sender)).backgroundSupported, true);
  await send.alarm(); assert.equal(calls.length, 0);
  const enabled = await send({ type: 'KBS_AGENT_START', binding: { consent: true, tenantId: 'hotel-a', userId: 'user-a' } }, sender);
  assert.equal(enabled.ok, true); await send.alarm();
  assert.equal(calls.filter(c => c.url.endsWith('/complete')).length, 2);
  assert.equal(calls.filter(c => c.url.includes('KonaklayanTurkVatandasiEkle')).length, 1);
  assert.equal(calls.filter(c => c.url.includes('KonaklayanPasifYap')).length, 1);
  for (const call of calls.filter(c => c.url.endsWith('/complete'))) assert.equal(JSON.parse(call.init.body).official_reference, false);
  assert.equal((await send({ type: 'KBS_AGENT_STATUS' }, sender)).state.sent, 2);
  assert.equal(JSON.stringify(session).includes('10000000146'), false);
});

test('profile edit after claim cannot switch an EGM-session batch to a custom token transport', async () => {
  const config = { polis: { mode: 'egm-session' }, jandarma: { mode: 'test' } };
  const sender = { id: 'test-extension', tab: { id: 1 }, frameId: 0, url: 'https://pms.syroce.com/app/pms' };
  const calls = [];
  const send = loadWorker(async (url) => {
    calls.push(url); let data = {};
    if (url.endsWith('/background/context')) data = { tenant_id: 'hotel-a', user_id: 'user-a' };
    if (url.endsWith('/background/jobs')) data = { jobs: [{ id: 'one', created_at: '2026-11-04T09:00:00+00:00' }] };
    if (url.endsWith('/claim')) {
      config.polis.mode = 'token'; config.polis.token = 'never-used'; config.polis.endpoint = 'https://kbs.egm.gov.tr/custom';
      data = { job: { id: 'one', tenant_id: 'hotel-a', action: 'checkin', payload: { nationality: 'TR', id_number: '10000000146', room_number: '101', check_in: '2026-11-04' } } };
    }
    return new Response(JSON.stringify(data), { status: 200, headers: { 'content-type': 'application/json' } });
  }, { agent: true, kbsConfig: config });
  await send({ type: 'KBS_AGENT_START', binding: { consent: true, tenantId: 'hotel-a', userId: 'user-a' } }, sender);
  await send.alarm();
  assert.equal(calls.some(url => url.includes('egm.gov.tr')), false);
  assert.equal((await send({ type: 'KBS_AGENT_STATUS' }, sender)).state.reason, 'egm_session_mode_required');
});

test("EGM checkout resolves the active guest before deactivating it", async () => {
  const calls = [];
  const send = loadWorker(async (url, init) => {
    calls.push({ url, body: init.body && JSON.parse(init.body) });
    const payload = url.endsWith("AktifKonaklayanGetir")
      ? { isSuccess: true, data: { items: [{ konaklayanId: "guest-7", kimlikNo: 10000000146, verilenOda: "8" }] } }
      : { isSuccess: true };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  });
  const result = await send({
    type: "KBS_SEND", authority: "polis",
    body: { action: "checkout", guest_name: "Ali Veli", nationality: "TR", id_number: "10000000146", room_number: "8", check_in: "2026-08-22", check_out: "2026-08-23" },
  });
  assert.equal(result.ok, true);
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /AktifKonaklayanGetir$/);
  assert.deepEqual(calls[1].body, { konaklayanId: "guest-7" });
});

test("checkout accepts the official minimum payload without entry-only fields", async () => {
  const calls = [];
  const send = loadWorker(async (url, init) => {
    calls.push({ url, body: init.body && JSON.parse(init.body) });
    const payload = url.endsWith("AktifKonaklayanGetir")
      ? { isSuccess: true, data: { items: [{ konaklayanId: "guest-9", kimlikNo: 10000000146 }] } }
      : { isSuccess: true };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  });
  const result = await send({
    type: "KBS_SEND", authority: "polis",
    body: { action: "checkout", nationality: "TR", id_number: "10000000146", check_out: "2026-08-23" },
  });

  assert.equal(result.ok, true);
  assert.equal(calls.length, 2);
});

test("foreign identity card requires nationality but not birth date or gender", async () => {
  const send = loadWorker(async () => {
    throw new Error("test mode must not call the authority");
  });
  const baseBody = {
    action: "checkin",
    id_type: "foreign_identity_card",
    id_number: "99123456789",
    room_number: "206",
    check_in: "2026-09-26",
  };

  const missingNationality = await send({
    type: "KBS_SEND", authority: "jandarma", body: baseBody,
  });
  assert.deepEqual(JSON.parse(JSON.stringify(missingNationality)), {
    ok: false,
    error: "payload_incomplete: nationality",
  });

  const complete = await send({
    type: "KBS_SEND", authority: "jandarma", body: { ...baseBody, nationality: "CN" },
  });
  assert.equal(complete.ok, true);
  assert.equal(complete.test, true);
});

test("Jandarma SOAP accepts live WSDL facility-code shape and returns auditable authority result", async () => {
  const calls = [];
  const send = loadWorker(async (url, init) => {
    calls.push({ url, init });
    return new Response(
      "<MusteriKimlikNoCikisResult><Basarili>true</Basarili><HataKodu>Basarili</HataKodu><Mesaj>İşlem başarılı</Mesaj></MusteriKimlikNoCikisResult>",
      { status: 200, headers: { "content-type": "text/xml" } },
    );
  }, {
    kbsConfig: {
      polis: { mode: "test" },
      jandarma: {
        mode: "jandarma-soap",
        endpoint: "https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc",
        userTc: "11111111110",
        facilityCode: "12345",
        liveConfirmed: true,
      },
    },
    session: { jandarmaWebServicePassword: "secret" },
  });
  const result = await send({
    type: "KBS_SEND", authority: "jandarma",
    body: { action: "checkout", nationality: "TR", id_number: "10000000146", check_out: "2026-08-23" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.officialReference, false);
  assert.equal(result.responseCode, "Basarili");
  assert.equal(result.responseMessage, "İşlem başarılı");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc");
  assert.match(calls[0].init.body, /<TssKod>12345<\/TssKod>/);
});

test("Jandarma SOAP can use the explicitly remembered device password after Chrome restarts", async () => {
  const send = loadWorker(async (_url, init) => {
    assert.match(init.body, /<Sifre>remembered-secret<\/Sifre>/);
    return new Response(
      "<MusteriKimlikNoCikisResult><Basarili>true</Basarili><HataKodu>Basarili</HataKodu><Mesaj>İşlem başarılı</Mesaj></MusteriKimlikNoCikisResult>",
      { status: 200, headers: { "content-type": "text/xml" } },
    );
  }, {
    kbsConfig: {
      polis: { mode: "test" },
      jandarma: {
        mode: "jandarma-soap",
        endpoint: "https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc",
        userTc: "11111111110", facilityCode: "12345", liveConfirmed: true,
      },
    },
    session: {},
    local: { jandarmaPersistentWebServicePassword: "remembered-secret" },
  });
  const result = await send({
    type: "KBS_SEND", authority: "jandarma",
    body: { action: "checkout", nationality: "TR", id_number: "10000000146", check_out: "2026-08-23" },
  });
  assert.equal(result.ok, true);
});

test("Jandarma connection test can use the explicitly remembered device password after Chrome restarts", async () => {
  const send = loadWorker(async (_url, init) => {
    assert.match(init.body, /<Sifre>remembered-secret<\/Sifre>/);
    return new Response(
      "<TesisBilgisiGetirResult><Basarili>true</Basarili><HataKodu>Basarili</HataKodu><Mesaj>İşlem başarılı</Mesaj></TesisBilgisiGetirResult>",
      { status: 200, headers: { "content-type": "text/xml" } },
    );
  }, {
    kbsConfig: {
      polis: { mode: "test" },
      jandarma: {
        mode: "jandarma-soap",
        endpoint: "https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc",
        userTc: "11111111110", facilityCode: "12345", liveConfirmed: true,
      },
    },
    session: {},
    local: { jandarmaPersistentWebServicePassword: "remembered-secret" },
  });
  const result = await send(
    { type: "KBS_TEST_JANDARMA_CONNECTION" },
    { id: "test-extension", url: "chrome-extension://test-extension/options.html" },
  );
  assert.equal(result.ok, true);
});
