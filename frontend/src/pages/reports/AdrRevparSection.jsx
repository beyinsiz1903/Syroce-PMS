import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, BarChart3, BedDouble, Hotel } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import { formatCurrency, formatPercent, KPICard, CustomTooltip, SectionHeader } from './ReportHelpers';

const AdrRevparSection = ({ data, s, pc, periodMetrics, reportPeriod }) => {
  const isDaily = reportPeriod === 'daily';
  const metrics = periodMetrics || s;
  const periodLabel = isDaily ? 'Seçili Gün' : '30 Gün';
  const previousLabel = isDaily ? 'Önceki Gün ADR' : 'Önceki 30 Gün ADR';
  const occupiedLabel = isDaily ? 'Dolu Oda' : 'Dolu Oda-Gecesi';
  const capacityLabel = isDaily ? 'Satılabilir Oda' : 'Satılabilir Oda-Gecesi';
  const occupied = metrics.occupied_room_nights ?? s.occupied_rooms ?? 0;
  const capacity = metrics.available_room_nights ?? s.total_rooms ?? 0;
  return (
  <div className="space-y-6" data-testid="section-adr-revpar">
    <SectionHeader title="ADR & RevPAR Analizi" description="Ortalama günlük oda fiyatı ve oda başına gelir metrikleri" />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title={`ADR (${periodLabel})`} value={metrics.adr} prevValue={pc.prev_month_adr} icon={TrendingUp} color="blue" />
      <KPICard title={`RevPAR (${periodLabel})`} value={metrics.revpar} icon={BarChart3} color="green" />
      <KPICard title={occupiedLabel} value={occupied} icon={BedDouble} color="purple" />
      <KPICard title={capacityLabel} value={capacity} icon={Hotel} color="cyan" />
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="border-l-4 border-l-sky-500">
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold text-slate-900 mb-3">ADR Detay</h3>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-slate-600">{periodLabel} ADR</span><span className="font-bold text-slate-900">{formatCurrency(metrics.adr)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">{previousLabel}</span><span className="font-bold text-slate-900">{formatCurrency(pc.prev_month_adr)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">{occupiedLabel}</span><span className="font-bold text-slate-900">{occupied}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Oda Geliri</span><span className="font-bold text-slate-900">{formatCurrency(metrics.room_revenue ?? s.today_room_revenue)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Gelir Kaynağı</span><span className="font-medium text-slate-700">{metrics.revenue_source === 'posted' ? 'Folyoya işlenmiş' : 'Tahakkuk eden'}</span></div>
          </div>
        </CardContent>
      </Card>
      <Card className="border-l-4 border-l-emerald-500">
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold text-slate-900 mb-3">RevPAR Detay</h3>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-slate-600">{periodLabel} RevPAR</span><span className="font-bold text-slate-900">{formatCurrency(metrics.revpar)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">{capacityLabel}</span><span className="font-bold text-slate-900">{capacity}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Boş Kapasite</span><span className="font-bold text-slate-900">{Math.max(capacity - occupied, 0)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Doluluk</span><span className="font-bold text-slate-900">{formatPercent(metrics.occupancy_percentage)}</span></div>
          </div>
        </CardContent>
      </Card>
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{isDaily ? 'Seçili Gün Gelir Performansı' : 'Son 14 Gün - Günlük Gelir Performansı'}</CardTitle></CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data?.revenue_trend?.slice(-14) || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} angle={-25} textAnchor="end" height={50} />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
            <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
            <Bar dataKey="revenue" name="Günlük Gelir" fill="#0284C7" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  </div>
  );
};

export default AdrRevparSection;
