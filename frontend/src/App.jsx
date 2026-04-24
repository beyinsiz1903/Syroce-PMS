import { useState, useEffect, useMemo, Suspense } from "react";
import "@/App.css";
import "@/config/axiosConfig";
import axios from "axios";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import PlanRouteGuard from "@/components/PlanRouteGuard";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import usePushNotifications from "@/hooks/usePushNotifications";
import { NotificationProvider } from "@/context/NotificationContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Toaster } from "@/components/ui/sonner";

import {
  AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal, getRouteConfigs,
} from "@/routes/routeDefinitions";
import {
  ProtectedRoute, ProtectedRouteWithMemory, ModuleGuardedRoute, LoadingFallback,
} from "@/routes/ProtectedRoute";
import { registerRoutes } from "@/routes/preload";

const TOKEN_MAX_AGE_MS = 24 * 60 * 60 * 1000;

function clearAuthStorage() {
  localStorage.removeItem("token");
  localStorage.removeItem("token_ts");
  localStorage.removeItem("user");
  localStorage.removeItem("tenant");
  localStorage.removeItem("modules");
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

  const handleLogin = async (token, userData, tenantData) => {
    clearAuthStorage();
    localStorage.setItem("token", token);
    localStorage.setItem("token_ts", String(Date.now()));
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
    clearAuthStorage();
    try { sessionStorage.clear(); } catch { /* ignore */ }
    delete axios.defaults.headers.common["Authorization"];
    setUser(null);
    setTenant(null);
    setModules(null);
    setIsAuthenticated(false);
    window.location.replace("/auth");
  };

  const hasFeature = (key) => {
    if (!key) return true;
    if ((user?.roles || []).includes("super_admin") || user?.role === "super_admin") return true;
    return !!tenant?.features?.[key];
  };

  const routeConfigs = useMemo(
    () => getRouteConfigs({ user, tenant, modules, isAuthenticated, onLogout: handleLogout, hasFeature }),
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
        <QueryClientProvider client={queryClient}>
          <div className="App">
            <Toaster position="top-right" />
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/privacy-policy" element={<PrivacyPolicy />} />
                <Route path="/gizlilik" element={<PrivacyPolicy />} />
                <Route path="/guest-portal/*" element={<GuestPortal user={user} onLogout={handleLogout} />} />
                <Route path="*" element={<Navigate to="/guest-portal" replace />} />
              </Routes>
            </BrowserRouter>
          </div>
        </QueryClientProvider>
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
      <QueryClientProvider client={queryClient}>
        <div className="App">
          <Toaster position="top-right" />
          <BrowserRouter>
            <ErrorBoundary>
              <PlanRouteGuard tenant={tenant} user={user}>
                <Routes>
                  {/* Auth */}
                  <Route path="/login" element={<Navigate to="/auth" replace />} />
                  <Route path="/auth" element={!isAuthenticated ? <AuthPage onLogin={handleLogin} /> : <PostAuthRedirect />} />
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
                        />
                      );
                    } else if (rc.type === "feature") {
                      if (!isAuthenticated) {
                        element = <Navigate to="/auth" replace />;
                      } else if (!hasFeature(rc.featureKey)) {
                        element = <Navigate to="/" replace />;
                      } else {
                        element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} />;
                      }
                    } else if (rc.requireSuperAdmin) {
                      const isSuperAdmin = (user?.roles || []).includes("super_admin") || user?.role === "super_admin";
                      if (!isAuthenticated) {
                        element = <Navigate to="/auth" replace />;
                      } else if (!isSuperAdmin) {
                        element = <Navigate to="/app/dashboard" replace />;
                      } else {
                        element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} />;
                      }
                    } else {
                      element = <ProtectedRoute isAuthenticated={isAuthenticated} element={<rc.component {...rc.props} />} />;
                    }

                    return <Route key={rc.path} path={rc.path} element={element} />;
                  })}

                  {/* Catch-all */}
                  <Route path="*" element={isAuthenticated ? <Navigate to="/app/dashboard" replace /> : <Navigate to="/auth" replace />} />
                </Routes>
              </PlanRouteGuard>
            </ErrorBoundary>
          </BrowserRouter>
        </div>
      </QueryClientProvider>
    </NotificationProvider>
  );
}

export default App;
