import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Download, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import apiErrorText from '@/utils/apiErrorText';
import { money } from '@/components/statements/StatementsWorkspace';

// Where do I sell, who owes whom and since when, what is waiting, what is
// coming: one row per hotel–agency pair and currency (never mixed). The
// numbers come from the same formula as the statements.

const localDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const firstOfMonth = () => { const now = new Date(); return localDate(new Date(now.getFullYear(), now.getMonth(), 1)); };
const overdueOf = aging => (aging?.overdue_1_30 || 0) + (aging?.overdue_31_60 || 0) + (aging?.overdue_61_90 || 0) + (aging?.overdue_90_plus || 0);
const pct = value => `%${(Number(value || 0) * 100).toLocaleString('tr-TR', { maximumFractionDigits: 1 })}`;

function Stat({ label, value, tone = '' }) {
  return <div className="rounded-lg border p-3"><div className="text-xs text-slate-500">{label}</div><div className={`text-base font-semibold ${tone}`}>{value}</div></div>;
}

// A text cell starting like a formula would run in a spreadsheet: prefix it.
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

export default function PerformanceReport({ side, api, path }) {
  const partyLabel = side === 'hotel' ? 'Acente' : 'Otel';
  const [period, setPeriod] = useState({ start: firstOfMonth(), end: localDate(new Date()) });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  // Only the latest request may fill the table: a slower answer for dates
  // the user already changed is dropped.
  const latest = useRef(0);
  const load = useCallback(async () => {
    const request = ++latest.current;
    setLoading(true);
    try {
      const { data } = await api.get(path, { params: { period_start: period.start, period_end: period.end } });
      if (request === latest.current) setReport(data);
    } catch (err) {
      if (request === latest.current) toast.error(apiErrorText(err, 'Rapor yüklenemedi.'));
    } finally { if (request === latest.current) setLoading(false); }
  }, [api, path, period.start, period.end]);
  useEffect(() => { load(); }, [load]);

  const rows = Array.isArray(report?.rows) ? report.rows : [];
  const totals = Array.isArray(report?.totals) ? report.totals : [];
  const download = () => {
    const blob = new Blob(['﻿' + toCsv(report, partyLabel)], { type: 'text/csv;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `acente-performans-${report.period_start}-${report.period_end}.csv`;
    link.click();
  };

  return (
    <div className="space-y-4" data-testid="performance-report">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Performans ve alacak</CardTitle>
          <p className="text-xs text-slate-500">Performans seçilen dönemde girişi olan rezervasyonlardan; alacaklar ve gelecek satışlar bugünün durumundan hesaplanır. Para birimleri ayrı tutulur. "Satışların otele net tutarı" komisyon sonrası satış tutarıdır, kâr değildir.</p>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div><Label htmlFor={`perf-start-${side}`}>Giriş tarihi başlangıç</Label><Input id={`perf-start-${side}`} type="date" value={period.start} onChange={e => setPeriod(p => ({ ...p, start: e.target.value }))} /></div>
          <div><Label htmlFor={`perf-end-${side}`}>Bitiş</Label><Input id={`perf-end-${side}`} type="date" value={period.end} onChange={e => setPeriod(p => ({ ...p, end: e.target.value }))} /></div>
          <Button variant="outline" onClick={load} disabled={loading}>{loading ? <Loader2 size={14} className="mr-2 animate-spin" /> : <RefreshCw size={14} className="mr-2" />}Yenile</Button>
          {rows.length > 0 && <Button variant="outline" onClick={download}><Download size={14} className="mr-2" />CSV indir</Button>}
        </CardContent>
      </Card>

      {totals.map(total => {
        const r = total.receivables || {};
        const overdue = overdueOf(r.aging);
        return (
          <Card key={total.currency} data-testid={`performance-totals-${total.currency}`}>
            <CardHeader className="pb-2"><CardTitle className="text-sm">{total.currency} özeti</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Brüt satış" value={money(total.performance?.gross, total.currency)} />
              <Stat label="Acente komisyonu" value={money(total.performance?.commission, total.currency)} />
              <Stat label="Satışların otele net tutarı" value={money(total.performance?.net_to_hotel, total.currency)} />
              <Stat label="İptal oranı · ceza geliri" value={`${pct(total.performance?.cancel_rate)} · ${money(total.performance?.penalty, total.currency)}`} />
              <Stat label="Açık: acente → otel" value={money(r.agency_owes_hotel, total.currency)} />
              <Stat label="Açık: otel → acente" value={money(r.hotel_owes_agency, total.currency)} />
              <Stat label="Vadesi geçen" value={money(overdue, total.currency)} tone={overdue > 0 ? 'text-red-700' : ''} />
              <Stat label="Faturalanmamış (acente → otel / otel → acente)" value={`${money(total.unbilled?.agency_owes_hotel, '')} / ${money(total.unbilled?.hotel_owes_agency, total.currency)}`} />
            </CardContent>
          </Card>
        );
      })}

      {report && (rows.length === 0 ? <p className="text-sm text-slate-400">Henüz satış yok.</p> : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full min-w-[1100px] text-xs">
              <thead className="bg-slate-50 text-left dark:bg-slate-900">
                <tr>
                  <th className="p-2">{partyLabel}</th><th className="text-right">Rez.</th><th className="text-right">Oda-gece</th><th className="text-right">Brüt</th>
                  <th className="text-right">Komisyon</th><th className="text-right">Otele net</th><th className="text-right">İptal / no-show</th>
                  <th className="text-right">Açık acente→otel</th><th className="text-right">Açık otel→acente</th><th className="text-right">Vadesi geçen</th>
                  <th className="text-right">Mutabakat bekleyen</th><th className="text-right">Faturalanmamış</th><th className="text-right">Bekleyen bildirim</th>
                  <th className="text-right">Gelecek 30/60/90</th><th className="p-2 text-right">Son 7 gün</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => {
                  const { performance: p, receivables: r, unbilled: u, forward: f, pickup_7d: k } = row;
                  const overdue = overdueOf(r.aging);
                  return (
                    <tr key={`${row.party_id}-${row.currency}`} className="border-t" data-testid={`performance-row-${row.party_id}-${row.currency}`}>
                      <td className="p-2 font-medium">{row.party_name || row.party_id}<div className="text-slate-400">{row.currency}</div></td>
                      <td className="text-right">{p.bookings}</td><td className="text-right">{p.room_nights}</td>
                      <td className="text-right">{money(p.gross, '')}</td><td className="text-right">{money(p.commission, '')}</td>
                      <td className="text-right">{money(p.net_to_hotel, '')}</td><td className="text-right">{p.cancelled} ({pct(p.cancel_rate)}){p.no_show ? ` · ${p.no_show} no-show` : ''}{p.penalty ? <div className="text-slate-500">ceza {money(p.penalty, '')}</div> : null}</td>
                      <td className="text-right">{money(r.agency_owes_hotel, '')}</td><td className="text-right">{money(r.hotel_owes_agency, '')}</td>
                      <td className={`text-right ${overdue > 0 ? 'font-semibold text-red-700' : ''}`}>{money(overdue, '')}</td>
                      <td className="text-right">{money(r.awaiting_agreement, '')}</td>
                      <td className="text-right">{u.bookings > 0 ? `${u.bookings} rez. · ${money(u.agency_owes_hotel - u.hotel_owes_agency, '')}` : '—'}</td>
                      <td className="text-right">{r.pending_notices.count > 0 ? `${r.pending_notices.count} · ${money(r.pending_notices.agency_to_hotel + r.pending_notices.hotel_to_agency, '')}` : '—'}</td>
                      <td className="text-right">{f['30'].bookings} / {f['60'].bookings} / {f['90'].bookings}</td>
                      <td className="p-2 text-right">+{k.bookings} / −{k.cancelled}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ))}
      {report && <p className="text-xs text-slate-500">Vade: ekstrenin iki tarafça onaylandığı gün + sözleşmedeki ödeme vadesi (ön ödemeli ve girişte ödemeli 0 gün, vadeli 7/15/30 gün). Faturalanmamış: konaklaması başlamış, henüz hiçbir ekstrede yer almayan satışlar (pozitif: acente öder). Rapor tarihi {report.as_of}.</p>}
    </div>
  );
}
