import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TrendingUp, BedDouble, DollarSign, LogIn, LogOut, AlertTriangle, RefreshCw, Printer, Users, UserX, UserPlus, XCircle, Sparkles } from 'lucide-react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import { useCurrency } from '@/context/CurrencyContext';
import { useTranslation } from 'react-i18next';
const PIE_COLORS = ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444', '#6366f1'];
const FlashReportContent = ({
  showDatePicker = false,
  rooms,
  bookings,
  arrivals,
  departures,
  inhouse
}) => {
  const {
    t
  } = useTranslation();
  const {
    format: fmtMoney,
    symbol: currencySymbol,
    code: currencyCode
  } = useCurrency();
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [usingFallback, setUsingFallback] = useState(false);
  const [error, setError] = useState(null);

  // Props'lardan client-side fallback üretebilir miyiz? (PMSModule sekmesi → evet, standalone → hayır)
  const hasFallbackData = Array.isArray(rooms) || Array.isArray(bookings) || Array.isArray(arrivals) || Array.isArray(departures) || Array.isArray(inhouse);
  const loadFlashReport = useCallback(async () => {
    setLoading(true);
    setUsingFallback(false);
    setError(null);
    const effectiveDate = showDatePicker ? selectedDate : new Date().toISOString().split('T')[0];
    try {
      const url = showDatePicker ? `/reports/flash-report?date=${selectedDate}` : '/reports/flash-report';
      const res = await axios.get(url);
      if (res.data && res.data.occupancy) {
        setReportData(res.data);
      } else {
        throw new Error('empty');
      }
    } catch (err) {
      if (!hasFallbackData) {
        // Standalone: yanıltıcı 0'lı rapor üretmek yerine açık hata göster
        setReportData(null);
        setError(err?.response?.data?.detail || err?.message || 'Sunucuya ulaşılamadı');
        return;
      }
      // PMS sekmesi: gerçek prop'lardan offline fallback
      const totalRooms = rooms?.length || 0;
      const occupiedRooms = rooms?.filter(r => r.status === 'occupied').length || 0;
      const occRate = totalRooms > 0 ? occupiedRooms / totalRooms * 100 : 0;
      const totalRevenue = bookings?.reduce((s, b) => s + (b.total_amount || 0), 0) || 0;
      const paidRevenue = bookings?.reduce((s, b) => s + (b.paid_amount || 0), 0) || 0;
      const adr = occupiedRooms > 0 ? totalRevenue / occupiedRooms : 0;
      const revpar = totalRooms > 0 ? totalRevenue / totalRooms : 0;
      setReportData({
        date: effectiveDate,
        occupancy: {
          rate: occRate,
          occupied: occupiedRooms,
          total: totalRooms,
          available: totalRooms - occupiedRooms
        },
        revenue: {
          total: totalRevenue,
          room: totalRevenue,
          fb: 0,
          spa: 0,
          minibar: 0,
          laundry: 0,
          other: 0,
          collected: paidRevenue,
          outstanding: totalRevenue - paidRevenue
        },
        kpi: {
          adr,
          revpar
        },
        operations: {
          arrivals: arrivals?.length || 0,
          departures: departures?.length || 0,
          inhouse: inhouse?.length || 0,
          no_shows: bookings?.filter(b => b.status === 'no_show').length || 0,
          walk_ins: bookings?.filter(b => b.channel === 'walk_in').length || 0,
          cancellations: bookings?.filter(b => b.status === 'cancelled').length || 0,
          overstays: 0
        },
        departments: [{
          name: 'Oda Geliri',
          amount: totalRevenue
        }, {
          name: 'Yiyecek & İçecek',
          amount: 0
        }, {
          name: 'Spa & Wellness',
          amount: 0
        }, {
          name: 'Minibar',
          amount: 0
        }, {
          name: 'Çamaşırhane',
          amount: 0
        }, {
          name: 'Diğer',
          amount: 0
        }]
      });
      setUsingFallback(true);
    } finally {
      setLoading(false);
    }
  }, [showDatePicker, selectedDate, rooms, bookings, arrivals, departures, inhouse, hasFallbackData]);
  useEffect(() => {
    loadFlashReport();
  }, [loadFlashReport]);
  const printReport = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow || !reportData) return;
    const d = reportData;
    const totalRev = d.revenue?.total || 0;
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
      <p>Tarih: ${d.date} | Hazırlayan: ${new Date().toLocaleTimeString('tr-TR')}</p>
      <div class="grid">
        <div class="card"><div class="label">Doluluk</div><div class="value">${(d.occupancy?.rate || 0).toFixed(1)}%</div><div>${d.occupancy?.occupied || 0}/${d.occupancy?.total || 0} oda</div></div>
        <div class="card"><div class="label">ADR</div><div class="value">${fmtMoney(d.kpi?.adr || 0)}</div></div>
        <div class="card"><div class="label">RevPAR</div><div class="value">${fmtMoney(d.kpi?.revpar || 0)}</div></div>
        <div class="card"><div class="label">Toplam Gelir</div><div class="value">${fmtMoney(totalRev)}</div></div>
      </div>
      <h3>Operasyonel Durum</h3>
      <div class="grid">
        <div class="card"><div class="label">Girişler</div><div class="value">${d.operations?.arrivals || 0}</div></div>
        <div class="card"><div class="label">Çıkışlar</div><div class="value">${d.operations?.departures || 0}</div></div>
        <div class="card"><div class="label">In-House</div><div class="value">${d.operations?.inhouse || 0}</div></div>
        <div class="card"><div class="label">No-Show</div><div class="value">${d.operations?.no_shows || 0}</div></div>
      </div>
      <h3>Departman Bazlı Gelir</h3>
      <table><thead><tr><th>Departman</th><th style="text-align:right">Tutar</th><th style="text-align:right">Oran</th></tr></thead>
      <tbody>${(d.departments || []).map(dep => `<tr><td>${dep.name}</td><td style="text-align:right">${fmtMoney(dep.amount || 0)}</td><td style="text-align:right">${totalRev > 0 ? ((dep.amount || 0) / totalRev * 100).toFixed(1) : 0}%</td></tr>`).join('')}</tbody></table>
      <h3>Tahsilat Durumu</h3>
      <table><tr><td>Toplam Gelir</td><td style="text-align:right">${fmtMoney(totalRev)}</td></tr>
      <tr><td>Tahsil Edilen</td><td style="text-align:right">${fmtMoney(d.revenue?.collected || 0)}</td></tr>
      <tr style="color:red"><td>Açık Bakiye</td><td style="text-align:right">${fmtMoney(d.revenue?.outstanding || 0)}</td></tr></table>
      <p style="margin-top:20px;font-size:10px;color:#999">Bu rapor ${new Date().toLocaleString('tr-TR')} tarihinde otomatik oluşturulmuştur.</p>
      </body></html>
    `);
    printWindow.document.close();
    printWindow.print();
  };
  if (loading && !reportData) {
    return <div className="flex items-center justify-center py-12" data-testid="flash-loading">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
      </div>;
  }
  if (error && !reportData) {
    return <Card className="border-red-200 bg-red-50" data-testid="flash-error">
        <CardContent className="p-6 text-center space-y-3">
          <AlertTriangle className="w-10 h-10 mx-auto text-red-500" />
          <div>
            <p className="text-base font-semibold text-red-800">{t('cm.components_pms_FlashReportContent.rapor_yuklenemedi')}</p>
            <p className="text-sm text-red-700 mt-1">{error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={loadFlashReport} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Tekrar Dene
          </Button>
        </CardContent>
      </Card>;
  }
  if (!reportData) {
    return <div className="text-center py-12 text-gray-500 text-sm" data-testid="flash-empty">
        {t('cm.components_pms_FlashReportContent.henuz_veri_yok')}
      </div>;
  }
  const d = reportData;
  const totalRev = d.revenue?.total || 0;
  const trevpar = d.occupancy?.total > 0 ? totalRev / d.occupancy.total : 0;
  const collectionPct = totalRev > 0 ? (d.revenue?.collected || 0) / totalRev * 100 : 0;
  const pieData = (d.departments || []).filter(dep => dep.amount > 0).map(dep => ({
    name: dep.name,
    value: dep.amount
  }));
  return <div className="space-y-4" data-testid="flash-report-content">
      {/* Toolbar: tarih + yazdır + yenile */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-gray-600">
          {t('cm.components_pms_FlashReportContent.tarih')} <span className="font-medium text-gray-900">{d.date}</span>
          {usingFallback && <span className="ml-2 text-xs text-amber-600">{t('cm.components_pms_FlashReportContent.cevrimdisi_veri_anlik_degil')}</span>}
        </div>
        <div className="flex items-center gap-2">
          {showDatePicker && <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} className="px-3 py-1.5 border rounded-lg text-sm" data-testid="flash-date-picker" />}
          <Button variant="outline" size="sm" onClick={loadFlashReport} disabled={loading} data-testid="flash-refresh">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> {t('cm.components_pms_FlashReportContent.yenile')}
          </Button>
          <Button variant="outline" size="sm" onClick={printReport} data-testid="flash-print">
            <Printer className="w-4 h-4 mr-1.5" /> {t('cm.components_pms_FlashReportContent.yazdir')}
          </Button>
        </div>
      </div>

      {/* Ana KPI'lar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-blue-50 border-blue-200" data-testid="flash-kpi-occupancy">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-blue-700 font-medium">{t('cm.components_pms_FlashReportContent.doluluk_orani')}</p>
                <p className="text-2xl font-bold text-blue-900">{(d.occupancy?.rate || 0).toFixed(1)}%</p>
                <p className="text-xs text-blue-600 mt-0.5">{d.occupancy?.occupied || 0}/{d.occupancy?.total || 0} oda</p>
              </div>
              <BedDouble className="w-7 h-7 text-blue-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-emerald-50 border-emerald-200" data-testid="flash-kpi-adr">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-emerald-700 font-medium">ADR</p>
                <p className="text-2xl font-bold text-emerald-900">{fmtMoney(d.kpi?.adr || 0)}</p>
                <p className="text-xs text-emerald-600 mt-0.5">{t('cm.components_pms_FlashReportContent.ort_oda_fiyati')}</p>
              </div>
              <DollarSign className="w-7 h-7 text-emerald-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-indigo-50 border-indigo-200" data-testid="flash-kpi-revpar">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-indigo-700 font-medium">RevPAR</p>
                <p className="text-2xl font-bold text-indigo-900">{fmtMoney(d.kpi?.revpar || 0)}</p>
                <p className="text-xs text-indigo-600 mt-0.5">{t('cm.components_pms_FlashReportContent.mevcut_oda')}</p>
              </div>
              <TrendingUp className="w-7 h-7 text-indigo-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-amber-50 border-amber-200" data-testid="flash-kpi-trevpar">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-amber-700 font-medium">TRevPAR</p>
                <p className="text-2xl font-bold text-amber-900">{fmtMoney(trevpar)}</p>
                <p className="text-xs text-amber-600 mt-0.5">{t('cm.components_pms_FlashReportContent.toplam_mevcut_oda')}</p>
              </div>
              <Sparkles className="w-7 h-7 text-amber-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Operasyonel KPI'lar */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card data-testid="flash-ops-arrivals">
          <CardContent className="p-3 text-center">
            <LogIn className="w-5 h-5 mx-auto text-emerald-500" />
            <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_FlashReportContent.girisler')}</p>
            <p className="text-xl font-bold text-emerald-700">{d.operations?.arrivals || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-departures">
          <CardContent className="p-3 text-center">
            <LogOut className="w-5 h-5 mx-auto text-blue-500" />
            <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_FlashReportContent.cikislar')}</p>
            <p className="text-xl font-bold text-blue-700">{d.operations?.departures || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-inhouse">
          <CardContent className="p-3 text-center">
            <Users className="w-5 h-5 mx-auto text-indigo-500" />
            <p className="text-[11px] text-gray-500 mt-1">In-House</p>
            <p className="text-xl font-bold text-indigo-700">{d.operations?.inhouse || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-noshow">
          <CardContent className="p-3 text-center">
            <UserX className="w-5 h-5 mx-auto text-red-500" />
            <p className="text-[11px] text-gray-500 mt-1">No-Show</p>
            <p className="text-xl font-bold text-red-700">{d.operations?.no_shows || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-walkin">
          <CardContent className="p-3 text-center">
            <UserPlus className="w-5 h-5 mx-auto text-teal-500" />
            <p className="text-[11px] text-gray-500 mt-1">Walk-In</p>
            <p className="text-xl font-bold text-teal-700">{d.operations?.walk_ins || 0}</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-cancel">
          <CardContent className="p-3 text-center">
            <XCircle className="w-5 h-5 mx-auto text-amber-500" />
            <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_FlashReportContent.iptal')}</p>
            <p className="text-xl font-bold text-amber-700">{d.operations?.cancellations || 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Departman gelirleri + Tahsilat durumu */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card data-testid="flash-departments">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-emerald-500" /> {t('cm.components_pms_FlashReportContent.departman_bazli_gelir')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pieData.length > 0 && <div className="h-40 mb-3">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={60} innerRadius={30}>
                      {pieData.map((_, i) => <Cell key={_.id || i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={v => fmtMoney(v)} />
                  </PieChart>
                </ResponsiveContainer>
              </div>}
            <div className="space-y-1.5">
              {(d.departments || []).map((dep, i) => {
              const pct = totalRev > 0 ? (dep.amount || 0) / totalRev * 100 : 0;
              return <div key={dep.id || i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700">{dep.name}</span>
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-gray-900">{fmtMoney(dep.amount || 0)}</span>
                      <span className="text-xs text-gray-500 w-12 text-right">{pct.toFixed(1)}%</span>
                    </div>
                  </div>;
            })}
            </div>
          </CardContent>
        </Card>

        <Card data-testid="flash-collection">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-500" /> Tahsilat Durumu
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">{t('cm.components_pms_FlashReportContent.toplam_gelir')}</span>
              <span className="text-lg font-bold text-gray-900">{fmtMoney(totalRev)}</span>
            </div>
            <div className="flex items-center justify-between bg-emerald-50 px-3 py-2 rounded">
              <span className="text-sm text-emerald-700 font-medium">Tahsil Edilen</span>
              <span className="text-lg font-bold text-emerald-700">{fmtMoney(d.revenue?.collected || 0)}</span>
            </div>
            <div className="flex items-center justify-between bg-red-50 px-3 py-2 rounded">
              <span className="text-sm text-red-700 font-medium">{t('cm.components_pms_FlashReportContent.acik_bakiye')}</span>
              <span className="text-lg font-bold text-red-700">{fmtMoney(d.revenue?.outstanding || 0)}</span>
            </div>
            <div className="pt-2">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span>{t('cm.components_pms_FlashReportContent.tahsilat_orani')}</span>
                <span className="font-medium">{collectionPct.toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-emerald-500 h-2 rounded-full transition-all duration-500" style={{
                width: `${Math.min(100, collectionPct)}%`
              }} />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Dikkat gerektiren durumlar */}
      {((d.operations?.no_shows || 0) > 0 || (d.operations?.cancellations || 0) > 0) && <Card className="border-amber-200 bg-amber-50" data-testid="flash-alerts">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-amber-800 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> Dikkat Gerektiren Durumlar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4 text-sm">
              {(d.operations?.no_shows || 0) > 0 && <div className="flex items-center gap-2 text-amber-700">
                  <XCircle className="w-4 h-4" />
                  <span className="font-semibold">{d.operations.no_shows} No-show</span>
                </div>}
              {(d.operations?.cancellations || 0) > 0 && <div className="flex items-center gap-2 text-amber-700">
                  <XCircle className="w-4 h-4" />
                  <span className="font-semibold">{d.operations.cancellations} {t('cm.components_pms_FlashReportContent.iptal_25174')}</span>
                </div>}
            </div>
          </CardContent>
        </Card>}

      <div className="text-[11px] text-gray-400 text-right">
        Para birimi: {currencyCode} ({currencySymbol})
      </div>
    </div>;
};
export default FlashReportContent;