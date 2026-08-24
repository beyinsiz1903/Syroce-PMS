import { useEffect, useState } from 'react';
import { Headset, MessagesSquare, Phone, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useNotifications } from '@/context/NotificationContext';

const OPEN_CHAT_EVENT = 'syroce:open-internal-chat';
const CLOSE_CHAT_EVENT = 'syroce:close-internal-chat';
const OPEN_PHONE_EVENT = 'syroce:open-softphone';
const CLOSE_PHONE_EVENT = 'syroce:close-softphone';

export default function CommunicationCenter({ user }) {
  const [open, setOpen] = useState(false);
  const { internalUnreadCount } = useNotifications();
  const unread = internalUnreadCount || 0;

  useEffect(() => {
    const close = () => setOpen(false);
    window.addEventListener('syroce:communication-panel-opened', close);
    return () => window.removeEventListener('syroce:communication-panel-opened', close);
  }, []);

  if (!user || user.role === 'guest') return null;

  const openPanel = (eventName, closeEventName) => {
    window.dispatchEvent(new CustomEvent(closeEventName));
    window.dispatchEvent(new CustomEvent(eventName));
    window.dispatchEvent(new CustomEvent('syroce:communication-panel-opened'));
    setOpen(false);
  };

  return (
    <div className="communication-center fixed bottom-5 right-5 z-50 flex flex-col items-end gap-2">
      {open && (
        <div
          className="w-64 rounded-2xl border border-slate-200 bg-white p-2 shadow-2xl dark:border-slate-700 dark:bg-slate-950"
          role="menu"
          aria-label="İletişim merkezi seçenekleri"
          data-testid="communication-center-menu"
        >
          <div className="flex items-center justify-between px-2 py-1.5">
            <div>
              <div className="text-sm font-bold text-slate-900">İletişim merkezi</div>
              <div className="text-[11px] text-slate-500">Mesaj ve telefon tek noktada</div>
            </div>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setOpen(false)} aria-label="İletişim merkezini kapat">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-900"
            onClick={() => openPanel(OPEN_CHAT_EVENT, CLOSE_PHONE_EVENT)}
            data-testid="communication-open-chat"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-700"><MessagesSquare className="h-4 w-4" /></span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-slate-800">Personel mesajları</span>
              <span className="block text-[11px] text-slate-500">Ekip içi yazışmalar</span>
            </span>
            {unread > 0 && <span className="rounded-full bg-rose-500 px-1.5 py-0.5 text-[10px] font-bold text-white">{unread > 99 ? '99+' : unread}</span>}
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-900"
            onClick={() => openPanel(OPEN_PHONE_EVENT, CLOSE_CHAT_EVENT)}
            data-testid="communication-open-phone"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700"><Phone className="h-4 w-4" /></span>
            <span>
              <span className="block text-sm font-semibold text-slate-800">Telefon</span>
              <span className="block text-[11px] text-slate-500">Softphone ve geri aramalar</span>
            </span>
          </button>
        </div>
      )}

      <Button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="communication-center-launcher h-12 rounded-full px-4 shadow-xl shadow-slate-900/20"
        aria-expanded={open}
        aria-label="İletişim merkezini aç"
        data-testid="communication-center-launcher"
      >
        {open ? <X className="h-5 w-5" /> : <Headset className="h-5 w-5" />}
        <span className="communication-center-label ml-2 text-xs font-semibold">İletişim merkezi</span>
        {!open && unread > 0 && (
          <span className="absolute -right-1 -top-1 min-w-[20px] rounded-full border-2 border-white bg-rose-500 px-1 py-0.5 text-[10px] font-bold leading-none text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </Button>
    </div>
  );
}
