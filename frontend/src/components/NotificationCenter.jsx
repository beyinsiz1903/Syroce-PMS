import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Bell, CheckCircle2, X, Trash2, MessageSquare, CheckCheck } from 'lucide-react';
import { useNotifications } from '@/context/NotificationContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';

// Task #38: when the internal-message backlog crosses this threshold the
// bell starts pulsing and a tooltip nudges the operator to clear the
// queue. Tuned to match the badge's "9+" cap so the pulse kicks in right
// when the user can no longer read the exact count.
const INTERNAL_UNREAD_PULSE_THRESHOLD = 10;

// Task #38: keyboard shortcut for "mark every internal message read"
// without opening the bell. Shift+R chosen because plain R is commonly
// captured by inputs (and by browsers as "reload" with Ctrl/Cmd) — the
// Shift modifier keeps it accessible while avoiding accidental triggers.
const MARK_ALL_SHORTCUT = { key: 'R', shiftKey: true };

const NotificationCenter = () => {
  const { t } = useTranslation();
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
  const { toast } = useToast();
  // Guards against the shortcut firing twice for a single keypress when
  // multiple panes mount the NotificationCenter (defensive — only one is
  // expected, but a hot-reload race could briefly mount two).
  const shortcutBusyRef = useRef(false);

  const handleToggle = () => setOpen((prev) => !prev);
  const unreadCount = totalUnreadCount;
  const shouldPulse = internalUnreadCount >= INTERNAL_UNREAD_PULSE_THRESHOLD;

  const handleMarkAllInternal = useCallback(
    async ({ silent = false } = {}) => {
      if (markingAll || internalUnreadCount === 0) {
        // Surface a gentle toast when the shortcut fires with nothing to
        // clear — otherwise the user has no feedback that the keypress
        // was received.
        if (!silent && internalUnreadCount === 0) {
          toast({
            title: 'Okunmamış mesaj yok',
            description: 'Tüm personel mesajları zaten okundu.',
          });
        }
        return;
      }
      setMarkingAll(true);
      try {
        const res = await markAllInternalRead();
        const updated = res?.updated_count ?? 0;
        if (!silent) {
          if (res?.success !== false && updated > 0) {
            toast({
              title: 'Tümü okundu olarak işaretlendi',
              description: `${updated} personel mesajı temizlendi.`,
            });
          } else if (res?.success === false) {
            toast({
              title: 'İşaretleme başarısız',
              description: 'Mesajlar okundu olarak işaretlenemedi.',
              variant: 'destructive',
            });
          }
        }
      } catch (err) {
        // Network/server failure — markAllInternalRead rejected. The
        // shortcut and the in-panel button both rely on this catch to
        // surface the error; without it the user would just see the
        // bell stay full with no explanation.
        if (!silent) {
          toast({
            title: 'İşaretleme başarısız',
            description:
              err?.response?.data?.detail ||
              err?.message ||
              'Mesajlar okundu olarak işaretlenemedi.',
            variant: 'destructive',
          });
        }
      } finally {
        setMarkingAll(false);
      }
    },
    [markingAll, internalUnreadCount, markAllInternalRead, toast],
  );

  // Task #38: global Shift+R shortcut. Skipped while typing in an
  // input/textarea/contentEditable so we don't hijack message composition.
  useEffect(() => {
    const handler = async (event) => {
      // Layout-tolerant key compare: AZERTY/QWERTZ etc. report the same
      // physical key as 'r'/'R'; lowercase normalises both shifted and
      // unshifted reports without affecting the modifier check below.
      if ((event.key || '').toLowerCase() !== MARK_ALL_SHORTCUT.key.toLowerCase()) return;
      if (event.shiftKey !== MARK_ALL_SHORTCUT.shiftKey) return;
      // Don't fire when modifier-stacked with Ctrl/Meta/Alt — those are
      // reserved for browser/OS shortcuts.
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      const tag = (target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) {
        return;
      }
      if (shortcutBusyRef.current) return;
      shortcutBusyRef.current = true;
      try {
        event.preventDefault();
        await handleMarkAllInternal();
      } finally {
        shortcutBusyRef.current = false;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleMarkAllInternal]);

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <Button
        variant="outline"
        size="icon"
        className={`relative rounded-full w-12 h-12 shadow-lg bg-white ${
          shouldPulse ? 'ring-2 ring-red-400 ring-offset-2 animate-pulse' : ''
        }`}
        onClick={handleToggle}
        data-testid="button-notification-bell"
        aria-label={
          shouldPulse
            ? `Bildirimler — ${internalUnreadCount} okunmamış personel mesajı (Shift+R ile tümünü okundu işaretle)`
            : 'Bildirimler'
        }
        title={
          shouldPulse
            ? `${internalUnreadCount} okunmamış personel mesajı — Shift+R ile tümünü okundu işaretle`
            : 'Bildirimler'
        }
      >
        <Bell className={`w-5 h-5 ${shouldPulse ? 'text-red-600' : ''}`} />
        {unreadCount > 0 && (
          <span
            className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] font-semibold rounded-full px-1.5 py-0.5"
            data-testid="badge-notification-count"
          >
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
                title={t('cm.components_NotificationCenter.tumunu_temizle')}
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
                {t('cm.components_NotificationCenter.masaustu_bildirimlerini_etkinlestir')}
              </button>
            )}
            <div className="max-h-[60vh] overflow-y-auto">
              {(internalMessages.length > 0 || internalUnreadCount > 0) && (
                <div className="border-b bg-amber-50/40">
                  <div className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-amber-700 flex items-center gap-2">
                    <MessageSquare className="w-3 h-3" />
                    {t('cm.components_NotificationCenter.personel_mesajlari')}
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
                <div className="py-8 text-center text-gray-500 text-sm">{t('cm.components_NotificationCenter.yukleniyor')}</div>
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
