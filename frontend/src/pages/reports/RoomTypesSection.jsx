import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Hotel } from 'lucide-react';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { COLORS, formatCurrency, SectionHeader, EmptyState } from './ReportHelpers';
const RoomTypesSection = ({
  roomTypeData
}) => <div className="space-y-6" data-testid="section-room-types">
    <SectionHeader title="Oda Tipi Analizi" description="Oda tipine göre doluluk ve gelir kırılımı" />
    {roomTypeData.length > 0 ? <>
      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Dağılımı</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart><Pie data={roomTypeData} cx="50%" cy="50%" outerRadius={90} dataKey="total" label={({
                name,
                total
              }) => name + ': ' + total}>
                {roomTypeData.map((_, i) => <Cell key={_.id || i} fill={COLORS[i % COLORS.length]} />)}
              </Pie><Tooltip /></PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Doluluk</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={roomTypeData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => v + '%'} tick={{
                fontSize: 10
              }} />
                <YAxis type="category" dataKey="name" tick={{
                fontSize: 10
              }} width={100} />
                <Tooltip /><Bar dataKey="occupancy" name="Doluluk %" fill="#4F46E5" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Detay Tablosu</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="room-type-table">
            <thead><tr className="border-b bg-gray-50">
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Oda Tipi</th>
              <th className="text-center py-2.5 px-3 font-semibold text-gray-600">Toplam</th>
              <th className="text-center py-2.5 px-3 font-semibold text-gray-600">Dolu</th>
              <th className="text-center py-2.5 px-3 font-semibold text-gray-600">Doluluk</th>
              <th className="text-right py-2.5 px-3 font-semibold text-gray-600">Gelir</th>
              <th className="text-right py-2.5 px-3 font-semibold text-gray-600">Oda Başı Gelir</th>
            </tr></thead>
            <tbody>{roomTypeData.map((rt, i) => <tr key={rt.id || i} className="border-b hover:bg-gray-50">
                <td className="py-2.5 px-3 font-medium">{rt.name}</td>
                <td className="py-2.5 px-3 text-center">{rt.total}</td>
                <td className="py-2.5 px-3 text-center">{rt.occupied}</td>
                <td className="py-2.5 px-3 text-center"><span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${rt.occupancy > 70 ? 'bg-emerald-100 text-emerald-700' : rt.occupancy > 30 ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'}`}>{rt.occupancy}%</span></td>
                <td className="py-2.5 px-3 text-right font-medium">{formatCurrency(rt.revenue)}</td>
                <td className="py-2.5 px-3 text-right text-gray-500">{rt.total > 0 ? formatCurrency(rt.revenue / rt.total) : '-'}</td>
              </tr>)}</tbody>
          </table></div>
        </CardContent>
      </Card>
    </> : <Card><CardContent className="py-12"><EmptyState icon={Hotel} message="Oda tipi verisi yok" /></CardContent></Card>}
  </div>;
export default RoomTypesSection;