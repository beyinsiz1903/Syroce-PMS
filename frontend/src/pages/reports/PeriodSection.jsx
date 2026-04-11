import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ComposedChart, Bar, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { formatCurrency, calcChange, CustomTooltip, SectionHeader } from './ReportHelpers';

const PeriodSection = ({ data, pc }) => {
  const revChange = calcChange(pc.month_revenue, pc.prev_month_revenue);
  const bookChange = calcChange(pc.month_bookings, pc.prev_month_bookings);
  return (
    <div className="space-y-6" data-testid="section-period">
      <SectionHeader title="Dönem Karşılaştırma" description="Haftalık, aylık ve önceki dönem karşılaştırmaları" />
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="border-l-4 border-l-blue-500"><CardContent className="p-4">
          <p className="text-[11px] text-gray-500 uppercase tracking-wide">Son 7 Gün Gelir</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.week_revenue)}</p>
          <p className="text-xs text-gray-400 mt-1">{pc.week_bookings} rezervasyon</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-emerald-500"><CardContent className="p-4">
          <p className="text-[11px] text-gray-500 uppercase tracking-wide">Son 30 Gün Gelir</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.month_revenue)}</p>
          <p className="text-xs text-gray-400 mt-1">{pc.month_bookings} rezervasyon</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-violet-500"><CardContent className="p-4">
          <p className="text-[11px] text-gray-500 uppercase tracking-wide">Önceki 30 Gün Gelir</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.prev_month_revenue)}</p>
          <p className="text-xs text-gray-400 mt-1">{pc.prev_month_bookings} rezervasyon</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-amber-500"><CardContent className="p-4">
          <p className="text-[11px] text-gray-500 uppercase tracking-wide">Geçen Yıl (Aynı Dönem)</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.last_year_revenue)}</p>
          <p className="text-xs text-gray-400 mt-1">{pc.last_year_bookings} rezervasyon</p>
        </CardContent></Card>
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Gelir & Rezervasyon Trendi</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={data?.revenue_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={3} />
              <YAxis yAxisId="left" tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="left" dataKey="revenue" name="Gelir" fill="#2563EB" opacity={0.6} radius={[2, 2, 0, 0]} />
              <Line yAxisId="left" type="monotone" dataKey="revenue" name="Trend" stroke="#EA580C" strokeWidth={2} dot={{ r: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      <div className="grid md:grid-cols-2 gap-4">
        <Card className={`border-2 ${Number(revChange.pct) > 0 && revChange.direction === 'up' ? 'border-emerald-200 bg-emerald-50/30' : 'border-rose-200 bg-rose-50/30'}`}>
          <CardContent className="p-5 text-center">
            <p className="text-sm font-medium text-gray-600">Gelir Değişimi (Önceki Aya Göre)</p>
            <p className={`text-3xl font-bold mt-2 ${revChange.direction === 'up' ? 'text-emerald-700' : 'text-rose-700'}`}>
              {revChange.direction === 'up' ? '+' : '-'}{revChange.pct}%
            </p>
            <p className="text-xs text-gray-500 mt-1">{formatCurrency(pc.month_revenue)} vs {formatCurrency(pc.prev_month_revenue)}</p>
          </CardContent>
        </Card>
        <Card className={`border-2 ${Number(bookChange.pct) > 0 && bookChange.direction === 'up' ? 'border-emerald-200 bg-emerald-50/30' : 'border-rose-200 bg-rose-50/30'}`}>
          <CardContent className="p-5 text-center">
            <p className="text-sm font-medium text-gray-600">Rezervasyon Değişimi (Önceki Aya Göre)</p>
            <p className={`text-3xl font-bold mt-2 ${bookChange.direction === 'up' ? 'text-emerald-700' : 'text-rose-700'}`}>
              {bookChange.direction === 'up' ? '+' : '-'}{bookChange.pct}%
            </p>
            <p className="text-xs text-gray-500 mt-1">{pc.month_bookings} vs {pc.prev_month_bookings}</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default PeriodSection;
