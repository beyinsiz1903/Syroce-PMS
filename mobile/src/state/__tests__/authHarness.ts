// Executes the actual mobile modules with only platform/storage/network ports
// replaced. No real credentials, SecureStore, HTTP, permission prompts or push.
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { ModuleKind, transpileModule } from 'typescript';

export function deferred<T = any>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
export const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
export const tick = () => new Promise<void>(done => setTimeout(done, 0));

export function authHarness(sourceReader = (file: string) => readFileSync(file, 'utf8')) {
  const root = resolve('src');
  const storage = new Map<string, string>();
  const calls: { path: string; init?: RequestInit }[] = [];
  const cache = { clears: 0, offlineClears: 0, clear() { this.clears++; }, async cancelQueries() {} };
  const notifications: any = {
    permission: 'granted', requested: 0, registered: 0, listener: null, last: null,
    setNotificationHandler() {}, async setNotificationChannelAsync() {}, AndroidImportance: { HIGH: 4 },
    async getPermissionsAsync() { return { status: this.permission }; },
    async requestPermissionsAsync() { notifications.requested++; return { status: notifications.permission }; },
    async getExpoPushTokenAsync() { return { data: 'ExponentPushToken[synthetic-only]' }; },
    addNotificationResponseReceivedListener(listener: any) { notifications.listener = listener; return { remove() {} }; },
    addNotificationReceivedListener() { return { remove() {} }; },
    async getLastNotificationResponseAsync() { return this.last; },
  };
  let fetcher = async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/api/auth/login') {
      const { email } = JSON.parse(String(init?.body));
      return reply({ access_token: `access-${email}`, refresh_token: `refresh-${email}`, user: { id: email, tenant_id: 'local-hotel', role: 'front_desk' } });
    }
    return reply({ ok: true });
  };
  const secure = {
    async getItemAsync(key: string) { return storage.get(key) ?? null; },
    async setItemAsync(key: string, value: string) { storage.set(key, value); },
    async deleteItemAsync(key: string) { storage.delete(key); },
  };
  const modules = new Map<string, { exports: any }>();
  function load(file: string): any {
    const path = resolve(root, file.endsWith('.ts') ? file : `${file}.ts`);
    if (modules.has(path)) return modules.get(path)!.exports;
    const module = { exports: {} as any };
    modules.set(path, module);
    const code = transpileModule(sourceReader(path), { compilerOptions: { module: ModuleKind.CommonJS } }).outputText;
    const requirePort = (name: string): any => {
      if (name === 'expo-constants') return { expoConfig: { hostUri: '127.0.0.1:8081', extra: { eas: { projectId: 'local-test-project' } } } };
      if (name === 'react-native') return { Platform: { OS: 'ios' } };
      if (name === 'expo-notifications') return notifications;
      if (name === 'zustand') return { create: (initializer: any) => {
        let state: any;
        const store = Object.assign(() => state, { getState: () => state, setState: (patch: any) => { state = { ...state, ...patch }; } });
        state = initializer(store.setState, store.getState);
        return store;
      } };
      const target = resolve(dirname(path), `${name}.ts`);
      if (target === resolve(root, 'storage/secureStore.ts')) return secure;
      if (target === resolve(root, 'cache/queryClient.ts')) return { queryClient: cache };
      if (target === resolve(root, 'cache/persister.ts')) return { clearOfflineCache: async () => { cache.offlineClears++; } };
      if (target === resolve(root, 'i18n/tr.ts')) return { tr: { auth: { twoFactorInvalid: 'Yeniden giriş yapın' } } };
      if (!name.startsWith('.')) throw new Error(`Unexpected native dependency: ${name}`);
      return load(target);
    };
    const fetchPort = async (input: string, init?: RequestInit) => {
      calls.push({ path: new URL(input).pathname, init });
      return fetcher(input, init);
    };
    new Function('require', 'module', 'exports', '__DEV__', 'fetch', code)(requirePort, module, module.exports, true, fetchPort);
    return module.exports;
  }
  return { storage, calls, cache, notifications, load, setFetch: (handler: typeof fetcher) => { fetcher = handler; },
    get store() { return load('state/authStore').useAuthStore; },
    get client() { return load('api/client'); },
    get auth() { return load('api/auth'); },
    get session() { return load('state/authSession'); },
  };
}
