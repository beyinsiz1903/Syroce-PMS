import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, ArrowUpRight, ArrowDownRight, ArrowLeftRight, CheckCircle2 } from 'lucide-react';
import { formatCurrency, KPICard, EmptyState } from './ReportHelpers';
import { SectionHeader } from './ReportHelpers';

const FrontOfficeSection = ({ s, todayArrivals, todayDepartures }) => (
  <div className="space-y-6" data-testid="section-front-office">
    <SectionHeader title="Giriş / Çıkış Raporu" description="Bugünkü giriş, çıkış ve oteldeki misafirler" />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Beklenen Giriş" value={s.arrivals || 0} icon={ArrowUpRight} color="blue" />
      <KPICard title="Beklenen Çıkış" value={s.departures || 0} icon={ArrowDownRight} color="amber" />
      <KPICard title="Otelde" value={s.in_house || 0} icon={Users} color="green" />
      <KPICard title="Müsait Oda" value={(s.total_rooms || 0) - (s.occupied_rooms || 0)} icon={CheckCircle2} color="cyan" />
    </div>
    {todayArrivals.length > 0 && (
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Bugünkü Beklenen Girişler ({todayArrivals.length})</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="border-b bg-sky-50"><th className="text-left py-2 px-3 text-xs font-semibold text-sky-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-sky-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-sky-700">Çıkış</th><th className="text-right py-2 px-3 text-xs font-semibold text-sky-700">Tutar</th></tr></thead>
            <tbody>{todayArrivals.map((g, i) => (
              <tr key={i} className="border-b hover:bg-sky-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
            ))}</tbody>
          </table></div>
        </CardContent>
      </Card>
    )}
    {todayDepartures.length > 0 && (
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Bugünkü Çıkışlar ({todayDepartures.length})</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="border-b bg-amber-50"><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Durum</th><th className="text-right py-2 px-3 text-xs font-semibold text-amber-700">Tutar</th></tr></thead>
            <tbody>{todayDepartures.map((g, i) => (
              <tr key={i} className="border-b hover:bg-amber-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3"><span className={`text-xs px-2 py-0.5 rounded-full ${g.status === 'checked_out' ? 'bg-gray-100 text-gray-600' : 'bg-amber-100 text-amber-700'}`}>{g.status === 'checked_out' ? 'Çıkış Yaptı' : 'Bekliyor'}</span></td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
            ))}</tbody>
          </table></div>
        </CardContent>
      </Card>
    )}
    {todayArrivals.length === 0 && todayDepartures.length === 0 && (
      <Card><CardContent className="py-12"><EmptyState icon={ArrowLeftRight} message="Bugün için giriş/çıkış hareketi yok" /></CardContent></Card>
    )}
  </div>
);

export default FrontOfficeSection;
