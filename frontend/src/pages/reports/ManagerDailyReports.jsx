import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeftRight, Banknote, BarChart3, BedDouble, CreditCard, HandCoins, ReceiptText } from 'lucide-react';
import { EmptyState, KPICard, SectionHeader, formatCurrency } from './ReportHelpers';

const formatDateTime = value => value ? new Date(value).toLocaleString('tr-TR') : '-';
const CurrencyBreakdown = ({ totals = {}, fallback }) => {
  const entries = Object.entries(totals);
  return entries.length
    ? <>{entries.map(([code, amount]) => <div key={code}>{formatCurrency(amount, code)}</div>)}</>
    : <>{fallback == null ? '-' : formatCurrency(fallback)}</>;
};

const BalanceEffect = ({ totals = {}, fallback }) => {
  const entries = Object.entries(totals);
  const values = entries.length ? entries : [[undefined, Number(fallback || 0)]];
  return <div className="space-y-1">{values.map(([code, rawAmount]) => {
    const amount = Number(rawAmount || 0);
    const label = amount < 0
      ? 'Önceki bakiyeden tahsilat'
      : amount > 0
        ? 'Gün içinde oluşan açık bakiye'
        : 'Günlük folyo ve tahsilat dengeli';
    return <div key={code || 'fallback'}>
      <p className={`font-bold text-lg ${amount < 0 ? 'text-emerald-700' : amount > 0 ? 'text-amber-700' : ''}`}>
        {formatCurrency(Math.abs(amount), code)}
      </p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>;
  })}</div>;
};

const FrontCashierReport = ({ summary, payments, reportDate }) => (
  <div className="space-y-5" data-testid="section-front-cashier">
    <SectionHeader title="Ön Kasa Raporu" description={`${reportDate} tarihli folyo ve tahsilat özeti`} />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Folyo İşlem Tutarı" value={<CurrencyBreakdown totals={summary.charge_total_by_currency} fallback={summary.charge_total} />} icon={ReceiptText} color="amber" />
      <KPICard title="Toplam Tahsilat" value={<CurrencyBreakdown totals={payments.totals_by_currency} />} icon={HandCoins} color="green" />
      <KPICard title="Nakit Tahsilat" value={<CurrencyBreakdown totals={payments.totals_by_method_currency?.cash} />} icon={Banknote} color="blue" />
      <KPICard title="Kart / Havale Tahsilatı" value={<CurrencyBreakdown totals={Object.entries(payments.totals_by_method_currency || {}).filter(([method]) => method !== 'cash').reduce((result, [, totals]) => { Object.entries(totals).forEach(([code, amount]) => { result[code] = (result[code] || 0) + amount; }); return result; }, {})} />} icon={CreditCard} color="purple" />
    </div>
    <Card><CardContent className="p-5 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div><p className="text-gray-500">Folyo hareketi</p><p className="font-bold text-lg">{summary.charge_count || 0}</p></div>
      <div><p className="text-gray-500">Ödeme hareketi</p><p className="font-bold text-lg">{summary.payment_count || 0}</p></div>
      <div><p className="text-gray-500">Net nakit tahsilatı</p><p className="font-bold text-lg"><CurrencyBreakdown totals={summary.net_cash_movement_by_currency} fallback={summary.net_cash_movement} /></p></div>
      <div><p className="text-gray-500">Günlük bakiye etkisi</p><BalanceEffect totals={summary.daily_balance_change_by_currency} fallback={summary.daily_balance_change} /></div>
      <div><p className="text-gray-500">Tahsil edilmemiş yeni tutar</p><p className="font-bold text-lg"><CurrencyBreakdown totals={summary.uncollected_charges_by_currency} fallback={summary.uncollected_charges} /></p></div>
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
          <thead><tr className="border-b bg-gray-50"><th className="text-left p-3">Saat</th><th className="text-left p-3">Oda</th><th className="text-left p-3">Misafir</th><th className="text-left p-3">Yöntem</th><th className="text-left p-3">İşleyen</th><th className="text-left p-3">Referans / Not</th><th className="text-right p-3">Tutar</th></tr></thead>
          <tbody>{payments.rows.map((row, index) => <tr key={row.id || index} className="border-b"><td className="p-3 whitespace-nowrap">{formatDateTime(row.processed_at)}</td><td className="p-3 font-semibold">{row.room_number || '-'}</td><td className="p-3">{row.guest_name || '-'}</td><td className="p-3">{row.method || '-'}</td><td className="p-3">{row.processed_by || '-'}</td><td className="p-3">{row.reference || row.notes || '-'}</td><td className="p-3 text-right font-semibold">{formatCurrency(row.received_amount ?? row.amount, row.received_currency || row.currency)}</td></tr>)}</tbody>
          <tfoot><tr className="bg-emerald-50"><td colSpan={6} className="p-3 font-semibold">Para birimine göre geçerli tahsilat</td><td className="p-3 text-right font-bold">{Object.entries(payments.totals_by_currency || {}).map(([code, amount]) => <div key={code}>{formatCurrency(amount, code)}</div>)}</td></tr></tfoot>
        </table> : <div className="py-12"><EmptyState icon={ArrowLeftRight} message="Seçili tarihte kasa hareketi yok" /></div>}
      </CardContent>
    </Card>
    {(payments.currency_exchanges || []).length > 0 && <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Döviz Bozdurma İşlemleri ({payments.currency_exchanges.length})</CardTitle></CardHeader>
      <CardContent className="p-0 overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="border-b bg-gray-50"><th className="text-left p-3">Saat</th><th className="text-left p-3">Oda</th><th className="text-left p-3">Misafir</th><th className="text-right p-3">Bozdurulan</th><th className="text-right p-3">Kur</th><th className="text-right p-3">Kasaya Giren</th><th className="text-left p-3">İşleyen / Not</th></tr></thead>
        <tbody>{payments.currency_exchanges.map((row, index) => <tr key={row.id || index} className="border-b"><td className="p-3 whitespace-nowrap">{formatDateTime(row.created_at)}</td><td className="p-3 font-semibold">{row.room_number || '-'}</td><td className="p-3">{row.guest_name || '-'}</td><td className="p-3 text-right font-semibold">{formatCurrency(row.source_amount || 0, row.source_currency)}</td><td className="p-3 text-right">{Number(row.rate || 0).toLocaleString('tr-TR', { minimumFractionDigits: 4 })}</td><td className="p-3 text-right font-semibold text-emerald-700">{formatCurrency(row.target_amount || 0, row.target_currency || 'TRY')}</td><td className="p-3">{row.created_by || '-'}{row.note ? ` · ${row.note}` : ''}</td></tr>)}</tbody>
      </table></CardContent>
    </Card>}
  </div>
);

const RateControlReport = ({ rows, reportDate }) => (
  <div className="space-y-5" data-testid="section-rate-control">
    <SectionHeader title="Oda Fiyat Kontrol Listesi" description={`${reportDate} tarihindeki rezervasyon gece fiyatı ile folyoya işlenen tutarın karşılaştırması`} />
    <Card><CardContent className="p-0 overflow-x-auto">
      {rows.length ? <table className="w-full text-sm">
        <thead><tr className="border-b bg-gray-50"><th className="text-left p-3">Oda</th><th className="text-left p-3">Oda Tipi</th><th className="text-left p-3">Misafir</th><th className="text-right p-3">Rezervasyon Gece Fiyatı</th><th className="text-right p-3">Folyoya İşlenen</th><th className="text-right p-3">Fark</th><th className="text-left p-3">Durum</th></tr></thead>
        <tbody>{rows.map((row, index) => <tr key={row.booking_id || index} className="border-b"><td className="p-3 font-semibold">{row.room_number}</td><td className="p-3">{row.room_type || '-'}</td><td className="p-3">{row.guest_name || '-'}</td><td className="p-3 text-right">{formatCurrency(row.agreed_rate, row.currency)}</td><td className="p-3 text-right">{formatCurrency(row.posted_rate, row.currency)}</td><td className={`p-3 text-right font-semibold ${row.variance !== 0 ? 'text-rose-600' : 'text-emerald-600'}`}>{formatCurrency(row.variance, row.currency)}</td><td className="p-3">{row.posting_status === 'posted' ? 'İşlendi' : 'Gün sonu bekliyor'}</td></tr>)}</tbody>
      </table> : <div className="py-12"><EmptyState icon={BedDouble} message="Seçili tarihte fiyat kontrol kaydı yok" /></div>}
    </CardContent></Card>
  </div>
);

const DailyAnalysisReport = ({ analysis }) => (
  <div className="space-y-5" data-testid="section-daily-analysis">
    <SectionHeader title="Günlük Analiz Raporu" description={`${analysis.date || ''} tarihli operasyon ve finans özeti`} />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Doluluk" value={`${analysis.occupancy_percentage || 0}%`} icon={BedDouble} color="blue" />
      <KPICard title={analysis.revenue_source === 'accrued' ? 'Tahakkuk Eden Oda Geliri' : 'Folyoya İşlenen Oda Geliri'} value={<CurrencyBreakdown totals={analysis.room_revenue_by_currency} fallback={analysis.room_revenue} />} icon={ReceiptText} color="green" />
      <KPICard title="Satılan Oda Başına Ortalama Fiyat" value={<CurrencyBreakdown totals={analysis.adr_by_currency} fallback={analysis.adr} />} icon={BarChart3} color="purple" />
      <KPICard title="Satılabilir Oda Başına Gelir" value={<CurrencyBreakdown totals={analysis.revpar_by_currency} fallback={analysis.revpar} />} icon={BarChart3} color="cyan" />
    </div>
    {analysis.revenue_source === 'accrued' && <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
      Gün sonu oda tahakkukları tamamlanmadığı için ortalama fiyat ve oda başına gelir, rezervasyonların tahakkuk eden gece tutarından hesaplanır. Folyoya işlenen tutar aşağıda ayrıca gösterilir.
    </div>}
    <Card><CardContent className="p-5 grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
      <div><p className="text-gray-500">Dolu / Toplam oda</p><p className="font-bold text-lg">{analysis.occupied_rooms || 0} / {analysis.total_rooms || 0}</p></div>
      <div><p className="text-gray-500">Giriş / Çıkış</p><p className="font-bold text-lg">{analysis.arrivals || 0} / {analysis.departures || 0}</p></div>
      <div><p className="text-gray-500">Konaklayan misafir</p><p className="font-bold text-lg">{analysis.in_house_guests || 0}</p></div>
      <div><p className="text-gray-500">Tahsilat</p><p className="font-bold text-lg"><CurrencyBreakdown totals={analysis.collections_by_currency} fallback={analysis.collections} /></p></div>
      <div><p className="text-gray-500">Hesaplamada kullanılan oda geliri</p><p className="font-bold text-lg"><CurrencyBreakdown totals={analysis.room_revenue_by_currency} fallback={analysis.room_revenue} /></p><p className="text-xs text-gray-400">{analysis.revenue_source === 'accrued' ? 'Tahakkuk eden gece tutarı' : 'Folyoya işlenmiş tutar'}</p></div>
      <div><p className="text-gray-500">Folyoya işlenen oda geliri</p><p className="font-bold text-lg"><CurrencyBreakdown totals={analysis.posted_room_revenue_by_currency} fallback={analysis.posted_room_revenue} /></p></div>
      <div><p className="text-gray-500">Satılan oda başına ortalama fiyat</p><p className="font-bold text-lg"><CurrencyBreakdown totals={analysis.adr_by_currency} fallback={analysis.adr} /></p></div>
      <div><p className="text-gray-500">Satılabilir oda başına gelir</p><p className="font-bold text-lg"><CurrencyBreakdown totals={analysis.revpar_by_currency} fallback={analysis.revpar} /></p></div>
    </CardContent></Card>
  </div>
);

export default function ManagerDailyReports({ section, data, reportDate }) {
  if (section === 'front_cashier') return <FrontCashierReport summary={data?.front_cashier || {}} payments={data?.payments || {}} reportDate={reportDate} />;
  if (section === 'cash_movements') return <CashMovementsReport payments={data?.payments || {}} reportDate={reportDate} />;
  if (section === 'rate_control') return <RateControlReport rows={data?.room_rate_control || []} reportDate={reportDate} />;
  return <DailyAnalysisReport analysis={data?.daily_analysis || { date: reportDate }} />;
}
