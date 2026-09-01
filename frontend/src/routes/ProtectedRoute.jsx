/**
 * ProtectedRoute — Auth-guarded route wrapper with Suspense.
 * Reduces boilerplate from 10+ lines per route to a single element.
 *
 * Opt-in `wrapLayout` mode (May 2026 — M5 pilot):
 *   Sayfa kendi Layout sarımını yapmak yerine route definition'da
 *   `wrapLayout: true, layoutModule: "..."` flag'i geçilir → ProtectedRoute
 *   Layout'u dışarıdan sarar. Mevcut sayfalar (Layout'u içinde sarıyorlar)
 *   bu flag olmadan eskisi gibi çalışır — geriye uyumlu, incremental migration.
 */
import { cloneElement, isValidElement, Suspense, lazy } from "react";
import { Navigate } from "react-router-dom";
import { useEntitlements } from "@/context/EntitlementContext";
import { ModuleAvailabilityState } from "@/components/shared/ModuleAvailabilityState";

const Layout = lazy(() => import("@/components/Layout"));

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-screen">
    <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
  </div>
);

const RouteContentLoadingFallback = () => (
  <div
    data-testid="route-content-loading"
    className="flex min-h-[40vh] items-center justify-center rounded-xl border border-slate-200 bg-white"
  >
    <div className="text-center">
      <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-b-blue-600" />
      <p className="text-sm font-medium text-slate-600">Sayfa hazırlanıyor…</p>
    </div>
  </div>
);

function withOptionalLayout(element, { wrapLayout, layoutModule, user, tenant, onLogout }) {
  if (!wrapLayout) return element;
  const embeddedElement = isValidElement(element)
    ? cloneElement(element, { embedded: true })
    : element;
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule={layoutModule}>
      <Suspense fallback={<RouteContentLoadingFallback />}>
        {embeddedElement}
      </Suspense>
    </Layout>
  );
}

export function ProtectedRoute({
  isAuthenticated,
  element,
  redirectTo = "/auth",
  wrapLayout = false,
  layoutModule,
  user,
  tenant,
  onLogout,
}) {
  if (!isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
  }
  return (
    <Suspense fallback={<LoadingFallback />}>
      {withOptionalLayout(element, { wrapLayout, layoutModule, user, tenant, onLogout })}
    </Suspense>
  );
}

export function ProtectedRouteWithMemory({
  isAuthenticated,
  element,
  targetPath,
  wrapLayout = false,
  layoutModule,
  user,
  tenant,
  onLogout,
}) {
  if (!isAuthenticated) {
    if (targetPath) {
      sessionStorage.setItem("postLoginRedirect", targetPath);
    }
    return <Navigate to="/auth" replace state={{ redirectTo: targetPath }} />;
  }
  return (
    <Suspense fallback={<LoadingFallback />}>
      {withOptionalLayout(element, { wrapLayout, layoutModule, user, tenant, onLogout })}
    </Suspense>
  );
}

export function ModuleGuardedRoute({
  isAuthenticated,
  moduleKey,
  featureKey,
  element,
  strict = false,
  wrapLayout = false,
  layoutModule,
  user,
  tenant,
  onLogout,
}) {
  const { hasModule, hasFeature, loading, error, refresh } = useEntitlements();

  if (!isAuthenticated) return <Navigate to="/auth" replace />;

  if (loading) {
    return <LoadingFallback />;
  }

  if (moduleKey && !hasModule(moduleKey)) {
    const moduleNames = {
      hr: "İnsan Kaynakları",
      mice: "MICE & Banquet",
      spa: "Spa & Wellness",
      pos_fnb: "Restoran POS",
    };
    const unavailable = (
      <ModuleAvailabilityState
        moduleName={moduleNames[moduleKey] || moduleKey}
        reason={error ? "temporary" : "disabled"}
        onRetry={error ? refresh : undefined}
      />
    );
    return (
      <Suspense fallback={<LoadingFallback />}>
        {withOptionalLayout(unavailable, { wrapLayout, layoutModule, user, tenant, onLogout })}
      </Suspense>
    );
  }
  
  if (featureKey && !hasFeature(moduleKey, featureKey)) {
    const unavailable = (
      <ModuleAvailabilityState moduleName={moduleKey || "Bu modül"} reason="disabled" />
    );
    return (
      <Suspense fallback={<LoadingFallback />}>
        {withOptionalLayout(unavailable, { wrapLayout, layoutModule, user, tenant, onLogout })}
      </Suspense>
    );
  }
  return (
    <Suspense fallback={<LoadingFallback />}>
      {withOptionalLayout(element, { wrapLayout, layoutModule, user, tenant, onLogout })}
    </Suspense>
  );
}

export { LoadingFallback, RouteContentLoadingFallback };
