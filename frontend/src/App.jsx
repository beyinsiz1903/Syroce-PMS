import { useState, useEffect, useMemo, Suspense, lazy } from "react";
import "@/App.css";
import { keepActiveSessionAlive } from "@/config/axiosConfig";
import { clearAxiosCache } from "@/lib/axios-cache";
import axios from "axios";
import { BrowserRouter, Routes, Route, Navigate, useParams, useNavigate } from "react-router-dom";
import PlanRouteGuard from "@/components/PlanRouteGuard";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import usePushNotifications from "@/hooks/usePushNotifications";
import { NotificationProvider, notifyAuthChanged } from "@/context/NotificationContext";
import InternalChatWidget from "@/components/InternalChatWidget";
import CommunicationCenter from "@/components/CommunicationCenter";
import { CurrencyProvider } from "@/context/CurrencyContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ModuleAvailabilityState } from "@/components/shared/ModuleAvailabilityState";
import { Toaster } from "@/components/ui/sonner";
import DialogHost from "@/components/DialogHost";
import OfflineStatusBar from "@/components/OfflineStatusBar";
import { SimulationProvider } from "@/context/SimulationContext";
import SimulationOverlay from "@/components/SimulationOverlay";
import {
  AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal, getRouteConfigs,
} from "@/routes/routeDefinitions";
import {
  ProtectedRoute, ProtectedRouteWithMemory, ModuleGuardedRoute, LoadingFallback,
} from "@/routes/ProtectedRoute";
import { registerRoutes } from "@/routes/preload";
import { EntitlementProvider } from "@/context/EntitlementContext";
import { prefetchHeavyModules } from "@/lib/prefetch";
import { websocket } from "@/lib/websocket";
import {
  ADMIN_TENANT_CONTEXT_KEY,
  reconcileAdminTenantContext,
} from "@/lib/adminTenantContext";

// Sesli softphone (Contact Center Faz 2) — yalnızca personel için, lazy.
// Twilio Voice SDK + mikrofon izni operatör "Aktifleştir"e basınca yüklenir.
const Softphone = lazy(() => import("@/components/contact-center/Softphone"));

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
  localStorage.removeItem(ADMIN_TENANT_CONTEXT_KEY);
  clearAxiosCache();
  // SessionStorage cache'leri de sil — aynı tab'da hesap değişiminde
  // önceki kullanıcının notification/business-date verisi sızmasın.
  try {
    sessionStorage.removeItem("notif_cache_v1");
    sessionStorage.removeItem("pms_bd_cache_v1");
  } catch { /* ignore */ }
  notifyServiceWorkerAuthChanged();
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [tenant, setTenant] = useState(null);
  const [modules, setModules] = useState(null);
  const [loading, setLoading] = useState(true);

  usePushNotifications(isAuthenticated ? user : null);

  useEffect(() => {
    const hasAuthCookieSession = localStorage.getItem("token_ts") !== null;
    const storedUser = localStorage.getItem("user");
    const storedTenant = localStorage.getItem("tenant");
    const storedModules = localStorage.getItem("modules");

    // Do not impose a client-side absolute session age. The server remains
    // authoritative and the 401 interceptor rotates the refresh token while
    // the account is active. This keeps an explicitly authenticated browser
    // session alive until logout, account revocation, or refresh rejection.
    if (hasAuthCookieSession && storedUser) {
      axios.get("/auth/me")
        .then((meResponse) => {
          const freshUser = meResponse.data;
          let parsedTenant = null;
          if (storedTenant && storedTenant !== "null") {
            try { parsedTenant = JSON.parse(storedTenant); } catch { /* ignore parse error */ }
          }
          let parsedModules = null;
          if (storedModules) {
            try { parsedModules = JSON.parse(storedModules); } catch { /* ignore parse error */ }
          }
          const reconciled = reconcileAdminTenantContext(freshUser, parsedTenant, parsedModules);
          const reconciledTenant = reconciled.tenant
            ? (reconciled.modules ? { ...reconciled.tenant, modules: reconciled.modules } : reconciled.tenant)
            : null;
          localStorage.setItem("user", JSON.stringify(reconciled.user));
          localStorage.setItem("tenant", reconciled.tenant ? JSON.stringify(reconciled.tenant) : "null");
          if (reconciled.modules) localStorage.setItem("modules", JSON.stringify(reconciled.modules));
          setUser(reconciled.user);
          setModules(reconciled.modules);
          setTenant(reconciledTenant);
          setIsAuthenticated(true);
          prefetchHeavyModules();
        })
        .catch((error) => {
          const status = error?.response?.status;
          if (status === 401) {
            clearAuthStorage();
            setIsAuthenticated(false);
            return;
          }

          // A deployment restart or a short network outage must not turn
          // into an implicit logout. Keep the last verified local identity;
          // API authorization remains enforced by the server and the global
          // interceptor will still hard-logout on a definitive 401.
          try {
            const cachedUser = JSON.parse(storedUser);
            const cachedTenant = storedTenant && storedTenant !== "null"
              ? JSON.parse(storedTenant)
              : null;
            const cachedModules = storedModules ? JSON.parse(storedModules) : null;
            setUser(cachedUser);
            setModules(cachedModules);
            setTenant(cachedTenant && cachedModules
              ? { ...cachedTenant, modules: cachedModules }
              : cachedTenant);
            setIsAuthenticated(true);
          } catch {
            // Corrupt cached identity is not a valid session fallback.
            clearAuthStorage();
            setIsAuthenticated(false);
          }
        })
        .finally(() => setLoading(false));
    } else {
      if (hasAuthCookieSession || localStorage.getItem("token")) clearAuthStorage();
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return undefined;

    const keepAlive = () => {
      keepActiveSessionAlive().catch(() => {
        // Ağ veya dağıtım kesintisi oturumu sonlandırmaz. Bir sonraki periyodik
        // kontrol tekrar dener; geçersiz oturum kararı merkezi auth katmanındadır.
      });
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") keepAlive();
    };

    const intervalId = window.setInterval(keepAlive, 5 * 60 * 1000);
    window.addEventListener("focus", keepAlive);
    window.addEventListener("online", keepAlive);
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", keepAlive);
      window.removeEventListener("online", keepAlive);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [isAuthenticated]);

  const handleLogin = async (token, userData, tenantData, refreshToken) => {
    // clearAuthStorage() içinden notifyServiceWorkerAuthChanged() çağrılıyor
    // Backend tokens are managed via HttpOnly cookies now. We just record the session start.
    clearAuthStorage();
    localStorage.setItem("token_ts", String(Date.now()));
    localStorage.setItem("tenant", tenantData ? JSON.stringify(tenantData) : "null");

    // In-memory token fallback: ensures immediate API requests (like /auth/me or /pms/dashboard)
    // succeed even if the browser/test-runner drops the newly set SameSite=Lax cookie.
    // This is safe against persistent XSS because it lives only in JS memory, not localStorage.
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      // refresh_token must be stored so the 401 interceptor can use Path A
      // (body token) when the in-memory access_token is gone (page reload,
      // Safari ITP blocking the httpOnly cookie). Access_token stays
      // in-memory only (more secure); refresh_token in localStorage is the
      // standard SPA pattern (Auth0, etc.) for cookie-less environments.
      if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
      // In development or E2E/test environments also persist the access_token
      // so Playwright doesn't drop it across browser contexts.
      if (window.navigator.webdriver || import.meta.env.DEV) {
        localStorage.setItem("token", token);
      }
    }

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
    try { websocket.disconnect?.(); } catch { /* noop */ }
    window.location.replace("/auth");
  };

  const hasFeature = (key) => {
    if (!key) return true;
    if (!user?.is_impersonating && ((user?.roles || []).includes("super_admin") || user?.role === "super_admin")) return true;
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
      <div className="loading-screen flex items-center justify-center h-screen bg-background text-foreground">
        <div className="text-center">
          <div className="spinner mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-muted border-t-primary" />
          <p className="text-muted-foreground">Yukleniyor...</p>
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


  const uRoles = (user?.roles || []).map(r => r.toLowerCase());
  const uRole = (user?.role || "").toLowerCase();
  const isSuperAdminUser = uRoles.includes("super_admin") || uRole === "super_admin" || uRole === "demo_manager_readonly";
  const isPlatformSuperAdmin = isSuperAdminUser && !user?.is_impersonating;

  return (
    <EntitlementProvider currentTenantId={tenant?.id} isSuperAdmin={isPlatformSuperAdmin}>
      <NotificationProvider>
      <CurrencyProvider isAuthenticated={isAuthenticated}>
      <QueryClientProvider client={queryClient}>
        <div className="App">
          <Toaster position="top-right" />
          <DialogHost />
          {isAuthenticated && <OfflineStatusBar />}
          <BrowserRouter>
            <SimulationProvider>
              <SimulationOverlay />
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
                      const uRoles = (user?.roles || []).map(r => r.toLowerCase());
                      const uRole = (user?.role || "").toLowerCase();
                      const isSuperAdmin = uRoles.includes("super_admin") || uRole === "super_admin" || uRole === "demo_manager_readonly";
                      element = (
                        <ModuleGuardedRoute
                          isAuthenticated={isAuthenticated}
                          moduleKey={rc.moduleKey}
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
                        element = (
                          <ProtectedRoute
                            isAuthenticated={isAuthenticated}
                            element={(
                              <ModuleAvailabilityState
                                moduleName={rc.moduleName || rc.layoutModule || "Bu modül"}
                                reason="disabled"
                              />
                            )}
                            wrapLayout={rc.wrapLayout}
                            layoutModule={rc.layoutModule}
                            user={user}
                            tenant={tenant}
                            onLogout={handleLogout}
                          />
                        );
                      } else {
                        element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} wrapLayout={rc.wrapLayout} layoutModule={rc.layoutModule} user={user} tenant={tenant} onLogout={handleLogout} />;
                      }
                    } else if (rc.requireSuperAdmin) {
                      const uRoles = (user?.roles || []).map(r => r.toLowerCase());
                      const uRole = (user?.role || "").toLowerCase();
                      const isSuperAdmin = !user?.is_impersonating && (uRoles.includes("super_admin") || uRole === "super_admin" || uRole === "demo_manager_readonly");
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
            </SimulationProvider>
          </BrowserRouter>
          {isAuthenticated && user && <InternalChatWidget user={user} hideLauncher />}
          {isAuthenticated && user && (
            <Suspense fallback={null}>
              <Softphone user={user} hideLauncher />
            </Suspense>
          )}
          {isAuthenticated && user && <CommunicationCenter user={user} />}
        </div>
      </QueryClientProvider>
      </CurrencyProvider>
    </NotificationProvider>
    </EntitlementProvider>
  );
}

export default App;
