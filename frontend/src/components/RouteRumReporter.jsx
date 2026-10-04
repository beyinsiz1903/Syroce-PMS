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
    addEventListener("pagehide", flush);
    return () => removeEventListener("pagehide", flush);
  }, []);
  return null;
}
