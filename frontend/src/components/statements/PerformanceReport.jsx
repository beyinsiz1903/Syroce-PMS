import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Download, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import apiErrorText from '@/utils/apiErrorText';
import { money } from '@/components/statements/StatementsWorkspace';

// Money is never combined across currencies. Split the wide report into task-
// oriented views; every monetary cell retains its currency and its own space.
const VIEWS = { sales: 'Satış performansı', receivables: 'Alacak ve takip', forward: 'Gelecek satışlar' };
const localDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const firstOfMonth = () => { const now = new Date(); return localDate(new Date(now.getFullYear(), now.getMonth(), 1)); };
const overdueOf = aging => (aging?.overdue_1_30 || 0) + (aging?.overdue_31_60 || 0) + (aging?.overdue_61_90 || 0) + (aging?.overdue_90_plus || 0);
const pct = value => `%${(Number(value || 0) * 100).toLocaleString('tr-TR', { maximumFractionDigits: 1 })}`;
const amountText = (value, currency) => money(value, currency === 'UNKNOWN' || !currency ? '(para birimi eksik)' : currency).trim();
const dateText = value => String(value || '').split('-').reverse().join('.');
const HEADER = 'min-w-[140px] border-l border-slate-200 px-4 py-3 text-right align-middle font-medium leading-5 text-slate-600';
const CELL = 'min-w-[140px] border-l border-slate-100 px-4 py-4 text-right align-top tabular-nums';
const NUMBER = 'block whitespace-nowrap font-medium text-slate-900 dark:text-slate-100';

function Stat({ label, value, detail, tone = '' }) {
  return <div className="min-w-0 rounded-lg border border-slate-200 p-3">
    <div className="text-xs leading-5 text-slate-500">{label}</div>
    <div className={`mt-1 break-words text-base font-semibold tabular-nums ${tone}`}>{value}</div>
    {detail && <div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div>}
  </div>;
}

function DirectionalAmounts({ agency, hotel, currency }) {
  return <div className="space-y-1.5 text-xs">
    <div><span className="block text-slate-500">Acente → otel</span><span className={NUMBER}>{amountText(agency, currency)}</span></div>
    <div><span className="block text-slate-500">Otel → acente</span><span className={NUMBER}>{amountText(hotel, currency)}</span></div>
  </div>;
}

const CSV_FORMULA_LEAD = /^[=+\-@\t\r]/;
export const csvCell = value => {
  let text = String(value ?? '');
  if (typeof value === 'string' && CSV_FORMULA_LEAD.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
};

export function toCsv(report, partyLabel) {
  const header = [partyLabel, 'Para birimi', 'Rezervasyon', 'İptal', 'No-show', 'İptal oranı', 'Oda-gece', 'Brüt satış', 'Komisyon', 'Satışların otele net tutarı', 'İptal/no-show cezası',
    'Açık: acente→otel', 'Açık: otel→acente', 'Vadesi gelmemiş', 'Vadesi geçen 1-30', '31-60', '61-90', '90+', 'Mutabakat bekleyen',
    'Faturalanmamış acente→otel', 'Faturalanmamış otel→acente', 'Bekleyen bildirim', 'Gelecek 30 gün', 'Gelecek 60 gün', 'Gelecek 90 gün', 'Son 7 gün yeni', 'Son 7 gün iptal'];
  const rows = (report.rows || []).map(row => {
    const { performance: p, receivables: r, unbilled: u, forward: f, pickup_7d: k } = row;
    return [row.party_name || row.party_id, row.currency, p.bookings, p.cancelled, p.no_show || 0, p.cancel_rate, p.room_nights, p.gross, p.commission, p.net_to_hotel, p.penalty || 0,
      r.agency_owes_hotel, r.hotel_owes_agency, r.aging.not_due, r.aging.overdue_1_30, r.aging.overdue_31_60, r.aging.overdue_61_90, r.aging.overdue_90_plus,
      r.awaiting_agreement, u.agency_owes_hotel, u.hotel_owes_agency, r.pending_notices.count, f['30'].bookings, f['60'].bookings, f['90'].bookings, k.bookings, k.cancelled];
  });
  return [header, ...rows].map(cells => cells.map(csvCell).join(';')).join('\n');
}

export function reportPeriodError(period) {
  const validDay = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && Number.isFinite(Date.parse(value))
    && new Date(value).toISOString().slice(0, 10) === value;
  if (!validDay(period.start) || !validDay(period.end)) return 'Geçerli bir başlangıç ve bitiş tarihi seçin.';
  if (period.end < period.start) return 'Dönem bitişi başlangıçtan önce olamaz.';
  if ((Date.parse(period.end) - Date.parse(period.start)) / 86400000 > 366) return 'Rapor dönemi en fazla bir yıl olabilir.';
  return '';
}

function PartyCell({ row }) {
  return <th scope="row" className="min-w-[200px] max-w-[280px] px-4 py-4 text-left align-top font-medium">
    <div className="break-words leading-5 text-slate-900 dark:text-slate-100">{row.party_name || row.party_id}</div>
    <span className="mt-1 inline-block rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{row.currency === 'UNKNOWN' ? 'Para birimi eksik' : row.currency}</span>
  </th>;
}

function MoneyCell({ value, currency, tone = '' }) {
  return <td className={CELL}><span className={`block whitespace-nowrap font-medium ${tone || 'text-slate-900 dark:text-slate-100'}`}>{amountText(value, currency)}</span></td>;
}

function ReportTable({ rows, view, partyLabel, report }) {
  const headers = view === 'sales'
    ? ['Rezervasyon', 'Oda-gece', 'Brüt satış', 'Komisyon', 'Otele net', 'İptal / no-show']
    : view === 'receivables'
      ? ['Açık: acente → otel', 'Açık: otel → acente', 'Vadesi geçen', 'Mutabakat bekleyen', 'Faturalanmamış', 'Bekleyen ödeme bildirimi']
      : ['Gelecek 30 gün', 'Gelecek 60 gün', 'Gelecek 90 gün', 'Son 7 gün: yeni', 'Son 7 gün: iptal'];
  return <div className="max-w-full overflow-x-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-500"
    role="region" aria-label={`${VIEWS[view]} tablosu`} tabIndex={0} data-testid="performance-table-scroll">
    <table className="w-full min-w-[1120px] border-separate border-spacing-0 text-sm">
      <caption className="sr-only">{VIEWS[view]} · Giriş dönemi {dateText(report.period_start)} – {dateText(report.period_end)} · Para birimleri ayrı gösterilir</caption>
      <thead className="bg-slate-50 dark:bg-slate-900"><tr>
        <th scope="col" className="min-w-[200px] px-4 py-3 text-left font-medium text-slate-600">{partyLabel} / para birimi</th>
        {headers.map(label => <th key={label} scope="col" className={HEADER}>{label}</th>)}
      </tr></thead>
      <tbody>{rows.map(row => {
        const p = row.performance || {}, r = row.receivables || {}, u = row.unbilled || {};
        const f = row.forward || {}, k = row.pickup_7d || {}, currency = row.currency;
        const overdue = overdueOf(r.aging);
        return <tr key={`${row.party_id}-${currency}`} className="[&>td]:border-t [&>th]:border-t hover:bg-slate-50/70"
          data-testid={`performance-row-${row.party_id}-${currency}`}>
          <PartyCell row={row} />
          {view === 'sales' && <>
            <td className={CELL}><span className={NUMBER}>{p.bookings || 0}</span></td>
            <td className={CELL}><span className={NUMBER}>{p.room_nights || 0}</span></td>
            <MoneyCell value={p.gross} currency={currency} />
            <MoneyCell value={p.commission} currency={currency} />
            <MoneyCell value={p.net_to_hotel} currency={currency} />
            <td className={CELL}><div className="whitespace-nowrap">{p.cancelled || 0} iptal · {pct(p.cancel_rate)}</div>
              <div className="mt-1 whitespace-nowrap text-xs text-slate-500">{p.no_show || 0} no-show</div>
              {p.penalty > 0 && <div className="mt-1 whitespace-nowrap text-xs text-slate-600">Ceza: {amountText(p.penalty, currency)}</div>}
            </td>
          </>}
          {view === 'receivables' && <>
            <MoneyCell value={r.agency_owes_hotel} currency={currency} />
            <MoneyCell value={r.hotel_owes_agency} currency={currency} />
            <MoneyCell value={overdue} currency={currency} tone={overdue > 0 ? 'text-red-700' : ''} />
            <MoneyCell value={r.awaiting_agreement} currency={currency} />
            <td className={CELL}>{u.bookings > 0 ? <><div className="mb-2 text-xs text-slate-500">{u.bookings} rezervasyon</div>
              <DirectionalAmounts agency={u.agency_owes_hotel} hotel={u.hotel_owes_agency} currency={currency} /></> : <span aria-label="Faturalanmamış rezervasyon yok">—</span>}</td>
            <td className={CELL}>{r.pending_notices?.count > 0 ? <><div className="mb-2 text-xs text-slate-500">{r.pending_notices.count} bildirim</div>
              <DirectionalAmounts agency={r.pending_notices.agency_to_hotel} hotel={r.pending_notices.hotel_to_agency} currency={currency} /></> : <span aria-label="Bekleyen ödeme bildirimi yok">—</span>}</td>
          </>}
          {view === 'forward' && <>
            {[30, 60, 90].map(days => <td key={days} className={CELL}><span className={NUMBER}>{f[days]?.bookings || 0} rezervasyon</span>
              <div className="mt-1 whitespace-nowrap text-xs text-slate-500">{amountText(f[days]?.gross, currency)} · {f[days]?.room_nights || 0} oda-gece</div></td>)}
            <td className={CELL}><span className={NUMBER}>+{k.bookings || 0} rezervasyon</span><div className="mt-1 whitespace-nowrap text-xs text-slate-500">{amountText(k.gross, currency)}</div></td>
            <td className={CELL}><span className={NUMBER}>−{k.cancelled || 0} rezervasyon</span></td>
          </>}
        </tr>;
      })}</tbody>
    </table>
  </div>;
}

export default function PerformanceReport({ side, api, path }) {
  const partyLabel = side === 'hotel' ? 'Acente' : 'Otel';
  const [period, setPeriod] = useState({ start: firstOfMonth(), end: localDate(new Date()) });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState('sales');
  const { start, end } = period;

  // Never show a previous period's prices under newly selected dates.
  const latest = useRef(0);
  const load = useCallback(async () => {
    const request = ++latest.current;
    setReport(null);
    const invalid = reportPeriodError({ start, end });
    setError(invalid);
    if (invalid) { setLoading(false); return; }
    setLoading(true);
    try {
      const { data } = await api.get(path, { params: { period_start: start, period_end: end } });
      if (request !== latest.current) return;
      if (!Array.isArray(data?.rows) || !Array.isArray(data?.totals)) throw new Error('Rapor yanıtı doğrulanamadı. Lütfen yeniden deneyin.');
      setReport(data);
    } catch (err) {
      if (request === latest.current) {
        const message = apiErrorText(err, 'Rapor yüklenemedi.');
        setError(message);
        toast.error(message);
      }
    } finally { if (request === latest.current) setLoading(false); }
  }, [api, path, start, end]);
  useEffect(() => { load(); return () => { latest.current += 1; }; }, [load]);

  const rows = report?.rows || [];
  const totals = report?.totals || [];
  const download = () => {
    const blob = new Blob(['\ufeff' + toCsv(report, partyLabel)], { type: 'text/csv;charset=utf-8' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = `acente-performans-${report.period_start}-${report.period_end}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return <div className="min-w-0 space-y-4" data-testid="performance-report" aria-busy={loading}>
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Performans ve alacak</CardTitle>
        <p className="text-sm leading-6 text-slate-500">Satışlar seçilen giriş tarihine göre hesaplanır. Alacaklar ve gelecek satışlar rapor günündeki durumu gösterir. Para birimleri birbirine eklenmez.</p>
        <p className="text-xs leading-5 text-slate-500">Otele net tutar = brüt satış − acente komisyonu. Bu tutar kâr veya ödenecek bakiye değildir.</p>
      </CardHeader>
      <CardContent className="grid gap-3 sm:flex sm:flex-wrap sm:items-end">
        <div className="min-w-0 space-y-1.5 sm:min-w-[180px]"><Label htmlFor={`perf-start-${side}`} className="block text-sm">Giriş tarihi başlangıç</Label><Input id={`perf-start-${side}`} type="date" value={period.start} onChange={e => setPeriod(p => ({ ...p, start: e.target.value }))} /></div>
        <div className="min-w-0 space-y-1.5 sm:min-w-[180px]"><Label htmlFor={`perf-end-${side}`} className="block text-sm">Bitiş</Label><Input id={`perf-end-${side}`} type="date" value={period.end} onChange={e => setPeriod(p => ({ ...p, end: e.target.value }))} /></div>
        <Button variant="outline" onClick={load} disabled={loading}>{loading ? <Loader2 size={14} className="mr-2 animate-spin" /> : <RefreshCw size={14} className="mr-2" />}Yenile</Button>
        {rows.length > 0 && <Button variant="outline" onClick={download}><Download size={14} className="mr-2" />CSV indir</Button>}
      </CardContent>
    </Card>

    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
    {loading && <div role="status" className="flex items-center gap-2 rounded-lg border bg-white p-4 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" />Seçilen dönemin raporu yükleniyor…</div>}

    {totals.map(total => {
      const r = total.receivables || {}, overdue = overdueOf(r.aging);
      return <Card key={total.currency} data-testid={`performance-totals-${total.currency}`}>
        <CardHeader className="pb-3"><CardTitle className="text-sm">{total.currency === 'UNKNOWN' ? 'Para birimi eksik kayıtlar' : `${total.currency} özeti`}</CardTitle>
          <p className="text-xs text-slate-500">Giriş dönemi: {dateText(report.period_start)} – {dateText(report.period_end)}</p></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Brüt satış" value={amountText(total.performance?.gross, total.currency)} />
          <Stat label="Acente komisyonu" value={amountText(total.performance?.commission, total.currency)} />
          <Stat label="Satışların otele net tutarı" value={amountText(total.performance?.net_to_hotel, total.currency)} />
          <Stat label="İptal oranı" value={pct(total.performance?.cancel_rate)} detail={`İptal / no-show cezası: ${amountText(total.performance?.penalty, total.currency)}`} />
          <Stat label="Açık: acente → otel" value={amountText(r.agency_owes_hotel, total.currency)} />
          <Stat label="Açık: otel → acente" value={amountText(r.hotel_owes_agency, total.currency)} />
          <Stat label="Vadesi geçen" value={amountText(overdue, total.currency)} tone={overdue > 0 ? 'text-red-700' : ''} />
          <Stat label="Faturalanmamış" value={<DirectionalAmounts agency={total.unbilled?.agency_owes_hotel} hotel={total.unbilled?.hotel_owes_agency} currency={total.currency} />} />
        </CardContent>
      </Card>;
    })}

    {report && (rows.length === 0 ? <p className="rounded-lg border bg-white p-4 text-sm text-slate-500">Seçilen dönemde satış veya açık alacak kaydı yok.</p> : <Card className="min-w-0 overflow-hidden">
      <Tabs value={view} onValueChange={setView}>
      <CardHeader className="gap-3 pb-3">
        <div><CardTitle className="text-base">{partyLabel} bazında detay</CardTitle><p className="mt-1 text-xs leading-5 text-slate-500">Her tutar kendi para birimiyle gösterilir. Dar ekranlarda yalnız tabloyu yatay kaydırabilirsiniz.</p></div>
          <TabsList className="h-auto w-full flex-wrap justify-start gap-1 p-1">
            {Object.entries(VIEWS).map(([key, label]) => <TabsTrigger key={key} value={key} className="min-h-9">{label}</TabsTrigger>)}
          </TabsList>
      </CardHeader>
      <TabsContent value={view} className="mt-0"><CardContent className="min-w-0 p-0"><ReportTable rows={rows} view={view} partyLabel={partyLabel} report={report} /></CardContent></TabsContent>
      </Tabs>
    </Card>)}
    {report && <p className="text-xs leading-5 text-slate-500">Vade: ekstrenin iki tarafça onaylandığı gün + sözleşmedeki ödeme vadesi (ön ödemeli ve girişte ödemeli 0 gün, vadeli 7/15/30 gün). Faturalanmamış: konaklaması başlamış, henüz hiçbir ekstrede yer almayan satışlar. Borç ve alacak yönleri birbirinden düşülmez. Rapor tarihi {report.as_of}.</p>}
  </div>;
}
