"use strict";

// Explicitly enabled, browser-session-only queue worker. Never persist guest
// payloads, cookies, passwords or bearer tokens. All URLs are compiled in.
(function (root) {
  const KEY = "kbsPoliceAgent";
  const ALARM = "syroce-kbs-police";
  const API = "https://pms.syroce.com/api/kbs";
  const safeId = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{1,120}$/.test(value);
  const buildBody = (job) => {
    const p = job.payload || {};
    const body = { action: job.action || "checkin" };
    for (const key of ["guest_name", "phone", "nationality", "id_type", "id_number", "passport_number",
      "birth_date", "gender", "father_name", "mother_name", "birth_place", "address", "room_number", "check_in", "check_out"]) {
      body[key] = p[key] || (key === "nationality" ? "TC" : "");
    }
    return body;
  };

  root.SyrocePoliceAgent = {
    KEY, ALARM,
    create({ chrome, fetch, send, profile, installId, now = () => Date.now() }) {
      let running = false;
      let revision = 0;
      let commands = Promise.resolve();
      const serial = (fn) => {
        const result = commands.then(fn, fn);
        commands = result.catch(() => {});
        return result;
      };
      const read = async () => (await chrome.storage.session.get(KEY))[KEY] || null;
      const write = async (state) => chrome.storage.session.set({ [KEY]: state });
      const publicState = (state) => state ? {
        supported: true, enabled: state.enabled === true, tenantId: state.tenantId,
        userId: state.userId, reason: state.reason || "", lastRunAt: state.lastRunAt || null,
        sent: state.sent || 0, failed: state.failed || 0,
      } : { supported: true, enabled: false, reason: "not_enabled" };
      const persist = (state, rev) => serial(async () => {
        if (revision === rev) await write(state);
      });
      const api = async (state, path, body, idem) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 15000);
        try {
          const headers = {
            Accept: "application/json", "X-KBS-Background": "1",
            "X-KBS-Tenant": state.tenantId, "X-KBS-User": state.userId,
          };
          if (body) headers["Content-Type"] = "application/json";
          if (idem) headers["Idempotency-Key"] = idem;
          const response = await fetch(API + path, {
            method: body ? "POST" : "GET", headers, credentials: "include",
            cache: "no-store", redirect: "error", signal: controller.signal,
            ...(body ? { body: JSON.stringify(body) } : {}),
          });
          if (!response.ok) {
            const error = new Error(`pms_http_${response.status}`);
            error.status = response.status;
            throw error;
          }
          return await response.json();
        } finally { clearTimeout(timer); }
      };
      const validateContext = async (state) => {
        const result = await api(state, "/background/context");
        if (result.tenant_id !== state.tenantId || result.user_id !== state.userId) {
          const error = new Error("context_changed"); error.status = 403; throw error;
        }
      };
      const pause = async (state, reason, rev) => {
        state.enabled = false; state.reason = reason;
        await persist(state, rev);
        if (revision === rev) await chrome.alarms.clear(ALARM);
      };
      const fatal = (error) => [401, 403].includes(error?.status);
      const fail = (state, jobId, worker, uncertain, error) => api(state, `/queue/${encodeURIComponent(jobId)}/fail`, {
        worker_id: worker, error, retry: !uncertain, delivery_uncertain: uncertain,
      }, `police-fail-${crypto.randomUUID()}`);

      async function run() {
        if (running) return;
        running = true;
        const rev = revision;
        let state;
        try {
          state = await read();
          if (!state?.enabled) return;
          const cfg = await profile();
          if (cfg.mode !== "egm-session") return await pause(state, "egm_session_mode_required", rev);
          await validateContext(state);
          const query = state.cursor ? `?after_created=${encodeURIComponent(state.cursor.created_at)}&after_id=${encodeURIComponent(state.cursor.id)}` : "";
          const page = await api(state, "/background/jobs" + query);
          if (!Array.isArray(page.jobs)) throw new Error("invalid_feed");
          state.lastRunAt = new Date(now()).toISOString();
          const worker = `police:${await installId()}`;
          const started = now();
          if (!page.jobs.length) state.cursor = null;
          for (const item of page.jobs) {
            if (revision !== rev || now() - started > 90000) break;
            if (!safeId(item.id) || typeof item.created_at !== "string") throw new Error("invalid_feed");
            // Do not let a permanently blocked/missing-data record monopolize a page.
            let job;
            try {
              const result = await api(state, `/queue/${encodeURIComponent(item.id)}/claim`, {
                worker_id: worker, lease_seconds: 300,
              });
              job = result.job;
            } catch (error) {
              if (![409, 422, 404].includes(error.status)) throw error;
            }
            if (job) {
              if (job.id !== item.id || job.tenant_id !== state.tenantId) throw new Error("invalid_claim");
              // Recheck the ordinary session after the claim and before authority IO.
              await validateContext(state);
              if (revision !== rev) {
                await fail(state, item.id, worker, false, "background_stopped_before_send");
                break;
              }
              let result;
              try { result = await send(buildBody(job)); }
              catch (_) { result = { ok: false, deliveryUncertain: true }; }
              const accepted = result.ok && result.reference && !result.test && !result.reference.startsWith("TEST-");
              if (accepted) {
                try {
                  await api(state, `/queue/${encodeURIComponent(item.id)}/complete`, {
                    worker_id: worker, kbs_reference: result.reference, authority: "polis",
                    official_reference: result.officialReference !== false,
                    authority_response_code: (result.responseCode || "").slice(0, 100),
                    // No authority response text / identity in extension storage.
                  }, `police-complete-${crypto.randomUUID()}`);
                  state.sent = (state.sent || 0) + 1;
                } catch (error) {
                  // Never repeat the authority write, even if only the PMS receipt failed.
                  try { await fail(state, item.id, worker, true, "delivery_unknown_check_authority"); } catch (_) { /* expired lease is held server-side */ }
                  if (fatal(error)) throw error;
                  state.failed = (state.failed || 0) + 1;
                }
              } else {
                const uncertain = result.deliveryUncertain === true;
                // Queue keeps the actionable authority reason; no raw errors saved locally.
                const error = uncertain ? "delivery_unknown_check_authority" : String(result.error || "authority_not_accepted").slice(0, 500);
                await fail(state, item.id, worker, uncertain, error);
                state.failed = (state.failed || 0) + 1;
                if (["egm_login_required", "egm_session_mode_required"].includes(result.error)) {
                  await pause(state, result.error, rev);
                  break;
                }
              }
            }
            state.cursor = { created_at: item.created_at, id: item.id };
            state.lastRunAt = new Date(now()).toISOString();
            state.reason = "";
            await persist(state, rev);
          }
          await persist(state, rev);
        } catch (error) {
          if (state) {
            if (fatal(error)) await pause(state, "pms_login_or_context_required", rev);
            else if (error.status === 423) await pause(state, "server_test_mode", rev);
            else if (error.status === 409) await pause(state, "server_managed", rev);
            else { state.reason = "pms_unavailable"; await persist(state, rev); }
          }
        } finally { running = false; }
      }

      return {
        run,
        status: async () => publicState(await read()),
        start: (binding) => serial(async () => {
          // No migration from page localStorage, no automatic opt-in on upgrade.
          if (binding?.consent !== true || !safeId(binding.tenantId) || !safeId(binding.userId)) {
            return { ok: false, error: "explicit_context_consent_required" };
          }
          if (running) return { ok: false, error: "sender_busy" };
          const previous = await read();
          if (previous?.enabled && (previous.tenantId !== binding.tenantId || previous.userId !== binding.userId)) {
            return { ok: false, error: "existing_sender_must_stop" };
          }
          const cfg = await profile();
          if (cfg.mode !== "egm-session") return { ok: false, error: "egm_session_mode_required" };
          const state = { enabled: true, tenantId: binding.tenantId, userId: binding.userId, cursor: null, sent: 0, failed: 0 };
          try { await validateContext(state); }
          catch (_) { return { ok: false, error: "pms_login_or_context_required" }; }
          revision++;
          await write(state);
          await chrome.alarms.create(ALARM, { periodInMinutes: 1, delayInMinutes: 1 });
          // The first pass is deliberately alarm-driven, not tied to a response port.
          return { ok: true, state: publicState(state) };
        }),
        stop: () => serial(async () => {
          revision++;
          const state = await read();
          if (state) { state.enabled = false; state.reason = "stopped"; await write(state); }
          await chrome.alarms.clear(ALARM);
          return { ok: true, state: publicState(state) };
        }),
        restore: () => serial(async () => {
          const state = await read();
          if (state?.enabled) await chrome.alarms.create(ALARM, { periodInMinutes: 1, delayInMinutes: 1 });
          else await chrome.alarms.clear(ALARM);
        }),
      };
    },
  };
})(globalThis);
