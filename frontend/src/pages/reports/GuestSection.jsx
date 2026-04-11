import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';
import { formatCurrency, SectionHeader } from './ReportHelpers';

const GuestTable = ({ guests, title, showId = false, searchGuest, setSearchGuest }) => (
  <div className="space-y-4">
    <div className="flex items-center justify-between">
      <SectionHeader title={title} />
      <Badge variant="outline" className="h-6">{guests.length} kayit</Badge>
    </div>
    <div className="relative">
      <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400 z-10" />
      <Input
        placeholder="Misafir, oda veya e-posta ara..."
        value={searchGuest}
        onChange={e => setSearchGuest(e.target.value)}
        className="pl-9 bg-white border-gray-300 text-gray-900 placeholder:text-gray-400 focus:border-blue-400 focus:ring-blue-200"
        data-testid="guest-search-input"
      />
    </div>
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="guest-table">
          <thead><tr className="border-b bg-gray-50">
            <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Misafir</th>
            <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Oda</th>
            {showId && <th className="text-left py-2.5 px-3 font-semibold text-gray-600">TC/Pasaport</th>}
            <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Giriş</th>
            <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Çıkış</th>
            <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Durum</th>
            <th className="text-right py-2.5 px-3 font-semibold text-gray-600">Tutar</th>
          </tr></thead>
          <tbody>
            {guests.length > 0 ? guests.map((g, i) => (
              <tr key={i} className="border-b hover:bg-blue-50/30 transition-colors">
                <td className="py-2 px-3"><div className="font-medium text-gray-900">{g.guest_name || '-'}</div><div className="text-[11px] text-gray-400">{g.guest_email || ''}</div></td>
                <td className="py-2 px-3 font-medium">{g.room_number || '-'}</td>
                {showId && <td className="py-2 px-3 text-xs font-mono">{g.id_number || g.passport_number || '-'}</td>}
                <td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td>
                <td className="py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td>
                <td className="py-2 px-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${g.status === 'checked_in' ? 'bg-emerald-100 text-emerald-700' : g.status === 'checked_out' ? 'bg-gray-100 text-gray-600' : g.status === 'no_show' ? 'bg-rose-100 text-rose-700' : g.status === 'cancelled' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>{g.status === 'checked_in' ? 'Otelde' : g.status === 'checked_out' ? 'Çıkış Yaptı' : g.status === 'no_show' ? 'No-Show' : g.status === 'cancelled' ? 'İptal' : 'Onayli'}</span></td>
                <td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td>
              </tr>
            )) : <tr><td colSpan={showId ? 7 : 6} className="py-8 text-center text-gray-400">Kayıt bulunamadı</td></tr>}
          </tbody>
        </table></div>
      </CardContent>
    </Card>
  </div>
);

export { GuestTable };
export default GuestTable;
