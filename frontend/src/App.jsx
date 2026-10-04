import { useState, useEffect, useMemo, Suspense, lazy } from "react";
import "@/App.css";
import { keepActiveSessionAlive } from "@/config/axiosConfig";
import { clearAxiosCache } from "@/lib/axios-cache";
import axios from "axios";
import { BrowserRouter, Routes, Route, Navigate, useParams, useNavigate, useLocation } from "react-router-dom";
import PlanRouteGuard from "@/components/PlanRouteGuard";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import usePushNotifications from "@/hooks/usePushNotifications";
import useUserAccessRefresh from "@/hooks/useUserAccessRefresh";
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
import { scheduleHeavyModulePrefetch } from "@/lib/prefetch";
import { websocket } from "@/lib/websocket";
import {
  ADMIN_TENANT_CONTEXT_KEY,
  ADMIN_TENANT_SESSION_EVENT,
  reconcileAdminTenantContext,
} from "@/lib/adminTenantContext";
import { resolvePostLoginDestination } from "@/lib/postLoginWorkspace";
import {
  blockTabAfterExternalSessionChange,
  clearAuthScopedSessionStorage,
  clearTabAuthScope,
  isForeignIdentityForTab,
  isTabAuthBlocked,
  readSharedAuthUser,
  rememberTabAuthSubject,
} from "@/lib/authSessionScope";

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

function RouteAwareCommunicationCenter({ user }) {
  const { pathname } = useLocation();
  const isGuestRoomService = /^\/g\/(?:room\/|[^/]+\/room\/)/.test(pathname) || pathname.startsWith("/room-qr/");
  return isGuestRoomService ? null : <CommunicationCenter user={user} />;
}

// Legacy bookmarks are kept working, but must converge on one workspace URL.
// Keeping the current query and hash is important for report section links and
// deep-linked settings tabs.
function CanonicalRedirect({ to }) {
  const location = useLocation();
  return <Navigate replace to={{ pathname: to, search: location.search, hash: location.hash }} />;
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
  localStorage.removeItem("entitlements");
  localStorage.removeItem(ADMIN_TENANT_CONTEXT_KEY);
  clearAxiosCache();
  // SessionStorage cache'leri de sil — aynı tab'da hesap değişiminde
  // önceki kullanıcının notification/business-date verisi sızmasın.
  clearAuthScopedSessionStorage();
  notifyServiceWorkerAuthChanged();
}

function clearAccessCaches() {
  clearAxiosCache();
  queryClient.clear();
  notifyServiceWorkerAuthChanged();
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [tenant, setTenant] = useState(null);
  const [modules, setModules] = useState(null);
  const [loading, setLoading] = useState(true);

  usePushNotifications(isAuthenticated ? user : null);
  useUserAccessRefresh(isAuthenticated ? user : null, setUser, clearAccessCaches);

  useEffect(() => {
    if (isTabAuthBlocked()) {
      // A different identity was established in another same-browser tab.
      // Do not silently adopt it. The user must explicitly authenticate here.
      setLoading(false);
      return undefined;
    }
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
          if (isForeignIdentityForTab(freshUser)) {
            // Never repaint an existing workspace as another hotel/user. This
            // is intentionally local to this tab; the new session must remain
            // valid in the tab/device where it was explicitly established.
            blockTabAfterExternalSessionChange();
            clearAccessCaches();
            delete axios.defaults.headers.common["Authorization"];
            setUser(null);
            setTenant(null);
            setModules(null);
            setIsAuthenticated(false);
            return;
          }
          let parsedTenant = null;
          if (storedTenant && storedTenant !== "null") {
            try { parsedTenant = JSON.parse(storedTenant); } catch { /* ignore parse error */ }
          }
          let parsedModules = null;
          if (storedModules) {
            try { parsedModules = JSON.parse(storedModules); } catch { /* ignore parse error */ }
          }
          const applyAuthenticatedSnapshot = (nextTenant, nextModules) => {
            const recoveredTenant = nextTenant || parsedTenant;
            const recoveredModules = nextModules || parsedModules || recoveredTenant?.modules || null;
            const reconciled = reconcileAdminTenantContext(freshUser, recoveredTenant, recoveredModules);
            const reconciledTenant = reconciled.tenant
              ? (reconciled.modules ? { ...reconciled.tenant, modules: reconciled.modules } : reconciled.tenant)
              : null;
            localStorage.setItem("user", JSON.stringify(reconciled.user));
            localStorage.setItem("tenant", reconciledTenant ? JSON.stringify(reconciledTenant) : "null");
            if (reconciled.modules) localStorage.setItem("modules", JSON.stringify(reconciled.modules));
            setUser(reconciled.user);
            setModules(reconciled.modules);
            setTenant(reconciledTenant);
            setIsAuthenticated(true);
            rememberTabAuthSubject(reconciled.user);
          };

          // Identity is the only blocking authentication check. Waiting for
          // subscription data here left the application as a blank spinner
          // after login even when this browser had a valid tenant snapshot.
          // Render the verified user's workspace immediately, then reconcile
          // package and module metadata in the background.
          applyAuthenticatedSnapshot(parsedTenant, parsedModules);
          scheduleHeavyModulePrefetch();

          if (freshUser?.tenant_id) {
            void axios.get("/subscription/current")
              .then((subscriptionResponse) => {
                const subscriptionContext = subscriptionResponse?.data || null;
                applyAuthenticatedSnapshot(
                  subscriptionContext?.tenant || parsedTenant,
                  subscriptionContext?.modules || parsedModules,
                );
              })
              .catch(() => {
                // EntitlementContext independently refreshes this data. A
                // delayed or unavailable subscription response must not make
                // the already verified first screen wait or disappear.
              });
          }
        })
        .catch((error) => {
          if (error?._sessionContextRestored) {
            // The auth interceptor has already restored the super-admin's
            // origin session and initiated navigation to its tenant list.
            // Do not clear the freshly restored local session because the
            // original request happened to be a 401 from the expired
            // short-lived workspace context.
            return;
          }
          const sessionVerificationTransient = Boolean(error?._sessionVerificationTransient);
          const status = error?.response?.status;
          if (status === 401 && !sessionVerificationTransient) {
            clearAuthStorage();
            setIsAuthenticated(false);
            return;
          }

          // A deployment restart or a short network outage must not turn
          // into an implicit logout. Keep the last verified local identity;
          // API authorization remains enforced by the server and the global
          // interceptor will still hard-logout on a definitive 401. This also
          // covers a 401 whose refresh retry could not be verified.
          try {
            const cachedUser = JSON.parse(storedUser);
            // Network fallback is safe only for the identity already verified
            // by this tab. A localStorage snapshot belongs to all tabs and is
            // never enough to establish a different account here.
            if (isForeignIdentityForTab(cachedUser)) {
              blockTabAfterExternalSessionChange();
              setIsAuthenticated(false);
              return;
            }
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
    const authKeys = new Set(["user", "tenant", "modules", "token_ts", "refresh_token", "token", ADMIN_TENANT_CONTEXT_KEY]);
    const onStorage = (event) => {
      if (!authKeys.has(event.key)) return;
      const sharedUser = readSharedAuthUser();
      if (!sharedUser) {
        // An explicit logout in another tab belongs to this browser session.
        // Clear only this tab's in-memory state; the tab that initiated
        // logout already owns the shared-storage cleanup.
        clearTabAuthScope();
        clearAccessCaches();
        delete axios.defaults.headers.common["Authorization"];
        setUser(null);
        setTenant(null);
        setModules(null);
        setIsAuthenticated(false);
        try { websocket.disconnect?.(); } catch { /* noop */ }
        notifyAuthChanged();
        return;
      }
      if (!isForeignIdentityForTab(sharedUser)) return;

      // `storage` is emitted in every *other* tab. A login, logout or
      // super-admin property switch elsewhere must close this tab's in-memory
      // workspace, never turn it into that other user's workspace.
      blockTabAfterExternalSessionChange();
      clearAccessCaches();
      delete axios.defaults.headers.common["Authorization"];
      setUser(null);
      setTenant(null);
      setModules(null);
      setIsAuthenticated(false);
      try { websocket.disconnect?.(); } catch { /* noop */ }
      notifyAuthChanged();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
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

  useEffect(() => {
    const applyTenantSession = (event) => {
      const next = event?.detail;
      if (!next?.user || !next?.tenant) return;
      const nextModules = next.modules || next.tenant.modules || {};
      setUser(next.user);
      setModules(nextModules);
      setTenant({ ...next.tenant, modules: nextModules });
      clearAccessCaches();
      try { websocket.reconnectWithFreshAuth?.(); } catch { /* non-fatal */ }
      notifyAuthChanged();
    };
    window.addEventListener(ADMIN_TENANT_SESSION_EVENT, applyTenantSession);
    return () => window.removeEventListener(ADMIN_TENANT_SESSION_EVENT, applyTenantSession);
  }, []);

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
    rememberTabAuthSubject(canonicalUser);

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
    scheduleHeavyModulePrefetch();

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

    // ── Post-login workspace routing ──────────────────────────────
    // A central chain manager chooses the hotel workspace before entering PMS.
    // The backend endpoint only returns siblings after verifying chain scope.
    // An explicit deep-link always wins over this default landing page.
    const resolvedLanding = await resolvePostLoginDestination({
      api: axios,
      user: canonicalUser,
      existingRedirect: sessionStorage.getItem("postLoginRedirect"),
    });
    if (resolvedLanding) sessionStorage.setItem("postLoginRedirect", resolvedLanding);

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
        <CurrencyProvider key={tenant?.id || tenant?._id || 'guest'} isAuthenticated={isAuthenticated}>
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
      <CurrencyProvider key={tenant?.id || tenant?._id || 'anonymous'} isAuthenticated={isAuthenticated}>
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
                      element = rc.preserveLocation
                        ? <CanonicalRedirect to={rc.to} />
                        : <Navigate to={rc.to} replace />;
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
                      element = (
                        <ModuleGuardedRoute
                          isAuthenticated={isAuthenticated}
                          moduleKey={rc.moduleKey}
                          strict={rc.strict}
                          allowedRoles={rc.allowedRoles}
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
                        element = (
                          <ProtectedRoute
                            isAuthenticated={isAuthenticated}
                            element={<ModuleAvailabilityState reason="forbidden" />}
                            wrapLayout
                            layoutModule="dashboard"
                            user={user}
                            tenant={tenant}
                            onLogout={handleLogout}
                          />
                        );
                      } else {
                        element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} wrapLayout={rc.wrapLayout} layoutModule={rc.layoutModule} user={user} tenant={tenant} onLogout={handleLogout} />;
                      }
                    } else {
                      element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} wrapLayout={rc.wrapLayout} layoutModule={rc.layoutModule} user={user} tenant={tenant} onLogout={handleLogout} />;
                    }

                    return <Route key={rc.path} path={rc.path} element={element} />;
                  })}

                  {/* Catch-all */}
                  <Route
                    path="*"
                    element={isAuthenticated ? (
                      <ProtectedRoute
                        isAuthenticated={isAuthenticated}
                        element={<ModuleAvailabilityState reason="disabled" />}
                        wrapLayout
                        layoutModule="dashboard"
                        user={user}
                        tenant={tenant}
                        onLogout={handleLogout}
                      />
                    ) : <Navigate to="/auth" replace />}
                  />
                </Routes>
                </Suspense>
              </PlanRouteGuard>
            </ErrorBoundary>
            </SimulationProvider>
            {isAuthenticated && user && <RouteAwareCommunicationCenter user={user} />}
          </BrowserRouter>
          {isAuthenticated && user && <InternalChatWidget user={user} hideLauncher />}
          {isAuthenticated && user && (
            <Suspense fallback={null}>
              <Softphone user={user} hideLauncher />
            </Suspense>
          )}
        </div>
      </QueryClientProvider>
      </CurrencyProvider>
    </NotificationProvider>
    </EntitlementProvider>
  );
}

export default App;
