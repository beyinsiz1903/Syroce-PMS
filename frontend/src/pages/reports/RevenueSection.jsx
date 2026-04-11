import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DollarSign, Calendar, TrendingUp, Utensils } from 'lucide-react';
import {
  BarChart, Bar, Cell, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { COLORS, formatCurrency, KPICard, CustomTooltip, SectionHeader } from './ReportHelpers';

const RevenueSection = ({ data, s, pc, roomTypeData }) => (
  <div className="space-y-6" data-testid="section-revenue">
    <SectionHeader title="Gelir Raporu" description="Detaylı gelir analizi ve trendler" />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Bugünkü Gelir" value={s.today_revenue} icon={DollarSign} color="green" />
      <KPICard title="Haftalık Gelir" value={pc.week_revenue} icon={Calendar} color="blue" />
      <KPICard title="Aylık Gelir" value={pc.month_revenue} prevValue={pc.prev_month_revenue} icon={TrendingUp} color="purple" />
      <KPICard title="F&B Geliri" value={s.fnb_revenue} icon={Utensils} color="amber" />
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">30 Günlük Gelir Trendi</CardTitle></CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={data?.revenue_trend || []}>
            <defs><linearGradient id="rvFull" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#059669" stopOpacity={0.2} /><stop offset="95%" stopColor="#059669" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
            <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#059669" fill="url(#rvFull)" strokeWidth={2} />
            <Line type="monotone" dataKey="revenue" name="Trend" stroke="#EA580C" strokeWidth={2} dot={false} strokeDasharray="5 5" />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
    {roomTypeData.length > 0 && (
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Bazlı Gelir</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={roomTypeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
              <Bar dataKey="revenue" name="Gelir" radius={[4, 4, 0, 0]}>{roomTypeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    )}
  </div>
);

export default RevenueSection;
