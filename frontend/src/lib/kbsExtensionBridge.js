/**
 * KBS Tarayici Eklentisi Koprusu (page tarafi).
 *
 * PMS sayfasi <-> Syroce KBS Gonderici eklentisi arasinda window.postMessage
 * uzerinden konusur. Eklentinin content script'i yalnizca ayni origin'den,
 * bizim isaretimizi tasiyan mesajlari kabul eder.
 *
 * Eklenti = saf EGM transport'u. Sayfa = kuyruk worker'i (staff JWT'yi tutar):
 * sayfa pending isi claim eder, payload'i eklentiye verir, eklenti otelin
 * IP'sinden EGM'ye POST eder, referansi geri dondurur, sayfa /complete (ya da
 * /fail) cagirir.
 */

const REQ = "__SYROCE_KBS_REQ__";
const RES = "__SYROCE_KBS_RES__";

const pending = new Map();
let listening = false;

function ensureListener() {
  if (listening) return;
  listening = true;
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.origin !== window.location.origin) return;
    const data = event.data;
    if (!data || data[RES] !== true) return;
    if (data.type === "READY") return;
    if (!data.requestId) return;
    const entry = pending.get(data.requestId);
    if (!entry) return;
    pending.delete(data.requestId);
    clearTimeout(entry.timer);
    entry.resolve(data);
  });
}

function newId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
}

function request(payload, timeoutMs) {
  ensureListener();
  return new Promise((resolve) => {
    const requestId = newId();
    const timer = setTimeout(() => {
      pending.delete(requestId);
      resolve({ timedOut: true });
    }, timeoutMs);
    pending.set(requestId, { resolve, timer });
    const out = Object.assign({ requestId }, payload);
    out[REQ] = true;
    window.postMessage(out, window.location.origin);
  });
}

/**
 * Eklentinin kurulu/yapilandirilmis olup olmadigini sorar.
 * @returns {Promise<{present:boolean, version?:string, state?:string, installId?:string}>}
 */
export async function pingExtension(timeoutMs = 1500) {
  const res = await request({ type: "PING" }, timeoutMs);
  if (res.timedOut) return { present: false, state: "absent", version: "", installId: "" };
  return {
    present: true,
    version: res.version || "",
    state: res.state || "unknown",
    installId: res.installId || "",
  };
}

/**
 * Tek bir KBS payload'ini eklenti uzerinden EGM'ye gonderir.
 * @returns {Promise<{ok:boolean, reference:string, error:string, test:boolean}>}
 */
export async function sendViaExtension(body, timeoutMs = 35000) {
  const res = await request({ type: "SEND", body }, timeoutMs);
  if (res.timedOut) return { ok: false, reference: "", error: "extension_timeout", test: false };
  return {
    ok: !!res.ok,
    reference: res.reference || "",
    error: res.error || "",
    test: !!res.test,
  };
}

/**
 * Kuyruk job payload'ini, sunucu tarafi gonderici (kbs_sender) ile ayni
 * kanonik istek govdesine cevirir.
 */
export function buildKbsBody(payload, action = "checkin") {
  const p = payload || {};
  return {
    action,
    guest_name: p.guest_name || "",
    nationality: p.nationality || "TC",
    id_number: p.id_number || "",
    passport_number: p.passport_number || "",
    birth_date: p.birth_date || "",
    gender: p.gender || "",
    father_name: p.father_name || "",
    mother_name: p.mother_name || "",
    birth_place: p.birth_place || "",
    address: p.address || "",
    room_number: p.room_number || "",
    check_in: p.check_in || "",
    check_out: p.check_out || "",
  };
}
