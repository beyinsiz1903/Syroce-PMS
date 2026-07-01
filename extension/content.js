"use strict";

// Syroce KBS Gonderici - icerik betigi (content script).
//
// Sayfa (PMS React uygulamasi) <-> arka plan servis worker'i arasinda
// guvenli kopru. Yalnizca ayni pencere + ayni origin'den, bizim isaretimizi
// tasiyan mesajlar kabul edilir. Arka plana hicbir URL aktarilmaz; sadece
// {type, body} aktarilir.

(function () {
  const REQ = "__SYROCE_KBS_REQ__";
  const RES = "__SYROCE_KBS_RES__";

  function post(payload) {
    const out = Object.assign({}, payload);
    out[RES] = true;
    window.postMessage(out, window.location.origin);
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.origin !== window.location.origin) return;
    const data = event.data;
    if (!data || data[REQ] !== true || typeof data.type !== "string") return;

    if (data.type === "PING") {
      chrome.runtime.sendMessage({ type: "KBS_STATE" }, (resp) => {
        if (chrome.runtime.lastError || !resp) {
          post({ type: "PONG", requestId: data.requestId, present: true, state: "error" });
          return;
        }
        post({
          type: "PONG",
          requestId: data.requestId,
          present: true,
          version: resp.version,
          state: resp.state,
          states: resp.states,
          installId: resp.installId,
        });
      });
      return;
    }

    if (data.type === "SEND") {
      const body = data.body;
      if (!body || typeof body !== "object") {
        post({ type: "RESULT", requestId: data.requestId, ok: false, error: "bad_body" });
        return;
      }
      chrome.runtime.sendMessage({ type: "KBS_SEND", body, authority: data.authority }, (resp) => {
        if (chrome.runtime.lastError || !resp) {
          post({ type: "RESULT", requestId: data.requestId, ok: false, error: "extension_error" });
          return;
        }
        post({
          type: "RESULT",
          requestId: data.requestId,
          ok: !!resp.ok,
          reference: resp.reference || "",
          error: resp.error || "",
          test: !!resp.test,
        });
      });
      return;
    }
  });

  // Sayfaya hazir oldugumuzu duyur (polling olmadan tespit icin).
  post({ type: "READY" });
})();
