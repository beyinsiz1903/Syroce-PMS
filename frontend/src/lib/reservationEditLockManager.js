import axios from 'axios';
import { toast } from 'sonner';

export const RESERVATION_EDIT_LOCK_LEASE_SECONDS = 120;
export const RESERVATION_EDIT_LOCK_HEARTBEAT_SECONDS = 30;
export const RESERVATION_EDIT_LOCK_HEADER = 'X-Reservation-Lock-ID';

const VIEW_RELEASE_GRACE_MS = 15000;
const MANAGER_KEY = '__syroceReservationEditLockManagerV1';

const FULL_DETAIL_RE = /(?:^|\/)(?:api\/)?pms\/reservations\/([^/?#]+)\/full-detail(?:[/?#]|$)/;
const RESERVATION_MUTATION_RE = /(?:^|\/)(?:api\/)?pms\/reservations\/([^/?#]+)(?:[/?#]|$)/;
const FRONTDESK_MUTATION_RE = /(?:^|\/)(?:api\/)?frontdesk\/(?:checkin|checkout)\/([^/?#]+)(?:[/?#]|$)/;

const normalizeMethod = (method) => String(method || 'get').toLowerCase();

export const reservationIdFromFullDetailUrl = (url) => {
  const match = String(url || '').match(FULL_DETAIL_RE);
  return match?.[1] || null;
};

export const reservationIdFromProtectedMutation = (url, method) => {
  const normalizedMethod = normalizeMethod(method);
  if (!['post', 'put', 'patch', 'delete'].includes(normalizedMethod)) return null;
  const raw = String(url || '');
  if (raw.includes('/edit-lock')) return null;
  return raw.match(RESERVATION_MUTATION_RE)?.[1]
    || raw.match(FRONTDESK_MUTATION_RE)?.[1]
    || null;
};

const createLockId = () => {
  if (typeof globalThis !== 'undefined' && globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `view-${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
};

const lockError = (message) => {
  const error = new Error(message);
  error.code = 'RESERVATION_EDIT_LOCK_REQUIRED';
  error.isReservationEditLockError = true;
  return error;
};

function createManager() {
  let current = null;
  let heartbeatTimer = null;
  let viewMonitorTimer = null;
  let acquirePromise = null;
  let lastBlockedToastAt = 0;

  const clearHeartbeat = () => {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  };

  const clearViewMonitor = () => {
    if (viewMonitorTimer) clearInterval(viewMonitorTimer);
    viewMonitorTimer = null;
  };

  const markViewActivity = () => {
    if (current) current.lastViewActivityAt = Date.now();
  };

  const releaseCurrent = async () => {
    const owned = current;
    current = null;
    acquirePromise = null;
    clearHeartbeat();
    clearViewMonitor();
    if (!owned?.bookingId || !owned?.lockId || owned.status !== 'acquired') return;

    try {
      await axios.delete(`/pms/reservations/${owned.bookingId}/edit-lock`, {
        data: { lock_id: owned.lockId },
        __skipReservationEditLock: true,
      });
    } catch (_error) {
      // Lease expiry is the safety net for abrupt navigation/network loss.
    }
  };

  const startViewMonitor = () => {
    clearViewMonitor();
    if (typeof document === 'undefined') return;

    viewMonitorTimer = setInterval(() => {
      if (!current) return;
      const visible = Boolean(document.querySelector('[data-testid="reservation-detail-modal"]'));
      if (visible) {
        current.seenModal = true;
        markViewActivity();
        return;
      }
      if (
        current.seenModal
        && Date.now() - Number(current.lastViewActivityAt || 0) >= VIEW_RELEASE_GRACE_MS
      ) {
        void releaseCurrent();
      }
    }, 1000);
  };

  const startHeartbeat = () => {
    clearHeartbeat();
    heartbeatTimer = setInterval(async () => {
      const owned = current;
      if (!owned || owned.status !== 'acquired') return;
      try {
        const response = await axios.post(
          `/pms/reservations/${owned.bookingId}/edit-lock/heartbeat`,
          { lock_id: owned.lockId },
          { __skipReservationEditLock: true },
        );
        if (current === owned) {
          current.expiresAt = response?.data?.expires_at || null;
          markViewActivity();
        }
      } catch (_error) {
        if (current === owned) {
          current.status = 'lost';
          clearHeartbeat();
          toast.error('Rezervasyon düzenleme kilidi kaybedildi. Pencere salt okunur kaldı.');
        }
      }
    }, RESERVATION_EDIT_LOCK_HEARTBEAT_SECONDS * 1000);
  };

  const acquire = async (bookingId) => {
    if (!bookingId) return null;

    if (current?.bookingId && current.bookingId !== bookingId) {
      await releaseCurrent();
    }

    if (!current) {
      current = {
        bookingId,
        lockId: createLockId(),
        status: 'idle',
        seenModal: false,
        lastViewActivityAt: Date.now(),
        expiresAt: null,
      };
    }

    markViewActivity();
    if (current.status === 'acquired') return current;
    if (acquirePromise) return acquirePromise;

    const owned = current;
    owned.status = 'acquiring';
    acquirePromise = axios.post(
      `/pms/reservations/${bookingId}/edit-lock/acquire`,
      { lock_id: owned.lockId },
      { __skipReservationEditLock: true },
    )
      .then((response) => {
        if (current !== owned) return null;
        owned.status = 'acquired';
        owned.expiresAt = response?.data?.expires_at || null;
        startHeartbeat();
        startViewMonitor();
        return owned;
      })
      .catch((error) => {
        if (current === owned) {
          owned.status = error?.response?.status === 409 ? 'blocked' : 'lost';
          startViewMonitor();
          const now = Date.now();
          if (now - lastBlockedToastAt > 5000) {
            toast.warning(
              error?.response?.status === 409
                ? 'Bu rezervasyon başka bir pencerede düzenleniyor. Salt okunur açıldı.'
                : 'Rezervasyon düzenleme kilidi alınamadı. Salt okunur açıldı.',
            );
            lastBlockedToastAt = now;
          }
        }
        return null;
      })
      .finally(() => {
        if (current === owned) acquirePromise = null;
      });

    return acquirePromise;
  };

  const interceptorId = axios.interceptors.request.use(async (config) => {
    if (config?.__skipReservationEditLock) return config;

    const method = normalizeMethod(config?.method);
    const fullDetailBookingId = method === 'get'
      ? reservationIdFromFullDetailUrl(config?.url)
      : null;

    if (fullDetailBookingId) {
      await acquire(fullDetailBookingId);
      markViewActivity();
      return config;
    }

    const mutationBookingId = reservationIdFromProtectedMutation(config?.url, method);
    if (!mutationBookingId) return config;

    if (
      current?.bookingId !== mutationBookingId
      || current?.status !== 'acquired'
      || !current?.lockId
    ) {
      throw lockError('Rezervasyon düzenleme kilidi aktif değil; işlem güvenlik nedeniyle engellendi.');
    }

    config.headers = config.headers || {};
    config.headers[RESERVATION_EDIT_LOCK_HEADER] = current.lockId;
    markViewActivity();
    return config;
  });

  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      clearHeartbeat();
      clearViewMonitor();
      // Do not attempt an unreliable async unlock during unload. The 120 s
      // server lease is intentionally the crash/tab-close safety net.
    });
  }

  return {
    acquire,
    releaseCurrent,
    getCurrent: () => current,
    interceptorId,
  };
}

export function installReservationEditLockManager() {
  if (typeof globalThis === 'undefined') return null;
  if (!globalThis[MANAGER_KEY]) {
    globalThis[MANAGER_KEY] = createManager();
  }
  return globalThis[MANAGER_KEY];
}

export const reservationEditLockManager = installReservationEditLockManager();
