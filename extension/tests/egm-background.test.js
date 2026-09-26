const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { webcrypto } = require("node:crypto");

function loadWorker(fetchImpl, overrides = {}) {
  let listener;
  const extensionDir = path.join(__dirname, "..");
  const local = { kbsConfig: overrides.kbsConfig || { polis: { mode: "egm-session" }, jandarma: { mode: "test" } } };
  const session = overrides.session || {};
  const context = {
    AbortController, URL, URLSearchParams, Response, Headers, crypto: webcrypto,
    setTimeout, clearTimeout, fetch: fetchImpl,
    chrome: {
      storage: {
        local: {
          get: async (key) => ({ [key]: local[key] }),
          set: async (values) => Object.assign(local, values),
        },
        session: { get: async (key) => ({ [key]: session[key] }) },
      },
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
  return (message) => new Promise((resolve) => {
    const keepOpen = listener(message, { id: "test-extension", tab: { id: 1 } }, resolve);
    assert.equal(keepOpen, true);
  });
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
  assert.deepEqual(JSON.parse(JSON.stringify(result)), { ok: false, error: "egm_login_required" });
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
