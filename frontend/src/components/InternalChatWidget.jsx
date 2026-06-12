import { useState, useEffect, useCallback, Suspense, lazy } from 'react';
import { Button } from '@/components/ui/button';
import { useNotifications } from '@/context/NotificationContext';
import { MessagesSquare, X } from 'lucide-react';

const InternalChatTab = lazy(() => import('@/components/pms/InternalChatTab'));

/**
 * Giriş yapmış personel için global, sağ-alt köşede duran kalıcı sohbet
 * balonu. Launcher hafif tutulur (anında görünür + okunmamış rozeti);
 * ağır sohbet paneli (InternalChatTab) yalnızca ilk açılışta lazy yüklenir.
 */
const InternalChatWidget = ({ user }) => {
  const [open, setOpen] = useState(false);
  const { internalUnreadCount } = useNotifications();
  const unread = internalUnreadCount || 0;

  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      // İçeride açık bir Radix katmanı (compose Dialog, acil AlertDialog,
      // Select/Popover) varsa Esc önce onu kapatsın; widget'ı kapatma.
      if (
        document.querySelector(
          '[data-radix-popper-content-wrapper], [role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]',
        )
      ) {
        return;
      }
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!user) return null;

  return (
    <>
      {open && (
        <div
          role="dialog"
          aria-label="Personel Mesajlaşması"
          data-testid="internal-chat-widget-panel"
          className="fixed bottom-24 right-6 z-50 flex flex-col w-[400px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-9rem)] rounded-2xl border bg-background shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          <div className="flex items-center gap-2 px-3 py-2.5 border-b bg-muted/40 shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shrink-0">
              <MessagesSquare className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold leading-tight truncate">Personel Mesajlaşması</div>
              <div className="text-[11px] text-muted-foreground leading-tight">Canlı bildirim açık</div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={close}
              data-testid="button-close-chat-widget"
              title="Kapat"
              aria-label="Kapat"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 min-h-0">
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  Yükleniyor…
                </div>
              }
            >
              <InternalChatTab currentUser={user} />
            </Suspense>
          </div>
        </div>
      )}

      <Button
        type="button"
        onClick={toggle}
        data-testid="button-toggle-chat-widget"
        aria-expanded={open}
        aria-label={open ? 'Mesajlaşmayı kapat' : 'Personel mesajlaşmasını aç'}
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full p-0 shadow-lg shadow-black/20 transition-transform hover:scale-105"
      >
        {open ? <X className="h-6 w-6" /> : <MessagesSquare className="h-6 w-6" />}
        {!open && unread > 0 && (
          <span
            className="absolute -top-1 -right-1 inline-flex items-center justify-center rounded-full border-2 border-background bg-red-500 px-1.5 py-1 text-[10px] font-bold leading-none text-white min-w-[20px]"
            data-testid="badge-chat-widget-unread"
          >
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </Button>
    </>
  );
};

export default InternalChatWidget;
