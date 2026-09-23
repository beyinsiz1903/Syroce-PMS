import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeftRight, BarChart3, BedDouble, DollarSign } from 'lucide-react';
import { EmptyState, KPICard, SectionHeader, formatCurrency } from './ReportHelpers';

const formatDateTime = value => value ? new Date(value).toLocaleString('tr-TR') : '-';

const FrontCashierReport = ({ summary, reportDate }) => (
  <div className="space-y-5" data-testid="section-front-cashier">
    <SectionHeader title="Ön Kasa Raporu" description={`${reportDate} tarihli folyo ve tahsilat özeti`} />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Folyo İşlem Tutarı" value={summary.charge_total || 0} icon={DollarSign} color="amber" />
      <KPICard title="Toplam Tahsilat" value={summary.collection_total || 0} icon={DollarSign} color="green" />
      <KPICard title="Nakit Tahsilat" value={summary.cash_total || 0} icon={DollarSign} color="blue" />
      <KPICard title="Kart / Havale Tahsilatı" value={summary.non_cash_total || 0} icon={DollarSign} color="purple" />
    </div>
    <Card><CardContent className="p-5 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div><p className="text-gray-500">Folyo hareketi</p><p className="font-bold text-lg">{summary.charge_count || 0}</p></div>
      <div><p className="text-gray-500">Ödeme hareketi</p><p className="font-bold text-lg">{summary.payment_count || 0}</p></div>
      <div><p className="text-gray-500">Günlük net hareket</p><p className="font-bold text-lg">{formatCurrency(summary.net_movement || 0)}</p></div>
      <div><p className="text-gray-500">Rapor tarihi</p><p className="font-bold text-lg">{reportDate}</p></div>
    </CardContent></Card>
  </div>
);

const CashMovementsReport = ({ payments, reportDate }) => (
  <div className="space-y-5" data-testid="section-cash-movements">
    <SectionHeader title="Kasa Hareketleri" description={`${reportDate} tarihinde işlenen geçerli tahsilatlar`} />
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Hareketler ({payments.rows?.length || 0})</CardTitle></CardHeader>
      <CardContent className="p-0 overflow-x-auto">
        {(payments.rows || []).length ? <table className="w-full text-sm">
          <thead><tr className="border-b bg-gray-50"><th className="text-left p-3">Saat</th><th className="text-left p-3">Yöntem</th><th className="text-left p-3">İşleyen</th><th className="text-left p-3">Referans / Not</th><th className="text-right p-3">Tutar</th></tr></thead>
          <tbody>{payments.rows.map((row, index) => <tr key={row.id || index} className="border-b"><td className="p-3 whitespace-nowrap">{formatDateTime(row.processed_at)}</td><td className="p-3">{row.method || '-'}</td><td className="p-3">{row.processed_by || '-'}</td><td className="p-3">{row.reference || row.notes || '-'}</td><td className="p-3 text-right font-semibold">{formatCurrency(row.amount)}</td></tr>)}</tbody>
          <tfoot><tr className="bg-emerald-50"><td colSpan={4} className="p-3 font-semibold">Toplam geçerli tahsilat</td><td className="p-3 text-right font-bold">{formatCurrency(payments.total_paid || 0)}</td></tr></tfoot>
        </table> : <div className="py-12"><EmptyState icon={ArrowLeftRight} message="Seçili tarihte kasa hareketi yok" /></div>}
      </CardContent>
    </Card>
  </div>
);

const RateControlReport = ({ rows, reportDate }) => (
  <div className="space-y-5" data-testid="section-rate-control">
    <SectionHeader title="Oda Fiyat Kontrol Listesi" description={`${reportDate} tarihinde konaklayan odaların tanımlı ve satılan fiyat karşılaştırması`} />
    <Card><CardContent className="p-0 overflow-x-auto">
      {rows.length ? <table className="w-full text-sm">
        <thead><tr className="border-b bg-gray-50"><th className="text-left p-3">Oda</th><th className="text-left p-3">Oda Tipi</th><th className="text-left p-3">Misafir</th><th className="text-right p-3">Tanımlı Fiyat</th><th className="text-right p-3">Satılan Fiyat</th><th className="text-right p-3">Fark</th></tr></thead>
        <tbody>{rows.map((row, index) => <tr key={row.booking_id || index} className="border-b"><td className="p-3 font-semibold">{row.room_number}</td><td className="p-3">{row.room_type || '-'}</td><td className="p-3">{row.guest_name || '-'}</td><td className="p-3 text-right">{formatCurrency(row.base_rate)}</td><td className="p-3 text-right">{formatCurrency(row.sold_rate)}</td><td className={`p-3 text-right font-semibold ${row.variance < 0 ? 'text-rose-600' : row.variance > 0 ? 'text-emerald-600' : ''}`}>{formatCurrency(row.variance)}</td></tr>)}</tbody>
      </table> : <div className="py-12"><EmptyState icon={BedDouble} message="Seçili tarihte fiyat kontrol kaydı yok" /></div>}
    </CardContent></Card>
  </div>
);

const DailyAnalysisReport = ({ analysis }) => (
  <div className="space-y-5" data-testid="section-daily-analysis">
    <SectionHeader title="Günlük Analiz Raporu" description={`${analysis.date || ''} tarihli operasyon ve finans özeti`} />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Doluluk" value={`${analysis.occupancy_percentage || 0}%`} icon={BedDouble} color="blue" />
      <KPICard title="Oda Geliri" value={analysis.room_revenue || 0} icon={DollarSign} color="green" />
      <KPICard title="ADR" value={analysis.adr || 0} icon={BarChart3} color="purple" />
      <KPICard title="RevPAR" value={analysis.revpar || 0} icon={BarChart3} color="cyan" />
    </div>
    <Card><CardContent className="p-5 grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
      <div><p className="text-gray-500">Dolu / Toplam oda</p><p className="font-bold text-lg">{analysis.occupied_rooms || 0} / {analysis.total_rooms || 0}</p></div>
      <div><p className="text-gray-500">Giriş / Çıkış</p><p className="font-bold text-lg">{analysis.arrivals || 0} / {analysis.departures || 0}</p></div>
      <div><p className="text-gray-500">Konaklayan misafir</p><p className="font-bold text-lg">{analysis.in_house_guests || 0}</p></div>
      <div><p className="text-gray-500">Tahsilat</p><p className="font-bold text-lg">{formatCurrency(analysis.collections || 0)}</p></div>
      <div><p className="text-gray-500">ADR</p><p className="font-bold text-lg">{formatCurrency(analysis.adr || 0)}</p></div>
      <div><p className="text-gray-500">RevPAR</p><p className="font-bold text-lg">{formatCurrency(analysis.revpar || 0)}</p></div>
    </CardContent></Card>
  </div>
);

export default function ManagerDailyReports({ section, data, reportDate }) {
  if (section === 'front_cashier') return <FrontCashierReport summary={data?.front_cashier || {}} reportDate={reportDate} />;
  if (section === 'cash_movements') return <CashMovementsReport payments={data?.payments || {}} reportDate={reportDate} />;
  if (section === 'rate_control') return <RateControlReport rows={data?.room_rate_control || []} reportDate={reportDate} />;
  return <DailyAnalysisReport analysis={data?.daily_analysis || { date: reportDate }} />;
}
