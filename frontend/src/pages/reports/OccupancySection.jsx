import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Hotel, BedDouble, TrendingUp, CheckCircle2 } from 'lucide-react';
import {
  ComposedChart, Bar, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { formatPercent, KPICard, CustomTooltip, SectionHeader } from './ReportHelpers';

const OccupancySection = ({ data, s, periodMetrics, reportPeriod }) => {
  const isDaily = reportPeriod === 'daily';
  const metrics = periodMetrics || s;
  const occupied = metrics.occupied_room_nights ?? s.occupied_rooms ?? 0;
  const capacity = metrics.available_room_nights ?? s.total_rooms ?? 0;
  const periodLabel = isDaily ? 'Seçili Gün' : '30 Gün';
  return (
  <div className="space-y-6" data-testid="section-occupancy">
    <SectionHeader title="Doluluk Raporu" description="Seçili rapor döneminin doluluk oranları ve trendleri" actions={<Badge className="bg-sky-100 text-sky-700 border-sky-200">Seçili dönem</Badge>} />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title={isDaily ? 'Satılabilir Oda' : 'Satılabilir Oda-Gecesi'} value={capacity} icon={Hotel} color="blue" />
      <KPICard title={isDaily ? 'Dolu Oda' : 'Dolu Oda-Gecesi'} value={occupied} icon={BedDouble} color="green" />
      <KPICard title={`Doluluk (${periodLabel})`} value={formatPercent(metrics.occupancy_percentage)} icon={TrendingUp} color="purple" />
      <KPICard title="Boş Kapasite" value={Math.max(capacity - occupied, 0)} icon={CheckCircle2} color="cyan" />
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Doluluk Oranı ({periodLabel})</CardTitle><CardDescription>Dolu oda sayısı ve doluluk yüzdesi</CardDescription></CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={data?.occupancy_trend || []}>
            <defs><linearGradient id="occFull" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#0284C7" stopOpacity={0.2} /><stop offset="95%" stopColor="#0284C7" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} />
            <YAxis yAxisId="left" domain={[0, 100]} tickFormatter={v => v + '%'} tick={{ fontSize: 10 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
            <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
            <Area yAxisId="left" type="monotone" dataKey="occupancy" name="Doluluk %" stroke="#0284C7" fill="url(#occFull)" strokeWidth={2} />
            <Bar yAxisId="right" dataKey="rooms_occupied" name="Dolu Oda" fill="#D97706" opacity={0.5} radius={[2, 2, 0, 0]} />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  </div>
  );
};

export default OccupancySection;
