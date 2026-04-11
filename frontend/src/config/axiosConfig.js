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
      console.warn("401 Unauthorized - Token may be invalid");
    }
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      if (Array.isArray(detail)) {
        error.response.data.detail = detail
          .map((d) => (typeof d === "object" ? d.msg || JSON.stringify(d) : d))
          .join("; ");
      } else if (typeof detail === "object") {
        error.response.data.detail = detail.msg || JSON.stringify(detail);
      }
    }
    return Promise.reject(error);
  }
);

export { BACKEND_URL };
export default axios;
