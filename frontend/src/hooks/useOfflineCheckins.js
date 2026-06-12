/**
 * useOfflineCheckins — çevrimiçi/çevrimdışı durumu + bekleyen/çakışan
 * çevrimdışı check-in kuyruğunu izler ve internet dönünce otomatik eşitlemeyi
 * tetikler (Background Sync + sayfa-bağlamı yedek).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  listQueuedCheckins,
  removeQueuedCheckin,
} from '@/utils/offlineQueueDB';
import {
  processQueuedCheckins,
  CHECKIN_QUEUE_EVENT,
} from '@/utils/offlineCheckin';

const isOnline = () =>
  typeof navigator === 'undefined' ? true : navigator.onLine !== false;

export default function useOfflineCheckins() {
  const [online, setOnline] = useState(isOnline());
  const [items, setItems] = useState([]);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const queued = await listQueuedCheckins();
      setItems(queued);
    } catch {
      setItems([]);
    }
  }, []);

  const sync = useCallback(async () => {
    if (!isOnline()) return;
    setSyncing(true);
    try {
      // Background Sync varsa SW'yi de dürt (idempotent — çift replay güvenli).
      if (typeof navigator !== 'undefined' && navigator.serviceWorker?.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'PROCESS_CHECKIN_QUEUE' });
      }
      await processQueuedCheckins();
    } catch {
      // sessiz — bir sonraki tetikte tekrar denenir
    } finally {
      setSyncing(false);
      await refresh();
    }
  }, [refresh]);

  const dismiss = useCallback(
    async (id) => {
      await removeQueuedCheckin(id);
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
      if (type === 'CHECKIN_SYNCED' || type === 'CHECKIN_CONFLICT') {
        refresh();
      }
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    window.addEventListener(CHECKIN_QUEUE_EVENT, handleQueueChanged);
    if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
      navigator.serviceWorker.addEventListener('message', handleSwMessage);
    }

    // İlk yüklemede online isek ve bekleyen varsa bir kez eşitlemeyi dene.
    if (isOnline()) {
      sync();
    }

    // Görünürlük geri gelince (sekmeye dönüş) tazele + eşitle.
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
      window.removeEventListener(CHECKIN_QUEUE_EVENT, handleQueueChanged);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
        navigator.serviceWorker.removeEventListener('message', handleSwMessage);
      }
    };
  }, [refresh, sync]);

  const pending = items.filter((it) => it.status !== 'conflict');
  const conflicts = items.filter((it) => it.status === 'conflict');

  return {
    online,
    items,
    pending,
    conflicts,
    pendingCount: pending.length,
    conflictCount: conflicts.length,
    syncing,
    sync,
    dismiss,
    refresh,
  };
}
