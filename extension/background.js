"use strict";

// Syroce KBS Gonderici - arka plan servis worker'i (Manifest V3).
//
// Gorev: PMS sayfasindan gelen KBS payload'ini Emniyet (EGM) ucuna,
// resepsiyon bilgisayarinin tarayicisi/IP'si uzerinden POST eder.
//
// Guvenlik ilkeleri:
// - Sayfadan ASLA bir URL kabul edilmez. Uc, yalnizca eklenti ayarlarindan
//   (chrome.storage) okunur ve host'unun *.egm.gov.tr oldugu zorunlu kilinir.
// - Yalnizca kendi content script'lerimizden gelen mesajlar islenir.
// - Payload sahte basari URETMEZ: test modu acik degilse ve uc
//   yapilandirilmamissa fail-closed (gonderim yok, hata doner).
// - Misafir PII kalici saklanmaz / console'a yazilmaz.

const EGM_HOST_SUFFIX = ".egm.gov.tr";
const EGM_HOST_EXACT = "egm.gov.tr";
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

async function getConfig() {
  const { kbsConfig } = await chrome.storage.local.get("kbsConfig");
  const cfg = kbsConfig || {};
  return {
    mode: cfg.mode || "test", // test | cookie | token
    endpoint: (cfg.endpoint || "").trim(),
    token: (cfg.token || "").trim(),
    requestFormat: cfg.requestFormat || "json", // json | form
    fieldMap: cfg.fieldMap && typeof cfg.fieldMap === "object" ? cfg.fieldMap : null,
    referenceKeys:
      Array.isArray(cfg.referenceKeys) && cfg.referenceKeys.length
        ? cfg.referenceKeys
        : DEFAULT_REFERENCE_KEYS,
    referenceRegex: (cfg.referenceRegex || "").trim(),
  };
}

async function getInstallId() {
  let { kbsInstallId } = await chrome.storage.local.get("kbsInstallId");
  if (!kbsInstallId) {
    kbsInstallId = randHex(16);
    await chrome.storage.local.set({ kbsInstallId });
  }
  return kbsInstallId;
}

function isEgmHost(hostname) {
  return hostname === EGM_HOST_EXACT || hostname.endsWith(EGM_HOST_SUFFIX);
}

function configState(cfg) {
  if (cfg.mode === "test") return "test";
  if (!cfg.endpoint) return "unconfigured";
  if (cfg.mode === "token" && !cfg.token) return "unconfigured";
  return "configured";
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
  return true;
}

async function sendToEgm(body) {
  const cfg = await getConfig();
  const state = configState(cfg);

  if (state === "test") {
    return { ok: true, reference: "TEST-" + randHex(16), test: true };
  }
  if (state === "unconfigured") {
    return { ok: false, error: "unconfigured" };
  }

  let url;
  try {
    url = new URL(cfg.endpoint);
  } catch (_e) {
    return { ok: false, error: "endpoint_invalid" };
  }
  if (url.protocol !== "https:" || !isEgmHost(url.hostname)) {
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
      const cfg = await getConfig();
      const installId = await getInstallId();
      sendResponse({
        ok: true,
        version: chrome.runtime.getManifest().version,
        state: configState(cfg),
        installId,
      });
    })();
    return true;
  }

  if (msg.type === "KBS_SEND") {
    (async () => {
      const result = await sendToEgm(msg.body);
      sendResponse(result);
    })();
    return true;
  }

  sendResponse({ ok: false, error: "unknown_type" });
  return false;
});
