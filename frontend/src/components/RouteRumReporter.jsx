import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { RouteRum } from "@/lib/routeRum";

export default function RouteRumReporter() {
  const location = useLocation();
  const reporter = useRef(null);
  if (!reporter.current) reporter.current = new RouteRum();

  useEffect(() => {
    reporter.current.start(location.pathname);
    return () => reporter.current.flush();
  }, [location.pathname]);

  useEffect(() => {
    const flush = () => reporter.current.flush();
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, []);

  useEffect(() => {
    const recordNavigation = (url) => {
      if (url == null) return;
      try {
        const next = new URL(String(url), window.location.origin);
        if (next.origin === window.location.origin && next.pathname !== window.location.pathname) {
          reporter.current.markTransition(next.pathname);
        }
      } catch { /* malformed history URL is not telemetry-worthy */ }
    };
    const originalPushState = window.history.pushState;
    const originalReplaceState = window.history.replaceState;
    window.history.pushState = function patchedPushState(...args) {
      recordNavigation(args[2]);
      return originalPushState.apply(this, args);
    };
    window.history.replaceState = function patchedReplaceState(...args) {
      recordNavigation(args[2]);
      return originalReplaceState.apply(this, args);
    };
    return () => {
      window.history.pushState = originalPushState;
      window.history.replaceState = originalReplaceState;
    };
  }, []);
  return null;
}
