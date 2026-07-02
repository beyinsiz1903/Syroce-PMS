import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, BarChart3 } from 'lucide-react';
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { COLORS, formatCurrency, SectionHeader, EmptyState, CustomTooltip } from './ReportHelpers';
export const ChannelsSection = ({
  sourceData
}) => <div className="space-y-6" data-testid="section-channels">
    <SectionHeader title="Kanal Dağılımı" description="Rezervasyon kanalları ve performans analizi" />
    <div className="grid md:grid-cols-2 gap-4">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Kaynak Dağılımı</CardTitle></CardHeader>
        <CardContent>
          {sourceData.length > 0 ? <ResponsiveContainer width="100%" height={300}>
              <PieChart><Pie data={sourceData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({
              name,
              count
            }) => name + ': ' + count}>
                {sourceData.map((_, i) => <Cell key={_.id || i} fill={COLORS[i % COLORS.length]} />)}
              </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{
              fontSize: 11
            }} /></PieChart>
            </ResponsiveContainer> : <EmptyState icon={Activity} message="Kanal verisi yok" />}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Kaynak Bazlı Gelir</CardTitle></CardHeader>
        <CardContent>
          {sourceData.length > 0 ? <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sourceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{
              fontSize: 10
            }} />
                <YAxis tick={{
              fontSize: 10
            }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
                <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                <Bar dataKey="revenue" name="Gelir" radius={[4, 4, 0, 0]}>{sourceData.map((_, i) => <Cell key={_.id || i} fill={COLORS[i % COLORS.length]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer> : <EmptyState icon={BarChart3} message="Kaynak gelir verisi yok" />}
        </CardContent>
      </Card>
    </div>
    {sourceData.length > 0 && <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Kanal Detay Tablosu</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="channel-table">
            <thead><tr className="border-b bg-gray-50">
              <th className="text-left py-2 px-3 font-semibold text-gray-600">Kanal</th>
              <th className="text-center py-2 px-3 font-semibold text-gray-600">Rezervasyon</th>
              <th className="text-right py-2 px-3 font-semibold text-gray-600">Gelir</th>
              <th className="text-right py-2 px-3 font-semibold text-gray-600">Ort. Tutar</th>
            </tr></thead>
            <tbody>{sourceData.map((src, i) => <tr key={src.id || i} className="border-b hover:bg-gray-50">
                <td className="py-2.5 px-3 flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{
                  backgroundColor: COLORS[i % COLORS.length]
                }} /><span className="font-medium">{src.name}</span></td>
                <td className="py-2.5 px-3 text-center">{src.count}</td>
                <td className="py-2.5 px-3 text-right font-medium">{formatCurrency(src.revenue)}</td>
                <td className="py-2.5 px-3 text-right text-gray-500">{src.count > 0 ? formatCurrency(src.revenue / src.count) : '-'}</td>
              </tr>)}</tbody>
          </table></div>
        </CardContent>
      </Card>}
  </div>;
export const SourcesSection = ({
  sourceData
}) => <div className="space-y-6" data-testid="section-sources">
    <SectionHeader title="Kaynak Analizi" description="Rezervasyon kaynaklarının detaylı performans karşılaştırması" />
    {sourceData.length > 0 ? <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {sourceData.slice(0, 4).map((src, i) => <Card key={src.id || i} className="border-l-4" style={{
        borderLeftColor: COLORS[i % COLORS.length]
      }}>
              <CardContent className="p-4">
                <p className="text-xs text-gray-500 font-medium">{src.name}</p>
                <p className="text-xl font-bold text-gray-900 mt-1">{src.count} rez.</p>
                <p className="text-sm text-gray-600 mt-0.5">{formatCurrency(src.revenue)}</p>
              </CardContent>
            </Card>)}
        </div>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Kaynak Karşılaştırması</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sourceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{
              fontSize: 10
            }} />
                <YAxis tick={{
              fontSize: 10
            }} />
                <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{
              fontSize: 11
            }} />
                <Bar dataKey="count" name="Rezervasyon" fill="#0284C7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </> : <Card><CardContent className="py-12"><EmptyState icon={BarChart3} message="Kaynak verisi yok" /></CardContent></Card>}
  </div>;