import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';
import { validateReportDate } from '@/utils/reportExports';

const fields = [['subtotal', 'Ara toplam'], ['discount', 'İndirim'], ['net', 'Net (vergi hariç)'], ['vat', 'KDV'], ['city_tax', 'Konaklama vergisi'], ['other_tax', 'Diğer / ayrıştırılmamış vergi'], ['difference', 'Açıklanamayan fark'], ['total', 'Toplam (vergi dahil)']];
const dayText = day => new Date(`${day}T12:00:00Z`).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', timeZone: 'UTC' });
const moneyText = (value, code) => value == null ? `Doğrulanamadı (${code})` : formatCurrencyBreakdown({ [code]: value }, 0, code);
const axisText = value => new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2, notation: Math.abs(value) >= 10000 ? 'compact' : 'standard' }).format(value);
const shift = (day, offset) => { const value = validateReportDate(day); value.setUTCDate(value.getUTCDate() + offset); return value.toISOString().slice(0, 10); };
const rangeFor = (day, period) => [period === 'daily' ? day : shift(day, -29), day];
function Amounts({ values, field }) {
  const entries = Object.entries(values || {});
  if (!entries.length) return '—';
  return entries.map(([code, value]) => <div key={code}>{moneyText(field ? value[field] : value, code)}</div>);
}

export default function RevenueSection({ reportDate, reportPeriod = 'monthly' }) {
  const initial = rangeFor(reportDate || new Date().toISOString().slice(0, 10), reportPeriod);
  const [first, setFirst] = useState(initial[0]);
  const [last, setLast] = useState(initial[1]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [details, setDetails] = useState(false);
  const [currency, setCurrency] = useState('');
  const [revision, setRevision] = useState(0);
  const [exporting, setExporting] = useState(false);
  const generation = useRef(0);
  const activeScope = useRef('');
  const scope = JSON.stringify([first, last]);
  activeScope.current = scope;
  useEffect(() => {
    const [start, end] = rangeFor(reportDate || new Date().toISOString().slice(0, 10), reportPeriod);
    setFirst(start); setLast(end);
  }, [reportDate, reportPeriod]);
  useEffect(() => {
    const request = ++generation.current;
    let alive = true;
    setReport(null); setError(''); setLoading(false);
    try {
      const days = (validateReportDate(last) - validateReportDate(first)) / 86400000;
      if (days < 0 || days > 365) throw new Error('Geçerli bir tarih aralığı seçin (en fazla 366 gün).');
    } catch {
      setError('Geçerli bir tarih aralığı seçin; başlangıç bitişten sonra olamaz (en fazla 366 gün).');
      return;
    }
    setLoading(true);
    axios.get('/folio/reports/revenue-by-category', { params: { date_from: first, date_to: last } }).then(({ data }) => {
      if (!alive || request !== generation.current) return;
      if (data.date_from !== first || data.date_to !== last || !Array.isArray(data.rows) || !data.totals_by_currency || !data.snapshot) throw new Error('Gelir yanıtı seçili tarih aralığıyla eşleşmiyor.');
      setReport({ scope, data });
      setCurrency(previous => previous in data.totals_by_currency ? previous : Object.keys(data.totals_by_currency)[0] || 'TRY');
    }).catch(e => { if (alive && request === generation.current) setError(e.response?.data?.detail || e.message || 'Gelir alınamadı.'); })
      .finally(() => { if (alive && request === generation.current) setLoading(false); });
    return () => { alive = false; };
  }, [first, last, scope, revision]);
  const data = report?.scope === scope ? report.data : null;
  const currencies = Object.keys(data?.totals_by_currency || {});
  const visibleFields = details ? fields : fields.filter(([key]) => ['net', 'total'].includes(key));
  const rows = data?.rows || [];
  const trend = (data?.revenue_trend || []).map(row => ({ ...row, label: dayText(row.date), value: row.revenue_by_currency?.[currency] ?? 0 }));
  const roomTypes = (data?.room_type_revenue || []).map(row => ({ ...row, value: row.revenue_by_currency?.[currency] ?? 0 }));
  const download = async () => {
    if (!data || exporting) return;
    const requestedScope = scope;
    setExporting(true); setError('');
    try {
      const response = await axios.get('/folio/reports/revenue-by-category/excel', { params: { date_from: first, date_to: last, snapshot: data.snapshot }, responseType: 'blob' });
      if (activeScope.current !== requestedScope) return;
      if (!String(response.headers?.['content-type']).includes('spreadsheetml')) throw new Error('Geçerli Excel çıktısı alınamadı.');
      const url = URL.createObjectURL(response.data), link = document.createElement('a');
      link.href = url; link.download = `gelir_${first}_${last}.xlsx`; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      if (activeScope.current !== requestedScope) return;
      if (e.response?.status === 409) { setReport(null); setError('Gelir verisi değişti. Yenile düğmesiyle tekrar yükleyin.'); }
      else setError(e.message || 'Excel indirilemedi.');
    } finally { setExporting(false); }
  };
  return <section data-testid="section-revenue" className="space-y-4">
    <div><h2 className="text-xl font-semibold">Gelir Raporu</h2><p className="text-sm text-muted-foreground">Tek tarih aralığı · aynı defterden kart, grafik, kategori ve Excel</p></div>
    <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3 print:hidden">
      <label className="text-sm">Başlangıç<input className="block rounded border bg-background p-2" aria-label="Gelir başlangıç tarihi" type="date" value={first} onChange={e => setFirst(e.target.value)} /></label>
      <label className="text-sm">Bitiş<input className="block rounded border bg-background p-2" aria-label="Gelir bitiş tarihi" type="date" value={last} onChange={e => setLast(e.target.value)} /></label>
      <Button variant="outline" onClick={() => setRevision(value => value + 1)} disabled={loading}>Yenile</Button>
      <Button variant="outline" onClick={download} disabled={!data || loading || exporting}>{exporting ? 'Hazırlanıyor…' : 'Excel indir'}</Button>
      <Button variant="outline" onClick={() => window.print()} disabled={!data || loading}>Yazdır / PDF</Button>
    </div>
    <p className="text-sm font-medium">{first} – {last} · İşlenen tutarlar (vergi dahil, iade düşülmüş, bahşiş hariç)</p>
    {loading && <p role="status">Yükleniyor…</p>}
    {error && <p role="alert" className="rounded border border-destructive p-3 text-destructive">{error}</p>}
    {!data && !loading && <p>Veri alınamadı.</p>}
    {data && <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <TotalCard label="Toplam işlenen tutar (vergi dahil)" values={data.totals_by_currency} field="total" />
        <TotalCard label="Net gelir (vergi hariç)" values={data.totals_by_currency} field="verified_net" />
        <TotalCard label="Konaklama (vergi dahil)" values={data.departments_by_currency?.room} />
        <TotalCard label="Yiyecek–içecek (minibar hariç)" values={data.departments_by_currency?.fnb} />
      </div>
      <p className="rounded-lg border bg-muted/30 p-3 text-sm">Tahsilat ve rezervasyon bedeli değildir. Oda ücreti henüz işlenmemişse burada gelir sayılmaz. Minibar ayrı satırdır. Vergi kırılımı olmayan eski kayıtlar sıfır vergili kabul edilmez.</p>
      {(data.reconciliation?.tax_unknown_count > 0 || data.reconciliation?.issue_count > 0) && <div role="status" className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950">
        {data.reconciliation.tax_unknown_count > 0 && <p>{data.reconciliation.tax_unknown_count} işlemin vergi kırılımı eksik; bu kapsamdaki net ve vergi toplamı doğrulanamadı.</p>}
        {data.reconciliation.issue_count > 0 && <p>{data.reconciliation.issue_count} kaynak harekette hesap uyuşmazlığı var. Farklar gizlenmedi; kaynak kayıt değiştirilmedi.</p>}
      </div>}
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Dönem kırılımı</h3><label className="text-sm print:hidden">Grafik para birimi <select aria-label="Gelir grafik para birimi" className="rounded border bg-background p-2" value={currency} onChange={e => setCurrency(e.target.value)}>{(currencies.length ? currencies : ['TRY']).map(code => <option key={code}>{code}</option>)}</select></label></div>
      <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Günlük işlenen tutar · {currency}</CardTitle></CardHeader><CardContent>
        <ResponsiveContainer width="100%" height={230}><AreaChart data={trend}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={18} /><YAxis tickFormatter={axisText} tick={{ fontSize: 11 }} />
          <Tooltip formatter={value => [moneyText(value, currency), 'İşlenen tutar']} /><Area type="linear" dataKey="value" name="İşlenen tutar" stroke="#059669" fill="#059669" fillOpacity={0.12} isAnimationActive={false} />
        </AreaChart></ResponsiveContainer>
      </CardContent></Card>
      <Card><CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2"><CardTitle className="text-sm">Kategori bazlı gelir</CardTitle><label className="text-sm print:hidden"><input type="checkbox" checked={details} onChange={e => setDetails(e.target.checked)} /> Vergi / indirim ayrıntıları</label></CardHeader><CardContent>
        <div className="overflow-x-auto"><table className="w-full text-sm" aria-label="Kategori bazlı gelir">
          <thead className="bg-muted"><tr><th className="p-2 text-left">Kategori</th><th className="p-2 text-right">İşlem</th>{visibleFields.map(([key, label]) => <th key={key} className="p-2 text-right">{label}</th>)}</tr></thead>
          <tbody>{rows.length ? rows.map(row => <tr key={row.category} className="border-t"><th scope="row" className="p-2 text-left font-medium" title={(row.source_categories || []).join(', ')}>{row.label}</th><td className="p-2 text-right">{row.count}</td>{visibleFields.map(([key]) => <td key={key} className={`p-2 text-right tabular-nums ${key === 'difference' ? 'text-amber-700' : ''}`}><Amounts values={row.by_currency} field={key === 'net' && !details ? 'verified_net' : key} /></td>)}</tr>) : <tr><td className="p-5 text-center" colSpan={visibleFields.length + 2}>Bu tarih aralığında işlem yok.</td></tr>}</tbody>
          {rows.length > 0 && <tfoot className="border-t bg-muted font-semibold"><tr><th scope="row" className="p-2 text-left">TOPLAM</th><td className="p-2 text-right">{data.totals?.count}</td>{visibleFields.map(([key]) => <td key={key} className="p-2 text-right"><Amounts values={data.totals_by_currency} field={key === 'net' && !details ? 'verified_net' : key} /></td>)}</tr></tfoot>}
        </table></div>
        <p className="mt-3 text-xs text-muted-foreground">Para birimleri ayrı tutulur. “Doğrulanamadı” sıfır değildir. Ayrıntılı görünümde kaynak kaydın neti ve açıklanamayan farkı ayrıca gösterilir. Upsell / extra bir hizmet kategorisi belirtmiyorsa sınıflandırılmamış olarak kalır.</p>
      </CardContent></Card>
      {roomTypes.length > 0 && <Card><CardHeader><CardTitle className="text-sm">Oda tipi bazlı konaklama geliri · {currency} (vergi dahil)</CardTitle></CardHeader><CardContent>
        <p className="mb-2 text-xs text-muted-foreground">Yalnız oda ücreti hareketleri; minibar, restoran ve diğer harcamalar dahil değildir. Eşleştirilemeyen kayıtlar toplamdan düşülmez.</p>
        <ResponsiveContainer width="100%" height={230}><BarChart data={roomTypes}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tickFormatter={axisText} tick={{ fontSize: 11 }} /><Tooltip formatter={value => [moneyText(value, currency), 'Konaklama']} /><Bar dataKey="value" name="Konaklama" fill="#0284c7" isAnimationActive={false} /></BarChart></ResponsiveContainer>
      </CardContent></Card>}
      {data.reconciliation?.issues?.length > 0 && <details className="rounded-lg border p-3 text-sm"><summary>Uyumsuz kaynak hareketleri ({data.reconciliation.issue_count})</summary><p className="my-2 text-xs">İlk 100 hareket gösterilir. Bu liste muhasebe düzeltmesi yapmaz.</p>{data.reconciliation.issues.map((issue, index) => <p key={`${issue.source}-${issue.id}-${index}`}>{issue.date} · {issue.source} / {issue.id || 'kimlik eksik'} · {issue.reasons.join('; ')} · {moneyText(issue.difference, issue.currency)}</p>)}</details>}
    </>}
  </section>;
}

function TotalCard({ label, values, field }) {
  return <Card><CardContent className="p-4"><h3 className="text-xs text-muted-foreground">{label}</h3><div className="mt-2 text-xl font-semibold tabular-nums"><Amounts values={values} field={field} /></div></CardContent></Card>;
}
