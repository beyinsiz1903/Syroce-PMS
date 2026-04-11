/**
 * ProtectedRoute — Auth-guarded route wrapper with Suspense.
 * Reduces boilerplate from 10+ lines per route to a single element.
 */
import { Suspense } from "react";
import { Navigate } from "react-router-dom";

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-screen">
    <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
  </div>
);

export function ProtectedRoute({ isAuthenticated, element, redirectTo = "/auth" }) {
  if (!isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
  }
  return <Suspense fallback={<LoadingFallback />}>{element}</Suspense>;
}

export function ProtectedRouteWithMemory({ isAuthenticated, element, targetPath }) {
  if (!isAuthenticated) {
    if (targetPath) {
      sessionStorage.setItem("postLoginRedirect", targetPath);
    }
    return <Navigate to="/auth" replace state={{ redirectTo: targetPath }} />;
  }
  return <Suspense fallback={<LoadingFallback />}>{element}</Suspense>;
}

export function ModuleGuardedRoute({ isAuthenticated, moduleEnabled, element }) {
  if (!isAuthenticated) return <Navigate to="/auth" replace />;
  if (moduleEnabled === false) return <Navigate to="/" replace />;
  return <Suspense fallback={<LoadingFallback />}>{element}</Suspense>;
}

export { LoadingFallback };
