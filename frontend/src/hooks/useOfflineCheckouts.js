/**
 * useOfflineCheckouts — çevrimiçi/çevrimdışı durumu + bekleyen/çakışan
 * çevrimdışı çıkış (yalnızca sıfır/kapalı bakiye) kuyruğunu izler ve internet
 * dönünce otomatik eşitlemeyi tetikler (Background Sync + sayfa-bağlamı yedek).
 * useOfflineCheckins deseninin birebir kardeşi — check-in yolu DEĞİŞTİRİLMEZ.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  listQueuedCheckouts,
  removeQueuedCheckout,
} from '@/utils/offlineQueueDB';
import {
  processQueuedCheckouts,
  requeueCheckout,
  requeueCheckouts,
  cancelQueuedCheckouts,
  CHECKOUT_QUEUE_EVENT,
  STALE_CHECKOUT_AGE_MS,
} from '@/utils/offlineCheckout';

const isOnline = () =>
  typeof navigator === 'undefined' ? true : navigator.onLine !== false;

export default function useOfflineCheckouts() {
  const [online, setOnline] = useState(isOnline());
  const [items, setItems] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    try {
      const queued = await listQueuedCheckouts();
      setItems(queued);
    } catch {
      setItems([]);
    }
  }, []);

  const sync = useCallback(async () => {
    if (!isOnline()) return;
    setSyncing(true);
    try {
      if (typeof navigator !== 'undefined' && navigator.serviceWorker?.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'PROCESS_CHECKOUT_QUEUE' });
      }
      await processQueuedCheckouts();
    } catch {
      // sessiz — bir sonraki tetikte tekrar denenir
    } finally {
      setSyncing(false);
      await refresh();
    }
  }, [refresh]);

  const dismiss = useCallback(
    async (id) => {
      await removeQueuedCheckout(id);
      await refresh();
    },
    [refresh],
  );

  const cancel = dismiss;

  const retry = useCallback(
    async (id) => {
      await requeueCheckout(id);
      await refresh();
      sync();
    },
    [refresh, sync],
  );

  const retryMany = useCallback(
    async (ids) => {
      const list = (Array.isArray(ids) ? ids : []).filter(Boolean);
      if (!list.length) return;
      await requeueCheckouts(list);
      await refresh();
      sync();
    },
    [refresh, sync],
  );

  const cancelMany = useCallback(
    async (ids) => {
      const list = (Array.isArray(ids) ? ids : []).filter(Boolean);
      if (!list.length) return;
      await cancelQueuedCheckouts(list);
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    refresh();

    const handleOnline = () => {
      setOnline(true);
      sync();
    };
    const handleOffline = () => setOnline(false);
    const handleQueueChanged = () => refresh();

    const handleSwMessage = (event) => {
      const type = event.data?.type;
      if (type === 'CHECKOUT_SYNCED' || type === 'CHECKOUT_CONFLICT') {
        refresh();
      }
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    window.addEventListener(CHECKOUT_QUEUE_EVENT, handleQueueChanged);
    if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
      navigator.serviceWorker.addEventListener('message', handleSwMessage);
    }

    if (isOnline()) {
      sync();
    }

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        refresh();
        if (isOnline()) sync();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener(CHECKOUT_QUEUE_EVENT, handleQueueChanged);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
        navigator.serviceWorker.removeEventListener('message', handleSwMessage);
      }
    };
  }, [refresh, sync]);

  useEffect(() => {
    const hasPending = items.some((it) => it.status !== 'conflict');
    if (!hasPending) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 30 * 1000);
    return () => clearInterval(timer);
  }, [items]);

  const pending = items.filter((it) => it.status !== 'conflict');
  const conflicts = items.filter((it) => it.status === 'conflict');
  const stalePending = pending.filter(
    (it) => now - (it.createdAt || now) >= STALE_CHECKOUT_AGE_MS,
  );

  return {
    online,
    items,
    pending,
    conflicts,
    stalePending,
    pendingCount: pending.length,
    conflictCount: conflicts.length,
    stalePendingCount: stalePending.length,
    now,
    syncing,
    sync,
    retry,
    retryMany,
    cancel,
    cancelMany,
    dismiss,
    refresh,
  };
}
