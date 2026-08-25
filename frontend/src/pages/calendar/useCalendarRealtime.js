import { useEffect, useRef } from 'react';
import { websocket } from '@/lib/websocket';

const DEFAULT_DEBOUNCE_MS = 150;
const DEFAULT_POLL_INTERVAL_MS = 30_000;

/**
 * Keep the reservation calendar synchronized with durable booking changes.
 *
 * Socket events provide the fast path. Focus/visibility refreshes and a
 * low-frequency poll are a safety net for temporary WebSocket or proxy
 * interruptions. The callback always re-fetches authoritative REST data;
 * event payloads never mutate calendar state directly.
 */
export function useCalendarRealtime(
  onRefresh,
  {
    debounceMs = DEFAULT_DEBOUNCE_MS,
    pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
  } = {},
) {
  const refreshRef = useRef(onRefresh);

  useEffect(() => {
    refreshRef.current = onRefresh;
  }, [onRefresh]);

  useEffect(() => {
    let active = true;
    let debounceTimer = null;
    let refreshInFlight = false;
    let refreshQueued = false;

    const runRefresh = async () => {
      if (!active || document.visibilityState === 'hidden') return;
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
      if (refreshInFlight) {
        refreshQueued = true;
        return;
      }

      refreshInFlight = true;
      try {
        await refreshRef.current?.();
      } finally {
        refreshInFlight = false;
        if (active && refreshQueued) {
          refreshQueued = false;
          debounceTimer = window.setTimeout(runRefresh, debounceMs);
        }
      }
    };

    const scheduleRefresh = () => {
      if (!active) return;
      if (debounceTimer) window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(runRefresh, debounceMs);
    };

    // Register first so a fast connection cannot deliver an event between the
    // handshake and listener installation.
    const unsubscribe = websocket.on('booking_update', scheduleRefresh);
    websocket.connect().catch((error) => {
      console.warn('[CalendarRealtime] websocket unavailable; polling fallback active.', error);
    });

    const onFocus = () => scheduleRefresh();
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') scheduleRefresh();
    };

    window.addEventListener('focus', onFocus);
    window.addEventListener('online', onFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);
    const pollTimer = window.setInterval(() => {
      if (document.visibilityState === 'visible') scheduleRefresh();
    }, pollIntervalMs);

    return () => {
      active = false;
      unsubscribe?.();
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('online', onFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.clearInterval(pollTimer);
      if (debounceTimer) window.clearTimeout(debounceTimer);
    };
  }, [debounceMs, pollIntervalMs]);
}

export default useCalendarRealtime;
