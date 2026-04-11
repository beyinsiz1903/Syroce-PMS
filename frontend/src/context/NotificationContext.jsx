import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { listNotifications, logNotification, clearNotification } from '@/utils/offlineQueueDB';

const NotificationContext = createContext({
  notifications: [],
  markRead: () => {},
  clearAll: () => {},
  unreadCount: 0
});

const isClient = typeof window !== 'undefined';

export const NotificationProvider = ({ children }) => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);

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
          read: false
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

  const markRead = async (id) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  };

  const clearAll = async () => {
    await Promise.all(notifications.map((n) => clearNotification(n.id)));
    setNotifications([]);
  };

  const value = useMemo(
    () => ({
      notifications,
      loading,
      unreadCount: notifications.filter((n) => !n.read).length,
      markRead,
      clearAll
    }),
    [notifications, loading]
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
};

export const useNotifications = () => useContext(NotificationContext);

