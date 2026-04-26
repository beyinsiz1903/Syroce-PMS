import React, { useState } from 'react';
import { Bell, CheckCircle2, X, Trash2, MessageSquare, CheckCheck } from 'lucide-react';
import { useNotifications } from '@/context/NotificationContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const NotificationCenter = () => {
  const {
    notifications,
    internalMessages,
    internalUnreadCount,
    totalUnreadCount,
    markRead,
    clearAll,
    loading,
    permission,
    requestPermission,
    markAllInternalRead,
  } = useNotifications();
  const [open, setOpen] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);

  const handleToggle = () => setOpen((prev) => !prev);
  const unreadCount = totalUnreadCount;

  const handleMarkAllInternal = async () => {
    if (markingAll || internalUnreadCount === 0) return;
    setMarkingAll(true);
    try {
      await markAllInternalRead();
    } finally {
      setMarkingAll(false);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <Button
        variant="outline"
        size="icon"
        className="relative rounded-full w-12 h-12 shadow-lg bg-white"
        onClick={handleToggle}
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] font-semibold rounded-full px-1.5 py-0.5">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </Button>

      {open && (
        <Card className="mt-3 w-80 max-h-[70vh] overflow-hidden shadow-2xl border">
          <CardHeader className="flex flex-row items-center justify-between py-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="w-4 h-4 text-blue-600" />
              Bildirimler
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={clearAll}
                disabled={!notifications.length}
                title="Tümünü temizle"
              >
                <Trash2 className="w-4 h-4 text-gray-500" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setOpen(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {permission === 'default' && (
              <button
                type="button"
                onClick={requestPermission}
                className="w-full text-xs text-blue-700 bg-blue-50 hover:bg-blue-100 py-2 border-b"
              >
                Masaüstü bildirimlerini etkinleştir
              </button>
            )}
            <div className="max-h-[60vh] overflow-y-auto">
              {(internalMessages.length > 0 || internalUnreadCount > 0) && (
                <div className="border-b bg-amber-50/40">
                  <div className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-amber-700 flex items-center gap-2">
                    <MessageSquare className="w-3 h-3" />
                    Personel mesajları
                    {internalUnreadCount > 0 && (
                      <span className="ml-auto bg-amber-200 text-amber-900 rounded-full px-2 py-0.5">
                        {internalUnreadCount}
                      </span>
                    )}
                  </div>
                  {internalUnreadCount > 0 && (
                    <button
                      type="button"
                      onClick={handleMarkAllInternal}
                      disabled={markingAll}
                      data-testid="button-internal-mark-all-read"
                      className="w-full text-xs text-amber-800 bg-amber-100 hover:bg-amber-200 disabled:opacity-60 py-2 border-t border-amber-200 flex items-center justify-center gap-1.5"
                    >
                      <CheckCheck className="w-3.5 h-3.5" />
                      {markingAll ? 'İşaretleniyor…' : 'Tümünü okundu olarak işaretle'}
                    </button>
                  )}
                  {internalMessages.slice(0, 5).map((msg) => (
                    <div
                      key={msg.id}
                      className={`px-4 py-2 border-t text-sm ${
                        msg.priority === 'urgent' ? 'bg-red-50' : 'bg-white'
                      }`}
                    >
                      <p className="font-semibold text-gray-800 text-xs">
                        {msg.from_user_name || 'Personel'}
                        {msg.priority === 'urgent' && (
                          <span className="ml-2 text-red-600 text-[10px] uppercase font-bold">
                            Acil
                          </span>
                        )}
                      </p>
                      <p className="text-gray-700 text-xs mt-0.5 line-clamp-2">{msg.message}</p>
                    </div>
                  ))}
                </div>
              )}
              {loading ? (
                <div className="py-8 text-center text-gray-500 text-sm">Yükleniyor...</div>
              ) : notifications.length === 0 && internalMessages.length === 0 ? (
                <div className="py-8 text-center text-gray-500 text-sm">Bildirim yok</div>
              ) : (
                notifications.map((notification) => (
                  <div
                    key={notification.id}
                    className={`px-4 py-3 border-b text-sm ${
                      notification.read ? 'bg-white' : 'bg-blue-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-gray-800">
                          {notification.title || 'Bildirim'}
                        </p>
                        {notification.body && (
                          <p className="text-gray-600 text-xs mt-1">{notification.body}</p>
                        )}
                        <p className="text-[11px] text-gray-400 mt-1">
                          {notification.createdAt
                            ? new Date(notification.createdAt).toLocaleString('tr-TR')
                            : ''}
                        </p>
                      </div>
                      {!notification.read && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-green-600"
                          onClick={() => markRead(notification.id)}
                        >
                          <CheckCircle2 className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default NotificationCenter;
