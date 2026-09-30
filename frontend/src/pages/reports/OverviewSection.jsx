import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ReceiptText, BedDouble, Users, Hotel, Utensils, TrendingUp, AlertTriangle, BarChart3, ArrowUpRight, ArrowDownRight, Calendar, BookOpen, LayoutDashboard } from 'lucide-react';
import { AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { COLORS, formatCurrency, formatPercent, KPICard, CustomTooltip, SectionHeader, EmptyState, StatBox, ROOM_STATUS_COLORS, ROOM_STATUS_LABELS } from './ReportHelpers';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';
const OverviewSection = ({
  data,
  s,
  pc,
  periodMetrics,
  roomStatusData,
  reportPeriod
}) => {
  const {
    t
  } = useTranslation();

  const isDaily = reportPeriod === 'daily';
  const labelSuffix = isDaily ? '(Seçili Gün)' : '(30 Gün)';
  const prevLabelSuffix = isDaily ? 'Önceki gün: ' : 'Önceki 30 gün: ';
  const metrics = periodMetrics || s;
  const hasMixedRevenueTrend = (data?.revenue_trend || []).some((row) => Object.keys(row.revenue_by_currency || {}).length > 1);
  const hasMultipleCurrencies = [
    pc.month_revenue_by_currency,
    metrics.adr_by_currency,
    metrics.revpar_by_currency,
  ].some((breakdown) => Object.keys(breakdown || {}).filter((code) => Number(breakdown[code]) !== 0).length > 1);

  return <div className="space-y-6" data-testid="section-overview">
    <SectionHeader title="Genel Bakış - Yönetici Özeti" description="Seçili rapor dönemi ile güncel operasyon durumunun özeti" icon={LayoutDashboard} actions={<StatusBadge intent="info">Seçili dönem</StatusBadge>} />
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      <KPICard title={`Toplam Gelir ${labelSuffix}`} value={pc.month_revenue} currencyBreakdown={pc.month_revenue_by_currency} prevValue={pc.prev_month_revenue} prevLabel={prevLabelSuffix + formatCurrencyBreakdown(pc.prev_month_revenue_by_currency, pc.prev_month_revenue)} icon={ReceiptText} color="success" />
      <KPICard title={`Satılan Oda Başına Ortalama Fiyat ${labelSuffix}`} value={metrics.adr} currencyBreakdown={metrics.adr_by_currency} prevValue={pc.prev_month_adr} prevLabel={hasMultipleCurrencies ? 'Her para birimi kendi oda geliri içinde hesaplanır' : prevLabelSuffix + formatCurrency(pc.prev_month_adr)} icon={TrendingUp} color="info" />
      <KPICard title={`Satılabilir Oda Başına Gelir ${labelSuffix}`} value={metrics.revpar} currencyBreakdown={metrics.revpar_by_currency} icon={BarChart3} color="warning" />
      <KPICard title={`Doluluk Oranı ${labelSuffix}`} value={formatPercent(metrics.occupancy_percentage)} icon={Hotel} color="info" />
      <KPICard title={`Toplam Rezervasyon ${labelSuffix}`} value={pc.month_bookings} prevValue={pc.prev_month_bookings} prevLabel={prevLabelSuffix + (pc.prev_month_bookings || 0)} icon={BookOpen} color="info" />
      <KPICard title="Yiyecek ve İçecek Geliri (Seçili Gün)" value={s.fnb_revenue} currencyBreakdown={s.fnb_revenue_by_currency} icon={Utensils} color="warning" />
    </div>
    {hasMultipleCurrencies && <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
      Tutarlar birbirine eklenmez ve otomatik olarak TL'ye çevrilmez. Her para birimi, rezervasyonun kayıtlı olduğu özgün tutarıyla ayrı gösterilir.
    </div>}

    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Günlük Hareket Özeti</CardTitle></CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatBox label="Giriş" value={s.arrivals || 0} color="blue" icon={ArrowUpRight} />
          <StatBox label={t('common.departureSingle')} value={s.departures || 0} color="amber" icon={ArrowDownRight} />
          <StatBox label="Otelde" value={s.in_house || 0} color="green" icon={Users} />
          <StatBox label="Gelmeyen" value={s.no_shows || 0} color="red" icon={AlertTriangle} />
          <StatBox label={t('common.cancellationSingle')} value={s.cancellations || 0} color="gray" icon={Calendar} />
        </div>
      </CardContent>
    </Card>

    <div className="grid md:grid-cols-3 gap-4">
      <Card className="shadow-sm">
        <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">{`Gelir Trendi ${labelSuffix}`}</CardTitle></CardHeader>
        <CardContent className="pb-3">
          {hasMixedRevenueTrend ? <div className="h-40 flex items-center justify-center px-4 text-center text-xs text-slate-500">Karma dövizli gelirler tek eksende toplanmaz.</div> : <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={data?.revenue_trend || []}>
              <defs><linearGradient id="rvG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#059669" stopOpacity={0.3} /><stop offset="95%" stopColor="#059669" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="label" tick={{
                fontSize: 9
              }} interval={5} />
              <YAxis tick={{
                fontSize: 9
              }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
              <Area type="monotone" dataKey="revenue" stroke="#059669" fill="url(#rvG)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>}
        </CardContent>
      </Card>
      <Card className="shadow-sm">
        <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">{`Doluluk Trendi ${labelSuffix}`}</CardTitle></CardHeader>
        <CardContent className="pb-3">
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={data?.occupancy_trend || []}>
              <defs><linearGradient id="ocG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#0284C7" stopOpacity={0.3} /><stop offset="95%" stopColor="#0284C7" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="label" tick={{
                fontSize: 9
              }} interval={5} />
              <YAxis tick={{
                fontSize: 9
              }} domain={[0, 100]} tickFormatter={v => v + '%'} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="occupancy" stroke="#0284C7" fill="url(#ocG)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <Card className="shadow-sm">
        <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Anlık Oda Durumu</CardTitle></CardHeader>
        <CardContent className="pb-3">
          {roomStatusData.length > 0 ? <ResponsiveContainer width="100%" height={160}>
              <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={40} outerRadius={80} dataKey="value" paddingAngle={3}>
                {roomStatusData.map((e, i) => <Cell key={e.id || i} fill={e.color} />)}
              </Pie><Tooltip /><Legend iconSize={8} wrapperStyle={{
                fontSize: '10px'
              }} /></PieChart>
            </ResponsiveContainer> : <EmptyState icon={Hotel} message="Oda verisi yok" />}
        </CardContent>
      </Card>
    </div>

    <div className="grid md:grid-cols-3 gap-3">
      <Card className="p-4 border-l-4 border-l-sky-500">
        <p className="text-xs text-slate-500 font-medium mb-1 uppercase tracking-wide">{isDaily ? 'Seçili Gün Oda Geliri' : 'Son 7 Gün'}</p>
        <p className="text-2xl font-bold text-slate-900">{isDaily ? formatCurrencyBreakdown(s.today_room_revenue_by_currency, s.today_room_revenue) : formatCurrencyBreakdown(pc.week_revenue_by_currency, pc.week_revenue)}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{pc.week_bookings} rezervasyon</p>
      </Card>
      <Card className="p-4 border-l-4 border-l-emerald-500">
        <p className="text-xs text-slate-500 font-medium mb-1 uppercase tracking-wide">{isDaily ? "Seçili Gün" : "Son 30 Gün"}</p>
        <p className="text-2xl font-bold text-slate-900">{formatCurrencyBreakdown(pc.month_revenue_by_currency, pc.month_revenue)}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{pc.month_bookings} rezervasyon</p>
      </Card>
      <Card className="p-4 border-l-4 border-l-indigo-500">
        <p className="text-xs text-slate-500 font-medium mb-1 uppercase tracking-wide">{isDaily ? "Önceki Gün" : "Önceki 30 Gün"}</p>
        <p className="text-2xl font-bold text-slate-900">{formatCurrencyBreakdown(pc.prev_month_revenue_by_currency, pc.prev_month_revenue)}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{pc.prev_month_bookings} rezervasyon</p>
      </Card>
    </div>
  </div>;
};
export default OverviewSection;
