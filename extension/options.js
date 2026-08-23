"use strict";

const $ = (id) => document.getElementById(id);

const AUTHORITIES = ["polis", "jandarma"];
const LABELS = { polis: "Polis", jandarma: "Jandarma" };
const HOST_RULES = {
  polis: {
    label: "*.egm.gov.tr",
    test: (h) => h === "egm.gov.tr" || h.endsWith(".egm.gov.tr"),
  },
  jandarma: {
    label: "*.jandarma.gov.tr",
    test: (h) => h === "jandarma.gov.tr" || h.endsWith(".jandarma.gov.tr"),
  },
};
const JANDARMA_SOAP_ENDPOINT = "https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc";
let hasSessionPassword = false;

function fillProfileForm(a, cfg) {
  const c = cfg || {};
  $(`${a}_mode`).value = c.mode || "test";
  $(`${a}_endpoint`).value = c.endpoint || (a === "jandarma" ? JANDARMA_SOAP_ENDPOINT : "");
  $(`${a}_token`).value = c.token || "";
  $(`${a}_requestFormat`).value = c.requestFormat || "json";
  $(`${a}_fieldMap`).value = c.fieldMap ? JSON.stringify(c.fieldMap, null, 2) : "";
  $(`${a}_referenceRegex`).value = c.referenceRegex || "";
  if (a === "jandarma") {
    $("jandarma_userTc").value = c.userTc || "";
    $("jandarma_facilityCode").value = c.facilityCode || "";
    $("jandarma_liveConfirmed").checked = c.liveConfirmed === true;
  }
}

async function load() {
  const { kbsConfig } = await chrome.storage.local.get("kbsConfig");
  const raw = kbsConfig || {};
  // Eski tek-profil bicim duz alanlar tasir -> Polis profiline tasinir.
  const isLegacyFlat =
    !raw.polis && !raw.jandarma && ("mode" in raw || "endpoint" in raw);
  for (const a of AUTHORITIES) {
    if (isLegacyFlat && a === "polis") fillProfileForm(a, raw);
    else fillProfileForm(a, raw[a]);
  }
  const { jandarmaWebServicePassword } = await chrome.storage.session.get("jandarmaWebServicePassword");
  hasSessionPassword = Boolean(jandarmaWebServicePassword);
  $("jandarma_password").placeholder = jandarmaWebServicePassword ? "Bu oturum icin yuklendi" : "Yeni web servis sifresi";
}

function buildProfile(a, status) {
  const mode = $(`${a}_mode`).value;
  const endpoint = $(`${a}_endpoint`).value.trim();
  const token = $(`${a}_token`).value.trim();
  const requestFormat = $(`${a}_requestFormat`).value;
  const referenceRegex = $(`${a}_referenceRegex`).value.trim();

  let fieldMap = null;
  const raw = $(`${a}_fieldMap`).value.trim();
  if (raw) {
    try {
      fieldMap = JSON.parse(raw);
    } catch (_e) {
      status.textContent = `${LABELS[a]}: Alan eslestirme gecerli JSON degil.`;
      return null;
    }
    if (typeof fieldMap !== "object" || Array.isArray(fieldMap)) {
      status.textContent = `${LABELS[a]}: Alan eslestirme bir JSON nesnesi olmalidir.`;
      return null;
    }
  }

  if (mode !== "test") {
    let host = "";
    try {
      const u = new URL(endpoint);
      host = u.protocol === "https:" ? u.hostname : "";
    } catch (_e) {
      host = "";
    }
    if (!host || !HOST_RULES[a].test(host)) {
      status.textContent = `${LABELS[a]}: KBS ucu https ve ${HOST_RULES[a].label} olmalidir.`;
      return null;
    }
    if (mode === "token" && !token) {
      status.textContent = `${LABELS[a]}: Token modu icin API token gereklidir.`;
      return null;
    }
  }

  const userTc = a === "jandarma" ? $("jandarma_userTc").value.trim() : "";
  const facilityCode = a === "jandarma" ? $("jandarma_facilityCode").value.trim() : "";
  const liveConfirmed = a === "jandarma" && $("jandarma_liveConfirmed").checked;
  if (mode === "jandarma-soap") {
    if (!/^\d{11}$/.test(userTc) || !/^\d{6}$/.test(facilityCode)) {
      status.textContent = "Jandarma: Yetkili T.C. 11, tesis kodu 6 hane olmalidir.";
      return null;
    }
    if (!liveConfirmed) {
      status.textContent = "Jandarma: Canli bildirim onay kutusunu isaretleyin.";
      return null;
    }
  }

  return { mode, endpoint, token, requestFormat, fieldMap, referenceRegex, userTc, facilityCode, liveConfirmed };
}

async function save() {
  const status = $("status");
  status.textContent = "";

  const cfg = {};
  for (const a of AUTHORITIES) {
    const profile = buildProfile(a, status);
    if (!profile) return; // dogrulama hatasi -> status zaten yazildi
    cfg[a] = profile;
  }

  await chrome.storage.local.set({ kbsConfig: cfg });
  const password = $("jandarma_password").value;
  if (password) {
    await chrome.storage.session.set({ jandarmaWebServicePassword: password });
    hasSessionPassword = true;
  }
  status.textContent = cfg.jandarma.mode === "jandarma-soap" && !password && !hasSessionPassword
    ? "Ayarlar kaydedildi. Bu oturum icin web servis sifresini de girin."
    : "Kaydedildi.";
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  $("save").addEventListener("click", save);
});
