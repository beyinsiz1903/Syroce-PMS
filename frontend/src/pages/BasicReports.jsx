import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import CostAnalyticsView from '@/components/cost/CostAnalyticsView';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  BarChart3, DollarSign, BedDouble, Users, Globe, Hotel, CreditCard,
  Shield, FileText, Building2, Utensils, TrendingUp, AlertTriangle,
  ArrowLeftRight, Loader2, RefreshCw, ChevronRight, Star,
  LayoutDashboard, Calendar, CheckCircle2, Activity, ListChecks
} from 'lucide-react';
import {
  ROOM_STATUS_COLORS, ROOM_STATUS_LABELS, formatPercent
} from './reports/ReportHelpers';

import OverviewSection from './reports/OverviewSection';
import RevenueSection from './reports/RevenueSection';
import AdrRevparSection from './reports/AdrRevparSection';
import PeriodSection from './reports/PeriodSection';
import OccupancySection from './reports/OccupancySection';
import RoomTypesSection from './reports/RoomTypesSection';
import { GuestTable } from './reports/GuestSection';
import NationalitySection from './reports/NationalitySection';
import FrontOfficeSection from './reports/FrontOfficeSection';
import { NoShowSection, RoomStatusSection, HousekeepingSection, PaymentsSection, DepartmentsSection, FnBSection } from './reports/OperationsSection';
import { ChannelsSection, SourcesSection } from './reports/ChannelsSection';
import { OfficialSection, PoliceSection } from './reports/OfficialSection';

const BACKEND_URL = "";

const REPORT_MENU = [
  { type: 'header', label: 'GENEL' },
  { id: 'overview', label: 'Genel Bakış', icon: LayoutDashboard, desc: 'Yönetici özet raporu' },
  { type: 'header', label: 'GELİR & FİNANS' },
  { id: 'revenue', label: 'Gelir Raporu', icon: DollarSign, desc: 'Gelir analizi ve trend' },
  { id: 'adr_revpar', label: 'ADR & RevPAR', icon: TrendingUp, desc: 'Performans metrikleri' },
  { id: 'period', label: 'Dönem Karşılaştırma', icon: Calendar, desc: 'Periyodik karşılaştırma' },
  { type: 'header', label: 'DOLULUK & KAPASİTE' },
  { id: 'occupancy', label: 'Doluluk Raporu', icon: BedDouble, desc: 'Doluluk oranları' },
  { id: 'room_types', label: 'Oda Tipi Analizi', icon: Hotel, desc: 'Oda tipi kırılımı' },
  { type: 'header', label: 'MİSAFİR' },
  { id: 'guests', label: 'Misafir Listesi', icon: Users, desc: 'Tüm misafirler' },
  { id: 'nationality', label: 'Milliyet Dağılımı', icon: Globe, desc: 'Ülke bazlı analiz' },
  { type: 'header', label: 'ÖN BÜRO' },
  { id: 'front_office', label: 'Giriş / Çıkış', icon: ArrowLeftRight, desc: 'Günlük hareketler' },
  { id: 'noshow', label: 'No-Show & İptaller', icon: AlertTriangle, desc: 'İptal ve no-show' },
  { type: 'header', label: 'OPERASYON' },
  { id: 'room_status', label: 'Oda Durumu', icon: Hotel, desc: 'Canlı oda durumu' },
  { id: 'housekeeping', label: 'Housekeeping', icon: CheckCircle2, desc: 'Temizlik raporları' },
  { type: 'header', label: 'KANAL & PAZAR' },
  { id: 'channels', label: 'Kanal Dağılımı', icon: Activity, desc: 'Kanal performansı' },
  { id: 'sources', label: 'Kaynak Analizi', icon: BarChart3, desc: 'Rezervasyon kaynakları' },
  { type: 'header', label: 'FİNANS & MUHASEBE' },
  { id: 'payments', label: 'Ödemeler', icon: CreditCard, desc: 'Ödeme yöntemleri' },
  { id: 'expenses', label: 'Gider Analitiği', icon: TrendingUp, desc: 'Kategoriye göre gider analizi' },
  { type: 'header', label: 'RESMİ RAPORLAR' },
  { id: 'official', label: 'Maliye Listesi', icon: FileText, desc: 'Resmi müşteri listesi' },
  { id: 'police', label: 'Polis Bildirimi', icon: Shield, desc: 'Emniyet bildirimi' },
  { type: 'header', label: 'DEPARTMANLAR' },
  { id: 'departments', label: 'Departman Özeti', icon: Building2, desc: 'Departman raporları' },
  { type: 'header', label: 'F&B' },
  { id: 'fnb', label: 'F&B Raporu', icon: Utensils, desc: 'Yiyecek & içecek' },
];

const SELF_CONTAINED_SECTIONS = new Set(['expenses', 'official']);

const BasicReports = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSection = searchParams.get('section') || 'overview';
  const [activeSection, setActiveSectionState] = useState(urlSection);
  // Keep tab state in sync with the URL so browser back/forward and external
  // navigations land on the right section (e.g. /app/cost-management redirect).
  useEffect(() => {
    if (urlSection !== activeSection) setActiveSectionState(urlSection);
  }, [urlSection, activeSection]);
  const setActiveSection = useCallback((section) => {
    setActiveSectionState(section);
    const next = new URLSearchParams(searchParams);
    if (section === 'overview') next.delete('section');
    else next.set('section', section);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);
  const [searchGuest, setSearchGuest] = useState('');

  const [officialDate, setOfficialDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [officialRows, setOfficialRows] = useState([]);
  const [officialLoading, setOfficialLoading] = useState(false);
  const [officialError, setOfficialError] = useState(null);
  const [officialSearch, setOfficialSearch] = useState('');

  const needsDashboard = useMemo(
    () => !SELF_CONTAINED_SECTIONS.has(activeSection),
    [activeSection]
  );

  const inFlightRef = useRef(false);

  const fetchData = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(BACKEND_URL + '/api/reports/basic-dashboard', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (!res.ok) throw new Error('Veri yüklenemedi');
      setData(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  }, []);

  // Only fetch the heavy dashboard payload when the active section actually
  // needs it. Self-contained sections (expenses, official) load their own
  // data and shouldn't block on the dashboard aggregate.
  useEffect(() => {
    if (needsDashboard && data === null && !error) {
      fetchData();
    }
  }, [needsDashboard, data, error, fetchData]);

  const fetchOfficialGuests = useCallback(async (dateParam) => {
    setOfficialLoading(true);
    setOfficialError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(BACKEND_URL + '/api/reports/official-guest-list?date=' + (dateParam || officialDate), {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (!res.ok) throw new Error('Resmi misafir listesi yüklenemedi');
      const result = await res.json();
      setOfficialRows(result?.rows || []);
    } catch (err) {
      setOfficialError(err.message);
    } finally {
      setOfficialLoading(false);
    }
  }, [officialDate]);

  const handleOfficialExportCsv = () => {
    if (!officialRows.length) return;
    const headers = ['booking_id','guest_name','national_id','passport_number','country','city','date_of_birth','room_number','check_in','check_out','adults','children','total_amount','billing_tax_number','billing_address','company_id','market_segment'];
    const lines = [headers.join(',')];
    officialRows.forEach(r => {
      lines.push([
        r.booking_id || '', (r.guest_name || '').replace(/,/g, ' '), r.national_id || '', r.passport_number || '',
        (r.country || '').replace(/,/g, ' '), (r.city || '').replace(/,/g, ' '), r.date_of_birth || '',
        r.room_number || '', r.check_in || '', r.check_out || '', String(r.adults ?? ''), String(r.children ?? ''),
        String(r.total_amount ?? ''), r.billing_tax_number || '', (r.billing_address || '').replace(/,/g, ' '),
        r.company_id || '', r.market_segment || ''
      ].join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `maliye_listesi_${officialDate}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleOfficialPrint = () => {
    const tableEl = document.querySelector('[data-testid="official-guest-table"]');
    if (!tableEl) return;
    const w = window.open('', '_blank', 'width=900,height=700');
    w.document.write('<html><head><title>Maliye Listesi - ' + officialDate + '</title>');
    w.document.write('<style>body{font-family:Arial,sans-serif;padding:20px;font-size:12px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:6px 8px;text-align:left}th{background:#f5f5f5;font-weight:600}h1{font-size:18px;margin:0 0 4px}p{color:#666;margin:0 0 16px;font-size:12px}</style>');
    w.document.write('</head><body>');
    w.document.write('<h1>Resmi Müşteri Listesi</h1>');
    w.document.write('<p>Tarih: ' + new Date(officialDate).toLocaleDateString('tr-TR') + ' | Toplam kayıt: ' + filteredOfficialRows.length + ' | Toplam kişi: ' + officialTotalGuests + ' | Toplam tutar: ' + officialTotalRevenue.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' }) + '</p>');
    w.document.write(tableEl.outerHTML);
    w.document.write('</body></html>');
    w.document.close();
    setTimeout(() => w.print(), 300);
  };

  const isInitialDashboardLoad = needsDashboard && data === null && !error;

  if ((loading || isInitialDashboardLoad) && needsDashboard) return (
    <>
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-3" />
          <p className="text-sm text-gray-500">Raporlar yükleniyor...</p>
        </div>
      </div>
    </>
  );

  if (error && needsDashboard) return (
    <>
      <div className="p-6">
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-6 text-center">
            <AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-3" />
            <p className="text-red-700">{error}</p>
            <Button onClick={fetchData} className="mt-4" variant="outline">
              <RefreshCw className="w-4 h-4 mr-2" />Tekrar Dene
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );

  const s = data?.summary || {};
  const pc = data?.period_comparison || {};
  const roomTypeOcc = data?.room_type_occupancy || {};
  const roomStatus = data?.room_status || {};
  const bookingSources = data?.booking_sources || {};
  const countryDist = data?.country_distribution || {};
  const payments = data?.payments || {};
  const guestList = data?.guest_list || [];
  const hk = data?.housekeeping || {};
  const maint = data?.maintenance || {};
  const finance = data?.finance || {};

  const roomStatusData = Object.entries(roomStatus).filter(([, v]) => v > 0).map(([key, value]) => ({
    name: ROOM_STATUS_LABELS[key] || key, value, color: ROOM_STATUS_COLORS[key] || '#6B7280'
  }));
  const roomTypeData = Object.entries(roomTypeOcc).map(([key, val]) => ({
    name: key, total: val.total, occupied: val.occupied, occupancy: val.occupancy, revenue: val.revenue
  }));
  const countryData = Object.entries(countryDist).sort((a, b) => b[1] - a[1]).map(([key, value]) => ({ name: key, count: value }));
  const paymentData = Object.entries(payments.by_method || {}).map(([key, value]) => ({
    name: key === 'credit_card' ? 'Kredi Kartı' : key === 'cash' ? 'Nakit' : key === 'bank_transfer' ? 'Havale/EFT' : key === 'debit_card' ? 'Banka Kartı' : key,
    value
  }));
  const sourceData = Object.entries(bookingSources.distribution || {}).map(([key, value]) => ({
    name: key === 'direct' ? 'Direkt' : key === 'ota' ? 'OTA' : key === 'corporate' ? 'Kurumsal' : key === 'walk_in' ? 'Walk-in' : key === 'booking_com' ? 'Booking.com' : key === 'company_direct' ? 'Şirket' : key,
    count: value, revenue: bookingSources.revenue?.[key] || 0
  }));

  const todayStr = new Date().toISOString().split('T')[0];
  const todayArrivals = guestList.filter(g => g.check_in?.startsWith(todayStr) && ['confirmed', 'guaranteed'].includes(g.status));
  const todayDepartures = guestList.filter(g => g.check_out?.startsWith(todayStr));
  const noShowGuests = guestList.filter(g => g.status === 'no_show');
  const cancelledGuests = guestList.filter(g => g.status === 'cancelled');

  const filteredGuests = guestList.filter(g => {
    if (!searchGuest) return true;
    const term = searchGuest.toLowerCase();
    return (g.guest_name || '').toLowerCase().includes(term) || (g.room_number || '').toString().includes(term) || (g.guest_email || '').toLowerCase().includes(term);
  });

  const officialTotalGuests = officialRows.reduce((a, r) => a + (r.adults || 0) + (r.children || 0), 0);
  const officialTotalRevenue = officialRows.reduce((a, r) => a + (r.total_amount || 0), 0);
  const filteredOfficialRows = officialRows.filter(r => {
    if (!officialSearch) return true;
    const term = officialSearch.toLowerCase();
    return (r.guest_name || '').toLowerCase().includes(term) ||
      (r.room_number || '').toString().includes(term) ||
      (r.national_id || '').includes(term) ||
      (r.passport_number || '').toLowerCase().includes(term);
  });

  const renderContent = () => {
    switch (activeSection) {
      case 'overview': return <OverviewSection data={data} s={s} pc={pc} roomStatusData={roomStatusData} />;
      case 'revenue': return <RevenueSection data={data} s={s} pc={pc} roomTypeData={roomTypeData} />;
      case 'adr_revpar': return <AdrRevparSection data={data} s={s} pc={pc} />;
      case 'period': return <PeriodSection data={data} pc={pc} />;
      case 'occupancy': return <OccupancySection data={data} s={s} />;
      case 'room_types': return <RoomTypesSection roomTypeData={roomTypeData} />;
      case 'guests': return <div data-testid="section-guests"><GuestTable guests={filteredGuests} title="Misafir Listesi" searchGuest={searchGuest} setSearchGuest={setSearchGuest} /></div>;
      case 'nationality': return <NationalitySection countryData={countryData} />;
      case 'front_office': return <FrontOfficeSection s={s} todayArrivals={todayArrivals} todayDepartures={todayDepartures} />;
      case 'noshow': return <NoShowSection s={s} noShowGuests={noShowGuests} cancelledGuests={cancelledGuests} />;
      case 'room_status': return <RoomStatusSection roomStatus={roomStatus} roomStatusData={roomStatusData} />;
      case 'housekeeping': return <HousekeepingSection hk={hk} />;
      case 'channels': return <ChannelsSection sourceData={sourceData} />;
      case 'sources': return <SourcesSection sourceData={sourceData} />;
      case 'payments': return <PaymentsSection payments={payments} paymentData={paymentData} />;
      case 'official': return <OfficialSection officialDate={officialDate} setOfficialDate={setOfficialDate} officialRows={officialRows} officialLoading={officialLoading} officialError={officialError} officialSearch={officialSearch} setOfficialSearch={setOfficialSearch} fetchOfficialGuests={fetchOfficialGuests} handleOfficialExportCsv={handleOfficialExportCsv} handleOfficialPrint={handleOfficialPrint} filteredOfficialRows={filteredOfficialRows} officialTotalGuests={officialTotalGuests} officialTotalRevenue={officialTotalRevenue} />;
      case 'police': return <PoliceSection filteredGuests={filteredGuests} searchGuest={searchGuest} setSearchGuest={setSearchGuest} />;
      case 'departments': return <DepartmentsSection s={s} hk={hk} maint={maint} finance={finance} />;
      case 'fnb': return <FnBSection s={s} />;
      case 'expenses': return <div data-testid="section-expenses"><CostAnalyticsView /></div>;
      default: return <OverviewSection data={data} s={s} pc={pc} roomStatusData={roomStatusData} />;
    }
  };

  const currentMenuItem = REPORT_MENU.find(m => m.id === activeSection);

  return (
    <>
      <div className="flex min-h-[calc(100vh-64px)]">
        <aside className="w-[260px] bg-white border-r border-gray-200 flex-shrink-0 hidden lg:flex lg:flex-col" data-testid="reports-sidebar">
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-600" />
              <h1 className="text-base font-bold text-gray-900">Rapor Merkezi</h1>
            </div>
            <p className="text-[11px] text-gray-400 mt-1">{new Date().toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {REPORT_MENU.map((item, idx) => {
              if (item.type === 'header') {
                return <p key={idx} className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-3 pt-4 pb-1">{item.label}</p>;
              }
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all text-[13px] ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-semibold border-l-[3px] border-blue-600 pl-[9px]'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                  data-testid={`report-nav-${item.id}`}
                >
                  <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="p-3 border-t border-gray-100">
            <a
              href="/app/rapor-olusturucu"
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-blue-600 hover:bg-blue-50 font-medium transition-colors"
              data-testid="report-builder-link"
            >
              <ListChecks className="w-4 h-4" />
              <span>Rapor Oluşturucu</span>
            </a>
          </div>
        </aside>

        <div className="lg:hidden w-full">
          <div className="p-3 bg-white border-b sticky top-0 z-10">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-bold text-gray-900">Rapor Merkezi</span>
            </div>
            <select
              value={activeSection}
              onChange={e => setActiveSection(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
              data-testid="mobile-report-selector"
            >
              {REPORT_MENU.filter(m => m.id).map(m => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="p-4" data-testid="reports-mobile-content">{renderContent()}</div>
        </div>

        <main className="flex-1 hidden lg:block overflow-y-auto" data-testid="reports-desktop-content">
          <div className="p-6 max-w-6xl">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span>Raporlar</span>
                <ChevronRight className="w-3 h-3" />
                <span className="text-gray-700 font-medium">{currentMenuItem?.label || 'Genel Bakış'}</span>
              </div>
              <Button onClick={fetchData} variant="outline" size="sm" data-testid="refresh-reports-btn">
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Yenile
              </Button>
            </div>
            {renderContent()}
          </div>
        </main>
      </div>
    </>
  );
};

export default BasicReports;
