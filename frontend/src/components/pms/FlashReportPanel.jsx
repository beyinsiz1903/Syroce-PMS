import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  BarChart3, TrendingUp, BedDouble, DollarSign,
  LogIn, LogOut, AlertTriangle, Clock, RefreshCw, Printer,
  Users, UserX, UserPlus, XCircle
} from 'lucide-react';
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip
} from 'recharts';

const fmt = (v) => (v || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const PIE_COLORS = ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444', '#6366f1'];

const FlashReportPanel = ({ rooms, bookings, arrivals, departures, inhouse }) => {
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const loadFlashReport = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await axios.get('/reports/flash-report');
      if (res.data && res.data.occupancy) {
        setReportData(res.data);
      } else {
        throw new Error('empty');
      }
    } catch {
      const totalRooms = rooms?.length || 0;
      const occupiedRooms = rooms?.filter(r => r.status === 'occupied').length || 0;
      const occRate = totalRooms > 0 ? (occupiedRooms / totalRooms * 100) : 0;
      const totalRevenue = bookings?.reduce((s, b) => s + (b.total_amount || 0), 0) || 0;
      const paidRevenue = bookings?.reduce((s, b) => s + (b.paid_amount || 0), 0) || 0;
      const adr = occupiedRooms > 0 ? totalRevenue / occupiedRooms : 0;
      const revpar = totalRooms > 0 ? totalRevenue / totalRooms : 0;

      setReportData({
        date: new Date().toISOString().split('T')[0],
        occupancy: { rate: occRate, occupied: occupiedRooms, total: totalRooms, available: totalRooms - occupiedRooms },
        revenue: { total: totalRevenue, room: totalRevenue, fb: 0, spa: 0, minibar: 0, laundry: 0, other: 0, collected: paidRevenue, outstanding: totalRevenue - paidRevenue },
        kpi: { adr, revpar },
        operations: {
          arrivals: arrivals?.length || 0,
          departures: departures?.length || 0,
          inhouse: inhouse?.length || 0,
          no_shows: bookings?.filter(b => b.status === 'no_show').length || 0,
          walk_ins: bookings?.filter(b => b.channel === 'walk_in').length || 0,
          cancellations: bookings?.filter(b => b.status === 'cancelled').length || 0,
          overstays: 0,
        },
        departments: [
          { name: 'Oda Geliri', amount: totalRevenue },
          { name: 'Yiyecek & İçecek', amount: 0 },
          { name: 'Spa & Wellness', amount: 0 },
          { name: 'Minibar', amount: 0 },
          { name: 'Çamaşırhane', amount: 0 },
          { name: 'Diğer', amount: 0 },
        ],
        _fallback: true,
      });
      setError(true);
    }
    setLoading(false);
  }, [rooms, bookings, arrivals, departures, inhouse]);

  useEffect(() => { loadFlashReport(); }, [loadFlashReport]);

  const printReport = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow || !reportData) return;
    const d = reportData;
    printWindow.document.write(`
      <html><head><title>Günlük Flash Rapor - ${d.date}</title>
      <style>body{font-family:Arial,sans-serif;padding:20px;font-size:12px}
      h1{font-size:18px;border-bottom:2px solid #333;padding-bottom:8px}
      .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
      .card{border:1px solid #ddd;border-radius:6px;padding:12px}
      .card .label{color:#666;font-size:10px;text-transform:uppercase}
      .card .value{font-size:20px;font-weight:bold;margin-top:4px}
      table{width:100%;border-collapse:collapse;margin-top:12px}
      th,td{border:1px solid #ddd;padding:6px 8px;text-align:left}
      th{background:#f5f5f5;font-size:11px}
      @media print{body{padding:0}}</style></head><body>
      <h1>GÜNLÜK FLASH RAPOR</h1>
      <p>Tarih: ${d.date} | Otel: Syroce Hotel | Hazırlayan: ${new Date().toLocaleTimeString('tr-TR')}</p>
      <div class="grid">
        <div class="card"><div class="label">Doluluk</div><div class="value">${d.occupancy?.rate?.toFixed(1)}%</div><div>${d.occupancy?.occupied}/${d.occupancy?.total} oda</div></div>
        <div class="card"><div class="label">ADR</div><div class="value">${fmt(d.kpi?.adr)} TL</div></div>
        <div class="card"><div class="label">RevPAR</div><div class="value">${fmt(d.kpi?.revpar)} TL</div></div>
        <div class="card"><div class="label">Toplam Gelir</div><div class="value">${fmt(d.revenue?.total)} TL</div></div>
      </div>
      <h3>Operasyonel Durum</h3>
      <div class="grid">
        <div class="card"><div class="label">Girişler</div><div class="value">${d.operations?.arrivals}</div></div>
        <div class="card"><div class="label">Çıkışlar</div><div class="value">${d.operations?.departures}</div></div>
        <div class="card"><div class="label">In-House</div><div class="value">${d.operations?.inhouse}</div></div>
        <div class="card"><div class="label">No-Show</div><div class="value">${d.operations?.no_shows}</div></div>
      </div>
      <h3>Departman Bazlı Gelir</h3>
      <table><thead><tr><th>Departman</th><th style="text-align:right">Tutar (TL)</th><th style="text-align:right">Oran</th></tr></thead>
      <tbody>${d.departments?.map(dep => `<tr><td>${dep.name}</td><td style="text-align:right">${fmt(dep.amount)}</td><td style="text-align:right">${d.revenue?.total > 0 ? (dep.amount / d.revenue.total * 100).toFixed(1) : 0}%</td></tr>`).join('')}</tbody></table>
      <h3>Tahsilat Durumu</h3>
      <table><tr><td>Toplam Gelir</td><td style="text-align:right">${fmt(d.revenue?.total)} TL</td></tr>
      <tr><td>Tahsil Edilen</td><td style="text-align:right">${fmt(d.revenue?.collected)} TL</td></tr>
      <tr style="color:red"><td>Açık Bakiye</td><td style="text-align:right">${fmt(d.revenue?.outstanding)} TL</td></tr></table>
      <p style="margin-top:20px;font-size:10px;color:#999">Bu rapor ${new Date().toLocaleString('tr-TR')} tarihinde otomatik oluşturulmuştur.</p>
      </body></html>
    `);
    printWindow.document.close();
    printWindow.print();
  };

  if (loading) return (
    <div className="flex items-center justify-center py-12">
      <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
    </div>
  );

  const d = reportData;

  const pieData = d?.departments?.filter(dep => dep.amount > 0).map(dep => ({
    name: dep.name, value: dep.amount
  })) || [];

  const collectionPct = d?.revenue?.total > 0
    ? Math.min(Math.round(d.revenue.collected / d.revenue.total * 100), 100)
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <BarChart3 className="w-6 h-6" /> Günlük Flash Rapor
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={printReport}>
            <Printer className="w-4 h-4 mr-2" /> Yazdır
          </Button>
          <Button variant="outline" onClick={loadFlashReport}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          Rapor sunucudan yüklenemedi. Gösterilen veriler mevcut oda ve rezervasyon bilgilerinden hesaplandı.
        </div>
      )}

      {d && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-4 text-center">
                <BedDouble className="w-6 h-6 mx-auto mb-1 text-blue-600" />
                <p className="text-xs text-blue-600">Doluluk Oranı</p>
                <p className="text-2xl font-bold text-blue-700">{d.occupancy?.rate?.toFixed(1)}%</p>
                <p className="text-xs text-blue-500">{d.occupancy?.occupied}/{d.occupancy?.total} oda</p>
              </CardContent>
            </Card>
            <Card className="bg-emerald-50 border-emerald-200">
              <CardContent className="p-4 text-center">
                <DollarSign className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
                <p className="text-xs text-emerald-600">ADR</p>
                <p className="text-2xl font-bold text-emerald-700">{fmt(d.kpi?.adr)}</p>
                <p className="text-xs text-emerald-500">₺ / Oda</p>
              </CardContent>
            </Card>
            <Card className="bg-purple-50 border-purple-200">
              <CardContent className="p-4 text-center">
                <TrendingUp className="w-6 h-6 mx-auto mb-1 text-purple-600" />
                <p className="text-xs text-purple-600">RevPAR</p>
                <p className="text-2xl font-bold text-purple-700">{fmt(d.kpi?.revpar)}</p>
                <p className="text-xs text-purple-500">₺ / Mevcut Oda</p>
              </CardContent>
            </Card>
            <Card className="bg-amber-50 border-amber-200">
              <CardContent className="p-4 text-center">
                <DollarSign className="w-6 h-6 mx-auto mb-1 text-amber-600" />
                <p className="text-xs text-amber-600">Toplam Gelir</p>
                <p className="text-2xl font-bold text-amber-700">{fmt(d.revenue?.total)}</p>
                <p className="text-xs text-amber-500">₺</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <Card className="bg-emerald-50 border-emerald-200">
              <CardContent className="p-3 text-center">
                <LogIn className="w-4 h-4 mx-auto mb-1 text-emerald-600" />
                <p className="text-[10px] text-emerald-600">Girişler</p>
                <p className="text-xl font-bold text-emerald-700">{d.operations?.arrivals || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-3 text-center">
                <LogOut className="w-4 h-4 mx-auto mb-1 text-blue-600" />
                <p className="text-[10px] text-blue-600">Çıkışlar</p>
                <p className="text-xl font-bold text-blue-700">{d.operations?.departures || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-purple-50 border-purple-200">
              <CardContent className="p-3 text-center">
                <Users className="w-4 h-4 mx-auto mb-1 text-purple-600" />
                <p className="text-[10px] text-purple-600">In-House</p>
                <p className="text-xl font-bold text-purple-700">{d.operations?.inhouse || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-red-50 border-red-200">
              <CardContent className="p-3 text-center">
                <AlertTriangle className="w-4 h-4 mx-auto mb-1 text-red-600" />
                <p className="text-[10px] text-red-600">No-Show</p>
                <p className="text-xl font-bold text-red-700">{d.operations?.no_shows || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-teal-50 border-teal-200">
              <CardContent className="p-3 text-center">
                <UserPlus className="w-4 h-4 mx-auto mb-1 text-teal-600" />
                <p className="text-[10px] text-teal-600">Walk-In</p>
                <p className="text-xl font-bold text-teal-700">{d.operations?.walk_ins || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-orange-50 border-orange-200">
              <CardContent className="p-3 text-center">
                <XCircle className="w-4 h-4 mx-auto mb-1 text-orange-600" />
                <p className="text-[10px] text-orange-600">İptal</p>
                <p className="text-xl font-bold text-orange-700">{d.operations?.cancellations || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-yellow-50 border-yellow-200">
              <CardContent className="p-3 text-center">
                <Clock className="w-4 h-4 mx-auto mb-1 text-yellow-600" />
                <p className="text-[10px] text-yellow-600">Overstay</p>
                <p className="text-xl font-bold text-yellow-700">{d.operations?.overstays || 0}</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <DollarSign className="w-4 h-4" /> Departman Bazlı Gelir
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {d.departments?.map((dep, i) => {
                    const pct = d.revenue?.total > 0 ? (dep.amount / d.revenue.total * 100) : 0;
                    return (
                      <div key={i} className="flex items-center gap-3">
                        <span className="text-xs text-gray-600 w-32 truncate">{dep.name}</span>
                        <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: `${Math.min(Math.max(pct, 0), 100)}%`, backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                          />
                        </div>
                        <span className="text-xs font-medium text-gray-700 w-28 text-right">{fmt(dep.amount)} ₺</span>
                        <span className="text-xs text-gray-400 w-12 text-right">{pct.toFixed(1)}%</span>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <DollarSign className="w-4 h-4" /> Tahsilat Durumu
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
                    <span className="text-sm text-gray-600">Toplam Gelir</span>
                    <span className="text-lg font-bold">{fmt(d.revenue?.total)} ₺</span>
                  </div>
                  <div className="flex justify-between items-center p-3 bg-emerald-50 rounded">
                    <span className="text-sm text-emerald-600">Tahsil Edilen</span>
                    <span className="text-lg font-bold text-emerald-700">{fmt(d.revenue?.collected)} ₺</span>
                  </div>
                  <div className="flex justify-between items-center p-3 bg-red-50 rounded">
                    <span className="text-sm text-red-600">Açık Bakiye</span>
                    <span className="text-lg font-bold text-red-700">{fmt(d.revenue?.outstanding)} ₺</span>
                  </div>
                  {d.revenue?.total > 0 && (
                    <div>
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Tahsilat Oranı</span>
                        <span>%{collectionPct}</span>
                      </div>
                      <div className="bg-gray-100 rounded-full h-3 overflow-hidden">
                        <div className="bg-emerald-500 h-full rounded-full transition-all" style={{ width: `${collectionPct}%` }} />
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {pieData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" /> Gelir Dağılımı
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center">
                  <div className="w-1/2" style={{ height: 220 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={85}
                          dataKey="value"
                          paddingAngle={2}
                        >
                          {pieData.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => `${fmt(v)} ₺`} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="w-1/2 space-y-2 pl-4">
                    {pieData.map((item, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="text-xs text-gray-600 flex-1">{item.name}</span>
                        <span className="text-xs font-medium">{fmt(item.value)} ₺</span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="text-xs text-gray-400 text-center">
            Rapor tarihi: {d.date} | Son güncelleme: {new Date().toLocaleString('tr-TR')}
          </div>
        </>
      )}
    </div>
  );
};

export default FlashReportPanel;
