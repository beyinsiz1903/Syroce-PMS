import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Bell, AlertCircle, Info, CheckCircle, AlertTriangle } from 'lucide-react';

const API = "";

// SessionStorage cache: Layout her sayfa geçişinde remount oluyor (ProtectedRoute Layout sarmıyor).
// Cache user_id ile scope edilir — aynı tab'da hesap değişiminde başka kullanıcının
// notification'ı sızmaz. Auth değişince App.clearAuthStorage cache key'i temizler.
const CACHE_KEY = 'notif_cache_v1';
const currentUserId = () => {
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null');
    return u?.id || u?._id || null;
  } catch { return null; }
};
const readCache = () => {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const c = JSON.parse(raw);
    if (Date.now() - (c.t || 0) > 30000) return null; // 30sn stale
    if (c.uid && c.uid !== currentUserId()) return null; // user mismatch
    return c;
  } catch { return null; }
};

const NotificationBell = () => {
  const cached = readCache();
  const [notifications, setNotifications] = useState(cached?.notifications || []);
  const [unreadCount, setUnreadCount] = useState(cached?.unread_count || 0);
  const [isOpen, setIsOpen] = useState(false);
  const markingRef = useRef(false);

  useEffect(() => {
    // Cache taze + aynı user ise mount fetch'i atla — interval zaten 15sn'de yenileyecek
    if (!cached) loadNotifications();
    const interval = setInterval(loadNotifications, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-mark all as read when dialog opens
  useEffect(() => {
    if (isOpen && unreadCount > 0 && !markingRef.current) {
      markingRef.current = true;
      markAllAsRead().finally(() => { markingRef.current = false; });
    }
  }, [isOpen, unreadCount]);

  const loadNotifications = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const response = await axios.get(`/notifications/list?limit=20`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const list = response.data.notifications || [];
      const unread = response.data.unread_count || 0;
      setNotifications(list);
      setUnreadCount(unread);
      try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ notifications: list, unread_count: unread, uid: currentUserId(), t: Date.now() })); } catch { /* sessionStorage quota / private mode — ignore */ }
    } catch (error) {
      console.error('Failed to load notifications:', error);
    }
  };

  const markAllAsRead = async () => {
    try {
      const token = localStorage.getItem('token');
      await axios.put(`/notifications/mark-all-read`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'reservation_cancelled':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case 'success':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'reservation_modified':
        return <Info className="w-5 h-5 text-blue-500" />;
      case 'ops_event':
        return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      default:
        return <Info className="w-5 h-5 text-blue-500" />;
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'critical':
        return 'border-l-4 border-red-500 bg-red-50';
      case 'high':
        return 'border-l-4 border-amber-500 bg-amber-50';
      case 'normal':
        return 'border-l-4 border-blue-500 bg-blue-50';
      case 'low':
        return 'border-l-4 border-gray-500 bg-gray-50';
      default:
        return 'border-l-4 border-gray-300';
    }
  };

  return (
    <>
      <div className="relative">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsOpen(true)}
          className="relative p-2 hover:bg-white/20"
          data-testid="notification-bell-button"
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <Badge className="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 bg-red-500 text-white text-xs">
              {unreadCount > 9 ? '9+' : unreadCount}
            </Badge>
          )}
        </Button>
      </div>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto" data-testid="notification-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center">
              <Bell className="w-5 h-5 mr-2" />
              Bildirimler
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-2">
            {notifications.length === 0 ? (
              <div className="text-center py-8 text-gray-500" data-testid="notification-empty">
                <Bell className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p className="text-sm">Bildirim yok</p>
              </div>
            ) : (
              notifications.map((notif) => (
                <div
                  key={notif.id}
                  className={`p-3 rounded-lg transition-all ${
                    notif.read ? 'bg-gray-50' : getPriorityColor(notif.priority)
                  }`}
                  data-testid={`notification-item-${notif.id}`}
                >
                  <div className="flex items-start space-x-3">
                    <div className="flex-shrink-0 mt-1">
                      {getNotificationIcon(notif.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className={`text-sm font-medium ${
                        notif.read ? 'text-gray-700' : 'text-gray-900'
                      }`}>
                        {notif.title || 'Bildirim'}
                      </h4>
                      <p className={`text-xs mt-1 ${
                        notif.read ? 'text-gray-500' : 'text-gray-700'
                      }`}>
                        {notif.message}
                      </p>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-gray-400">
                          {notif.created_at ? new Date(notif.created_at).toLocaleString('tr-TR', {
                            day: 'numeric',
                            month: 'short',
                            hour: '2-digit',
                            minute: '2-digit'
                          }) : ''}
                        </span>
                        {notif.category && (
                          <Badge variant="outline" className="text-xs">
                            {notif.category}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default NotificationBell;
