import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { CalendarCheck2, DoorOpen, Search, Users, WalletCards } from 'lucide-react';
import { formatCurrency, SectionHeader } from './ReportHelpers';

const GUEST_STATUS = {
  checked_in: { label: 'Otelde', className: 'bg-emerald-100 text-emerald-700' },
  in_house: { label: 'Otelde', className: 'bg-emerald-100 text-emerald-700' },
  checked_out: { label: 'Çıkış Yaptı', className: 'bg-slate-100 text-slate-600' },
  no_show: { label: 'Gelmedi', className: 'bg-rose-100 text-rose-700' },
  noshow: { label: 'Gelmedi', className: 'bg-rose-100 text-rose-700' },
  cancelled: { label: 'İptal', className: 'bg-rose-100 text-rose-700' },
  canceled: { label: 'İptal', className: 'bg-rose-100 text-rose-700' },
  confirmed: { label: 'Onaylı', className: 'bg-sky-100 text-sky-700' },
  guaranteed: { label: 'Garantili', className: 'bg-indigo-100 text-indigo-700' },
  pending: { label: 'Bekliyor', className: 'bg-amber-100 text-amber-700' },
};

const guestStatus = value => GUEST_STATUS[String(value || '').toLowerCase()] || {
  label: value ? String(value).replaceAll('_', ' ') : 'Bilinmiyor',
  className: 'bg-slate-100 text-slate-600'
};

export const convertToTry = (amount, currency, exchangeRates = {}) => {
  const numericAmount = Number(amount);
  if (!Number.isFinite(numericAmount)) return null;
  const code = String(currency || 'TRY').toUpperCase();
  if (code === 'TRY' || code === 'TL') return numericAmount;
  const rate = Number(exchangeRates[code]);
  return Number.isFinite(rate) && rate > 0 ? Math.round(numericAmount * rate * 100) / 100 : null;
};

export const MoneyCell = ({ amount, currency, exchangeRates }) => {
  if (amount == null) return '-';
  const code = String(currency || 'TRY').toUpperCase();
  const tryAmount = convertToTry(amount, code, exchangeRates);
  if (tryAmount == null || code === 'TRY' || code === 'TL') {
    return <span>{formatCurrency(amount, code)}</span>;
  }
  return <div className="leading-tight">
    <div>{formatCurrency(tryAmount, 'TRY')}</div>
    <div className="mt-0.5 text-[10px] font-normal text-gray-500">{formatCurrency(amount, code)}</div>
  </div>;
};

const ReceivedPaymentsCell = ({ payments = [] }) => {
  if (!payments.length) return '-';
  const totals = payments.reduce((result, payment) => {
    const currency = String(payment.currency || 'TRY').toUpperCase();
    result[currency] = (result[currency] || 0) + Number(payment.amount || 0);
    return result;
  }, {});
  return <div className="space-y-0.5">
    {Object.entries(totals).map(([currency, amount]) => (
      <div key={currency} className="font-semibold text-emerald-700">
        {new Intl.NumberFormat('tr-TR', { style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount)}
      </div>
    ))}
  </div>;
};

const COMP_MODE_LABELS = {
  entire_stay: 'Tüm konaklama',
  full: 'Tüm konaklama',
  open_nights: 'Açık/kalan gece',
  closed_nights_adjustment: 'Finansal düzeltme',
};

const PricingTreatmentCell = ({ guest }) => {
  if (guest.is_primary === false) return '-';
  if (!guest.is_complimentary_night) return <span className="text-xs text-slate-500">Ücretli</span>;
  return <div className="max-w-[220px] space-y-1 text-left">
    <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">Comp</Badge>
    <div className="text-[11px] font-medium text-amber-800">{COMP_MODE_LABELS[guest.complimentary_mode] || 'Misafire ücretsiz'}</div>
    <div className="whitespace-normal text-[11px] leading-snug text-slate-600">Neden: {guest.complimentary_reason || 'Belirtilmedi'}</div>
  </div>;
};

const GuestNightChargeCell = ({ guest, exchangeRates }) => {
  if (guest.is_primary === false) return '-';
  if (!guest.is_complimentary_night) {
    return <MoneyCell amount={guest.guest_nightly_charge ?? guest.nightly_rate} currency={guest.currency} exchangeRates={exchangeRates} />;
  }
  return <div className="leading-tight">
    <div className="font-bold text-emerald-700"><MoneyCell amount={0} currency={guest.currency} exchangeRates={exchangeRates} /></div>
    {Number(guest.reference_nightly_rate) > 0 && <div className="mt-1 text-[10px] font-normal text-slate-500">
      Emsal değer: <MoneyCell amount={guest.reference_nightly_rate} currency={guest.currency} exchangeRates={exchangeRates} />
    </div>}
  </div>;
};

const sumByCurrency = entries => entries.reduce((totals, entry) => {
  const currency = String(entry.currency || 'TRY').toUpperCase();
  totals[currency] = (totals[currency] || 0) + Number(entry.amount || 0);
  return totals;
}, {});

const CurrencyBreakdown = ({ totals, empty = '-' }) => {
  const rows = Object.entries(totals || {}).filter(([, amount]) => Number.isFinite(amount) && amount !== 0);
  if (!rows.length) return empty;
  return <div className="space-y-0.5">{rows.map(([currency, amount]) => (
    <div key={currency}>{new Intl.NumberFormat('tr-TR', { style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount)}</div>
  ))}</div>;
};

const GuestTable = ({
  guests,
  title,
  showId = false,
  showNightlyRate = false,
  exchangeRates = {},
  searchGuest,
  setSearchGuest,
  totalCount,
  reportDate,
  historical = false,
  showAmount = true,
  showEmail = true,
}) => {
  const reservationKey = guest => guest.booking_id || guest.reservation_id || String(guest.id || '').split(':')[0];
  const uniqueReservations = new Set(guests.map(reservationKey).filter(Boolean)).size;
  const uniqueRooms = new Set(guests.map(guest => guest.room_number).filter(Boolean)).size;
  const primaryRows = guests.filter(guest => guest.is_primary !== false);
  const accommodationTotals = sumByCurrency(primaryRows.map(guest => ({ amount: guest.total_amount, currency: guest.currency })));
  const paymentTotals = sumByCurrency(primaryRows.flatMap(guest => guest.received_payments || []));
  const departureCount = reportDate
    ? new Set(guests.filter(guest => String(guest.check_out || '').slice(0, 10) === reportDate).map(reservationKey).filter(Boolean)).size
    : 0;
  const shownCount = guests.length;
  const availableCount = Number.isFinite(totalCount) ? totalCount : shownCount;

  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <SectionHeader title={title} />
      <Badge variant="outline" className="h-6 shrink-0">
        {shownCount === availableCount ? `${shownCount} misafir` : `${shownCount} / ${availableCount} misafir`}
      </Badge>
    </div>
    {showNightlyRate && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="inhouse-summary">
      <Card className="report-keep-together border-l-4 border-l-sky-500 p-4">
        <div className="flex items-center gap-3"><Users className="h-5 w-5 text-sky-600" /><div><p className="text-xs text-slate-500">Oteldeki misafir</p><p className="text-xl font-bold text-slate-900">{shownCount}</p></div></div>
      </Card>
      <Card className="report-keep-together border-l-4 border-l-indigo-500 p-4">
        <div className="flex items-center gap-3"><DoorOpen className="h-5 w-5 text-indigo-600" /><div><p className="text-xs text-slate-500">Dolu oda / rezervasyon</p><p className="text-xl font-bold text-slate-900">{uniqueRooms} / {uniqueReservations}</p></div></div>
      </Card>
      <Card className="report-keep-together border-l-4 border-l-amber-500 p-4">
        <div className="flex items-center gap-3"><CalendarCheck2 className="h-5 w-5 text-amber-600" /><div><p className="text-xs text-slate-500">Seçili gün çıkış</p><p className="text-xl font-bold text-slate-900">{departureCount}</p></div></div>
      </Card>
      <Card className="report-keep-together border-l-4 border-l-emerald-500 p-4">
        <div className="flex items-start gap-3"><WalletCards className="mt-0.5 h-5 w-5 text-emerald-600" /><div><p className="text-xs text-slate-500">Toplam tahsilat</p><div className="mt-1 text-sm font-bold text-slate-900"><CurrencyBreakdown totals={paymentTotals} empty="Tahsilat yok" /></div></div></div>
      </Card>
    </div>}
    <div className="relative" data-report-screen-only="true">
      <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400 z-10" />
      <Input placeholder={showEmail ? 'Misafir, oda veya e-posta ara...' : 'Misafir veya oda ara...'} value={searchGuest} onChange={e => setSearchGuest(e.target.value)} className="pl-9 bg-white border-gray-300 text-gray-900 placeholder:text-gray-400 focus:border-blue-400 focus:ring-blue-200" data-testid="guest-search-input" />
    </div>
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto" role="region" aria-label={`${title} tablosu`} tabIndex={0}>
          <table className={`w-full text-sm ${showNightlyRate ? 'min-w-[1240px]' : 'min-w-[820px]'}`} data-testid="guest-table">
          <thead><tr className="border-b bg-gray-50">
            <th className="min-w-[190px] text-left py-2.5 px-3 font-semibold text-gray-600">Misafir</th>
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Oda</th>
            {showId && <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">TC/Pasaport</th>}
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Giriş</th>
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Çıkış</th>
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Durum</th>
            {showNightlyRate && <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Ücretlendirme</th>}
            {showNightlyRate && <th className="whitespace-nowrap text-right py-2.5 px-3 font-semibold text-gray-600">Misafire Yansıtılan</th>}
            {showNightlyRate && <th className="whitespace-nowrap text-right py-2.5 px-3 font-semibold text-gray-600">Tahsilat</th>}
            {showAmount && <th className="whitespace-nowrap text-right py-2.5 px-3 font-semibold text-gray-600">{showNightlyRate ? 'Konaklama Toplamı' : 'Tutar'}</th>}
          </tr></thead>
          <tbody>
            {guests.length > 0 ? guests.map((g, i) => {
              const status = historical ? { label: 'Seçili tarihte otelde', className: 'bg-emerald-100 text-emerald-700' } : guestStatus(g.status);
              return <tr key={g.id || i} className="border-b hover:bg-sky-50/30 transition-colors">
                <td className="min-w-[190px] max-w-[260px] py-2 px-3">
                  <div className="truncate font-medium text-gray-900" title={g.guest_name || '-'}>{g.guest_name || '-'}</div>
                  {showEmail && <div className="truncate text-[11px] text-gray-400" title={g.guest_email || ''}>{g.guest_email && g.guest_email.includes('@') ? g.guest_email : ''}</div>}
                </td>
                <td className="whitespace-nowrap py-2 px-3 font-medium">{g.room_number || '-'}</td>
                {showId && <td className="whitespace-nowrap py-2 px-3 text-xs font-mono">{g.id_number || g.passport_number || '-'}</td>}
                <td className="whitespace-nowrap py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td>
                <td className="whitespace-nowrap py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td>
                <td className="whitespace-nowrap py-2 px-3"><span className={`inline-flex whitespace-nowrap text-xs px-2 py-0.5 rounded-full font-medium ${status.className}`}>{status.label}</span></td>
                {showNightlyRate && <td className="py-2 px-3"><PricingTreatmentCell guest={g} /></td>}
                {showNightlyRate && <td className="whitespace-nowrap py-2 px-3 text-right font-semibold tabular-nums text-blue-700"><GuestNightChargeCell guest={g} exchangeRates={exchangeRates} /></td>}
                {showNightlyRate && <td className="whitespace-nowrap py-2 px-3 text-right tabular-nums"><ReceivedPaymentsCell payments={g.received_payments} /></td>}
                {showAmount && <td className="whitespace-nowrap py-2 px-3 text-right font-medium tabular-nums">{g.is_primary === false ? '-' : <MoneyCell amount={g.total_amount} currency={g.currency} exchangeRates={exchangeRates} />}</td>}
              </tr>;
            }) : <tr><td colSpan={5 + (showId ? 1 : 0) + (showNightlyRate ? 3 : 0) + (showAmount ? 1 : 0)} className="py-8 text-center text-gray-400">Kayıt bulunamadı</td></tr>}
          </tbody>
          {showNightlyRate && primaryRows.length > 0 && <tfoot>
            <tr className="border-t-2 border-slate-200 bg-slate-50 font-semibold text-slate-800">
              <td colSpan={showId ? 7 : 6} className="px-3 py-3 text-right">Filtrelenen kayıtların toplamı</td>
              <td className="px-3 py-3 text-right">—</td>
              <td className="px-3 py-3 text-right text-emerald-700"><CurrencyBreakdown totals={paymentTotals} /></td>
              <td className="px-3 py-3 text-right"><CurrencyBreakdown totals={accommodationTotals} /></td>
            </tr>
          </tfoot>}
        </table></div>
      </CardContent>
    </Card>
  </div>;
};
export { GuestTable };
export default GuestTable;
