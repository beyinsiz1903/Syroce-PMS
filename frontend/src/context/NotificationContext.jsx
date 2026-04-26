import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { listNotifications, logNotification, clearNotification } from '@/utils/offlineQueueDB';
import { websocket } from '@/lib/websocket';

const NotificationContext = createContext({
  notifications: [],
  internalMessages: [],
  internalUnreadCount: 0,
  totalUnreadCount: 0,
  unreadCount: 0,
  loading: false,
  markRead: () => {},
  clearAll: () => {},
  resetInternalUnread: () => {},
  decrementInternalUnread: () => {},
  refreshInternalUnread: async () => {},
  permission: 'default',
  requestPermission: async () => 'default',
});

const isClient = typeof window !== 'undefined';
const MAX_INTERNAL_MESSAGES = 50;
const AUTH_EVENT = 'syroce:auth-changed';

const readUserFromStorage = () => {
  if (!isClient) return null;
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const isStaffUser = (user) => {
  if (!user) return false;
  const role = user.role || (user.roles && user.roles[0]);
  return role && role !== 'guest';
};

export const NotificationProvider = ({ children }) => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [internalMessages, setInternalMessages] = useState([]);
  const [internalUnreadCount, setInternalUnreadCount] = useState(0);
  const [permission, setPermission] = useState(() =>
    isClient && 'Notification' in window ? Notification.permission : 'default'
  );

  // ── Reactive auth state ──
  // The provider stays mounted across login/logout, so reading the user
  // once at mount time would leave us blind to authentication changes
  // (the bell would never wire up its socket subscription). Re-read on
  // any auth-changed signal: our own custom event after login/logout, the
  // browser `storage` event (other tabs), and a one-shot focus check.
  const [authUser, setAuthUser] = useState(() => readUserFromStorage());

  useEffect(() => {
    if (!isClient) return undefined;
    const refresh = () => setAuthUser(readUserFromStorage());

    const onStorage = (e) => {
      if (!e.key || e.key === 'user' || e.key === 'token') refresh();
    };
    const onAuthChanged = () => refresh();
    const onFocus = () => refresh();

    window.addEventListener('storage', onStorage);
    window.addEventListener(AUTH_EVENT, onAuthChanged);
    window.addEventListener('focus', onFocus);

    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(AUTH_EVENT, onAuthChanged);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const authUserId = authUser?.id || null;
  const authUserIdRef = useRef(authUserId);
  useEffect(() => {
    authUserIdRef.current = authUserId;
  }, [authUserId]);

  // ── 1. Load persisted notifications + listen for service worker push events ──
  useEffect(() => {
    let mounted = true;

    const loadNotifications = async () => {
      try {
        const items = await listNotifications(100);
        if (mounted) {
          setNotifications(items.sort((a, b) => b.createdAt - a.createdAt));
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadNotifications();

    if (!isClient || !navigator.serviceWorker) {
      return () => {
        mounted = false;
      };
    }

    const handleMessage = async (event) => {
      const { data } = event;
      if (!data) return;

      if (data.type === 'PUSH_NOTIFICATION') {
        const record = {
          ...data.payload,
          id: data.payload?.id || crypto.randomUUID(),
          createdAt: Date.now(),
          read: false,
        };
        await logNotification(record);
        setNotifications((prev) => [record, ...prev]);
      } else if (data.type === 'SYNC_NOTIFICATION_LOG') {
        const items = await listNotifications(100);
        setNotifications(items.sort((a, b) => b.createdAt - a.createdAt));
      }
    };

    navigator.serviceWorker.addEventListener('message', handleMessage);

    return () => {
      mounted = false;
      navigator.serviceWorker.removeEventListener('message', handleMessage);
    };
  }, []);

  // ── 2. Live internal-chat stream via Socket.IO ──
  // Re-runs whenever the authenticated user changes so a fresh login picks
  // up its tenant-scoped subscription without a page reload.
  useEffect(() => {
    if (!isClient) return undefined;
    if (!isStaffUser(authUser)) {
      // Logged out (or guest) → clear stale state from a previous session.
      setInternalMessages([]);
      setInternalUnreadCount(0);
      return undefined;
    }

    let detached = false;
    let unsubscribe = null;

    const showOsNotification = (msg) => {
      if (!('Notification' in window)) return;
      if (Notification.permission !== 'granted') return;
      const docHidden = typeof document !== 'undefined' && document.hidden;
      // In-tab toast is unnecessary when the user is actively looking at
      // the page; only surface a system notification on hidden tabs or
      // for urgent messages so the user is not pulled away unnecessarily.
      if (!docHidden && msg.priority !== 'urgent') return;
      try {
        const title =
          msg.priority === 'urgent'
            ? `Acil mesaj — ${msg.from_user_name || 'Personel'}`
            : `Yeni mesaj — ${msg.from_user_name || 'Personel'}`;
        const body =
          (msg.message || '').length > 140
            ? `${msg.message.slice(0, 137)}…`
            : msg.message || '';
        const notif = new Notification(title, {
          body,
          tag: `internal-msg-${msg.id}`,
          icon: '/syroce-icon.svg',
          requireInteraction: msg.priority === 'urgent',
        });
        notif.onclick = () => {
          window.focus();
          notif.close();
        };
      } catch (err) {
        console.warn('[NotificationContext] OS notification failed', err);
      }
    };

    const onInternalMessage = (envelope) => {
      const msg = envelope?.message;
      if (!msg) return;
      if (msg.from_user_id && msg.from_user_id === authUserIdRef.current) return;

      setInternalMessages((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        return [msg, ...prev].slice(0, MAX_INTERNAL_MESSAGES);
      });
      setInternalUnreadCount((c) => c + 1);
      showOsNotification(msg);
    };

    const init = async () => {
      try {
        await websocket.connect();
        if (detached) return;
        unsubscribe = websocket.on('internal_message', onInternalMessage);
      } catch (err) {
        console.warn('[NotificationContext] websocket subscribe failed', err);
      }
    };

    init();

    return () => {
      detached = true;
      if (unsubscribe) unsubscribe();
    };
  }, [authUser]);

  // ── 3. Initial / on-demand unread count snapshot from the inbox endpoint. ──
  const refreshInternalUnread = useCallback(async () => {
    if (!isClient || !isStaffUser(authUser)) return 0;
    try {
      const axios = (await import('axios')).default;
      const res = await axios.get('/messaging/internal/inbox', {
        params: { unread_only: true, limit: 1 },
      });
      const count = res.data?.unread_count || 0;
      setInternalUnreadCount(count);
      return count;
    } catch {
      return 0;
    }
  }, [authUser]);

  useEffect(() => {
    if (!isStaffUser(authUser)) return;
    refreshInternalUnread();
  }, [authUser, refreshInternalUnread]);

  const markRead = useCallback(async (id) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }, []);

  const clearAll = useCallback(async () => {
    await Promise.all(notifications.map((n) => clearNotification(n.id)));
    setNotifications([]);
  }, [notifications]);

  const resetInternalUnread = useCallback(() => {
    setInternalUnreadCount(0);
  }, []);

  const decrementInternalUnread = useCallback((n = 1) => {
    setInternalUnreadCount((c) => Math.max(0, c - n));
  }, []);

  const requestPermission = useCallback(async () => {
    if (!isClient || !('Notification' in window)) return 'denied';
    if (Notification.permission === 'granted' || Notification.permission === 'denied') {
      setPermission(Notification.permission);
      return Notification.permission;
    }
    const result = await Notification.requestPermission();
    setPermission(result);
    return result;
  }, []);

  const swPushUnread = notifications.filter((n) => !n.read).length;

  const value = useMemo(
    () => ({
      notifications,
      internalMessages,
      internalUnreadCount,
      unreadCount: swPushUnread,
      totalUnreadCount: swPushUnread + internalUnreadCount,
      loading,
      markRead,
      clearAll,
      resetInternalUnread,
      decrementInternalUnread,
      refreshInternalUnread,
      permission,
      requestPermission,
    }),
    [
      notifications,
      internalMessages,
      internalUnreadCount,
      swPushUnread,
      loading,
      markRead,
      clearAll,
      resetInternalUnread,
      decrementInternalUnread,
      refreshInternalUnread,
      permission,
      requestPermission,
    ]
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
};

export const useNotifications = () => useContext(NotificationContext);

// Helper for non-React modules (e.g. App.jsx after login/logout) to notify
// the provider that the cached user identity may have changed. We avoid
// importing React state from outside the tree by using a window event.
export const notifyAuthChanged = () => {
  if (!isClient) return;
  try {
    window.dispatchEvent(new CustomEvent(AUTH_EVENT));
  } catch {
    /* noop */
  }
};
