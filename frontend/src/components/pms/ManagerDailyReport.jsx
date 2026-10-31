import { useEffect, useState } from 'react';
import api from '@/api/axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  FileText, Printer, Users, BedDouble,
  Calendar, ArrowUpRight, ArrowDownRight, Minus
} from 'lucide-react';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';

const localDateKey = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
};
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
}[character]));
export const buildManagerDailyMetrics = ({ day, operations }) => {
  if (!operations || operations.date !== day || operations.basis !== 'actual_in_house_reservations_on_business_date') return null;
  const counters = ['totalRooms', 'availableRooms', 'oooRooms', 'occupiedRooms', 'emptyRooms', 'occupancy', 'inhouseReservations', 'vipGuests', 'groupBookings', 'arrivals', 'departures', 'noShows', 'cancellations', 'walkIns'];
  const breakdowns = ['nationality', 'losDistribution'].every(key => operations[key] && !Array.isArray(operations[key]) && Object.values(operations[key]).every(value => Number.isInteger(value) && value >= 0) && Object.values(operations[key]).reduce((sum, value) => sum + value, 0) === operations.inhouseReservations);
  return counters.every(key => Number.isFinite(operations[key]) && operations[key] >= 0) && breakdowns ? operations : null;
};

const ManagerDailyReport = ({ businessDate = null }) => {
  const { t } = useTranslation();
  const tm = (k) => t(`pmsComponents.managerReport.${k}`);
  const [reportDate, setReportDate] = useState(businessDate || localDateKey());
  const [financial, setFinancial] = useState(null);
  const [operations, setOperations] = useState(null);
  const [loadedDate, setLoadedDate] = useState(null);
  const [financialError, setFinancialError] = useState('');
  useEffect(() => {
    let current = true;
    setFinancial(null); setOperations(null); setFinancialError('');
    Promise.all([api.get(`/reports/revenue?start_date=${reportDate}&end_date=${reportDate}&nocache=1`), api.get(`/reports/manager-daily-operations?date_str=${reportDate}`)]).then(([{ data }, operational]) => {
      if (!data?.total_revenue_by_currency || !data?.adr_by_currency || !data?.rev_par_by_currency) throw new Error('Finansal rapor kaynağı doğrulanamadı');
      const verified = buildManagerDailyMetrics({ day: reportDate, operations: operational.data });
      if (!verified) throw new Error('Operasyon rapor kaynağı doğrulanamadı');
      if (current) { setFinancial(data); setOperations(verified); setLoadedDate(reportDate); }
    }).catch(() => { if (current) setFinancialError('Finansal rapor veya gerçekleşen konaklama kaynağı alınamadı. Eksik veriler sıfır ya da planlanan rezervasyonlarla doldurulmadı.'); });
    return () => { current = false; };
  }, [reportDate]);
  const ready = loadedDate === reportDate && Boolean(financial && operations);
  const money = key => ready ? formatCurrencyBreakdown(financial[key]) : 'Alınamadı';
  const metrics = ready ? operations : {};
  const { totalRooms, oooRooms, availableRooms, occupiedRooms, emptyRooms } = metrics;
  const occupancy = ready ? metrics.occupancy.toFixed(1) : '—';
  const todayArrivals = metrics.arrivals;
  const todayDepartures = metrics.departures;
  const inhouseGuests = metrics.inhouseReservations;
  const vipGuests = metrics.vipGuests;
  const groupBookings = metrics.groupBookings;
  const { noShows, cancellations, walkIns } = metrics;

  const nationality = metrics.nationality || {};
  const topNationalities = Object.entries(nationality).sort((a, b) => b[1] - a[1]).slice(0, 5);

  const losDistribution = metrics.losDistribution || {};

  const printReport = () => {
    if (!ready) return;
    const w = window.open('', '_blank');
    if (!w) return;
    w.document.write(`<html><head><title>${tm('printTitle')} - ${reportDate}</title><style>body{font-family:Arial;padding:30px;font-size:12px}h1{text-align:center;font-size:18px;border-bottom:2px solid #333;padding-bottom:8px}h2{font-size:14px;margin-top:20px;border-bottom:1px solid #999;padding-bottom:4px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0}.box{border:1px solid #ddd;padding:10px;text-align:center;border-radius:4px}.box .val{font-size:20px;font-weight:bold}.box .lbl{font-size:10px;color:#666}table{width:100%;border-collapse:collapse;margin:10px 0}td,th{border:1px solid #ccc;padding:6px;text-align:left;font-size:11px}th{background:#f5f5f5}.footer{margin-top:30px;font-size:10px;color:#999;text-align:center}@media print{body{padding:15px}}</style></head><body>`);
    w.document.write(`<h1>${tm('printTitle')}</h1><p style="text-align:center">${reportDate}</p>`);
    w.document.write(`<h2>${tm('roomStatus')}</h2><div class="grid"><div class="box"><div class="val">${totalRooms}</div><div class="lbl">${tm('totalRooms')}</div></div><div class="box"><div class="val">${occupiedRooms}</div><div class="lbl">${tm('occupied')}</div></div><div class="box"><div class="val">${emptyRooms}</div><div class="lbl">${tm('empty')}</div></div><div class="box"><div class="val">%${occupancy}</div><div class="lbl">${tm('occupancy')}</div></div></div>`);
    w.document.write(`<h2>${tm('revenueSection')}</h2><p>Folyoya işlenmiş gelir; dövizler ayrı gösterilir. Konaklama planı veya tahsilat değildir.</p><div class="grid"><div class="box"><div class="val">${escapeHtml(money('total_revenue_by_currency'))}</div><div class="lbl">${tm('totalRevenue')}</div></div><div class="box"><div class="val">${escapeHtml(money('adr_by_currency'))}</div><div class="lbl">${tm('adr')}</div></div><div class="box"><div class="val">${escapeHtml(money('rev_par_by_currency'))}</div><div class="lbl">${tm('revpar')}</div></div><div class="box"><div class="val">${oooRooms}</div><div class="lbl">${tm('oooOos')}</div></div></div>`);
    w.document.write(`<h2>${tm('guestMovementSection')}</h2><table><tr><th></th><th>#</th></tr><tr><td>${tm('arrivals')}</td><td>${todayArrivals}</td></tr><tr><td>${tm('departures')}</td><td>${todayDepartures}</td></tr><tr><td>${tm('inHouse')}</td><td>${inhouseGuests}</td></tr><tr><td>${tm('vip')}</td><td>${vipGuests}</td></tr><tr><td>${tm('group')}</td><td>${groupBookings}</td></tr><tr><td>${tm('walkIn')}</td><td>${walkIns}</td></tr><tr><td>${tm('noShow')}</td><td>${noShows}</td></tr><tr><td>${tm('cancellation')}</td><td>${cancellations}</td></tr></table>`);
    if (topNationalities.length > 0) { w.document.write(`<h2>${tm('nationalitySection')}</h2><table><tr><th></th><th>#</th></tr>`); topNationalities.forEach(([nat, count]) => w.document.write(`<tr><td>${escapeHtml(nat)}</td><td>${count}</td></tr>`)); w.document.write('</table>'); }
    w.document.write(`<h2>${tm('stayDurationSection')}</h2><table><tr><th></th><th>#</th></tr>`); Object.entries(losDistribution).forEach(([k, v]) => w.document.write(`<tr><td>${k} ${tm('nights')}</td><td>${v}</td></tr>`)); w.document.write('</table>');
    w.document.write(`<div class="footer">${tm('generatedAt')} ${new Date().toLocaleString()} | Syroce PMS</div></body></html>`);
    w.document.close();
    w.print();
  };

  const Metric = ({ label, value, suffix = '', trend }) => (
    <div className="text-center">
      <div className="text-2xl font-bold">{value ?? '—'}{suffix}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {trend !== undefined && (
        <div className={`text-xs flex items-center justify-center gap-1 ${trend > 0 ? 'text-green-600' : trend < 0 ? 'text-red-600' : 'text-gray-500'}`}>
          {trend > 0 ? <ArrowUpRight className="h-3 w-3" /> : trend < 0 ? <ArrowDownRight className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
          {Math.abs(trend)}%
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5" /> {tm('title')}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Input type="date" value={reportDate} onChange={e => setReportDate(e.target.value)} className="min-w-40 flex-1 sm:flex-none" />
          <Button onClick={printReport} disabled={!ready}><Printer className="h-4 w-4 mr-1" /> {tm('print')}</Button>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">Finansal tutarlar seçilen iş gününde folyoya işlenmiş gelirden alınır; konaklama planı veya tahsilat değildir. Dövizler ayrı gösterilir.</p>
      <p className="text-sm text-muted-foreground">Doluluk ve misafir dağılımları seçilen iş gününün gerçekleşen konaklamalarıdır; henüz giriş yapmamış rezervasyonlar dahil değildir. Konaklama sayısı kişi sayısı değildir. Kapalı oda sayısı tarihli oda bloklarından alınır.</p>
      {financialError && <p role="alert" className="text-sm text-red-700">{financialError}</p>}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <Card><CardContent className="p-3"><Metric label={tm('occupancy')} value={occupancy} suffix="%" /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label={tm('occupiedRooms')} value={occupiedRooms} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label={tm('emptyRooms')} value={emptyRooms} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label={tm('adr')} value={<span className="text-sm">{money('adr_by_currency')}</span>} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label={tm('revpar')} value={<span className="text-sm">{money('rev_par_by_currency')}</span>} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label={tm('totalRevenue')} value={<span className="text-sm">{money('total_revenue_by_currency')}</span>} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label={tm('oooOos')} value={oooRooms} /></CardContent></Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Users className="h-4 w-4" /> {tm('guestMovement')}</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm"><span>{tm('arrivals')}</span><Badge variant="outline">{todayArrivals}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('departures')}</span><Badge variant="outline">{todayDepartures}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('inHouse')}</span><Badge>{inhouseGuests}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('vip')}</span><Badge className="bg-indigo-100 text-indigo-800">{vipGuests}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('group')}</span><Badge variant="outline">{groupBookings}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('walkIn')}</span><Badge variant="outline">{walkIns}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('noShow')}</span><Badge variant="destructive">{noShows}</Badge></div>
            <div className="flex justify-between text-sm"><span>{tm('cancellation')}</span><Badge variant="secondary">{cancellations}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Calendar className="h-4 w-4" /> {tm('nationalityDist')}</CardTitle></CardHeader>
          <CardContent>
            {topNationalities.length > 0 ? topNationalities.map(([nat, count]) => (
              <div key={nat} className="flex justify-between text-sm py-1 border-b last:border-0">
                <span>{nat}</span><Badge variant="outline">{count}</Badge>
              </div>
            )) : <p className="text-sm text-muted-foreground text-center py-4">{tm('noData')}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><BedDouble className="h-4 w-4" /> {tm('stayDuration')}</CardTitle></CardHeader>
          <CardContent>
            {Object.entries(losDistribution).map(([key, val]) => (
              <div key={key} className="flex justify-between text-sm py-1 border-b last:border-0">
                <span>{key} {tm('nights')}</span>
                <div className="flex items-center gap-2">
                  <div className="w-20 bg-gray-200 rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${inhouseGuests > 0 ? (val / inhouseGuests * 100) : 0}%` }} />
                  </div>
                  <Badge variant="outline">{val}</Badge>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default ManagerDailyReport;
