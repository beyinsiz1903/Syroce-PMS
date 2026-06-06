// Web fallback for expo-secure-store (which is native-only).
//
// On Expo Web the native module is empty (`ExpoSecureStore.web.js` is
// `export default {}`), so calling SecureStore.setItemAsync/getItemAsync/
// deleteItemAsync invokes an undefined method and throws a TypeError. That
// breaks the login token-persist path (apiLogin → setToken throws → the auth
// store never sets `user` → AuthGate never redirects), which is why the F10
// Expo-Web smoke suite hangs at the post-login navigation.
//
// We back the identical async API with localStorage on web. Native builds
// resolve `secureStore.ts` instead, so native storage is untouched. All
// methods are best-effort and never throw (privacy mode / quota / sandboxed
// iframe), mirroring the try/catch already used by the native callers.

function localStore(): Storage | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    // localStorage access can throw in sandboxed iframes or privacy modes.
  }
  return null;
}

export async function getItemAsync(key: string, _options?: unknown): Promise<string | null> {
  const s = localStore();
  if (!s) return null;
  try {
    return s.getItem(key);
  } catch {
    return null;
  }
}

export async function setItemAsync(key: string, value: string, _options?: unknown): Promise<void> {
  const s = localStore();
  if (!s) return;
  try {
    s.setItem(key, value);
  } catch {
    // quota exceeded / privacy mode — best-effort, do not break the caller.
  }
}

export async function deleteItemAsync(key: string, _options?: unknown): Promise<void> {
  const s = localStore();
  if (!s) return;
  try {
    s.removeItem(key);
  } catch {
    // ignore — best-effort cleanup.
  }
}
