import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Globe } from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { COLORS, SectionHeader, EmptyState } from './ReportHelpers';

const NationalitySection = ({ countryData }) => {
  const totalGuests = countryData.reduce((a, b) => a + b.count, 0);
  return (
    <div className="space-y-6" data-testid="section-nationality">
      <SectionHeader title="Milliyet Dağılımı" description="Misafirlerin ülke bazlı dağılımı" />
      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Milliyet Dağılımı</CardTitle></CardHeader>
          <CardContent>
            {countryData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart><Pie data={countryData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({ name, count }) => name + ': ' + count}>
                  {countryData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={Globe} message="Milliyet verisi yok" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Ülke Detayları</CardTitle></CardHeader>
          <CardContent>
            {countryData.length > 0 ? (
              <div className="space-y-2 max-h-[300px] overflow-y-auto">{countryData.slice(0, 20).map((c, i) => {
                const pct = totalGuests > 0 ? (c.count / totalGuests * 100).toFixed(1) : 0;
                return (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="flex-1 text-sm font-medium truncate">{c.name}</span>
                    <span className="text-sm text-gray-500">{c.count} kişi</span>
                    <span className="text-xs text-gray-400 w-12 text-right">{pct}%</span>
                  </div>
                );
              })}</div>
            ) : <p className="text-gray-400 text-center py-12">Veri yok</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default NationalitySection;
