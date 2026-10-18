import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

export const MODULE_SALES_CHANGED = 'syroce:module-sales-changed';
export const signalModuleSalesChanged = () => window.dispatchEvent(new Event(MODULE_SALES_CHANGED));
const storedUser = () => { try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; } };

/** Platform-only inbox. Never reuse a previous administrator's response. */
export function useModuleSalesInbox(suppliedUser) {
  const [stored, setStored] = useState(storedUser);
  const user = suppliedUser === undefined ? stored : suppliedUser;
  const userId = user?.id || user?._id;
  const enabled = user?.role === 'super_admin' && Boolean(userId);
  const key = enabled ? `super_admin:${userId}` : '';
  const [snapshot, setSnapshot] = useState(null);
  const requestId = useRef(0);
  const invalidate = useCallback(() => { ++requestId.current; }, []);

  useEffect(() => {
    if (suppliedUser !== undefined) return undefined;
    const read = () => setStored(storedUser());
    window.addEventListener('storage', read);
    window.addEventListener('syroce:auth-changed', read);
    return () => { window.removeEventListener('storage', read); window.removeEventListener('syroce:auth-changed', read); };
  }, [suppliedUser]);

  const refresh = useCallback(async () => {
    if (!key) return;
    const id = ++requestId.current;
    setSnapshot(previous => ({ key, data: previous?.key === key ? previous.data : null, loading: true, error: '' }));
    try {
      const { data } = await axios.get('/module-store/admin/quote-requests/inbox');
      if (id === requestId.current) setSnapshot({ key, data, loading: false, error: '' });
    } catch {
      if (id === requestId.current) setSnapshot(previous => ({ key, data: previous?.key === key ? previous.data : null, loading: false, error: 'Satış talepleri alınamadı.' }));
    }
  }, [key]);

  useEffect(() => {
    if (!key) { invalidate(); return undefined; }
    const visibleRefresh = () => { if (document.visibilityState === 'visible') void refresh(); };
    visibleRefresh();
    const timer = setInterval(visibleRefresh, 60000);
    document.addEventListener('visibilitychange', visibleRefresh);
    window.addEventListener(MODULE_SALES_CHANGED, visibleRefresh);
    return () => {
      invalidate(); clearInterval(timer);
      document.removeEventListener('visibilitychange', visibleRefresh);
      window.removeEventListener(MODULE_SALES_CHANGED, visibleRefresh);
    };
  }, [key, refresh, invalidate]);

  const acknowledge = useCallback(async ids => {
    if (!key || !ids.length) return;
    // A GET started before this acknowledgment must not restore unread badges.
    ++requestId.current;
    try {
      await axios.post('/module-store/admin/quote-requests/acknowledge', { request_ids: ids });
    } catch (failure) {
      setSnapshot(previous => previous?.key === key ? { ...previous, loading: false } : previous);
      throw failure;
    }
    setSnapshot(previous => {
      if (previous?.key !== key || !previous.data) return previous;
      const notifications = previous.data.notifications || [];
      const newlyRead = notifications.filter(row => ids.includes(row.request_id) && !row.read).length;
      return { ...previous, loading: false, data: { ...previous.data,
        unread_count: Math.max(0, previous.data.unread_count - newlyRead),
        notifications: notifications.map(row => ids.includes(row.request_id) ? { ...row, read: true } : row),
      } };
    });
  }, [key]);

  const current = snapshot?.key === key ? snapshot : null;
  return { enabled, data: current?.data, error: current?.error || '', loading: current?.loading || false, refresh, acknowledge };
}
