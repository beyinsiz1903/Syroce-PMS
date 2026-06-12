"use strict";

const $ = (id) => document.getElementById(id);

async function load() {
  const { kbsConfig } = await chrome.storage.local.get("kbsConfig");
  const cfg = kbsConfig || {};
  $("mode").value = cfg.mode || "test";
  $("endpoint").value = cfg.endpoint || "";
  $("token").value = cfg.token || "";
  $("requestFormat").value = cfg.requestFormat || "json";
  $("fieldMap").value = cfg.fieldMap ? JSON.stringify(cfg.fieldMap, null, 2) : "";
  $("referenceRegex").value = cfg.referenceRegex || "";
}

async function save() {
  const status = $("status");
  status.textContent = "";

  let fieldMap = null;
  const raw = $("fieldMap").value.trim();
  if (raw) {
    try {
      fieldMap = JSON.parse(raw);
    } catch (_e) {
      status.textContent = "Alan eslestirme gecerli JSON degil.";
      return;
    }
    if (typeof fieldMap !== "object" || Array.isArray(fieldMap)) {
      status.textContent = "Alan eslestirme bir JSON nesnesi olmalidir.";
      return;
    }
  }

  const cfg = {
    mode: $("mode").value,
    endpoint: $("endpoint").value.trim(),
    token: $("token").value.trim(),
    requestFormat: $("requestFormat").value,
    fieldMap,
    referenceRegex: $("referenceRegex").value.trim(),
  };

  if (cfg.mode !== "test") {
    let host = "";
    try {
      const u = new URL(cfg.endpoint);
      host = u.protocol === "https:" ? u.hostname : "";
    } catch (_e) {
      host = "";
    }
    if (!host || !(host === "egm.gov.tr" || host.endsWith(".egm.gov.tr"))) {
      status.textContent = "KBS ucu https ve *.egm.gov.tr olmalidir.";
      return;
    }
    if (cfg.mode === "token" && !cfg.token) {
      status.textContent = "Token modu icin API token gereklidir.";
      return;
    }
  }

  await chrome.storage.local.set({ kbsConfig: cfg });
  status.textContent = "Kaydedildi.";
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  $("save").addEventListener("click", save);
});
