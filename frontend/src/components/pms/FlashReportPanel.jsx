import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  BarChart3, TrendingUp, Users, BedDouble, DollarSign,
  LogIn, LogOut, AlertTriangle, Clock, RefreshCw, Printer,
  Utensils, Droplets, ShoppingBag, Coffee
} from 'lucide-react';

const FlashReportPanel = ({ rooms, bookings, arrivals, departures, inhouse }) => {
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadFlashReport = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/reports/flash-report');
      setReportData(res.data);
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
        revenue: { total: totalRevenue, room: totalRevenue * 0.7, fb: totalRevenue * 0.2, other: totalRevenue * 0.1, collected: paidRevenue, outstanding: totalRevenue - paidRevenue },
        kpi: { adr, revpar, avg_los: 2.3 },
        operations: {
          arrivals: arrivals?.length || 0,
          departures: departures?.length || 0,
          inhouse: inhouse?.length || 0,
          no_shows: bookings?.filter(b => b.status === 'no_show').length || 0,
          overstays: 0,
          walk_ins: bookings?.filter(b => b.channel === 'walk_in').length || 0,
          cancellations: bookings?.filter(b => b.status === 'cancelled').length || 0,
        },
        departments: [
          { name: 'Oda Geliri', amount: totalRevenue * 0.7, icon: 'bed' },
          { name: 'Yiyecek & Icecek', amount: totalRevenue * 0.15, icon: 'food' },
          { name: 'Spa & Wellness', amount: totalRevenue * 0.08, icon: 'spa' },
          { name: 'Minibar', amount: totalRevenue * 0.04, icon: 'minibar' },
          { name: 'Camasirhane', amount: totalRevenue * 0.02, icon: 'laundry' },
          { name: 'Diger', amount: totalRevenue * 0.01, icon: 'other' },
        ]
      });
    }
    setLoading(false);
  }, [rooms, bookings, arrivals, departures, inhouse]);

  useEffect(() => { loadFlashReport(); }, [loadFlashReport]);

  const printReport = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow || !reportData) return;
    const d = reportData;
    printWindow.document.write(`
      <html><head><title>Gunluk Flash Rapor - ${d.date}</title>
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
      <h1>GUNLUK FLASH RAPOR</h1>
      <p>Tarih: ${d.date} | Otel: Syroce Hotel | Hazirlayan: ${new Date().toLocaleTimeString('tr-TR')}</p>
      <div class="grid">
        <div class="card"><div class="label">Doluluk</div><div class="value">${d.occupancy?.rate?.toFixed(1)}%</div><div>${d.occupancy?.occupied}/${d.occupancy?.total} oda</div></div>
        <div class="card"><div class="label">ADR</div><div class="value">${d.kpi?.adr?.toFixed(2)} TL</div></div>
        <div class="card"><div class="label">RevPAR</div><div class="value">${d.kpi?.revpar?.toFixed(2)} TL</div></div>
        <div class="card"><div class="label">Toplam Gelir</div><div class="value">${d.revenue?.total?.toFixed(2)} TL</div></div>
      </div>
      <h3>Operasyonel Durum</h3>
      <div class="grid">
        <div class="card"><div class="label">Girisler</div><div class="value">${d.operations?.arrivals}</div></div>
        <div class="card"><div class="label">Cikislar</div><div class="value">${d.operations?.departures}</div></div>
        <div class="card"><div class="label">In-House</div><div class="value">${d.operations?.inhouse}</div></div>
        <div class="card"><div class="label">No-Show</div><div class="value">${d.operations?.no_shows}</div></div>
      </div>
      <h3>Departman Bazli Gelir</h3>
      <table><thead><tr><th>Departman</th><th style="text-align:right">Tutar (TL)</th><th style="text-align:right">Oran</th></tr></thead>
      <tbody>${d.departments?.map(dep => `<tr><td>${dep.name}</td><td style="text-align:right">${dep.amount?.toFixed(2)}</td><td style="text-align:right">${d.revenue?.total > 0 ? (dep.amount / d.revenue.total * 100).toFixed(1) : 0}%</td></tr>`).join('')}</tbody></table>
      <h3>Tahsilat Durumu</h3>
      <table><tr><td>Toplam Gelir</td><td style="text-align:right">${d.revenue?.total?.toFixed(2)} TL</td></tr>
      <tr><td>Tahsil Edilen</td><td style="text-align:right">${d.revenue?.collected?.toFixed(2)} TL</td></tr>
      <tr style="color:red"><td>Acik Bakiye</td><td style="text-align:right">${d.revenue?.outstanding?.toFixed(2)} TL</td></tr></table>
      <p style="margin-top:20px;font-size:10px;color:#999">Bu rapor ${new Date().toLocaleString('tr-TR')} tarihinde otomatik olusturulmustur.</p>
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

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <BarChart3 className="w-6 h-6" /> Gunluk Flash Rapor
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={printReport}>
            <Printer className="w-4 h-4 mr-2" /> Yazdir
          </Button>
          <Button variant="outline" onClick={loadFlashReport}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>
      </div>

      {d && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-4 text-center">
                <BedDouble className="w-6 h-6 mx-auto mb-1 text-blue-600" />
                <p className="text-xs text-blue-600">Doluluk Orani</p>
                <p className="text-2xl font-bold text-blue-700">{d.occupancy?.rate?.toFixed(1)}%</p>
                <p className="text-xs text-blue-500">{d.occupancy?.occupied}/{d.occupancy?.total} oda</p>
              </CardContent>
            </Card>
            <Card className="bg-emerald-50 border-emerald-200">
              <CardContent className="p-4 text-center">
                <DollarSign className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
                <p className="text-xs text-emerald-600">ADR</p>
                <p className="text-2xl font-bold text-emerald-700">{d.kpi?.adr?.toFixed(2)}</p>
                <p className="text-xs text-emerald-500">TL / Oda</p>
              </CardContent>
            </Card>
            <Card className="bg-purple-50 border-purple-200">
              <CardContent className="p-4 text-center">
                <TrendingUp className="w-6 h-6 mx-auto mb-1 text-purple-600" />
                <p className="text-xs text-purple-600">RevPAR</p>
                <p className="text-2xl font-bold text-purple-700">{d.kpi?.revpar?.toFixed(2)}</p>
                <p className="text-xs text-purple-500">TL / Mevcut Oda</p>
              </CardContent>
            </Card>
            <Card className="bg-amber-50 border-amber-200">
              <CardContent className="p-4 text-center">
                <DollarSign className="w-6 h-6 mx-auto mb-1 text-amber-600" />
                <p className="text-xs text-amber-600">Toplam Gelir</p>
                <p className="text-2xl font-bold text-amber-700">{d.revenue?.total?.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</p>
                <p className="text-xs text-amber-500">TL</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {[
              { label: 'Girisler', value: d.operations?.arrivals, icon: LogIn, color: 'emerald' },
              { label: 'Cikislar', value: d.operations?.departures, icon: LogOut, color: 'blue' },
              { label: 'In-House', value: d.operations?.inhouse, icon: Users, color: 'purple' },
              { label: 'No-Show', value: d.operations?.no_shows, icon: AlertTriangle, color: 'red' },
              { label: 'Walk-In', value: d.operations?.walk_ins, icon: Users, color: 'teal' },
              { label: 'Iptal', value: d.operations?.cancellations, icon: AlertTriangle, color: 'orange' },
              { label: 'Overstay', value: d.operations?.overstays, icon: Clock, color: 'yellow' },
            ].map((item, i) => (
              <Card key={i} className={`bg-${item.color}-50 border-${item.color}-200`}>
                <CardContent className="p-3 text-center">
                  <item.icon className={`w-4 h-4 mx-auto mb-1 text-${item.color}-600`} />
                  <p className={`text-[10px] text-${item.color}-600`}>{item.label}</p>
                  <p className={`text-xl font-bold text-${item.color}-700`}>{item.value || 0}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <DollarSign className="w-4 h-4" /> Departman Bazli Gelir
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {d.departments?.map((dep, i) => {
                    const pct = d.revenue?.total > 0 ? (dep.amount / d.revenue.total * 100) : 0;
                    return (
                      <div key={i} className="flex items-center gap-3">
                        <span className="text-xs text-gray-600 w-32">{dep.name}</span>
                        <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                          <div className="bg-blue-500 h-full rounded-full transition-all" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs font-medium text-gray-700 w-24 text-right">{dep.amount?.toFixed(2)} TL</span>
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
                    <span className="text-lg font-bold">{d.revenue?.total?.toFixed(2)} TL</span>
                  </div>
                  <div className="flex justify-between items-center p-3 bg-emerald-50 rounded">
                    <span className="text-sm text-emerald-600">Tahsil Edilen</span>
                    <span className="text-lg font-bold text-emerald-700">{d.revenue?.collected?.toFixed(2)} TL</span>
                  </div>
                  <div className="flex justify-between items-center p-3 bg-red-50 rounded">
                    <span className="text-sm text-red-600">Acik Bakiye</span>
                    <span className="text-lg font-bold text-red-700">{d.revenue?.outstanding?.toFixed(2)} TL</span>
                  </div>
                  {d.revenue?.total > 0 && (
                    <div className="bg-gray-100 rounded-full h-3 overflow-hidden">
                      <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${(d.revenue.collected / d.revenue.total * 100)}%` }} />
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default FlashReportPanel;
