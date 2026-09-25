import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TrendingUp, BedDouble, DollarSign, LogIn, LogOut, AlertTriangle, RefreshCw, Printer, Users, UserX, UserPlus, XCircle, Sparkles, X } from 'lucide-react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import { useCurrency } from '@/context/CurrencyContext';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
const PIE_COLORS = ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444', '#6366f1'];

const dateKey = value => value ? String(value).slice(0, 10) : '';
const localDateKey = (value = new Date()) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};
const bookingArrival = booking => dateKey(booking.check_in || booking.arrival_date || booking.start_date);
const bookingDeparture = booking => dateKey(booking.check_out || booking.departure_date || booking.end_date);
const bookingStatus = booking => String(booking.status || '').toLowerCase();
const nonCommercialStatuses = new Set(['cancelled', 'canceled', 'no_show', 'noshow']);
const fnbCategories = new Set(['fnb', 'food_beverage', 'food', 'beverage', 'restaurant', 'bar', 'room_service']);

const bookingNights = booking => {
  const arrival = new Date(`${bookingArrival(booking)}T12:00:00`);
  const departure = new Date(`${bookingDeparture(booking)}T12:00:00`);
  const nights = Math.round((departure - arrival) / 86400000);
  return Number.isFinite(nights) && nights > 0 ? nights : 1;
};

const activeOnDate = (booking, targetDate) => (
  bookingArrival(booking) <= targetDate
  && bookingDeparture(booking) > targetDate
  && !nonCommercialStatuses.has(bookingStatus(booking))
);

export const buildFallbackFlashReport = ({ targetDate, rooms = [], bookings = [], arrivals = [], departures = [], inhouse = [] }) => {
  const activeBookings = bookings.filter(booking => activeOnDate(booking, targetDate));
  const occupiedIdentifiers = new Set(activeBookings.map(booking => booking.room_id || booking.room_number || booking.room_no).filter(Boolean));
  const occupiedRooms = occupiedIdentifiers.size || activeBookings.length || inhouse.filter(booking => activeOnDate(booking, targetDate)).length;
  const totalRooms = rooms.length;
  const roomRevenue = activeBookings.reduce((sum, booking) => {
    const stayTotal = Number(booking.accommodation_total ?? booking.room_total ?? booking.total_amount ?? booking.total_price ?? 0) || 0;
    return sum + stayTotal / bookingNights(booking);
  }, 0);
  const collected = activeBookings.reduce((sum, booking) => (
    sum + (Number(booking.paid_amount ?? booking.total_paid ?? 0) || 0) / bookingNights(booking)
  ), 0);
  const categoryRevenue = { fb: 0, spa: 0, minibar: 0, laundry: 0, other: 0 };
  activeBookings.forEach(booking => {
    (booking.charges || booking.folio_charges || []).forEach(charge => {
      if (charge.voided) return;
      const chargeDate = dateKey(charge.business_date || charge.date || charge.created_at);
      if (chargeDate && chargeDate !== targetDate) return;
      const category = String(charge.charge_category || charge.charge_type || 'other').toLowerCase();
      const amount = Number(charge.total ?? charge.amount ?? 0) || 0;
      if (fnbCategories.has(category)) categoryRevenue.fb += amount;
      else if (category === 'spa') categoryRevenue.spa += amount;
      else if (category === 'minibar') categoryRevenue.minibar += amount;
      else if (category === 'laundry') categoryRevenue.laundry += amount;
      else if (!['room', 'accommodation', 'room_charge'].includes(category)) categoryRevenue.other += amount;
    });
  });
  const ancillaryRevenue = Object.values(categoryRevenue).reduce((sum, amount) => sum + amount, 0);
  const totalRevenue = roomRevenue + ancillaryRevenue;
  const datedArrivals = bookings.filter(booking => bookingArrival(booking) === targetDate && !nonCommercialStatuses.has(bookingStatus(booking))).length;
  const datedDepartures = bookings.filter(booking => bookingDeparture(booking) === targetDate && !nonCommercialStatuses.has(bookingStatus(booking))).length;
  const fallbackArrivals = datedArrivals || arrivals.filter(booking => bookingArrival(booking) === targetDate).length;
  const fallbackDepartures = datedDepartures || departures.filter(booking => bookingDeparture(booking) === targetDate).length;
  const fallbackInhouse = inhouse.filter(booking => activeOnDate(booking, targetDate)).length;
  const noShowBookings = bookings.filter(booking => ['no_show', 'noshow'].includes(bookingStatus(booking)) && bookingArrival(booking) === targetDate);
  const cancelledBookings = bookings.filter(booking => ['cancelled', 'canceled'].includes(bookingStatus(booking)) && dateKey(booking.cancelled_at || booking.canceled_at || booking.updated_at) === targetDate);

  return {
    date: targetDate,
    occupancy: {
      rate: totalRooms > 0 ? occupiedRooms / totalRooms * 100 : 0,
      occupied: occupiedRooms,
      total: totalRooms,
      available: Math.max(0, totalRooms - occupiedRooms),
    },
    revenue: {
      total: totalRevenue,
      room: roomRevenue,
      ...categoryRevenue,
      collected,
      outstanding: totalRevenue - collected,
    },
    kpi: {
      adr: occupiedRooms > 0 ? roomRevenue / occupiedRooms : 0,
      revpar: totalRooms > 0 ? roomRevenue / totalRooms : 0,
    },
    operations: {
      arrivals: fallbackArrivals,
      departures: fallbackDepartures,
      inhouse: activeBookings.length || fallbackInhouse,
      no_shows: noShowBookings.length,
      walk_ins: bookings.filter(booking => bookingArrival(booking) === targetDate && ['walk_in', 'walkin'].includes(String(booking.channel || booking.booking_source || '').toLowerCase())).length,
      cancellations: cancelledBookings.length,
      overstays: 0,
    },
    attention_details: {
      cancellations: cancelledBookings,
      no_shows: noShowBookings,
    },
    scope: {
      business_date: targetDate,
      occupancy: 'Seçili iş gecesinde dolu ve satılabilir odalar',
      revenue: 'Seçili iş gününe dağıtılan konaklama ve ek gelirler',
      collections: 'Seçili iş gününe dağıtılan tahsilatlar',
      operations: 'Seçili iş günündeki giriş, çıkış ve durum hareketleri',
    },
    departments: [
      { name: 'Oda Geliri', amount: roomRevenue },
      { name: 'Yiyecek & İçecek', amount: categoryRevenue.fb },
      { name: 'Spa & Wellness', amount: categoryRevenue.spa },
      { name: 'Minibar', amount: categoryRevenue.minibar },
      { name: 'Çamaşırhane', amount: categoryRevenue.laundry },
      { name: 'Diğer', amount: categoryRevenue.other },
    ],
  };
};

const FlashReportContent = ({
  showDatePicker = false,
  isEmbedded = false,
  targetDate = null,
  businessDate = null,
  rooms,
  bookings,
  arrivals,
  departures,
  inhouse
}) => {
  const navigate = useNavigate();
  const {
    t
  } = useTranslation();
  const {
    format: fmtMoney,
    symbol: currencySymbol,
    code: currencyCode
  } = useCurrency();
  const [selectedDate, setSelectedDate] = useState(targetDate || businessDate || localDateKey());
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [usingFallback, setUsingFallback] = useState(false);
  const [error, setError] = useState(null);
  const [showBreakdownModal, setShowBreakdownModal] = useState(false);

  // Props'lardan client-side fallback üretebilir miyiz? (PMSModule sekmesi → evet, standalone → hayır)
  const hasFallbackData = Array.isArray(rooms) || Array.isArray(bookings) || Array.isArray(arrivals) || Array.isArray(departures) || Array.isArray(inhouse);
  const loadFlashReport = useCallback(async () => {
    setLoading(true);
    setUsingFallback(false);
    setError(null);
    const effectiveDate = targetDate || (showDatePicker ? selectedDate : businessDate) || localDateKey();
    try {
      const url = targetDate || showDatePicker ? `/reports/flash-report?date=${targetDate || selectedDate}` : '/reports/flash-report';
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
      setReportData(buildFallbackFlashReport({
        targetDate: effectiveDate,
        rooms,
        bookings,
        arrivals,
        departures,
        inhouse,
      }));
      setUsingFallback(true);
    } finally {
      setLoading(false);
    }
  }, [showDatePicker, selectedDate, targetDate, businessDate, rooms, bookings, arrivals, departures, inhouse, hasFallbackData]);
  useEffect(() => {
    loadFlashReport();
  }, [loadFlashReport]);
  const printReport = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow || !reportData) return;
    const d = reportData;
    const totalRev = d.revenue?.total || 0;
    const collected = Number(d.revenue?.collected || 0);
    const openBalance = Math.max(0, totalRev - collected);
    const advance = Math.max(0, collected - totalRev);
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
      <tr><td>Tahsil Edilen</td><td style="text-align:right">${fmtMoney(collected)}</td></tr>
      ${openBalance > 0 ? `<tr style="color:red"><td>Açık Bakiye</td><td style="text-align:right">${fmtMoney(openBalance)}</td></tr>` : ''}
      ${advance > 0 ? `<tr style="color:#1d4ed8"><td>Avans / Önceki Dönem Tahsilatı</td><td style="text-align:right">+${fmtMoney(advance)}</td></tr>` : ''}</table>
      <p style="font-size:10px;color:#666">Gelir ve tahsilat seçili iş gününün farklı hareketleridir. Tahsilat; avans veya önceki dönem borç ödemesi içerdiğinde geliri aşabilir.</p>
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
  const collected = Number(d.revenue?.collected || 0);
  const outstandingDue = Math.max(0, totalRev - collected);
  const advanceCollected = Math.max(0, collected - totalRev);
  const trevpar = d.occupancy?.total > 0 ? totalRev / d.occupancy.total : 0;
  const collectionPct = totalRev > 0 ? collected / totalRev * 100 : 0;
  const attentionItems = [
    ...(d.attention_details?.no_shows || []).map(item => ({ ...item, attentionType: 'No-show' })),
    ...(d.attention_details?.cancellations || []).map(item => ({ ...item, attentionType: 'İptal' })),
  ];
  const openBooking = booking => {
    const bookingId = booking.id || booking.booking_id;
    if (bookingId) navigate(`/app/pms?edit=${encodeURIComponent(bookingId)}#bookings`);
  };
  const pieData = (d.departments || []).filter(dep => dep.amount > 0).map(dep => ({
    name: dep.name,
    value: dep.amount
  }));
  return <div className="space-y-4" data-testid="flash-report-content">
      {/* Toolbar: tarih + yazdır + yenile */}
      {!isEmbedded && (
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
      )}

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600" data-testid="flash-scope">
        <p className="font-semibold text-slate-800">Rapor kapsamı: {d.scope?.business_date || d.date}</p>
        <p className="mt-1">Tüm göstergeler seçili iş gününe aittir. Gelir o gün kaydedilen harcamaları, tahsilat ise o gün alınan ödemeleri gösterir; farklı rezervasyon dönemlerinden avans veya borç tahsilatı içerebilir.</p>
      </div>

      {/* Ana KPI'lar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-blue-50 border-blue-200" data-testid="flash-kpi-occupancy">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-blue-700 font-medium">{t('cm.components_pms_FlashReportContent.doluluk_orani')}</p>
                <p className="text-2xl font-bold text-blue-900">{(d.occupancy?.rate || 0).toFixed(1)}%</p>
                <p className="text-xs text-blue-600 mt-0.5">{d.occupancy?.occupied || 0}/{d.occupancy?.total || 0} oda · gece doluluğu</p>
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
                <p className="text-xs text-emerald-600 mt-0.5">Dolu oda başına oda geliri</p>
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
                <p className="text-xs text-indigo-600 mt-0.5">Mevcut oda başına oda geliri</p>
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
                <p className="text-xs text-amber-600 mt-0.5">Mevcut oda başına toplam gelir</p>
              </div>
              <Sparkles className="w-7 h-7 text-amber-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Operasyonel KPI'lar */}
      <div className="-mb-2 text-xs text-slate-500">
        Operasyonel hareketler · seçili iş gününün rezervasyon giriş, çıkış ve durum kayıtları
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card data-testid="flash-ops-arrivals">
          <CardContent className="p-3 text-center">
            <LogIn className="w-5 h-5 mx-auto text-emerald-500" />
            <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_FlashReportContent.girisler')}</p>
            <p className="text-xl font-bold text-emerald-700">{d.operations?.arrivals || 0}</p>
            <p className="text-[10px] text-gray-400">Bugün giriş</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-departures">
          <CardContent className="p-3 text-center">
            <LogOut className="w-5 h-5 mx-auto text-blue-500" />
            <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_FlashReportContent.cikislar')}</p>
            <p className="text-xl font-bold text-blue-700">{d.operations?.departures || 0}</p>
            <p className="text-[10px] text-gray-400">Bugün çıkış</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-inhouse">
          <CardContent className="p-3 text-center">
            <Users className="w-5 h-5 mx-auto text-indigo-500" />
            <p className="text-[11px] text-gray-500 mt-1">In-House</p>
            <p className="text-xl font-bold text-indigo-700">{d.operations?.inhouse || 0}</p>
            <p className="text-[10px] text-gray-400">Geceleyen oda</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-noshow">
          <CardContent className="p-3 text-center">
            <UserX className="w-5 h-5 mx-auto text-red-500" />
            <p className="text-[11px] text-gray-500 mt-1">No-Show</p>
            <p className="text-xl font-bold text-red-700">{d.operations?.no_shows || 0}</p>
            <p className="text-[10px] text-gray-400">Bugün işaretlenen</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-walkin">
          <CardContent className="p-3 text-center">
            <UserPlus className="w-5 h-5 mx-auto text-teal-500" />
            <p className="text-[11px] text-gray-500 mt-1">Walk-In</p>
            <p className="text-xl font-bold text-teal-700">{d.operations?.walk_ins || 0}</p>
            <p className="text-[10px] text-gray-400">Bugün gelen</p>
          </CardContent>
        </Card>
        <Card data-testid="flash-ops-cancel">
          <CardContent className="p-3 text-center">
            <XCircle className="w-5 h-5 mx-auto text-amber-500" />
            <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_FlashReportContent.iptal')}</p>
            <p className="text-xl font-bold text-amber-700">{d.operations?.cancellations || 0}</p>
            <p className="text-[10px] text-gray-400">Bugün iptal edilen</p>
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
              const isRoomRev = dep.name === 'Oda Geliri';
              return (
                <div 
                  key={dep.id || i} 
                  className={`flex items-center justify-between text-sm py-1.5 px-2 rounded -mx-2 ${isRoomRev ? 'cursor-pointer hover:bg-blue-50 transition-colors border border-transparent hover:border-blue-100' : ''}`}
                  onClick={isRoomRev ? () => setShowBreakdownModal(true) : undefined}
                  title={isRoomRev ? "Detayları görüntülemek için tıklayın" : undefined}
                >
                  <span className={`${isRoomRev ? 'text-blue-700 font-medium' : 'text-gray-700'} flex items-center`}>
                    {dep.name} {isRoomRev && <span className="ml-1.5 text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-normal">DETAY</span>}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-gray-900">{fmtMoney(dep.amount || 0)}</span>
                    <span className="text-xs text-gray-500 w-12 text-right">{pct.toFixed(1)}%</span>
                  </div>
                </div>
              );
            })}
            </div>
          </CardContent>
        </Card>

        <Card data-testid="flash-collection">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-500" /> Tahsilat Durumu
            </CardTitle>
            <p className="text-xs text-slate-500">Seçili iş günündeki gelir kayıtları ve ödeme hareketleri</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">{t('cm.components_pms_FlashReportContent.toplam_gelir')}</span>
              <span className="text-lg font-bold text-gray-900">{fmtMoney(totalRev)}</span>
            </div>
            <div className="flex items-center justify-between bg-emerald-50 px-3 py-2 rounded">
              <span className="text-sm text-emerald-700 font-medium">Tahsil Edilen</span>
              <span className="text-lg font-bold text-emerald-700">{fmtMoney(collected)}</span>
            </div>
            {outstandingDue > 0 && <div className="flex items-center justify-between bg-red-50 px-3 py-2 rounded">
                <span className="text-sm text-red-700 font-medium">{t('cm.components_pms_FlashReportContent.acik_bakiye')}</span>
                <span className="text-lg font-bold text-red-700">{fmtMoney(outstandingDue)}</span>
              </div>}
            {advanceCollected > 0 && <div className="flex items-center justify-between bg-blue-50 px-3 py-2 rounded" data-testid="flash-advance-collected">
                <span className="text-sm text-blue-700 font-medium">Avans / Önceki Dönem Tahsilatı</span>
                <span className="text-lg font-bold text-blue-700">+{fmtMoney(advanceCollected)}</span>
              </div>}
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
            <p className="text-[11px] leading-relaxed text-slate-500">
              Tahsilat geliri aşabilir: bugün alınan ön ödemeler veya önceki dönem borç tahsilatları bu toplama dahildir. Bu nedenle oran %100'ün üzerinde olabilir.
            </p>
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
          <CardContent className="space-y-3">
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
            {attentionItems.length > 0 ? <div className="grid gap-2" data-testid="flash-alert-details">
                {attentionItems.map((item, index) => {
                  const bookingId = item.id || item.booking_id;
                  return <div key={bookingId || item.booking_number || index} className="flex flex-col gap-2 rounded-lg border border-amber-200 bg-white/80 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-800">{item.attentionType}</span>
                          <span className="font-semibold text-slate-900">{item.guest_name || 'Misafir bilgisi yok'}</span>
                        </div>
                        <p className="mt-1 text-xs text-slate-600">
                          {item.booking_number ? `Rez. ${item.booking_number}` : 'Rezervasyon numarası yok'}
                          {item.room_number ? ` · Oda ${item.room_number}` : ' · Oda atanmamış'}
                          {(item.check_in || item.check_out) ? ` · ${dateKey(item.check_in) || '?'} → ${dateKey(item.check_out) || '?'}` : ''}
                        </p>
                        {item.cancellation_reason && <p className="mt-1 text-xs text-amber-800">Neden: {item.cancellation_reason}</p>}
                      </div>
                      {bookingId && <Button variant="outline" size="sm" className="shrink-0" onClick={() => openBooking(item)}>
                          Rezervasyonu Aç
                        </Button>}
                    </div>;
                })}
              </div> : <p className="text-xs text-amber-800">
                Sayı mevcut, ancak kayıt ayrıntısı bu rapor yanıtında bulunmuyor. Raporu yenileyerek ayrıntıları yükleyin.
              </p>}
          </CardContent>
        </Card>}

      <div className="text-[11px] text-gray-400 text-right">
        Para birimi: {currencyCode} ({currencySymbol})
      </div>

      {showBreakdownModal && reportData?.revenue?.room_revenue_breakdown && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4 print:hidden" onClick={() => setShowBreakdownModal(false)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold text-lg text-slate-800">Oda Geliri Detayları (In-House Odalar)</h3>
              <button onClick={() => setShowBreakdownModal(false)} className="p-1 hover:bg-gray-100 rounded-full">
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="p-0 overflow-y-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-500 uppercase bg-slate-50 sticky top-0 shadow-sm">
                  <tr>
                    <th className="px-4 py-3">Oda</th>
                    <th className="px-4 py-3">Misafir</th>
                    <th className="px-4 py-3 text-right">Geceleme</th>
                    <th className="px-4 py-3 text-right">Toplam Tutar</th>
                    <th className="px-4 py-3 text-right font-bold text-blue-600">Günlük Fiyat (Gelir)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {reportData.revenue.room_revenue_breakdown.map((item, i) => (
                    <tr key={i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-2 font-medium">{item.room_number || '?'}</td>
                      <td className="px-4 py-2">{item.guest_name || 'İsimsiz'}</td>
                      <td className="px-4 py-2 text-right">{item.nights} Gece</td>
                      <td className="px-4 py-2 text-right text-gray-500">{fmtMoney(item.total_stay_amount)}</td>
                      <td className="px-4 py-2 text-right font-semibold text-emerald-600">{fmtMoney(item.daily_rate)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-50 sticky bottom-0 border-t border-gray-200">
                  <tr>
                    <td colSpan={4} className="px-4 py-3 text-right font-bold text-slate-700">TOPLAM GÜNLÜK ODA GELİRİ:</td>
                    <td className="px-4 py-3 text-right text-lg font-bold text-emerald-700">{fmtMoney(reportData.revenue.room_revenue_breakdown.reduce((sum, item) => sum + (item.daily_rate || 0), 0))}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}

    </div>;
};
export default FlashReportContent;
