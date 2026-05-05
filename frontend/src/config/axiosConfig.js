/**
 * Axios Configuration — Centralized HTTP client setup.
 * Configures base URL, interceptors, and error handling.
 */
import axios from "axios";

const RAW_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "/api";
const BACKEND_URL = RAW_BACKEND_URL.endsWith("/api")
  ? RAW_BACKEND_URL
  : RAW_BACKEND_URL.replace(/\/+$/, "") + "/api";

axios.defaults.baseURL = BACKEND_URL;
axios.defaults.timeout = 30000;

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

// Response interceptor — 401 handling + Pydantic error normalization
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn("401 Unauthorized - clearing session");
      localStorage.removeItem("token");
      localStorage.removeItem("token_ts");
      localStorage.removeItem("user");
      localStorage.removeItem("tenant");
      localStorage.removeItem("modules");
      delete axios.defaults.headers.common["Authorization"];
      if (window.location.pathname !== "/auth" && window.location.pathname !== "/") {
        window.location.assign("/auth");
      }
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
