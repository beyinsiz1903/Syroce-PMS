import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import CostAnalyticsView from '@/components/cost/CostAnalyticsView';
import ProductState from '@/components/shared/ProductState';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { BarChart3, DollarSign, BedDouble, Users, Globe, Hotel, CreditCard, Shield, FileText, Building2, Utensils, TrendingUp, AlertTriangle, ArrowLeftRight, Loader2, RefreshCw, ChevronRight, LayoutDashboard, Calendar, CheckCircle2, Activity, ListChecks, ClipboardCheck, Download, Printer, Search, Scale, FileSpreadsheet } from 'lucide-react';
import ForecastReportsPage from './ForecastReportsPage';
import FlashReportContent from '@/components/pms/FlashReportContent';
import TrialBalancePage from './TrialBalancePage';
import { ROOM_STATUS_COLORS, ROOM_STATUS_LABELS, formatCurrency, formatPercent } from './reports/ReportHelpers';
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
import ManagerDailyReports from './reports/ManagerDailyReports';
import AccountingStatementsSection from './reports/AccountingStatementsSection';
import ReportFrame from './reports/ReportFrame';
import GuestPrivacyNotice from './reports/GuestPrivacyNotice';
import { getReportContract } from '@/lib/reportContracts';
import { fetchJsonWithRetry } from '@/lib/fetchRetry';
import { useBusinessDate } from '@/hooks/useBusinessDate';
const BACKEND_URL = "";
const CSV_FORMULA_PREFIX = /^[=+\-@\t\r]/;
const csvCell = value => {
  let text = value === undefined || value === null ? '' : String(value);
  if (CSV_FORMULA_PREFIX.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""').replace(/\r?\n/g, ' ')}"`;
};
const REPORT_MENU = [{
  type: 'header',
  label: 'GENEL'
}, {
  id: 'flash_report',
  label: 'Günlük Yönetim Özeti',
  icon: Activity,
  desc: 'Anlık kasa ve tesis durumu'
}, {
  id: 'overview',
  label: 'Genel Bakış',
  icon: LayoutDashboard,
  desc: 'Yönetici özet raporu'
}, {
  type: 'header',
  label: 'GELİR & FİNANS'
}, {
  id: 'revenue',
  label: 'Gelir Raporu',
  icon: DollarSign,
  desc: 'Gelir analizi ve trend'
}, {
  id: 'adr_revpar',
  label: 'Oda Gelir Performansı',
  icon: TrendingUp,
  desc: 'Performans metrikleri'
}, {
  id: 'forecast_reports',
  label: 'Öngörü Raporları',
  icon: TrendingUp,
  desc: 'Doluluk tahmini ve rezervasyon gelişimi'
}, {
  id: 'period',
  label: 'Dönem Karşılaştırma',
  icon: Calendar,
  desc: 'Periyodik karşılaştırma'
}, {
  type: 'header',
  label: 'DOLULUK & KAPASİTE'
}, {
  id: 'occupancy',
  label: 'Doluluk Raporu',
  icon: BedDouble,
  desc: 'Doluluk oranları'
}, {
  id: 'room_types',
  label: 'Oda Tipi Analizi',
  icon: Hotel,
  desc: 'Oda tipi kırılımı'
}, {
  type: 'header',
  label: 'MİSAFİR'
}, {
  id: 'guests',
  label: 'Tüm Misafirler',
  icon: Users,
  desc: 'Genel misafir listesi'
}, {
  id: 'inhouse',
  label: 'Otelde Konaklayanlar',
  icon: Hotel,
  desc: 'Şu an otelde olan misafirler'
}, {
  id: 'nationality',
  label: 'Milliyet Dağılımı',
  icon: Globe,
  desc: 'Ülke bazlı analiz'
}, {
  type: 'header',
  label: 'ÖN BÜRO'
}, {
  id: 'front_office',
  label: 'Beklenen Girişler ve Çıkışlar',
  icon: ArrowLeftRight,
  desc: 'Giriş ve çıkış hareketleri'
}, {
  id: 'noshow',
  label: 'Gelmeyen Misafirler ve İptaller',
  icon: AlertTriangle,
  desc: 'İptal ve no-show'
}, {
  type: 'header',
  label: 'OPERASYON'
}, {
  id: 'room_status',
  label: 'Oda Durumu',
  icon: Hotel,
  desc: 'Canlı oda durumu'
}, {
  id: 'housekeeping',
  label: 'Kat Hizmetleri',
  icon: CheckCircle2,
  desc: 'Temizlik raporları'
}, {
  type: 'header',
  label: 'KANAL & PAZAR'
}, {
  id: 'channels',
  label: 'Kanal Dağılımı',
  icon: Activity,
  desc: 'Kanal performansı'
}, {
  id: 'sources',
  label: 'Kaynak Analizi',
  icon: BarChart3,
  desc: 'Rezervasyon kaynakları'
}, {
  type: 'header',
  label: 'FİNANS & MUHASEBE'
}, {
  id: 'payments',
  label: 'Kasa Raporu (Ödemeler)',
  icon: CreditCard,
  desc: 'Tahsilat ve ödeme yöntemleri'
}, {
  id: 'front_cashier',
  label: 'Ön Kasa Raporu',
  icon: DollarSign,
  desc: 'Günlük ön kasa özeti'
}, {
  id: 'cash_movements',
  label: 'Kasa Hareketleri',
  icon: ArrowLeftRight,
  desc: 'Günlük tahsilat hareketleri'
}, {
  id: 'rate_control',
  label: 'Oda Fiyat Kontrol Listesi',
  icon: BedDouble,
  desc: 'Satılan ve tanımlı fiyat farkları'
}, {
  id: 'daily_analysis',
  label: 'Günlük Analiz Raporu',
  icon: BarChart3,
  desc: 'Doluluk, gelir ve hareket özeti'
}, {
  id: 'expenses',
  label: 'Gider Analitiği',
  icon: TrendingUp,
  desc: 'Kategoriye göre gider analizi'
}, {
  id: 'trial_balance',
  label: 'Günlük Mutabakat',
  icon: ClipboardCheck,
  desc: 'Operasyon, gelir ve tahsilat kontrolü'
}, {
  id: 'gl_trial_balance',
  label: 'Genel Muhasebe Mizanı',
  icon: Scale,
  desc: 'Hesap bazında borç ve alacak bakiyeleri'
}, {
  id: 'income_statement',
  label: 'Gelir Tablosu',
  icon: FileSpreadsheet,
  desc: 'Muhasebeleşmiş gelir, gider ve net sonuç'
}, {
  id: 'balance_sheet',
  label: 'Bilanço',
  icon: Building2,
  desc: 'Varlık, yükümlülük ve özkaynak dengesi'
}, {
  id: 'journal',
  label: 'Yevmiye Defteri',
  icon: FileText,
  desc: 'Onaylanmış muhasebe fişleri'
}, {
  type: 'header',
  label: 'RESMİ RAPORLAR'
}, {
  id: 'official',
  label: 'Maliye Listesi',
  icon: FileText,
  desc: 'Resmi müşteri listesi'
}, {
  id: 'police',
  label: 'Polis Bildirimi',
  icon: Shield,
  desc: 'Emniyet bildirimi'
}, {
  type: 'header',
  label: 'DEPARTMANLAR'
}, {
  id: 'departments',
  label: 'Departman Özeti',
  icon: Building2,
  desc: 'Departman raporları'
}, {
  type: 'header',
  label: 'YİYECEK VE İÇECEK'
}, {
  id: 'fnb',
  label: 'Yiyecek ve İçecek Raporu',
  icon: Utensils,
  desc: 'Yiyecek & içecek'
}];
const SELF_CONTAINED_SECTIONS = new Set(['expenses', 'official', 'forecast_reports', 'trial_balance', 'gl_trial_balance', 'income_statement', 'balance_sheet', 'journal']);
const ACCOUNTING_STATEMENT_SECTIONS = new Set(['gl_trial_balance', 'income_statement', 'balance_sheet', 'journal']);
const REPORT_SECTION_IDS = new Set(REPORT_MENU.filter(item => item.id).map(item => item.id));
const TABLE_EXPORT_SECTIONS = new Set(['guests', 'inhouse', 'front_office', 'noshow', 'housekeeping', 'payments', 'cash_movements', 'rate_control', 'official', 'police']);
const DAILY_REPORT_SECTIONS = new Set(['inhouse', 'front_office', 'room_status', 'housekeeping', 'payments', 'front_cashier', 'cash_movements', 'rate_control', 'daily_analysis', 'official', 'police']);
const BasicReports = ({
  user,
  tenant,
  onLogout
}) => {
  const { t } = useTranslation();
  const businessDate = useBusinessDate();
  const [data, setData] = useState(null);
  const [reportPeriod, setReportPeriod] = useState("monthly");
  const [reportDate, setReportDate] = useState(businessDate);
  const reportDateEditedRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [reportRefreshedAt, setReportRefreshedAt] = useState(null);
  const [error, setError] = useState(null);
  const [exchangeRates, setExchangeRates] = useState({ TRY: 1, TL: 1 });
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSection = searchParams.get('section') || 'overview';
  const urlSection = REPORT_SECTION_IDS.has(requestedSection) ? requestedSection : 'overview';
  const [activeSection, setActiveSectionState] = useState(urlSection);
  // Keep tab state in sync with the URL so browser back/forward and external
  // navigations land on the right section (e.g. /app/cost-management redirect).
  useEffect(() => {
    if (urlSection !== activeSection) setActiveSectionState(urlSection);
  }, [urlSection, activeSection]);
  const setActiveSection = useCallback(section => {
    setActiveSectionState(section);
    const next = new URLSearchParams(searchParams);
    if (section === 'overview') next.delete('section');else next.set('section', section);
    setSearchParams(next, {
      replace: true
    });
  }, [searchParams, setSearchParams]);
  const [searchGuest, setSearchGuest] = useState('');
  const [reportQuery, setReportQuery] = useState('');
  const [officialDate, setOfficialDate] = useState(businessDate);
  const officialDateEditedRef = useRef(false);
  const [officialRows, setOfficialRows] = useState([]);
  const [officialPrivacy, setOfficialPrivacy] = useState(null);
  const [officialLoading, setOfficialLoading] = useState(false);
  const [officialError, setOfficialError] = useState(null);
  const [officialSearch, setOfficialSearch] = useState('');
  useEffect(() => {
    if (!reportDateEditedRef.current && businessDate) setReportDate(businessDate);
    if (!officialDateEditedRef.current && businessDate) setOfficialDate(businessDate);
  }, [businessDate]);
  const needsDashboard = useMemo(() => !SELF_CONTAINED_SECTIONS.has(activeSection), [activeSection]);
  const showReportControls = needsDashboard || ACCOUNTING_STATEMENT_SECTIONS.has(activeSection);
  const requestSequenceRef = useRef(0);
  const fetchData = useCallback(async () => {
    const requestSequence = ++requestSequenceRef.current;
    setLoading(true);
    setError(null);
    try {
      const urlParams = new URLSearchParams();
      if (reportPeriod) urlParams.append('period', reportPeriod);
      if (reportDate) urlParams.append('date', reportDate);
      const json = await fetchJsonWithRetry(BACKEND_URL + `/api/reports/basic-dashboard?${urlParams.toString()}`, {
        credentials: 'include',
      });
      if (requestSequence === requestSequenceRef.current) {
        setData(json);
        setReportRefreshedAt(new Date().toLocaleString('tr-TR'));
      }
    } catch (err) {
      if (requestSequence === requestSequenceRef.current) setError(err && err.status ? 'Veri yüklenemedi' : err.message || 'Veri yüklenemedi');
    } finally {
      if (requestSequence === requestSequenceRef.current) setLoading(false);
    }
  }, [reportPeriod, reportDate]);

  // Only fetch the heavy dashboard payload when the active section actually
  // needs it. Self-contained sections (expenses, official) load their own
  // data and shouldn't block on the dashboard aggregate.
    useEffect(() => {
    if (needsDashboard) {
      fetchData();
    }
  }, [needsDashboard, fetchData]);
  useEffect(() => {
    if (activeSection !== 'inhouse') return;
    let active = true;
    fetchJsonWithRetry(BACKEND_URL + '/exchange-rates', { credentials: 'include' })
      .then(result => {
        if (active && result?.rates) setExchangeRates({ TRY: 1, TL: 1, ...result.rates });
      })
      .catch(() => {
        // The table falls back to the reservation currency rather than
        // presenting an unconverted amount as Turkish lira.
      });
    return () => { active = false; };
  }, [activeSection]);
  const fetchOfficialGuests = useCallback(async dateParam => {
    setOfficialLoading(true);
    setOfficialError(null);
    try {
      const result = await fetchJsonWithRetry(BACKEND_URL + '/api/reports/official-guest-list?date=' + (dateParam || officialDate), {
        credentials: 'include',
      });
      setOfficialRows(result?.rows || []);
      setOfficialPrivacy(result?.privacy || null);
    } catch (err) {
      setOfficialError(err && err.status ? 'Resmi misafir listesi yüklenemedi' : err.message || 'Resmi misafir listesi yüklenemedi');
    } finally {
      setOfficialLoading(false);
    }
  }, [officialDate]);
  const handleOfficialExportCsv = () => {
    if (!filteredOfficialRows.length) return;
    const headers = ['Rezervasyon No', 'Misafir Adı', 'T.C. Kimlik No', 'Pasaport No', 'Ülke', 'Şehir', 'Doğum Tarihi', 'Oda', 'Giriş', 'Çıkış', 'Yetişkin', 'Çocuk', 'Toplam Tutar', 'Para Birimi', 'Vergi No', 'Fatura Adresi', 'Şirket No', 'Pazar Bölümü'];
    const lines = [headers.map(csvCell).join(',')];
    filteredOfficialRows.forEach(r => {
      lines.push([r.booking_id, r.guest_name, r.national_id, r.passport_number, r.country, r.city, r.date_of_birth, r.room_number, r.check_in, r.check_out, r.adults, r.children, r.total_amount, r.currency, r.billing_tax_number, r.billing_address, r.company_id, r.market_segment].map(csvCell).join(','));
    });
    const blob = new Blob([lines.join('\n')], {
      type: 'text/csv;charset=utf-8;'
    });
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
    w.document.write('<p>Tarih: ' + new Date(`${officialDate}T12:00:00`).toLocaleDateString('tr-TR') + ' | Gösterilen kayıt: ' + filteredOfficialRows.length + ' | Toplam kişi: ' + officialTotalGuests + ' | Konaklama toplamı: ' + officialRevenueSummary + '</p>');
    if (officialPrivacy?.server_side_enforced) {
      w.document.write('<p><strong>Veri koruması etkin.</strong> Maskeli alan sayısı: ' + (officialPrivacy.masked_fields?.length || 0) + ' | Gizli alan sayısı: ' + (officialPrivacy.hidden_fields?.length || 0) + '. Bu çıktı kullanıcıya özel veri görünürlüğü profiliyle hazırlanmıştır.</p>');
    }
    w.document.write(tableEl.outerHTML);
    w.document.write('</body></html>');
    w.document.close();
    setTimeout(() => w.print(), 300);
  };
  const isInitialDashboardLoad = needsDashboard && data === null && !error;
  if ((loading || isInitialDashboardLoad) && needsDashboard) return <ProductState state="loading" moduleName="Raporlar" showDashboardLink={false} />;
  if (error && needsDashboard) return <ProductState state="error" moduleName="Raporlar" description={error} onRetry={fetchData} showDashboardLink={false} />;
  const s = data?.summary || {};
  const periodMetrics = data?.period_metrics || {};
  const periodActivity = data?.period_activity || {};
  const pc = data?.period_comparison || {};
  const roomTypeOcc = data?.room_type_occupancy || {};
  const roomStatus = data?.room_status || {};
  const bookingSources = data?.booking_sources || {};
  const countryDist = data?.country_distribution || {};
  const payments = data?.payments || {};
  const dailyLists = data?.daily_lists || {};
  const guestList = data?.guest_list || [];
  const hk = data?.housekeeping || {};
  const maint = data?.maintenance || {};
  const finance = data?.finance || {};
  const roomStatusData = Object.entries(roomStatus).filter(([, v]) => v > 0).map(([key, value]) => ({
    name: ROOM_STATUS_LABELS[key] || key,
    value,
    color: ROOM_STATUS_COLORS[key] || '#6B7280'
  }));
  const roomTypeData = Object.entries(roomTypeOcc).map(([key, val]) => ({
    name: key,
    total: val.total,
    occupied: val.occupied,
    occupancy: val.occupancy,
    revenue: Object.keys(val.revenue_by_currency || {}).length <= 1 ? val.revenue : 0,
    revenueByCurrency: val.revenue_by_currency || {}
  }));
  const countryData = Object.entries(countryDist).sort((a, b) => b[1] - a[1]).map(([key, value]) => ({
    name: key,
    count: value
  }));
  const paymentMethodBreakdowns = payments.totals_by_method_currency || {};
  const paymentData = Object.entries(Object.keys(paymentMethodBreakdowns).length ? paymentMethodBreakdowns : payments.by_method || {}).map(([key, rawValue]) => {
    const totals = rawValue && typeof rawValue === 'object' ? rawValue : { TRY: Number(rawValue || 0) };
    const currencies = Object.keys(totals).filter(currency => Number(totals[currency]) !== 0);
    return {
    name: key === 'credit_card' ? 'Kredi Kartı' : key === 'cash' ? 'Nakit' : key === 'bank_transfer' ? 'Havale/EFT' : key === 'debit_card' ? 'Banka Kartı' : key,
    value: currencies.length === 1 ? Number(totals[currencies[0]] || 0) : 0,
    currency: currencies.length === 1 ? currencies[0] : null,
    totals,
  };
  });
  const sourceData = Object.entries(bookingSources.distribution || {}).map(([key, value]) => ({
    name: key === 'direct' ? 'Doğrudan' : key === 'ota' ? 'Online acente' : key === 'corporate' ? 'Kurumsal' : key === 'walk_in' ? 'Kapı müşterisi' : key === 'booking_com' ? 'Booking.com' : key === 'company_direct' ? 'Şirket' : key === 'ota_import' ? 'Kanal yöneticisi' : key === 'hotelrunner' ? 'HotelRunner' : key === 'exely' ? 'Exely' : key,
    count: value,
    revenue: Object.keys(bookingSources.revenue_by_currency?.[key] || {}).length <= 1 ? (bookingSources.revenue?.[key] || 0) : 0,
    revenueByCurrency: bookingSources.revenue_by_currency?.[key] || {}
  })).sort((a, b) => b.count - a.count || b.revenue - a.revenue || a.name.localeCompare(b.name, 'tr'));
  const selectedDate = data?.date || reportDate;
  const todayArrivals = dailyLists.arrivals || [];
  const todayDepartures = dailyLists.departures || [];
  const noShowGuests = guestList.filter(g => ['no_show', 'noshow'].includes(String(g.status || '').toLowerCase()));
  const cancelledGuests = guestList.filter(g => ['cancelled', 'canceled'].includes(String(g.status || '').toLowerCase()));
  const filteredGuests = guestList.filter(g => {
    if (!searchGuest) return true;
    const term = searchGuest.toLowerCase();
    return (g.guest_name || '').toLowerCase().includes(term) || (g.room_number || '').toString().includes(term) || (g.guest_email || '').toLowerCase().includes(term);
  });
  const fallbackInHouseGuests = guestList.filter(g => {
    const ci = g.check_in ? g.check_in.substring(0, 10) : '';
    const co = g.check_out ? g.check_out.substring(0, 10) : '';
    return ci && co && ci <= selectedDate && selectedDate < co && ['checked_in', 'in_house', 'checked_out'].includes(g.status);
  });
  const allSelectedInHouseGuests = Array.isArray(dailyLists.in_house) ? dailyLists.in_house : fallbackInHouseGuests;
  const selectedInHouseGuests = allSelectedInHouseGuests.filter(g => {
    if (!searchGuest) return true;
    const term = searchGuest.toLowerCase();
    return (g.guest_name || '').toLowerCase().includes(term) || (g.room_number || '').toString().includes(term) || (g.guest_email || '').toLowerCase().includes(term);
  });
  const filteredOfficialRows = officialRows.filter(r => {
    if (!officialSearch) return true;
    const term = officialSearch.toLowerCase();
    return (r.guest_name || '').toLowerCase().includes(term) || (r.room_number || '').toString().includes(term) || (r.national_id || '').includes(term) || (r.passport_number || '').toLowerCase().includes(term);
  });
  const officialTotalGuests = filteredOfficialRows.reduce((a, r) => a + (r.adults || 0) + (r.children || 0), 0);
  const officialRevenueByCurrency = filteredOfficialRows.reduce((totals, row) => {
    const currency = String(row.currency || 'TRY').toUpperCase();
    totals[currency] = (totals[currency] || 0) + Number(row.total_amount || 0);
    return totals;
  }, {});
  const officialRevenueSummary = Object.entries(officialRevenueByCurrency)
    .filter(([, amount]) => Number(amount) !== 0)
    .map(([currency, amount]) => formatCurrency(amount, currency))
    .join(' · ') || '-';

  const handleGenericExportCsv = () => {
    if (activeSection === 'official' && typeof handleOfficialExportCsv === 'function') {
      handleOfficialExportCsv();
      return;
    }
    
    const sectionContainer = document.querySelector('[data-testid="reports-desktop-content"]');
    if (!sectionContainer) return;
    
    const tables = sectionContainer.querySelectorAll('table');
    if (tables.length === 0) {
      toast.error('Bu raporda dışa aktarılabilecek bir tablo bulunamadı. Lütfen tablo içeren bir rapor seçin.');
      return;
    }

    let csvContent = "";
    
    tables.forEach((table, index) => {
      if (index > 0) csvContent += "\n\n";
      
      const rows = table.querySelectorAll('tr');
      rows.forEach(row => {
        const rowData = [];
        const cells = row.querySelectorAll('th, td');
        cells.forEach(cell => {
          rowData.push(csvCell((cell.innerText || '').trim()));
        });
        csvContent += rowData.join(',') + "\n";
      });
    });

    const blob = new Blob(["\ufeff" + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `rapor_${activeSection}_${reportDate}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleGenericPrint = () => {
    window.print();
  };

  const withGuestPrivacy = content => <div className="space-y-4">
    <GuestPrivacyNotice privacy={data?.privacy} compact />
    {content}
  </div>;

  const renderContent = () => {

    switch (activeSection) {
      case 'flash_report':
        return <FlashReportContent showDatePicker={false} isEmbedded={true} targetDate={reportDate} />;
      case 'overview':
        return <OverviewSection data={data} s={s} pc={pc} periodMetrics={periodMetrics} roomStatusData={roomStatusData} reportPeriod={reportPeriod} />;
      case 'revenue':
        return <RevenueSection data={data} s={s} pc={pc} roomTypeData={roomTypeData} reportPeriod={reportPeriod} reportDate={selectedDate} />;
      case 'adr_revpar':
        return <AdrRevparSection data={data} s={s} pc={pc} periodMetrics={periodMetrics} reportPeriod={reportPeriod} />;
      case 'forecast_reports':
        return <div data-testid="section-forecast-reports"><ForecastReportsPage /></div>;
      case 'period':
        return <PeriodSection data={data} pc={pc} />;
      case 'occupancy':
        return <OccupancySection data={data} s={s} periodMetrics={periodMetrics} reportPeriod={reportPeriod} />;
      case 'room_types':
        return <RoomTypesSection roomTypeData={roomTypeData} />;
      case 'guests':
        return withGuestPrivacy(<div data-testid="section-guests"><GuestTable guests={filteredGuests} title="Tüm Misafir Listesi" searchGuest={searchGuest} setSearchGuest={setSearchGuest} /></div>);
      case 'inhouse':
        return withGuestPrivacy(<div data-testid="section-inhouse"><GuestTable guests={selectedInHouseGuests} totalCount={allSelectedInHouseGuests.length} title={`Otelde Konaklayanlar · ${new Date(selectedDate + 'T12:00:00').toLocaleDateString('tr-TR')}`} showNightlyRate historical reportDate={selectedDate} exchangeRates={exchangeRates} searchGuest={searchGuest} setSearchGuest={setSearchGuest} /></div>);
      case 'nationality':
        return <NationalitySection countryData={countryData} />;
      case 'front_office':
        return withGuestPrivacy(<FrontOfficeSection s={s} todayArrivals={todayArrivals} todayDepartures={todayDepartures} reportDate={selectedDate} exchangeRates={exchangeRates} />);
      case 'noshow':
        return withGuestPrivacy(<NoShowSection s={{ ...s, ...periodActivity }} noShowGuests={noShowGuests} cancelledGuests={cancelledGuests} exchangeRates={exchangeRates} />);
      case 'room_status':
        return <RoomStatusSection roomStatus={roomStatus} roomStatusData={roomStatusData} />;
      case 'housekeeping':
        return withGuestPrivacy(<HousekeepingSection hk={hk} reportDate={selectedDate} />);
      case 'channels':
        return <ChannelsSection sourceData={sourceData} />;
      case 'sources':
        return <SourcesSection sourceData={sourceData} />;
      case 'payments':
        return withGuestPrivacy(<PaymentsSection payments={payments} paymentData={paymentData} reportDate={selectedDate} />);
      case 'front_cashier':
      case 'cash_movements':
      case 'rate_control':
      case 'daily_analysis':
        return ['cash_movements', 'rate_control'].includes(activeSection)
          ? withGuestPrivacy(<ManagerDailyReports section={activeSection} data={data} reportDate={selectedDate} />)
          : <ManagerDailyReports section={activeSection} data={data} reportDate={selectedDate} />;
      case 'trial_balance':
        return <div data-testid="section-trial-balance"><TrialBalancePage reportDate={reportDate} /></div>;
      case 'gl_trial_balance':
      case 'income_statement':
      case 'balance_sheet':
      case 'journal':
        return <AccountingStatementsSection type={activeSection} reportDate={reportDate} reportPeriod={reportPeriod} />;
      case 'official':
        return <OfficialSection officialDate={officialDate} setOfficialDate={value => {
          officialDateEditedRef.current = true;
          setOfficialDate(value);
        }} officialRows={officialRows} officialPrivacy={officialPrivacy} officialLoading={officialLoading} officialError={officialError} officialSearch={officialSearch} setOfficialSearch={setOfficialSearch} fetchOfficialGuests={fetchOfficialGuests} handleOfficialExportCsv={handleOfficialExportCsv} handleOfficialPrint={handleOfficialPrint} filteredOfficialRows={filteredOfficialRows} officialTotalGuests={officialTotalGuests} officialRevenueByCurrency={officialRevenueByCurrency} />;
      case 'police':
        return withGuestPrivacy(<PoliceSection filteredGuests={selectedInHouseGuests} searchGuest={searchGuest} setSearchGuest={setSearchGuest} reportDate={selectedDate} />);
      case 'departments':
        return <DepartmentsSection s={s} hk={hk} maint={maint} finance={finance} />;
      case 'fnb':
        return <FnBSection s={s} reportDate={selectedDate} />;
      case 'expenses':
        return <div data-testid="section-expenses"><CostAnalyticsView /></div>;
      default:
        return <OverviewSection data={data} s={s} pc={pc} periodMetrics={periodMetrics} roomStatusData={roomStatusData} reportPeriod={reportPeriod} />;
    }
  };
  const currentMenuItem = REPORT_MENU.find(m => m.id === activeSection);
  const periodLabel = DAILY_REPORT_SECTIONS.has(activeSection)
    ? 'Seçili gün'
    : reportPeriod === 'daily' ? 'Seçili gün' : 'Son 30 gün';
  const normalizedReportQuery = reportQuery.trim().toLocaleLowerCase('tr-TR');
  const visibleMenuItems = normalizedReportQuery
    ? REPORT_MENU.filter(item => item.id && `${item.label} ${item.desc || ''}`.toLocaleLowerCase('tr-TR').includes(normalizedReportQuery))
    : REPORT_MENU;
  return <>
      <div className="flex min-h-[calc(100vh-64px)] bg-slate-50/70">
        <aside className="w-[288px] bg-white border-r border-slate-200 flex-shrink-0 hidden print:hidden lg:flex lg:flex-col" data-testid="reports-sidebar">
          <div className="p-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500 text-white shadow-sm"><BarChart3 className="w-5 h-5" /></div>
              <div><h1 className="text-base font-bold text-slate-900">Rapor Merkezi</h1><p className="text-[11px] text-slate-500">Operasyon ve finans</p></div>
            </div>
            <p className="mt-3 text-[11px] text-slate-400">PMS tarihi · {businessDate || reportDate ? new Date((businessDate || reportDate) + 'T12:00:00').toLocaleDateString('tr-TR', {
              day: 'numeric',
              month: 'long',
              year: 'numeric'
            }) : 'PMS tarihi yükleniyor'}</p>
            <label className="relative mt-3 block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input value={reportQuery} onChange={event => setReportQuery(event.target.value)} placeholder="Rapor ara…" className="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-2 focus:ring-blue-100" />
            </label>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {visibleMenuItems.map((item, idx) => {
            if (item.type === 'header') {
              return <p key={idx} className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-3 pt-4 pb-1">{item.label}</p>;
            }
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            return <button key={item.id} onClick={() => setActiveSection(item.id)} className={`group w-full rounded-lg px-3 py-2.5 text-left transition-all ${isActive ? 'bg-blue-50 text-blue-800 ring-1 ring-inset ring-blue-100' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`} data-testid={`report-nav-${item.id}`} title={item.desc}>
                  <span className="flex items-center gap-2.5"><Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600'}`} /><span className="truncate text-[13px] font-medium">{t(`cm.pages_BasicReports.${item.id}`, item.label)}</span></span>
                  {isActive && <span className="mt-1 block truncate pl-6 text-[10px] font-normal text-blue-600">{item.desc}</span>}
                </button>;
          })}
            {normalizedReportQuery && visibleMenuItems.length === 0 && <p className="px-3 py-8 text-center text-xs text-slate-400">Eşleşen rapor bulunamadı.</p>}
          </nav>
          <div className="p-3 border-t border-gray-100">
            <a href="/app/rapor-olusturucu" className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-sky-600 hover:bg-sky-50 font-medium transition-colors" data-testid="report-builder-link">
              <ListChecks className="w-4 h-4" />
              <span>Rapor Oluşturucu</span>
            </a>
          </div>
        </aside>

        <div className="lg:hidden print:hidden w-full">
          <div className="p-3 bg-white border-b sticky top-0 z-10">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-4 h-4 text-sky-600" />
              <span className="text-sm font-bold text-gray-900">Rapor Merkezi</span>
            </div>
            <select value={activeSection} onChange={e => setActiveSection(e.target.value)} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white" data-testid="mobile-report-selector">
              {REPORT_MENU.filter(m => m.id).map(m => <option key={m.id} value={m.id}>{t(`cm.pages_BasicReports.${m.id}`, m.label)}</option>)}
            </select>
            {showReportControls && <div className={`grid gap-2 mt-2 ${DAILY_REPORT_SECTIONS.has(activeSection) ? 'grid-cols-1' : 'grid-cols-2'}`}>
              {!DAILY_REPORT_SECTIONS.has(activeSection) && <select className="border rounded-lg px-2 py-2 text-sm bg-white" value={reportPeriod} onChange={e => setReportPeriod(e.target.value)}>
                <option value="monthly">Son 30 Gün</option>
                <option value="daily">Günlük</option>
              </select>}
              <input type="date" className="border rounded-lg px-2 py-2 text-sm bg-white" value={reportDate} onChange={e => { reportDateEditedRef.current = true; setReportDate(e.target.value); }} />
            </div>}
          </div>
          <div className="p-4" data-testid="reports-mobile-content">{renderContent()}</div>
        </div>

        <main className="flex-1 hidden print:block lg:block overflow-y-auto" data-testid="reports-desktop-content">
          <div className="mx-auto w-full max-w-[1520px] p-5 xl:p-7">
            <div className="mb-5 flex min-h-12 flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-2.5 shadow-sm print:hidden">
              <div className="flex min-w-0 items-center gap-2 text-xs text-gray-400">
                <span>Raporlar</span>
                <ChevronRight className="w-3 h-3" />
                <span className="text-gray-700 font-medium">{t(`cm.pages_BasicReports.${currentMenuItem?.id}`, currentMenuItem?.label || 'Genel Bakış')}</span>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {showReportControls && activeSection !== 'flash_report' && !DAILY_REPORT_SECTIONS.has(activeSection) && (
                <select 
                  className="h-9 min-w-[132px] border rounded-lg px-2 text-sm bg-white"
                  value={reportPeriod}
                  onChange={(e) => setReportPeriod(e.target.value)}
                >
                  <option value="monthly">Son 30 Gün</option>
                  <option value="daily">Günlük (Seçili Tarih)</option>
                </select>
                )}
                {showReportControls && <label className="flex shrink-0 items-center gap-2 whitespace-nowrap text-xs font-medium text-gray-500">
                  <span>Rapor tarihi</span>
                  <input
                    type="date"
                    className="h-9 min-w-[145px] border rounded-lg px-2 text-sm bg-white text-gray-900"
                    value={reportDate}
                    onChange={(e) => {
                      reportDateEditedRef.current = true;
                      setReportDate(e.target.value);
                    }}
                    data-testid="report-date-input"
                  />
                </label>}
                {activeSection !== 'official' && <Button onClick={handleGenericPrint} variant="outline" size="sm" className="hidden print:hidden sm:flex">
                  <Printer className="w-3.5 h-3.5 mr-1.5" />Yazdır
                </Button>}
                {TABLE_EXPORT_SECTIONS.has(activeSection) && activeSection !== 'official' && <Button onClick={handleGenericExportCsv} variant="outline" size="sm" className="hidden print:hidden sm:flex">
                  <Download className="w-3.5 h-3.5 mr-1.5" />CSV İndir
                </Button>}
                {needsDashboard && <Button onClick={fetchData} variant="outline" size="sm" data-testid="refresh-reports-btn" className="print:hidden">
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Yenile
                </Button>}
              </div>
            </div>
            <ReportFrame reportName={currentMenuItem?.label || 'Genel Bakış'} reportDate={activeSection === 'official' ? officialDate : selectedDate} periodLabel={periodLabel} tenant={tenant} user={user} contract={getReportContract(activeSection)} refreshedAt={needsDashboard ? reportRefreshedAt : null}>
              {renderContent()}
            </ReportFrame>
          </div>
        </main>
      </div>
    </>;
};
export default BasicReports;
