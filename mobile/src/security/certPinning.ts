/**
 * Certificate pinning (V3 — Syroce mobil).
 *
 * Why this module exists
 * ----------------------
 * A stolen or mis-issued CA certificate would otherwise let an attacker
 * on a hostile Wi-Fi (hotel-staff captive portal, conference network…)
 * MITM the API traffic and steal staff/guest data. We pin the production
 * API origin's SPKI(s) so even a fully-trusted CA chain is rejected
 * unless one of the bundled fingerprints matches.
 *
 * Architecture
 * ------------
 * Pinning at the network layer requires native code — Expo Go cannot do
 * it because it ships a fixed JS-only fetch. The module therefore runs
 * in three modes selected at boot:
 *
 *  1. **Production / EAS dev-client build with pins configured**:
 *     `react-native-ssl-pinning` is loaded via a guarded `require` and
 *     `globalThis.fetch` is wrapped so every request to a pinned host
 *     goes through the pinned `fetch`. Non-pinned hosts (Expo OTA,
 *     third-party assets) keep the OS trust store.
 *
 *  2. **Production with `certPinningRequired: true` but pinning lib
 *     missing or no pins**: we *fail closed* by replacing
 *     `globalThis.fetch` with a function that throws on every call.
 *     This guarantees a build that was supposed to pin can never
 *     silently regress to plain HTTPS.
 *
 *  3. **Expo Go / dev / no pins / not required**: transparent
 *     passthrough so the dev experience still works. A single boot log
 *     line records the active mode.
 *
 * Configuration lives under `app.json` `extra.certPins` (array of
 * `{ host, pins[] }`) and `extra.certPinningRequired` (bool). Pins are
 * Base64-encoded SHA-256 SPKI hashes; OWASP recommends two per host so
 * a single rotation doesn't brick the fleet. Both values can be hot-
 * rotated via Expo OTA without a store release.
 */
import Constants from 'expo-constants';

export type PinnedHost = {
  /** Fully-qualified hostname, e.g. `api.syroce.com`. */
  host: string;
  /** Base64-encoded SHA-256 SPKI pins (two minimum per OWASP). */
  pins: string[];
};

let _installed = false;
let _backend: 'pinned' | 'passthrough' | 'fail-closed' | 'uninstalled' = 'uninstalled';

type CertConfig = {
  certPins?: PinnedHost[];
  certPinningRequired?: boolean;
};

function readConfig(): CertConfig {
  const cfg = Constants.expoConfig as { extra?: CertConfig } | null | undefined;
  return cfg?.extra ?? {};
}

export function getPinnedHosts(): PinnedHost[] {
  return readConfig().certPins ?? [];
}

export function isPinningRequired(): boolean {
  return readConfig().certPinningRequired === true;
}

export function isPinningEnabled(): boolean {
  if (__DEV__) return false;
  return getPinnedHosts().length > 0;
}

export function getCertPinningBackend(): typeof _backend {
  return _backend;
}

type FetchLike = typeof globalThis.fetch;

function tryLoadPinnedFetch(pins: PinnedHost[]): FetchLike | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require('react-native-ssl-pinning');
    if (!mod || typeof mod.fetch !== 'function') return null;
    const pinIndex = new Map<string, string[]>();
    for (const p of pins) pinIndex.set(p.host.toLowerCase(), p.pins);

    const originalFetch = (globalThis as { __SYROCE_NATIVE_FETCH__?: FetchLike })
      .__SYROCE_NATIVE_FETCH__!;

    const wrapped: FetchLike = async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      let host = '';
      try {
        host = new URL(url).hostname.toLowerCase();
      } catch {
        return originalFetch(input, init);
      }
      const hostPins = pinIndex.get(host);
      if (!hostPins || hostPins.length === 0) {
        return originalFetch(input, init);
      }
      const headers: Record<string, string> = {};
      if (init?.headers) {
        const h = init.headers as Record<string, string> | Headers;
        if (h instanceof Headers) {
          h.forEach((v: string, k: string) => {
            headers[k] = v;
          });
        } else {
          Object.assign(headers, h);
        }
      }
      const res = await mod.fetch(url, {
        method: (init?.method as string) || 'GET',
        headers,
        body: init?.body as string | undefined,
        sslPinning: { certs: hostPins },
        timeoutInterval: 30000,
      });
      return new Response(res.bodyString ?? res.data ?? '', {
        status: res.status,
        headers: res.headers || {},
      });
    };
    return wrapped;
  } catch {
    return null;
  }
}

function makeFailClosedFetch(reason: string): FetchLike {
  return async () => {
    throw new Error(`[certPinning] fail-closed: ${reason}`);
  };
}

/**
 * Install the cert-pinning fetch wrapper. Must be called before any API
 * request fires. Idempotent.
 */
export function installCertPinning(): void {
  if (_installed) return;
  _installed = true;
  const original = globalThis.fetch;
  (globalThis as { __SYROCE_NATIVE_FETCH__?: FetchLike }).__SYROCE_NATIVE_FETCH__ = original;

  const pins = getPinnedHosts();
  const required = isPinningRequired();

  // Dev / Expo Go: never pin, but log so reviewers see the mode.
  if (__DEV__) {
    _backend = 'passthrough';
    // eslint-disable-next-line no-console
    console.info(
      '[certPinning] dev build → passthrough (production will pin %d host(s), required=%s)',
      pins.length,
      required,
    );
    return;
  }

  // Production with pins configured → try to install.
  if (pins.length > 0) {
    const pinned = tryLoadPinnedFetch(pins);
    if (pinned) {
      globalThis.fetch = pinned;
      _backend = 'pinned';
      // eslint-disable-next-line no-console
      console.info('[certPinning] enabled for %d host(s)', pins.length);
      return;
    }
    // Library missing in this build.
    if (required) {
      globalThis.fetch = makeFailClosedFetch(
        'react-native-ssl-pinning not available but certPinningRequired=true',
      );
      _backend = 'fail-closed';
      // eslint-disable-next-line no-console
      console.error(
        '[certPinning] FAIL-CLOSED: pinning required but native module missing — every fetch will throw',
      );
      return;
    }
    // Pins listed but not strictly required → log loudly and pass through.
    _backend = 'passthrough';
    // eslint-disable-next-line no-console
    console.warn(
      '[certPinning] pins configured but react-native-ssl-pinning missing; falling back to OS trust store',
    );
    return;
  }

  // Production, no pins listed. If required, also fail closed so an
  // accidentally-empty config can't ship.
  if (required) {
    globalThis.fetch = makeFailClosedFetch(
      'certPinningRequired=true but no certPins configured',
    );
    _backend = 'fail-closed';
    // eslint-disable-next-line no-console
    console.error('[certPinning] FAIL-CLOSED: no pins configured');
    return;
  }
  _backend = 'passthrough';
  // eslint-disable-next-line no-console
  console.info('[certPinning] no pins configured → passthrough');
}
