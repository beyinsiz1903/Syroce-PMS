import { useState, useEffect, useMemo, Suspense, lazy } from "react";
import "@/App.css";
import "@/config/axiosConfig";
import axios from "axios";
import { BrowserRouter, Routes, Route, Navigate, useParams, useNavigate } from "react-router-dom";
import PlanRouteGuard from "@/components/PlanRouteGuard";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import usePushNotifications from "@/hooks/usePushNotifications";
import { NotificationProvider, notifyAuthChanged } from "@/context/NotificationContext";
import InternalChatWidget from "@/components/InternalChatWidget";
import { CurrencyProvider } from "@/context/CurrencyContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Toaster } from "@/components/ui/sonner";
import DialogHost from "@/components/DialogHost";

import {
  AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal, getRouteConfigs,
} from "@/routes/routeDefinitions";
import {
  ProtectedRoute, ProtectedRouteWithMemory, ModuleGuardedRoute, LoadingFallback,
} from "@/routes/ProtectedRoute";
import { registerRoutes } from "@/routes/preload";
import { prefetchHeavyModules } from "@/lib/prefetch";

// Misafir akışı için lazy yüklenen sayfa wrapper'ları
const SelfCheckinPage = lazy(() => import("@/pages/SelfCheckin"));
const DigitalKeyPage = lazy(() => import("@/pages/DigitalKey"));
const SupplierAuthPage = lazy(() => import("@/pages/SupplierAuthPage"));

function SelfCheckinRoute() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  return (
    <SelfCheckinPage
      bookingId={bookingId}
      onComplete={() => navigate(`/guest/digital-key/${bookingId}`)}
    />
  );
}

function DigitalKeyRoute() {
  const { bookingId } = useParams();
  return <DigitalKeyPage bookingId={bookingId} />;
}

// 7 gün — silent-refresh akışı varken bile, refresh token ömrü dolmuş
// (30 gün) bir cihazda yerel kontrol ek bir savunma katmanı sağlıyor.
const TOKEN_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function notifyServiceWorkerAuthChanged() {
  // SW v1.1.0+ AUTH_CHANGED mesajına karşılık tüm `hotel-pms-*` cache'leri
  // siler. Login/logout/clearAuthStorage akışlarından çağrılır → cross-user
  // veri sızıntısı önlenir (User A'nın cache'lediği /api/rooms response'u
  // User B'ye servis edilmez).
  try {
    if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "AUTH_CHANGED" });
    }
  } catch { /* ignore — SW yoksa zaten cache de yok */ }
}

function clearAuthStorage() {
  localStorage.removeItem("token");
  localStorage.removeItem("token_ts");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
  localStorage.removeItem("tenant");
  localStorage.removeItem("modules");
  // SessionStorage cache'leri de sil — aynı tab'da hesap değişiminde
  // önceki kullanıcının notification/business-date verisi sızmasın.
  try {
    sessionStorage.removeItem("notif_cache_v1");
    sessionStorage.removeItem("pms_bd_cache_v1");
  } catch { /* ignore */ }
  notifyServiceWorkerAuthChanged();
}

function isTokenExpiredLocally() {
  const ts = localStorage.getItem("token_ts");
  if (!ts) return true;
  return Date.now() - Number(ts) > TOKEN_MAX_AGE_MS;
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [tenant, setTenant] = useState(null);
  const [modules, setModules] = useState(null);
  const [loading, setLoading] = useState(true);

  usePushNotifications(isAuthenticated ? user : null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    const storedUser = localStorage.getItem("user");
    const storedTenant = localStorage.getItem("tenant");
    const storedModules = localStorage.getItem("modules");

    if (token && storedUser && !isTokenExpiredLocally()) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      axios.get("/auth/me")
        .then((meResponse) => {
          const freshUser = meResponse.data;
          localStorage.setItem("user", JSON.stringify(freshUser));
          setUser(freshUser);
          let parsedTenant = null;
          if (storedTenant && storedTenant !== "null") {
            try { parsedTenant = JSON.parse(storedTenant); } catch { /* ignore parse error */ }
          }
          let parsedModules = null;
          if (storedModules) {
            try { parsedModules = JSON.parse(storedModules); setModules(parsedModules); } catch { /* ignore parse error */ }
          }
          setTenant(parsedTenant ? (parsedModules ? { ...parsedTenant, modules: parsedModules } : parsedTenant) : null);
          setIsAuthenticated(true);
          prefetchHeavyModules();
        })
        .catch(() => {
          clearAuthStorage();
          setIsAuthenticated(false);
        })
        .finally(() => setLoading(false));
    } else {
      if (token) clearAuthStorage();
      setLoading(false);
    }
  }, []);

  const handleLogin = async (token, userData, tenantData, refreshToken) => {
    // clearAuthStorage() içinden notifyServiceWorkerAuthChanged() çağrılıyor
    // → eski kullanıcının cache'i SW tarafında temizlenir, yeni token ile
    // taze veri çekilir.
    clearAuthStorage();
    localStorage.setItem("token", token);
    localStorage.setItem("token_ts", String(Date.now()));
    if (refreshToken) {
      localStorage.setItem("refresh_token", refreshToken);
    }
    localStorage.setItem("tenant", tenantData ? JSON.stringify(tenantData) : "null");
    axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;

    // Canonical user from /auth/me — role/permission kaynağı login response değil, /me
    let canonicalUser = userData;
    try {
      const me = await axios.get("/auth/me");
      if (me?.data) canonicalUser = me.data;
    } catch { /* fallback: login response */ }
    localStorage.setItem("user", JSON.stringify(canonicalUser));

    const fetchModules = async () => {
      try {
        const res = await axios.get("/subscription/current");
        const tenantModules = res.data?.modules || null;
        if (tenantModules) { localStorage.setItem("modules", JSON.stringify(tenantModules)); setModules(tenantModules); }
      } catch { /* ignore fetch error */ }
    };

    setUser(canonicalUser);
    setTenant(tenantData);
    setIsAuthenticated(true);
    fetchModules();
    prefetchHeavyModules();

    // Reconnect the realtime socket so the new JWT is sent during the
    // socket.io handshake and the user joins their tenant-scoped rooms
    // (internal_chat:{tenant}:user:{uid}, :dept:{dept}, :broadcast).
    try {
      const { websocket } = await import('@/lib/websocket');
      websocket.reconnectWithFreshAuth?.();
    } catch { /* non-fatal */ }

    // Tell the NotificationProvider (which is mounted across login/logout
    // and would otherwise hold a stale snapshot of the user) to re-read
    // the cached identity and rewire its socket subscription + unread fetch.
    notifyAuthChanged();

    // ── Auto-redirect to Onboarding Wizard ───────────────────────
    // For tenant admins on a fresh setup (not dismissed, fewer than
    // 3 steps complete), land them on the wizard instead of the
    // dashboard. A deep-link in postLoginRedirect always wins.
    const ADMIN_ROLES = new Set([
      "super_admin", "platform_admin", "admin", "owner",
    ]);
    const role = (canonicalUser?.role || "").toLowerCase();
    const isTenantAdmin = ADMIN_ROLES.has(role) && !!canonicalUser?.tenant_id;
    const hasDeepLink = !!sessionStorage.getItem("postLoginRedirect");
    if (isTenantAdmin && !hasDeepLink) {
      try {
        const r = await axios.get("/onboarding/progress");
        const d = r?.data || {};
        if (d.dismissed === false && (d.completed ?? 0) < 3) {
          sessionStorage.setItem("postLoginRedirect", "/app/onboarding");
        }
      } catch { /* non-fatal */ }
    }

    const redirectAfterLogin = sessionStorage.getItem("postLoginRedirect");
    if (redirectAfterLogin) {
      sessionStorage.removeItem("postLoginRedirect");
      window.location.assign(redirectAfterLogin);
    }
  };

  const handleLogout = () => {
    // Best-effort: backend'e refresh_token'ı bildir → server-side revoke list'e
    // yazılır, çalınmış token çıkış sonrası kullanılamaz. Hata olsa bile
    // local clear yapılır (network down olsa bile kullanıcı çıkmış sayılır).
    const refreshToken = localStorage.getItem("refresh_token");
    try {
      axios.post("/auth/logout", refreshToken ? { refresh_token: refreshToken } : {})
        .catch(() => { /* non-fatal: local clear yine de uygulanır */ });
    } catch { /* ignore */ }
    clearAuthStorage();
    try { sessionStorage.clear(); } catch { /* ignore */ }
    delete axios.defaults.headers.common["Authorization"];
    setUser(null);
    setTenant(null);
    setModules(null);
    setIsAuthenticated(false);
    // Drop the realtime socket and tell the notification provider so it can
    // clear stale internal-chat state immediately (it would otherwise wait
    // for the page reload below).
    notifyAuthChanged();
    import('@/lib/websocket').then(({ websocket }) => {
      try { websocket.disconnect?.(); } catch { /* noop */ }
    }).catch(() => { /* non-fatal */ });
    window.location.replace("/auth");
  };

  const hasFeature = (key) => {
    if (!key) return true;
    if ((user?.roles || []).includes("super_admin") || user?.role === "super_admin") return true;
    return !!tenant?.features?.[key];
  };

  const routeConfigs = useMemo(
    () => getRouteConfigs({ user, tenant, modules, isAuthenticated, onLogout: handleLogout, hasFeature }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
    [user, tenant, modules, isAuthenticated]
  );
  useEffect(() => { registerRoutes(routeConfigs); }, [routeConfigs]);

  if (loading) {
    return (
      <div className="loading-screen" style={{
        display: "flex", justifyContent: "center", alignItems: "center", height: "100vh",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}>
        <div style={{ textAlign: "center", color: "white" }}>
          <div className="spinner" style={{
            border: "4px solid rgba(255,255,255,0.3)", borderTop: "4px solid white",
            borderRadius: "50%", width: "40px", height: "40px",
            animation: "spin 1s linear infinite", margin: "0 auto 1rem",
          }} />
          <p>Yukleniyor...</p>
        </div>
      </div>
    );
  }

  // Guest user routes
  if (isAuthenticated && user?.role === "guest") {
    return (
      <NotificationProvider>
        <CurrencyProvider isAuthenticated={isAuthenticated}>
        <QueryClientProvider client={queryClient}>
          <div className="App">
            <Toaster position="top-right" />
            <DialogHost />
            <BrowserRouter>
              <Suspense fallback={<LoadingFallback />}>
                <Routes>
                  <Route path="/" element={<LandingPage />} />
                  <Route path="/privacy-policy" element={<PrivacyPolicy />} />
                  <Route path="/gizlilik" element={<PrivacyPolicy />} />
                  {/* Misafir self-checkin / digital key akışı: GuestPortal'dan
                      yönlendirilir, kendi rezervasyonu için tam ekran sayfa. */}
                  <Route path="/guest/checkin/:bookingId" element={<SelfCheckinRoute />} />
                  <Route path="/guest/digital-key/:bookingId" element={<DigitalKeyRoute />} />
                  <Route path="/guest-portal/*" element={<GuestPortal user={user} onLogout={handleLogout} />} />
                  <Route path="*" element={<Navigate to="/guest-portal" replace />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </div>
        </QueryClientProvider>
        </CurrencyProvider>
      </NotificationProvider>
    );
  }

  const PostAuthRedirect = () => {
    const redirectTarget = sessionStorage.getItem("postLoginRedirect") || "/app/dashboard";
    sessionStorage.removeItem("postLoginRedirect");
    return <Navigate to={redirectTarget} replace />;
  };

  return (
    <NotificationProvider>
      <CurrencyProvider isAuthenticated={isAuthenticated}>
      <QueryClientProvider client={queryClient}>
        <div className="App">
          <Toaster position="top-right" />
          <DialogHost />
          <BrowserRouter>
            <ErrorBoundary>
              <PlanRouteGuard tenant={tenant} user={user}>
                <Suspense fallback={<LoadingFallback />}>
                <Routes>
                  {/* Auth */}
                  <Route path="/login" element={<Navigate to="/auth" replace />} />
                  <Route path="/auth" element={!isAuthenticated ? <AuthPage onLogin={handleLogin} /> : <PostAuthRedirect />} />
                  <Route path="/tedarikci/giris" element={<SupplierAuthPage />} />
                  <Route path="/" element={isAuthenticated ? <Navigate to="/app/dashboard" replace /> : <LandingPage />} />

                  {/* Dynamic routes from config */}
                  {routeConfigs.map((rc) => {
                    let element;

                    if (rc.type === "redirect") {
                      element = <Navigate to={rc.to} replace />;
                    } else if (rc.type === "public") {
                      element = <Suspense fallback={<LoadingFallback />}><rc.component {...(rc.props || {})} /></Suspense>;
                    } else if (rc.type === "memory") {
                      element = (
                        <ProtectedRouteWithMemory
                          isAuthenticated={isAuthenticated}
                          targetPath={rc.targetPath}
                          element={<rc.component {...rc.props} />}
                          wrapLayout={rc.wrapLayout}
                          layoutModule={rc.layoutModule}
                          user={user}
                          tenant={tenant}
                          onLogout={handleLogout}
                        />
                      );
                    } else if (rc.type === "module") {
                      const isSuperAdmin = (user?.roles || []).includes("super_admin") || user?.role === "super_admin";
                      element = (
                        <ModuleGuardedRoute
                          isAuthenticated={isAuthenticated}
                          moduleEnabled={isSuperAdmin ? true : modules?.[rc.moduleKey]}
                          strict={rc.strict}
                          element={<rc.component {...rc.props} />}
                          wrapLayout={rc.wrapLayout}
                          layoutModule={rc.layoutModule}
                          user={user}
                          tenant={tenant}
                          onLogout={handleLogout}
                        />
                      );
                    } else if (rc.type === "feature") {
                      if (!isAuthenticated) {
                        element = <Navigate to="/auth" replace />;
                      } else if (!hasFeature(rc.featureKey)) {
                        element = <Navigate to="/" replace />;
                      } else {
                        element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} wrapLayout={rc.wrapLayout} layoutModule={rc.layoutModule} user={user} tenant={tenant} onLogout={handleLogout} />;
                      }
                    } else if (rc.requireSuperAdmin) {
                      const isSuperAdmin = (user?.roles || []).includes("super_admin") || user?.role === "super_admin";
                      if (!isAuthenticated) {
                        element = <Navigate to="/auth" replace />;
                      } else if (!isSuperAdmin) {
                        element = <Navigate to="/app/dashboard" replace />;
                      } else {
                        element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} wrapLayout={rc.wrapLayout} layoutModule={rc.layoutModule} user={user} tenant={tenant} onLogout={handleLogout} />;
                      }
                    } else {
                      element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} wrapLayout={rc.wrapLayout} layoutModule={rc.layoutModule} user={user} tenant={tenant} onLogout={handleLogout} />;
                    }

                    return <Route key={rc.path} path={rc.path} element={element} />;
                  })}

                  {/* Catch-all */}
                  <Route path="*" element={isAuthenticated ? <Navigate to="/app/dashboard" replace /> : <Navigate to="/auth" replace />} />
                </Routes>
                </Suspense>
              </PlanRouteGuard>
            </ErrorBoundary>
          </BrowserRouter>
          {isAuthenticated && user && <InternalChatWidget user={user} />}
        </div>
      </QueryClientProvider>
      </CurrencyProvider>
    </NotificationProvider>
  );
}

export default App;
