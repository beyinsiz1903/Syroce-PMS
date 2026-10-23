import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

// Keep full history independent of the operational date-window dataset.
// Only a complete, current pagination run may replace the displayed history.
export function usePmsBookingHistory({ enabled, scopeKey }) {
  const generation = useRef(0);
  const requested = useRef(false);
  const currentScope = useRef(scopeKey);
  currentScope.current = scopeKey;
  const [snapshot, setSnapshot] = useState({ scopeKey, rows: null, loading: false, error: null });

  const refresh = useCallback(async () => {
    if (currentScope.current !== scopeKey) return;
    const requestId = ++generation.current;
    requested.current = true;
    setSnapshot(previous => ({ scopeKey, rows: previous.scopeKey === scopeKey ? previous.rows : null, loading: true, error: null }));
    try {
      const rows = [];
      const seen = new Set();
      const pageSize = 1000;
      for (let offset = 0; ; offset += pageSize) {
        const response = await axios.get(`/pms/bookings?limit=${pageSize}&offset=${offset}&full_history=true`, { timeout: 30000 });
        if (requestId !== generation.current) return;
        const page = Array.isArray(response?.data) ? response.data : response?.data?.bookings;
        if (!Array.isArray(page)) throw new Error('Invalid booking history response');
        let added = 0;
        for (const row of page) {
          if (!row || typeof row.id !== 'string' || !row.id) throw new Error('Invalid booking history row');
          if (seen.has(row.id)) continue;
          seen.add(row.id);
          rows.push(row);
          added += 1;
        }
        if (page.length === pageSize && added === 0) throw new Error('Booking history pagination made no progress');
        if (page.length < pageSize) break;
      }
      if (requestId === generation.current) setSnapshot({ scopeKey, rows, loading: false, error: null });
    } catch {
      if (requestId !== generation.current) return;
      setSnapshot(previous => ({ ...previous, loading: false, error: 'Tüm rezervasyonlar yüklenemedi. Son doğrulanan liste korunuyor; liste eksik olabilir.' }));
    }
  }, [scopeKey]);

  useEffect(() => {
    generation.current += 1;
    requested.current = false;
    setSnapshot({ scopeKey, rows: null, loading: false, error: null });
    if (enabled) void refresh();
    return () => { generation.current += 1; requested.current = false; };
  }, [enabled, scopeKey, refresh]);

  const refreshIfRequested = useCallback(() => {
    if (requested.current) void refresh();
  }, [refresh]);

  return {
    rows: snapshot.scopeKey === scopeKey ? snapshot.rows : null,
    loading: snapshot.scopeKey === scopeKey && snapshot.loading,
    error: snapshot.scopeKey === scopeKey ? snapshot.error : null,
    refresh,
    refreshIfRequested,
  };
}
