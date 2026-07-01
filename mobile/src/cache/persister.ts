/**
 * TanStack Query offline cache (V3 — Syroce mobil).
 *
 * Storage strategy
 * ----------------
 * The V3 spec calls for an MMKV-backed persister so cache writes are
 * synchronous and ~10× faster than AsyncStorage. MMKV requires a native
 * module, so it cannot run inside Expo Go (the convenience preview
 * client) — only inside an EAS dev-client / production build.
 *
 * To satisfy both worlds, this module:
 *   1. Tries to load `react-native-mmkv` at module init via a guarded
 *      `require`. If the native binary is present we wire the official
 *      `@tanstack/query-sync-storage-persister` against an MMKV-backed
 *      `Storage` shim — this is the path that runs in production.
 *   2. If MMKV is unavailable (Expo Go, web preview, etc.) we fall back
 *      to the AsyncStorage persister so the user still gets offline
 *      cache, just with async writes.
 *
 * Cache versioning: bumping `CACHE_VERSION` invalidates every persisted
 * query. Use it whenever a query payload shape changes in a non-backwards
 * compatible way to avoid serving stale results to upgraded clients.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Persister } from '@tanstack/react-query-persist-client';
import type { QueryClient } from '@tanstack/react-query';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { persistQueryClient } from '@tanstack/react-query-persist-client';

export const CACHE_VERSION = 'v3-2026-05';
const CACHE_KEY = 'syroce.tq.cache';
const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24h

type SyncStorageLike = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};

let _backend: 'mmkv' | 'async-storage' | 'memory' = 'memory';

function tryCreateMMKVStorage(): SyncStorageLike | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require('react-native-mmkv');
    if (!mod || typeof mod.MMKV !== 'function') return null;
    const mmkv = new mod.MMKV({ id: 'syroce-tq-cache' });
    return {
      getItem: (k) => {
        const v = mmkv.getString(k);
        return v === undefined ? null : v;
      },
      setItem: (k, v) => mmkv.set(k, v),
      removeItem: (k) => mmkv.delete(k),
    };
  } catch {
    return null;
  }
}

function buildPersister(): Persister {
  const mmkv = tryCreateMMKVStorage();
  if (mmkv) {
    _backend = 'mmkv';
    return createSyncStoragePersister({
      storage: mmkv,
      key: CACHE_KEY,
      throttleTime: 1000,
    });
  }
  _backend = 'async-storage';
  return createAsyncStoragePersister({
    storage: AsyncStorage,
    key: CACHE_KEY,
    throttleTime: 1500,
  });
}

const _persister = buildPersister();

export function getCacheBackend(): 'mmkv' | 'async-storage' | 'memory' {
  return _backend;
}

/**
 * Wire up the persister against an existing QueryClient. Returns an
 * unsubscribe function for HMR / tests; in production the listener lives
 * for the lifetime of the app.
 */
export function setupOfflineCache(client: QueryClient): () => void {
  const [unsubscribe] = persistQueryClient({
    queryClient: client,
    persister: _persister,
    maxAge: CACHE_MAX_AGE_MS,
    buster: CACHE_VERSION,
    dehydrateOptions: {
      // Don't persist queries that errored — we don't want to "remember"
      // a failure; the next online tick will re-fetch fresh data.
      shouldDehydrateQuery: (q) => q.state.status === 'success',
    },
  });
  return unsubscribe;
}

export async function clearOfflineCache(): Promise<void> {
  try {
    if (_backend === 'mmkv') {
      const mmkv = tryCreateMMKVStorage();
      mmkv?.removeItem(CACHE_KEY);
    } else {
      await AsyncStorage.removeItem(CACHE_KEY);
    }
  } catch {
    // ignore — best-effort
  }
}
