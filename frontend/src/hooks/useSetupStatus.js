import { useEffect, useState } from "react";
import axios from "axios";

// Hook to fetch minimal PMS setup status (rooms/bookings counts)
// Usage: const { data, loading, error } = useSetupStatus({ enabled: isLite });
export function useSetupStatus({ enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    if (!enabled) return;

    (async () => {
      try {
        setLoading(true);
        // axios baseURL is already '/api', so we use relative path here
        const res = await axios.get("/pms/setup-status");
        if (!mounted) return;
        setData(res.data);
      } catch (e) {
        if (!mounted) return;
        setError(e);
      } finally {
        setLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, [enabled]);

  return { data, loading, error };
}
