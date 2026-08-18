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
import { hasModuleScope } from "@/utils/authRoles";

const Layout = lazy(() => import("@/components/Layout"));

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-screen">
    <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
  </div>
);

function withOptionalLayout(element, { wrapLayout, layoutModule, user, tenant, onLogout }) {
  if (!wrapLayout) return element;
  const embeddedElement = isValidElement(element)
    ? cloneElement(element, { embedded: true })
    : element;
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule={layoutModule}>
      {embeddedElement}
    </Layout>
  );
}

function inferScopeFromPath(path) {
  if (typeof path !== "string") return "";
  const pathname = path.split("?", 1)[0];
  const segments = pathname.split("/").filter(Boolean);
  return segments.at(-1) || "";
}

function scopeDenied(user, ...scopeKeys) {
  const keys = scopeKeys.filter(Boolean);
  return keys.length > 0 && !keys.some((key) => hasModuleScope(user, key));
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
  if (scopeDenied(user, layoutModule)) {
    return <Navigate to="/app/dashboard" replace />;
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
  const inferredScope = inferScopeFromPath(targetPath);
  if (scopeDenied(user, layoutModule, inferredScope)) {
    return <Navigate to="/app/dashboard" replace />;
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
  const { hasModule, hasFeature, loading, error, isSuperAdmin } = useEntitlements();

  if (!isAuthenticated) return <Navigate to="/auth" replace />;

  if (loading) {
    return <LoadingFallback />;
  }

  // Prevent redirect loops by checking if the user is already on the fallback route
  const currentPath = window.location.pathname;
  const fallbackRoute = isSuperAdmin ? "/admin" : "/app/dashboard";

  if (scopeDenied(user, moduleKey, layoutModule)) {
    if (currentPath === fallbackRoute) return null;
    return <Navigate to={fallbackRoute} replace />;
  }

  if (moduleKey && !hasModule(moduleKey)) {
    if (currentPath === fallbackRoute) return null; // Avoid loop
    return <Navigate to={fallbackRoute} replace />;
  }
  
  if (featureKey && !hasFeature(moduleKey, featureKey)) {
    if (currentPath === fallbackRoute) return null; // Avoid loop
    return <Navigate to={fallbackRoute} replace />;
  }
  return (
    <Suspense fallback={<LoadingFallback />}>
      {withOptionalLayout(element, { wrapLayout, layoutModule, user, tenant, onLogout })}
    </Suspense>
  );
}

export { LoadingFallback };
