import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  DollarSign, BedDouble, Users, Hotel, Utensils, TrendingUp,
  AlertTriangle, BarChart3, ArrowUpRight, ArrowDownRight, Calendar, BookOpen, LayoutDashboard
} from 'lucide-react';
import {
  AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import {
  COLORS, formatCurrency, formatPercent,
  KPICard, CustomTooltip, SectionHeader, EmptyState, StatBox,
  ROOM_STATUS_COLORS, ROOM_STATUS_LABELS
} from './ReportHelpers';

const OverviewSection = ({ data, s, pc, roomStatusData }) => {
  const { t } = useTranslation();
  return (
  <div className="space-y-6" data-testid="section-overview">
    <SectionHeader title="Genel Bakış - Yönetici Özeti" description="Temel KPI'lar ve günlük operasyonel özet" actions={<Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">Canlı</Badge>} />
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      <KPICard title="Toplam Gelir (30 Gün)" value={pc.month_revenue} prevValue={pc.prev_month_revenue} prevLabel={'Önceki ay: ' + formatCurrency(pc.prev_month_revenue)} icon={DollarSign} color="green" />
      <KPICard title="Ortalama ADR" value={s.adr} prevValue={pc.prev_month_adr} prevLabel={'Önceki ay: ' + formatCurrency(pc.prev_month_adr)} icon={TrendingUp} color="blue" />
      <KPICard title="RevPAR" value={s.revpar} icon={BarChart3} color="amber" />
      <KPICard title="Doluluk Oranı" value={formatPercent(s.occupancy_percentage)} icon={Hotel} color="purple" />
      <KPICard title="Toplam Rezervasyon" value={pc.month_bookings} prevValue={pc.prev_month_bookings} prevLabel={'Önceki ay: ' + (pc.prev_month_bookings || 0)} icon={BookOpen} color="cyan" />
      <KPICard title="F&B Geliri (Bugün)" value={s.fnb_revenue} icon={Utensils} color="teal" />
    </div>

    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Günlük Hareket Özeti</CardTitle></CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatBox label="Giriş" value={s.arrivals || 0} color="blue" icon={ArrowUpRight} />
          <StatBox label={t('common.departureSingle')} value={s.departures || 0} color="amber" icon={ArrowDownRight} />
          <StatBox label="Otelde" value={s.in_house || 0} color="green" icon={Users} />
          <StatBox label="No-Show" value={s.no_shows || 0} color="red" icon={AlertTriangle} />
          <StatBox label={t('common.cancellationSingle')} value={s.cancellations || 0} color="gray" icon={Calendar} />
        </div>
      </CardContent>
    </Card>

    <div className="grid md:grid-cols-3 gap-4">
      <Card className="shadow-sm">
        <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Gelir Trendi (30 Gün)</CardTitle></CardHeader>
        <CardContent className="pb-3">
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={data?.revenue_trend || []}>
              <defs><linearGradient id="rvG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#059669" stopOpacity={0.3} /><stop offset="95%" stopColor="#059669" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={5} />
              <YAxis tick={{ fontSize: 9 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
              <Area type="monotone" dataKey="revenue" stroke="#059669" fill="url(#rvG)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <Card className="shadow-sm">
        <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Doluluk Trendi (30 Gün)</CardTitle></CardHeader>
        <CardContent className="pb-3">
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={data?.occupancy_trend || []}>
              <defs><linearGradient id="ocG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563EB" stopOpacity={0.3} /><stop offset="95%" stopColor="#2563EB" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={5} />
              <YAxis tick={{ fontSize: 9 }} domain={[0, 100]} tickFormatter={v => v + '%'} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="occupancy" stroke="#2563EB" fill="url(#ocG)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <Card className="shadow-sm">
        <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Oda Durumu</CardTitle></CardHeader>
        <CardContent className="pb-3">
          {roomStatusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} dataKey="value" paddingAngle={3}>
                {roomStatusData.map((e, i) => <Cell key={i} fill={e.color} />)}
              </Pie><Tooltip /><Legend iconSize={8} wrapperStyle={{ fontSize: '10px' }} /></PieChart>
            </ResponsiveContainer>
          ) : <EmptyState icon={Hotel} message="Oda verisi yok" />}
        </CardContent>
      </Card>
    </div>

    <div className="grid md:grid-cols-3 gap-3">
      <div className="p-4 bg-blue-50 rounded-xl border border-blue-100">
        <p className="text-xs text-blue-600 font-medium mb-1">Son 7 Gün</p>
        <p className="text-2xl font-bold text-blue-800">{formatCurrency(pc.week_revenue)}</p>
        <p className="text-[11px] text-blue-500 mt-0.5">{pc.week_bookings} rezervasyon</p>
      </div>
      <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100">
        <p className="text-xs text-emerald-600 font-medium mb-1">Son 30 Gün</p>
        <p className="text-2xl font-bold text-emerald-800">{formatCurrency(pc.month_revenue)}</p>
        <p className="text-[11px] text-emerald-500 mt-0.5">{pc.month_bookings} rezervasyon</p>
      </div>
      <div className="p-4 bg-violet-50 rounded-xl border border-violet-100">
        <p className="text-xs text-violet-600 font-medium mb-1">Önceki 30 Gün</p>
        <p className="text-2xl font-bold text-violet-800">{formatCurrency(pc.prev_month_revenue)}</p>
        <p className="text-[11px] text-violet-500 mt-0.5">{pc.prev_month_bookings} rezervasyon</p>
      </div>
    </div>
  </div>
  );
};

export default OverviewSection;
