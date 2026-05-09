import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, BarChart3, BedDouble, Hotel } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import { formatCurrency, formatPercent, KPICard, CustomTooltip, SectionHeader } from './ReportHelpers';

const AdrRevparSection = ({ data, s, pc }) => (
  <div className="space-y-6" data-testid="section-adr-revpar">
    <SectionHeader title="ADR & RevPAR Analizi" description="Ortalama günlük oda fiyatı ve oda başına gelir metrikleri" />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="ADR (Bugün)" value={s.adr} prevValue={pc.prev_month_adr} icon={TrendingUp} color="blue" />
      <KPICard title="RevPAR (Bugün)" value={s.revpar} icon={BarChart3} color="green" />
      <KPICard title="Dolu Oda" value={s.occupied_rooms} icon={BedDouble} color="purple" />
      <KPICard title="Toplam Oda" value={s.total_rooms} icon={Hotel} color="cyan" />
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="border-l-4 border-l-sky-500">
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold text-slate-900 mb-3">ADR Detay</h3>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-slate-600">Bugünkü ADR</span><span className="font-bold text-slate-900">{formatCurrency(s.adr)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Önceki Ay ADR</span><span className="font-bold text-slate-900">{formatCurrency(pc.prev_month_adr)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Dolu Oda Sayısı</span><span className="font-bold text-slate-900">{s.occupied_rooms}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Bugünkü Oda Geliri</span><span className="font-bold text-slate-900">{formatCurrency(s.today_revenue)}</span></div>
          </div>
        </CardContent>
      </Card>
      <Card className="border-l-4 border-l-emerald-500">
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold text-slate-900 mb-3">RevPAR Detay</h3>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-slate-600">Bugünkü RevPAR</span><span className="font-bold text-slate-900">{formatCurrency(s.revpar)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Toplam Oda</span><span className="font-bold text-slate-900">{s.total_rooms}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Müsait Oda</span><span className="font-bold text-slate-900">{(s.total_rooms || 0) - (s.occupied_rooms || 0)}</span></div>
            <div className="flex justify-between"><span className="text-sm text-slate-600">Doluluk</span><span className="font-bold text-slate-900">{formatPercent(s.occupancy_percentage)}</span></div>
          </div>
        </CardContent>
      </Card>
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Son 14 Gün - Günlük Gelir Performansı</CardTitle></CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data?.revenue_trend?.slice(-14) || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
            <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
            <Bar dataKey="revenue" name="Günlük Gelir" fill="#0284C7" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  </div>
);

export default AdrRevparSection;
