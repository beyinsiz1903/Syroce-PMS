import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

/**
 * useHRPagination — Shared pagination hook for HR sub-resource tabs.
 *
 * @param {string} url        - API endpoint base URL (e.g. `/hr/staff/${id}/documents`)
 * @param {object} params     - Additional query params (merged with page/limit)
 * @param {object} options    - Options: { defaultLimit = 25, enabled = true }
 *
 * @returns {object} { items, total, page, totalPages, limit, loading, error, setPage, setLimit, refresh }
 */
export function useHRPagination(url, params = {}, options = {}) {
  const { defaultLimit = 25, enabled = true } = options;

  const [page, setPageState] = useState(1);
  const [limit, setLimitState] = useState(defaultLimit);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [meta, setMeta] = useState({});
  const [rev, setRev] = useState(0); // increment to force refresh

  const abortRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (!url || !enabled) return;

    // Cancel any in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const res = await axios.get(url, {
        params: { ...params, page, limit },
        signal: controller.signal,
      });
      const data = res.data || {};
      setItems(data.items || []);
      setTotal(data.total ?? 0);
      setTotalPages(data.total_pages ?? Math.max(1, Math.ceil((data.total ?? 0) / limit)));
      setMeta(data);
    } catch (err) {
      if (axios.isCancel(err) || err?.name === 'CanceledError') return;
      setError(err?.response?.data?.detail || err.message || 'Bilinmeyen hata');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, page, limit, rev, enabled, JSON.stringify(params)]);

  useEffect(() => {
    fetchData();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [fetchData]);

  const setPage = useCallback((p) => {
    setPageState(p);
  }, []);

  const setLimit = useCallback((l) => {
    setLimitState(l);
    setPageState(1); // reset to page 1 on limit change
  }, []);

  const refresh = useCallback(() => {
    setRev((r) => r + 1);
  }, []);

  return { items, total, page, totalPages, limit, loading, error, meta, setPage, setLimit, refresh };
}
