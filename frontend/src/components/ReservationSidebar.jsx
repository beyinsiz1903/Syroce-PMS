import { useMemo, useState } from 'react';
import {
  ArrowRight, BedDouble, Building2, CalendarDays, FileText, Mail,
  MessageSquareText, Phone, Send, UserRound, UsersRound, X, XCircle, Loader2,
} from 'lucide-react';
import axios from 'axios';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import CallButton from '@/components/contact-center/CallButton';
import { confirmDialog } from '@/lib/dialogs';
import { cachedTenantCurrency } from '@/lib/currency';
import { bookingSourceLabel } from '@/utils/bookingSource';

export const reservationQuickPanelSummary = (booking, folio) => {
  const checkIn = new Date(booking?.check_in);
  const checkOut = new Date(booking?.check_out);
  const nights = Number.isFinite(checkIn.getTime()) && Number.isFinite(checkOut.getTime())
    ? Math.max(1, Math.round((checkOut - checkIn) / 86400000))
    : 1;
  const total = Number(booking?.total_amount || 0);
  const folioBalance = Number(folio?.balance ?? folio?.total_balance);
  const bookingBalance = Number(booking?.remaining_balance ?? booking?.balance);
  return {
    nights,
    total,
    balance: Number.isFinite(folioBalance) ? folioBalance : Number.isFinite(bookingBalance) ? bookingBalance : null,
    guestCount: Number(booking?.adults || 0) + Number(booking?.children || 0) || Number(booking?.guests_count || 0) || 1,
    currency: String(folio?.currency || booking?.currency || cachedTenantCurrency()).toUpperCase(),
  };
};

const formatDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
};

const formatMoney = (amount, currency) => {
  const normalized = currency === 'TL' ? 'TRY' : currency;
  try {
    return new Intl.NumberFormat('tr-TR', {
      style: 'currency', currency: normalized, minimumFractionDigits: 0, maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    return `${Number(amount || 0).toLocaleString('tr-TR')} ${currency}`;
  }
};

const statusTone = (status) => {
  if (status === 'checked_in') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (status === 'checked_out') return 'bg-rose-50 text-rose-700 border-rose-200';
  return 'bg-blue-50 text-blue-700 border-blue-200';
};

const visibleContact = (value) => {
  const normalized = String(value || '').trim();
  return normalized && !normalized.startsWith('SYR1:') ? normalized : '';
};

const ReservationSidebar = ({
  booking, folio, room, onClose, getStatusLabel, onViewFolio,
  onOpenWorkspace, onSendConfirmation, onDataRefresh,
}) => {
  const [cancelling, setCancelling] = useState(false);
  const summary = useMemo(() => reservationQuickPanelSummary(booking, folio), [booking, folio]);
  if (!booking) return null;

  const guestName = booking.guest_name || booking.guest?.name || 'Misafir';
  const initials = guestName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
  const roomNumber = room?.room_number || booking.room_number || 'Atanmadı';
  const source = bookingSourceLabel(booking);
  const guestEmail = visibleContact(booking.guest_email);
  const guestPhone = visibleContact(booking.guest_phone);

  return (
    <aside
      className="fixed bottom-3 right-3 top-3 z-[55] flex w-[430px] max-w-[calc(100vw-24px)] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_28px_90px_rgba(15,23,42,0.28)] animate-in slide-in-from-right duration-200"
      data-testid="reservation-quick-panel"
      aria-label={`${guestName} hızlı rezervasyon özeti`}
    >
      <header className="border-b border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 px-5 pb-5 pt-4 text-white">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15 text-lg font-bold ring-1 ring-white/20">{initials || 'M'}</span>
            <div className="min-w-0"><p className="truncate text-lg font-bold">{guestName}</p><p className="mt-0.5 truncate text-xs text-slate-300">{source} · {summary.guestCount} misafir</p></div>
          </div>
          <button type="button" onClick={onClose} className="rounded-xl p-2 text-slate-300 transition hover:bg-white/10 hover:text-white" aria-label="Hızlı paneli kapat"><X className="h-5 w-5" /></button>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl border border-white/10 bg-white/10 px-3 py-2"><p className="text-[10px] uppercase tracking-wide text-slate-300">Oda</p><p className="mt-0.5 font-bold">{roomNumber}</p></div>
          <div className="rounded-xl border border-white/10 bg-white/10 px-3 py-2"><p className="text-[10px] uppercase tracking-wide text-slate-300">Konaklama</p><p className="mt-0.5 font-bold">{summary.nights} gece</p></div>
          <div className="rounded-xl border border-white/10 bg-white/10 px-3 py-2"><p className="text-[10px] uppercase tracking-wide text-slate-300">Toplam</p><p className="mt-0.5 truncate font-bold">{formatMoney(summary.total, summary.currency)}</p></div>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/80 p-4">
        <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div><p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Rezervasyon durumu</p><Badge className={`mt-2 border ${statusTone(booking.status)}`}>{getStatusLabel(booking.status)}</Badge></div>
          <div className="text-right"><p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Kalan bakiye</p><p className={`mt-1 text-xl font-bold ${summary.balance == null ? 'text-slate-500' : summary.balance > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{summary.balance == null ? 'Hesaplanıyor' : formatMoney(summary.balance, summary.currency)}</p></div>
        </div>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900"><CalendarDays className="h-4 w-4 text-blue-600" /> Konaklama</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-xl bg-slate-50 p-3"><p className="text-[11px] text-slate-500">Giriş</p><p className="mt-1 font-semibold text-slate-800">{formatDate(booking.check_in)}</p></div>
            <div className="rounded-xl bg-slate-50 p-3"><p className="text-[11px] text-slate-500">Çıkış</p><p className="mt-1 font-semibold text-slate-800">{formatDate(booking.check_out)}</p></div>
          </div>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-500"><BedDouble className="h-4 w-4" /> Oda tipi</span><strong className="text-slate-800">{room?.room_type || booking.room_type || '—'}</strong></div>
            <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-500"><UsersRound className="h-4 w-4" /> Misafir</span><strong className="text-slate-800">{booking.adults || 0} yetişkin · {booking.children || 0} çocuk</strong></div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900"><UserRound className="h-4 w-4 text-blue-600" /> Misafir ve iletişim</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 text-slate-600"><Mail className="h-4 w-4 text-slate-400" /><span className="truncate">{guestEmail || 'E-posta bilgisi yok'}</span></div>
            <div className="flex items-center justify-between gap-2 text-slate-600"><span className="flex min-w-0 items-center gap-2"><Phone className="h-4 w-4 shrink-0 text-slate-400" /><span className="truncate">{guestPhone || 'Telefon bilgisi yok'}</span></span>{guestPhone && <CallButton number={guestPhone} />}</div>
            {booking.company_name && <div className="flex items-center gap-2 text-slate-600"><Building2 className="h-4 w-4 text-slate-400" />{booking.company_name}</div>}
          </div>
        </section>

        {booking.special_requests && <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4"><h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-amber-900"><MessageSquareText className="h-4 w-4" /> Misafir notu</h3><p className="line-clamp-4 text-sm leading-5 text-amber-800">{booking.special_requests}</p></section>}
      </div>

      <footer className="border-t border-slate-200 bg-white p-4">
        <Button className="h-11 w-full justify-between bg-blue-600 hover:bg-blue-700" onClick={() => onOpenWorkspace?.(booking)} data-testid="open-reservation-workspace"><span className="flex items-center gap-2"><ArrowRight className="h-4 w-4" /> Tam rezervasyon detayını aç</span><span className="text-xs text-blue-100">Tüm işlemler</span></Button>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Button variant="outline" className="h-10" onClick={() => onViewFolio?.(booking.id)} data-testid="view-folio-btn"><FileText className="mr-2 h-4 w-4" /> Folyo</Button>
          <Button variant="outline" className="h-10" onClick={() => onSendConfirmation?.(booking)}><Send className="mr-2 h-4 w-4" /> Onay gönder</Button>
        </div>
        {booking.status !== 'cancelled' && !['checked_in', 'checked_out'].includes(booking.status) && (
          <Button variant="ghost" className="mt-2 h-9 w-full text-rose-600 hover:bg-rose-50 hover:text-rose-700" data-testid="sidebar-cancel-booking-btn" disabled={cancelling} onClick={async () => {
            if (!await confirmDialog({ message: 'Bu rezervasyonu iptal etmek istediğinize emin misiniz?', variant: 'danger' })) return;
            setCancelling(true);
            try {
              await axios.post('/pms-core/cancel', { booking_id: booking.id, reason: 'Kullanıcı tarafından iptal edildi' });
              toast.success('Rezervasyon başarıyla iptal edildi'); onClose(); onDataRefresh?.();
            } catch (error) {
              const detail = error.response?.data?.detail;
              toast.error(typeof detail === 'string' ? detail : detail?.error || 'İptal işlemi başarısız');
            } finally { setCancelling(false); }
          }}>{cancelling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <XCircle className="mr-2 h-4 w-4" />} Rezervasyonu iptal et</Button>
        )}
      </footer>
    </aside>
  );
};

export default ReservationSidebar;
