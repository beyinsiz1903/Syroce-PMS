/**
 * Axios global GET dedupe + micro-cache
 *
 * Amaç: aynı GET endpoint'inin (örn. /pms/dashboard, /notifications/list)
 * kısa zaman aralığında birden fazla bileşenden istenmesi durumunda
 *  1) uçuştaki istek paylaşılsın (in-flight dedupe), ve
 *  2) yeni gelen istek 1.5 sn boyunca cache'den dönsün.
 *
 * Sayfalar arası geçişlerde, dialog açıp kapamada ve KPI/Layout/Modules
 * çakışan fetch'lerinde gözle görülür hızlanma sağlar.
 *
 * Mutation (POST/PUT/PATCH/DELETE) sonrası cache komple temizlenir →
 * stale veri riski sıfır. TTL kısa (1.5 sn) tutulduğu için kullanıcı
 * yenileme gecikmesi hissetmez.
 *
 * Skip yolları:
 *  - Auth endpoint'leri (login/refresh) — security açısından
 *  - responseType !== 'json' (blob/arraybuffer/stream — dosya indirme)
 *  - config._noCache: true → çağıran sayfa açıkça cache istemiyorsa
 */

const TTL_MS = 1500;
const MAX_ENTRIES = 200;

const microCache = new Map(); // key → { response, ts }
const inFlight = new Map();   // key → Promise<response>

const isAuthUrl = (url = '') =>
  url.includes('/auth/login') ||
  url.includes('/auth/refresh-token') ||
  url.includes('/auth/register') ||
  url.includes('/auth/forgot-password') ||
  url.includes('/auth/reset-password');

export function stableSerialize(value) {
  if (value == null) return "";
  if (typeof URLSearchParams !== "undefined" && value instanceof URLSearchParams) {
    return JSON.stringify([...value.entries()].sort(([a], [b]) => a.localeCompare(b)));
  }
  if (Array.isArray(value)) return `[${value.map(stableSerialize).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${stableSerialize(value[key])}`,
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function cacheTenantScope(storage = globalThis.localStorage) {
  if (!storage) return "tenant:unknown|user:unknown";
  try {
    const tenant = JSON.parse(storage.getItem("tenant") || "null");
    const user = JSON.parse(storage.getItem("user") || "null");
    const tenantId = tenant?.id || tenant?.tenant_id || tenant?.hotel_id || user?.tenant_id || "unknown";
    const userId = user?.id || user?.user_id || "unknown";
    return `tenant:${tenantId}|user:${userId}`;
  } catch {
    return "tenant:unknown|user:unknown";
  }
}

function keyFor(config) {
  const method = (config.method || 'get').toUpperCase();
  const url = config.url || '';
  const params = stableSerialize(config.params);
  // Tenant/auth header değişimi farklı kullanıcı/oturum demektir; token'ı
  // key'e dahil ederek user A'nın cache'i user B'ye sızmasın.
  const tok = (config.headers && (config.headers.Authorization || config.headers.authorization)) || '';
  return `${cacheTenantScope()}|${method} ${url}?${params}|${tok.slice(-12)}`;
}

function shouldSkip(config) {
  const method = (config.method || 'get').toLowerCase();
  if (method !== 'get') return true;
  if (config._noCache) return true;
  if (config._forceRefresh) return true;
  if (config.responseType && config.responseType !== 'json') return true;
  if (isAuthUrl(config.url || '')) return true;
  return false;
}

function pruneCache() {
  if (microCache.size <= MAX_ENTRIES) return;
  // FIFO: en eski girişi sil. Map insertion order'ı korur.
  const oldest = microCache.keys().next().value;
  if (oldest !== undefined) microCache.delete(oldest);
}

function cloneErrorForConfig(error, config) {
  if (!error || typeof error !== "object") return error;
  const clone = Object.create(Object.getPrototypeOf(error));
  const descriptors = Object.getOwnPropertyDescriptors(error);
  delete descriptors.config;
  Object.defineProperties(clone, descriptors);
  Object.defineProperty(clone, "config", {
    value: config,
    writable: true,
    configurable: true,
    enumerable: true,
  });
  return clone;
}

export function installAxiosCache(axios) {
  // HMR-safe install: orijinal adapter'ı tek bir kez yedekle ve sakla.
  // Bu sayede HMR sırasında axios-cache.js veya axiosConfig.js yeniden
  // yüklendiğinde önceki cachingAdapter'ı orijinal sanıp recursion'a
  // girmiyoruz; yeni install eski cachingAdapter'ı yeni sürümle değiştirir.
  if (!axios.__originalAdapter) {
    const rawAdapter = axios.defaults.adapter;
    const resolved =
      typeof rawAdapter === 'function'
        ? rawAdapter
        : (typeof axios.getAdapter === 'function' ? axios.getAdapter(rawAdapter) : rawAdapter);
    if (typeof resolved !== 'function') {
      // Adapter'ı resolve edemedik → cache'i hiç kurma, orijinal davranışı bozma.
      return;
    }
    axios.__originalAdapter = resolved;
  }
  const originalAdapter = axios.__originalAdapter;

  axios.defaults.adapter = function cachingAdapter(config) {
    if (shouldSkip(config)) return originalAdapter(config);

    const key = keyFor(config);
    const now = Date.now();

    const cached = microCache.get(key);
    if (cached && now - cached.ts < cached.ttl) {
      // Shallow clone → çağıran taraf headers'ı mutate ederse cache bozulmasın.
      return Promise.resolve({
        ...cached.response,
        config,
        headers: { ...cached.response.headers },
        cached: true,
      });
    }

    const existing = inFlight.get(key);
    if (existing) {
      return existing.then(
        (res) => ({ ...res, config, headers: { ...res.headers }, cached: true }),
        // Her tüketici kendi retry sayacını/config'ini taşımalı. Aynı AxiosError
        // nesnesini paylaşmak, paralel bekleyenlerin birbirinin retry bütçesini
        // artırmasına ve erken tükenmesine neden olur.
        (err) => Promise.reject(cloneErrorForConfig(err, config)),
      );
    }

    const promise = originalAdapter(config).then(
      (res) => {
        const requestedTtl = Number(config._cacheTtlMs);
        const ttl = Number.isFinite(requestedTtl) && requestedTtl >= 0 ? requestedTtl : TTL_MS;
        microCache.set(key, { response: res, ts: Date.now(), ttl });
        pruneCache();
        inFlight.delete(key);
        return res;
      },
      (err) => {
        inFlight.delete(key);
        throw err;
      },
    );
    inFlight.set(key, promise);
    return promise;
  };

  // Mutation sonrası tüm cache invalidate. Endpoint-bazlı tag sistemine
  // göre çok daha az kod; TTL kısa olduğu için "fazla invalidate" maliyeti
  // ihmal edilebilir.
  const invalidateOnMutation = (config) => {
    const method = (config?.method || '').toLowerCase();
    if (['post', 'put', 'patch', 'delete'].includes(method)) {
      microCache.clear();
    }
  };

  axios.interceptors.response.use(
    (response) => {
      invalidateOnMutation(response.config);
      return response;
    },
    (error) => {
      invalidateOnMutation(error?.config);
      return Promise.reject(error);
    },
  );
}

export function clearAxiosCache() {
  microCache.clear();
  inFlight.clear();
}
