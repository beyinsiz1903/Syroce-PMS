"use strict";

importScripts("jandarma-soap.js", "egm-kbs.js");

// Syroce KBS Gonderici - arka plan servis worker'i (Manifest V3).
//
// Gorev: PMS sayfasindan gelen KBS payload'ini secili makama (Polis/Emniyet
// veya Jandarma) ait uca, resepsiyon bilgisayarinin tarayicisi/IP'si uzerinden
// POST eder. KBS yonlendirmesi otelin kayitli adresine gore Polis ya da
// Jandarma sistemine gider; her iki makam icin ayri profil tanimlanabilir.
//
// Guvenlik ilkeleri:
// - Sayfadan ASLA bir URL kabul edilmez. Uc, yalnizca eklenti ayarlarindan
//   (chrome.storage) okunur ve host'unun secili makamin izinli alan adi
//   (Polis -> *.egm.gov.tr, Jandarma -> *.jandarma.gov.tr) oldugu zorunlu
//   kilinir.
// - Yalnizca kendi content script'lerimizden gelen mesajlar islenir.
// - Payload sahte basari URETMEZ: test modu acik degilse ve uc
//   yapilandirilmamissa fail-closed (gonderim yok, hata doner).
// - Misafir PII kalici saklanmaz / console'a yazilmaz.

const AUTHORITIES = ["polis", "jandarma"];
const DEFAULT_AUTHORITY = "polis";
const AUTHORITY_HOSTS = {
  polis: { exact: "egm.gov.tr", suffix: ".egm.gov.tr" },
  jandarma: { exact: "jandarma.gov.tr", suffix: ".jandarma.gov.tr" },
};
const DEFAULT_REFERENCE_KEYS = [
  "kbs_reference", "reference", "reference_no", "referans", "ref", "id"
];
const SEND_TIMEOUT_MS = 30000;

function randHex(n) {
  const a = new Uint8Array(n);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, n)
    .toUpperCase();
}

function normalizeAuthority(a) {
  return AUTHORITIES.includes(a) ? a : DEFAULT_AUTHORITY;
}

function normalizeProfile(cfg) {
  const c = cfg && typeof cfg === "object" ? cfg : {};
  return {
    mode: c.mode || "test", // test | egm-session | jandarma-soap | cookie | token
    endpoint: (c.endpoint || "").trim(),
    token: (c.token || "").trim(),
    requestFormat: c.requestFormat || "json", // json | form
    fieldMap: c.fieldMap && typeof c.fieldMap === "object" ? c.fieldMap : null,
    referenceKeys:
      Array.isArray(c.referenceKeys) && c.referenceKeys.length
        ? c.referenceKeys
        : DEFAULT_REFERENCE_KEYS,
    referenceRegex: (c.referenceRegex || "").trim(),
    userTc: (c.userTc || "").trim(),
    facilityCode: (c.facilityCode || "").trim(),
    liveConfirmed: c.liveConfirmed === true,
    countryMap: c.countryMap && typeof c.countryMap === "object" ? c.countryMap : null,
  };
}

async function getAllConfig() {
  const { kbsConfig } = await chrome.storage.local.get("kbsConfig");
  const raw = kbsConfig || {};
  // Yeni bicim: { polis: {...}, jandarma: {...} }.
  // Eski (tek profil) bicim duz alanlar tasir (mode/endpoint...) -> Polis
  // profiline tasinir (geriye uyumluluk).
  const isLegacyFlat =
    !raw.polis && !raw.jandarma && ("mode" in raw || "endpoint" in raw);
  const out = {};
  for (const a of AUTHORITIES) {
    if (isLegacyFlat && a === DEFAULT_AUTHORITY) out[a] = normalizeProfile(raw);
    else out[a] = normalizeProfile(raw[a]);
  }
  return out;
}

async function getProfile(authority) {
  const all = await getAllConfig();
  return all[normalizeAuthority(authority)];
}

async function getInstallId() {
  let { kbsInstallId } = await chrome.storage.local.get("kbsInstallId");
  if (!kbsInstallId) {
    kbsInstallId = randHex(16);
    await chrome.storage.local.set({ kbsInstallId });
  }
  return kbsInstallId;
}

function isAllowedHost(hostname, authority) {
  const rule = AUTHORITY_HOSTS[normalizeAuthority(authority)];
  return hostname === rule.exact || hostname.endsWith(rule.suffix);
}

function configState(profile, hasSessionPassword = false) {
  if (profile.mode === "test") return "test";
  if (profile.mode === "egm-session") return "configured";
  if (profile.mode === "jandarma-soap") {
    if (!profile.liveConfirmed) return "confirmation_required";
    if (!/^\d{11}$/.test(profile.userTc) || !/^\d{6}$/.test(profile.facilityCode)) return "unconfigured";
    return hasSessionPassword ? "configured" : "password_required";
  }
  if (!profile.endpoint) return "unconfigured";
  if (profile.mode === "token" && !profile.token) return "unconfigured";
  return "configured";
}

async function allStates() {
  const all = await getAllConfig();
  const { jandarmaWebServicePassword } = await chrome.storage.session.get("jandarmaWebServicePassword");
  const states = {};
  for (const a of AUTHORITIES) states[a] = configState(all[a], a === "jandarma" && Boolean(jandarmaWebServicePassword));
  return states;
}

function applyFieldMap(body, fieldMap) {
  if (!fieldMap) return body;
  const out = {};
  for (const [canonical, egmKey] of Object.entries(fieldMap)) {
    if (egmKey) out[egmKey] = body[canonical] != null ? body[canonical] : "";
  }
  if (!("action" in out) && body.action) out.action = body.action;
  return out;
}

function extractReference(text, cfg) {
  if (cfg.referenceRegex) {
    try {
      const m = new RegExp(cfg.referenceRegex).exec(text);
      if (m && (m[1] || m[0])) return String(m[1] || m[0]).trim();
    } catch (_e) {
      // gecersiz regex -> JSON yoluna dus
    }
  }
  let data = null;
  try {
    data = JSON.parse(text);
  } catch (_e) {
    data = null;
  }
  if (data && typeof data === "object") {
    for (const k of cfg.referenceKeys) {
      if (data[k]) return String(data[k]).trim();
    }
  }
  return "";
}

function validBody(body) {
  if (!body || typeof body !== "object") return false;
  if (!body.guest_name) return false;
  if (!body.id_number && !body.passport_number) return false;
  if (!body.check_in) return false;
  if (!body.check_out) return false;
  if (!body.room_number) return false;
  return true;
}

async function sendToKbs(body, authority) {
  const auth = normalizeAuthority(authority);
  const cfg = await getProfile(auth);
  const { jandarmaWebServicePassword } = await chrome.storage.session.get("jandarmaWebServicePassword");
  const state = configState(cfg, Boolean(jandarmaWebServicePassword));

  // Test modu dahil, eksik operasyon verisini "basarili prova" gibi gosterme.
  // Backend ayni kontrolu yapsa da eski kuyruk kayitlari veya farkli istemciler
  // eklentiye ulasabilir; kurum cagrisi oncesi son savunma burada.
  if (!validBody(body)) {
    const missing = [];
    if (!body || !body.guest_name) missing.push("guest_name");
    if (!body || (!body.id_number && !body.passport_number)) missing.push("identity");
    if (!body || !body.room_number) missing.push("room_number");
    if (!body || !body.check_in) missing.push("check_in");
    if (!body || !body.check_out) missing.push("check_out");
    return { ok: false, error: `payload_incomplete: ${missing.join(", ")}` };
  }

  if (state === "test") {
    return { ok: true, reference: "TEST-" + randHex(16), test: true };
  }
  if (state === "unconfigured") {
    return { ok: false, error: "unconfigured" };
  }
  if (state !== "configured") return { ok: false, error: state };

  if (auth === "jandarma" && cfg.mode === "jandarma-soap") {
    let request;
    try {
      request = SyroceJandarmaSoap.buildRequest(body, body.action, {
        userTc: cfg.userTc,
        facilityCode: cfg.facilityCode,
        password: jandarmaWebServicePassword,
        countryMap: cfg.countryMap,
      });
    } catch (e) {
      return { ok: false, error: e && e.message ? e.message : String(e) };
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), SEND_TIMEOUT_MS);
    try {
      const resp = await fetch(cfg.endpoint, {
        method: "POST",
        headers: { "Content-Type": "text/xml; charset=utf-8", SOAPAction: `"${request.soapAction}"` },
        body: request.envelope,
        signal: ctrl.signal,
      });
      const text = await resp.text();
      if (!resp.ok) return { ok: false, error: `HTTP ${resp.status}: ${text.slice(0, 300)}` };
      const parsed = SyroceJandarmaSoap.parseResponse(text, request.method);
      if (!parsed.ok) return parsed;
      // The official response has no transaction id. Record a local receipt only
      // after Basarili=true/code=100; never present it as an official reference.
      return { ok: true, reference: `JANDARMA-${request.method}-${Date.now()}`, officialReference: false };
    } catch (e) {
      return { ok: false, error: "network: " + (e && e.message ? e.message : String(e)) };
    } finally {
      clearTimeout(timer);
    }
  }

  if (auth === "polis" && cfg.mode === "egm-session") {
    return sendToEgmSession(body);
  }

  let url;
  try {
    url = new URL(cfg.endpoint);
  } catch (_e) {
    return { ok: false, error: "endpoint_invalid" };
  }
  if (url.protocol !== "https:" || !isAllowedHost(url.hostname, auth)) {
    return { ok: false, error: "endpoint_not_allowed" };
  }
  if (!validBody(body)) {
    return { ok: false, error: "payload_incomplete" };
  }

  const mapped = applyFieldMap(body, cfg.fieldMap);
  const init = { method: "POST", headers: {} };
  if (cfg.mode === "cookie") init.credentials = "include";
  if (cfg.mode === "token" && cfg.token) {
    init.headers["Authorization"] = "Bearer " + cfg.token;
  }
  if (cfg.requestFormat === "form") {
    init.headers["Content-Type"] = "application/x-www-form-urlencoded";
    init.body = new URLSearchParams(mapped).toString();
  } else {
    init.headers["Content-Type"] = "application/json";
    init.headers["Accept"] = "application/json";
    init.body = JSON.stringify(mapped);
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), SEND_TIMEOUT_MS);
  init.signal = ctrl.signal;

  let resp;
  try {
    resp = await fetch(url.toString(), init);
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, error: "network: " + (e && e.message ? e.message : String(e)) };
  }
  clearTimeout(timer);

  let text = "";
  try {
    text = await resp.text();
  } catch (_e) {
    text = "";
  }
  if (!resp.ok) {
    return { ok: false, error: "HTTP " + resp.status + ": " + text.slice(0, 300) };
  }
  const reference = extractReference(text, cfg);
  if (!reference) {
    return { ok: false, error: "no_reference_in_response" };
  }
  return { ok: true, reference };
}

function egmError(error) {
  const message = typeof error === "string"
    ? error
    : (error && (error.message || error.title || error.detail)) || "egm_request_failed";
  return String(message).slice(0, 500);
}

async function egmRequest(path, payload, method = "POST") {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), SEND_TIMEOUT_MS);
  try {
    const init = {
      method, credentials: "include", signal: ctrl.signal,
      headers: { Accept: "application/json, text/plain, */*" },
    };
    if (method !== "GET") {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(payload || {});
    }
    const resp = await fetch(`${SyroceEgmKbs.API_BASE}/${path}`, init);
    const contentType = resp.headers.get("content-type") || "";
    const raw = await resp.text();
    if (resp.status === 401 || resp.status === 403 || /text\/html/i.test(contentType)) {
      throw new Error("egm_login_required");
    }
    let data;
    try { data = raw ? JSON.parse(raw) : {}; } catch (_e) { throw new Error("egm_invalid_response"); }
    if (!resp.ok) throw new Error(`egm_http_${resp.status}: ${egmError(data)}`);
    if (data && data.isSuccess === false) throw new Error(egmError(data));
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function sendToEgmSession(body) {
  if (!validBody(body)) return { ok: false, error: "payload_incomplete" };
  try {
    if (body.action === "checkout") {
      const filters = {};
      if (body.room_number) filters.verilenOda = String(body.room_number).trim();
      const active = await egmRequest("Konaklayan/AktifKonaklayanGetir", {
        filters, pageNumber: 0, pageSize: 200,
        sortField: "gelisTarihi", sortOrder: "desc",
      });
      const guest = SyroceEgmKbs.selectActiveGuest(active, body);
      const guestId = guest && (guest.konaklayanId || guest.id);
      if (!guestId) return { ok: false, error: "egm_active_guest_not_found" };
      await egmRequest("Konaklayan/KonaklayanPasifYap", { konaklayanId: guestId });
      return {
        ok: true, reference: SyroceEgmKbs.localReceipt("CHECKOUT"),
        officialReference: false,
      };
    }

    let countries = [];
    if (!SyroceEgmKbs.isTurkish(body.nationality) || !body.id_number) {
      const countryResponse = await egmRequest("Ortak/UlkeGetir", null, "GET");
      countries = Array.isArray(countryResponse?.data) ? countryResponse.data : [];
    }
    const request = SyroceEgmKbs.buildCheckin(body, countries);
    await egmRequest(`Konaklayan/${request.operation}`, request.payload);
    return {
      ok: true, reference: SyroceEgmKbs.localReceipt("CHECKIN"),
      officialReference: false,
    };
  } catch (e) {
    return { ok: false, error: egmError(e) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Yalnizca kendi content script'lerimiz (sekme baglamli) kabul edilir.
  if (!sender || sender.id !== chrome.runtime.id || !sender.tab) {
    sendResponse({ ok: false, error: "forbidden" });
    return false;
  }
  if (!msg || typeof msg !== "object") {
    sendResponse({ ok: false, error: "bad_message" });
    return false;
  }

  if (msg.type === "KBS_STATE") {
    (async () => {
      const states = await allStates();
      const installId = await getInstallId();
      sendResponse({
        ok: true,
        version: chrome.runtime.getManifest().version,
        states,
        // Geriye uyumluluk: tekil 'state' alani Polis profiline isaret eder.
        state: states[DEFAULT_AUTHORITY],
        installId,
      });
    })();
    return true;
  }

  if (msg.type === "KBS_SEND") {
    (async () => {
      const result = await sendToKbs(msg.body, msg.authority);
      sendResponse(result);
    })();
    return true;
  }

  sendResponse({ ok: false, error: "unknown_type" });
  return false;
});
