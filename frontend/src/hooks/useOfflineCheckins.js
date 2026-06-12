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
  requeueCheckin,
  CHECKIN_QUEUE_EVENT,
  STALE_CHECKIN_AGE_MS,
} from '@/utils/offlineCheckin';

const isOnline = () =>
  typeof navigator === 'undefined' ? true : navigator.onLine !== false;

export default function useOfflineCheckins() {
  const [online, setOnline] = useState(isOnline());
  const [items, setItems] = useState([]);
  const [syncing, setSyncing] = useState(false);
  // Yaş hesaplamasının canlı kalması için periyodik bir "tik" — uzun süredir
  // bekleyen girişler için süre dolunca uyarı kendiliğinden belirsin.
  const [now, setNow] = useState(() => Date.now());

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

  // Operatörün manuel iptali (bekleyen veya çakışan girişi kuyruktan kaldır).
  const cancel = dismiss;

  // Operatörün manuel "yeniden dene"si: girişi pending'e çevir, sayacı sıfırla,
  // ardından eşitlemeyi tetikle.
  const retry = useCallback(
    async (id) => {
      await requeueCheckin(id);
      await refresh();
      sync();
    },
    [refresh, sync],
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

  // Bekleyen giriş varsa yaşın güncel kalması için dakikada bir tik at.
  useEffect(() => {
    const hasPending = items.some((it) => it.status !== 'conflict');
    if (!hasPending) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 30 * 1000);
    return () => clearInterval(timer);
  }, [items]);

  const pending = items.filter((it) => it.status !== 'conflict');
  const conflicts = items.filter((it) => it.status === 'conflict');
  // Uzun süredir bekleyen (eşik yaşı aşan) girişler — operatör uyarısı için.
  const stalePending = pending.filter(
    (it) => now - (it.createdAt || now) >= STALE_CHECKIN_AGE_MS,
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
    cancel,
    dismiss,
    refresh,
  };
}
