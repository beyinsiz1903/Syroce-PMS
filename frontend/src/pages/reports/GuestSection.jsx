import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';
import { formatCurrency, SectionHeader } from './ReportHelpers';

const GUEST_STATUS = {
  checked_in: { label: 'Otelde', className: 'bg-emerald-100 text-emerald-700' },
  in_house: { label: 'Otelde', className: 'bg-emerald-100 text-emerald-700' },
  checked_out: { label: 'Çıkış Yaptı', className: 'bg-slate-100 text-slate-600' },
  no_show: { label: 'No-Show', className: 'bg-rose-100 text-rose-700' },
  noshow: { label: 'No-Show', className: 'bg-rose-100 text-rose-700' },
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
const GuestTable = ({
  guests,
  title,
  showId = false,
  showNightlyRate = false,
  searchGuest,
  setSearchGuest
}) => <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <SectionHeader title={title} />
      <Badge variant="outline" className="h-6 shrink-0">{guests.length} kayıt</Badge>
    </div>
    <div className="relative">
      <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400 z-10" />
      <Input placeholder="Misafir, oda veya e-posta ara..." value={searchGuest} onChange={e => setSearchGuest(e.target.value)} className="pl-9 bg-white border-gray-300 text-gray-900 placeholder:text-gray-400 focus:border-blue-400 focus:ring-blue-200" data-testid="guest-search-input" />
    </div>
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto" role="region" aria-label={`${title} tablosu`} tabIndex={0}>
          <table className={`w-full text-sm ${showNightlyRate ? 'min-w-[980px]' : 'min-w-[820px]'}`} data-testid="guest-table">
          <thead><tr className="border-b bg-gray-50">
            <th className="min-w-[190px] text-left py-2.5 px-3 font-semibold text-gray-600">Misafir</th>
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Oda</th>
            {showId && <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">TC/Pasaport</th>}
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Giriş</th>
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Çıkış</th>
            <th className="whitespace-nowrap text-left py-2.5 px-3 font-semibold text-gray-600">Durum</th>
            {showNightlyRate && <th className="whitespace-nowrap text-right py-2.5 px-3 font-semibold text-gray-600">Gece Ücreti</th>}
            <th className="whitespace-nowrap text-right py-2.5 px-3 font-semibold text-gray-600">{showNightlyRate ? 'Konaklama Toplamı' : 'Tutar'}</th>
          </tr></thead>
          <tbody>
            {guests.length > 0 ? guests.map((g, i) => {
              const status = guestStatus(g.status);
              return <tr key={g.id || i} className="border-b hover:bg-sky-50/30 transition-colors">
                <td className="min-w-[190px] max-w-[260px] py-2 px-3">
                  <div className="truncate font-medium text-gray-900" title={g.guest_name || '-'}>{g.guest_name || '-'}</div>
                  <div className="truncate text-[11px] text-gray-400" title={g.guest_email || ''}>{g.guest_email && g.guest_email.includes('@') ? g.guest_email : ''}</div>
                </td>
                <td className="whitespace-nowrap py-2 px-3 font-medium">{g.room_number || '-'}</td>
                {showId && <td className="whitespace-nowrap py-2 px-3 text-xs font-mono">{g.id_number || g.passport_number || '-'}</td>}
                <td className="whitespace-nowrap py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td>
                <td className="whitespace-nowrap py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td>
                <td className="whitespace-nowrap py-2 px-3"><span className={`inline-flex whitespace-nowrap text-xs px-2 py-0.5 rounded-full font-medium ${status.className}`}>{status.label}</span></td>
                {showNightlyRate && <td className="whitespace-nowrap py-2 px-3 text-right font-semibold tabular-nums text-blue-700">{g.nightly_rate == null ? '-' : formatCurrency(g.nightly_rate, g.currency)}</td>}
                <td className="whitespace-nowrap py-2 px-3 text-right font-medium tabular-nums">{g.is_primary === false ? '-' : formatCurrency(g.total_amount, g.currency)}</td>
              </tr>;
            }) : <tr><td colSpan={6 + (showId ? 1 : 0) + (showNightlyRate ? 1 : 0)} className="py-8 text-center text-gray-400">Kayıt bulunamadı</td></tr>}
          </tbody>
        </table></div>
      </CardContent>
    </Card>
  </div>;
export { GuestTable };
export default GuestTable;
