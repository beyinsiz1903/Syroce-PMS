/**
 * Axios Configuration — Centralized HTTP client setup.
 * Configures base URL, interceptors, and error handling.
 */
import axios from "axios";
import { installAxiosCache, clearAxiosCache } from "@/lib/axios-cache";

const RAW_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "/api";
const BACKEND_URL = RAW_BACKEND_URL.endsWith("/api")
  ? RAW_BACKEND_URL
  : RAW_BACKEND_URL.replace(/\/+$/, "") + "/api";

axios.defaults.baseURL = BACKEND_URL;
axios.defaults.timeout = 30000;
axios.defaults.withCredentials = true;

// Global GET dedupe + 1.5sn micro-cache. Aynı endpoint'in art arda
// (sayfa geçişi, paralel bileşenler, KPI/Layout overlap) çağrılmasında
// tek backend hit'e indirir. Mutation sonrası otomatik invalidate.
installAxiosCache(axios);

// Request interceptor — token injection + cache headers
axios.interceptors.request.use(
  (config) => {
    const url = config.url || "";
    const isPublicAuthEndpoint =
      url.includes("/auth/login") ||
      url.includes("/auth/register") ||
      url.includes("/auth/forgot-password") ||
      url.includes("/auth/reset-password");

    if (!config.headers) {
      config.headers = {};
    }

    if (!isPublicAuthEndpoint) {
      // Legacy token fallback - in cookie-auth era this is mostly unused
      // but kept briefly for migration. We no longer write it on login.
      const token = localStorage.getItem("token");
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } else {
      if (config.headers.Authorization) {
        delete config.headers.Authorization;
      }
    }

    if (config.method === "get") {
      config.headers["Cache-Control"] = "max-age=60";
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Silent refresh state ─────────────────────────────────────────────
// Aynı anda gelen birden çok 401, tek bir refresh isteği bekler;
// başarılıysa hepsi yeni token ile retry edilir.
let _refreshInFlight = null;
const _isRefreshableUrl = (url = "") =>
  !url.includes("/auth/login") &&
  !url.includes("/auth/refresh-token") &&
  !url.includes("/auth/register") &&
  !url.includes("/auth/forgot-password") &&
  !url.includes("/auth/reset-password");

function _hardLogout() {
  localStorage.removeItem("token");
  localStorage.removeItem("token_ts");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
  localStorage.removeItem("tenant");
  localStorage.removeItem("modules");
  // Eski oturum cache'i yeni kullanıcıya sızmasın.
  clearAxiosCache();
  delete axios.defaults.headers.common["Authorization"];
  if (window.location.pathname !== "/auth" && window.location.pathname !== "/") {
    window.location.assign("/auth");
  }
}

// Refresh sonucu üç durumdan biri:
//   { token: string }  — başarılı, retry yapılır
//   { transient: true } — 5xx/ağ; oturum SİLİNMEZ, istek reddedilir
//   { invalid: true }  — 401/400; refresh token gerçekten ölmüş, hard logout
async function _attemptRefresh() {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!_refreshInFlight) {
    _refreshInFlight = axios
      .post(
        "/auth/refresh-token",
        refreshToken ? { refresh_token: refreshToken } : {},
        { _skipAuthRetry: true },
      )
      .then((r) => {
        const newAccess = r?.data?.access_token;
        const newRefresh = r?.data?.refresh_token;
        if (!newAccess) return { invalid: true };

        // Always update the in-memory axios default so subsequent requests
        // are authenticated even in cookie-less environments (Safari ITP).
        axios.defaults.headers.common["Authorization"] = `Bearer ${newAccess}`;
        localStorage.setItem("token_ts", String(Date.now()));

        // Rotate the stored refresh_token if the backend issued a new one.
        if (newRefresh) localStorage.setItem("refresh_token", newRefresh);

        // In development or E2E tests, also persist the access_token.
        if (window.navigator.webdriver || import.meta.env.DEV) {
          localStorage.setItem("token", newAccess);
        }

        return { token: newAccess };
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (!status || status >= 500) return { transient: true };
        return { invalid: true };
      })
      .finally(() => {
        _refreshInFlight = null;
      });
  }
  return _refreshInFlight;
}

// Response interceptor — 401 handling + Pydantic error normalization
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {};
    if (
      error.response?.status === 401 &&
      !original._skipAuthRetry &&
      !original._retried &&
      _isRefreshableUrl(original.url || "")
    ) {
      original._retried = true;
      const result = await _attemptRefresh();
      if (result?.token) {
        original.headers = original.headers || {};
        // Always set the new token on the retried request.
        // axios.defaults.headers.common["Authorization"] was already updated
        // by _attemptRefresh, so subsequent calls are also covered.
        original.headers.Authorization = `Bearer ${result.token}`;
        return axios(original);
      }
      if (result?.transient) {
        console.warn("Refresh transient failure (5xx/network); session preserved");
        return Promise.reject(error);
      }
      console.warn("401 Unauthorized - refresh failed, clearing session. URL:", original.url);
      _hardLogout();
    } else if (error.response?.status === 401 && !original._skipAuthRetry) {
      // A _retried request returned 401 again → hard fail.
      console.warn("401 Unauthorized after retry - clearing session. URL:", original.url);
      _hardLogout();
    }
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      // Yapılandırılmış iş hatası nesnesinden insan-okunur metin türet.
      // Legacy çağrılar `e.response?.data?.detail || e.message` veya
      // `'Hata: ' + detail` paterniyle tüketiyor; toString override sayesinde
      // hem nesne korunur hem string concat'te '[object Object]' çıkmaz.
      const humanize = (d) =>
        d?.error || d?.message || d?.msg || (d?.code ? `İşlem engellendi (${d.code})` : "İşlem başarısız");
      const wrapStructured = (d) => {
        Object.defineProperty(d, "toString", {
          value: () => humanize(d),
          enumerable: false,
          configurable: true,
        });
        return d;
      };
      if (Array.isArray(detail)) {
        const hasStructured = detail.some(
          (d) => typeof d === "object" && d !== null && d.code,
        );
        if (hasStructured) {
          // Code'lu yapılandırılmış nesneleri içeren array'i koru, çağıran
          // handler ilk elemanı kendi mantığıyla işlesin.
          detail.forEach((d) => {
            if (typeof d === "object" && d !== null) wrapStructured(d);
          });
        } else {
          error.response.data.detail = detail
            .map((d) => (typeof d === "object" && d !== null ? d.msg || JSON.stringify(d) : d))
            .join("; ");
        }
      } else if (typeof detail === "object" && detail !== null) {
        // Pydantic tek-hata nesnesi ({msg, type, loc}) ve `code` yoksa string'e çevir.
        // Yapılandırılmış iş hatası nesneleri ({code, run, ...}) dokunulmadan
        // bırakılır; toString override ile legacy concat çağrıları korunur.
        if (typeof detail.msg === "string" && !detail.code) {
          error.response.data.detail = detail.msg;
        } else {
          wrapStructured(detail);
        }
      }
    }
    return Promise.reject(error);
  }
);

export { BACKEND_URL };
export default axios;
