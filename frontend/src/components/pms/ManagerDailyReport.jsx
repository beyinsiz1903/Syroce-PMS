import { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  FileText, Printer, TrendingUp, TrendingDown, Users, BedDouble,
  DollarSign, Calendar, ArrowUpRight, ArrowDownRight, Minus
} from 'lucide-react';

const ManagerDailyReport = ({ rooms = [], bookings = [], arrivals = [], departures = [], inhouse = [] }) => {
  const [reportDate, setReportDate] = useState(new Date().toISOString().split('T')[0]);
  const [prevData, setPrevData] = useState({});

  const totalRooms = rooms.length || 30;
  const oooRooms = rooms.filter(r => r.status === 'out_of_order' || r.status === 'maintenance').length;
  const availableRooms = totalRooms - oooRooms;
  const occupiedRooms = rooms.filter(r => r.status === 'occupied').length;
  const occupancy = availableRooms > 0 ? ((occupiedRooms / availableRooms) * 100).toFixed(1) : 0;

  const confirmedBookings = bookings.filter(b => b.status === 'checked_in' || b.status === 'confirmed');
  const totalRevenue = confirmedBookings.reduce((s, b) => s + (b.total_price || b.rate || 0), 0);
  const adr = occupiedRooms > 0 ? (totalRevenue / occupiedRooms).toFixed(0) : 0;
  const revpar = availableRooms > 0 ? (totalRevenue / availableRooms).toFixed(0) : 0;

  const todayArrivals = arrivals.length;
  const todayDepartures = departures.length;
  const inhouseGuests = inhouse.length;
  const vipGuests = inhouse.filter(b => b.vip || b.guest_vip).length;
  const groupBookings = bookings.filter(b => b.group_id || b.is_group).length;

  const noShows = bookings.filter(b => b.status === 'no_show').length;
  const cancellations = bookings.filter(b => b.status === 'cancelled').length;
  const walkIns = bookings.filter(b => b.source === 'walk_in' || b.channel === 'walk_in').length;

  const nationality = {};
  bookings.filter(b => b.status === 'checked_in').forEach(b => {
    const nat = b.guest_nationality || b.nationality || 'Belirtilmemiş';
    nationality[nat] = (nationality[nat] || 0) + 1;
  });
  const topNationalities = Object.entries(nationality).sort((a,b) => b[1]-a[1]).slice(0, 5);

  const losDistribution = { '1': 0, '2-3': 0, '4-7': 0, '7+': 0 };
  bookings.filter(b => b.check_in && b.check_out).forEach(b => {
    const ci = new Date(b.check_in);
    const co = new Date(b.check_out);
    const nights = Math.ceil((co - ci) / 86400000);
    if (nights <= 1) losDistribution['1']++;
    else if (nights <= 3) losDistribution['2-3']++;
    else if (nights <= 7) losDistribution['4-7']++;
    else losDistribution['7+']++;
  });

  const printReport = () => {
    const w = window.open('', '_blank');
    w.document.write(`<html><head><title>Müdür Günlük Raporu - ${reportDate}</title><style>body{font-family:Arial;padding:30px;font-size:12px}h1{text-align:center;font-size:18px;border-bottom:2px solid #333;padding-bottom:8px}h2{font-size:14px;margin-top:20px;border-bottom:1px solid #999;padding-bottom:4px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0}.box{border:1px solid #ddd;padding:10px;text-align:center;border-radius:4px}.box .val{font-size:20px;font-weight:bold}.box .lbl{font-size:10px;color:#666}table{width:100%;border-collapse:collapse;margin:10px 0}td,th{border:1px solid #ccc;padding:6px;text-align:left;font-size:11px}th{background:#f5f5f5}.footer{margin-top:30px;font-size:10px;color:#999;text-align:center}@media print{body{padding:15px}}</style></head><body>`);
    w.document.write(`<h1>MÜDÜR GÜNLÜK RAPORU</h1><p style="text-align:center">${reportDate}</p>`);
    w.document.write(`<h2>ODA DURUMU</h2><div class="grid"><div class="box"><div class="val">${totalRooms}</div><div class="lbl">Toplam Oda</div></div><div class="box"><div class="val">${occupiedRooms}</div><div class="lbl">Dolu</div></div><div class="box"><div class="val">${availableRooms - occupiedRooms}</div><div class="lbl">Boş</div></div><div class="box"><div class="val">%${occupancy}</div><div class="lbl">Doluluk</div></div></div>`);
    w.document.write(`<h2>GELİR</h2><div class="grid"><div class="box"><div class="val">${totalRevenue.toLocaleString()} TL</div><div class="lbl">Toplam Gelir</div></div><div class="box"><div class="val">${adr} TL</div><div class="lbl">ADR</div></div><div class="box"><div class="val">${revpar} TL</div><div class="lbl">RevPAR</div></div><div class="box"><div class="val">${oooRooms}</div><div class="lbl">OOO/OOS</div></div></div>`);
    w.document.write(`<h2>MİSAFİR HAREKETİ</h2><table><tr><th>Bilgi</th><th>Sayı</th></tr><tr><td>Bugünkü Girişler</td><td>${todayArrivals}</td></tr><tr><td>Bugünkü Çıkışlar</td><td>${todayDepartures}</td></tr><tr><td>Otelde Misafir</td><td>${inhouseGuests}</td></tr><tr><td>VIP Misafir</td><td>${vipGuests}</td></tr><tr><td>Grup Rezervasyon</td><td>${groupBookings}</td></tr><tr><td>Walk-In</td><td>${walkIns}</td></tr><tr><td>No-Show</td><td>${noShows}</td></tr><tr><td>İptal</td><td>${cancellations}</td></tr></table>`);
    if (topNationalities.length > 0) { w.document.write(`<h2>MİLLİYET DAĞILIMI</h2><table><tr><th>Milliyet</th><th>Sayı</th></tr>`); topNationalities.forEach(([nat, count]) => w.document.write(`<tr><td>${nat}</td><td>${count}</td></tr>`)); w.document.write('</table>'); }
    w.document.write(`<h2>KONAKLAMA SÜRESİ DAĞILIMI</h2><table><tr><th>Süre</th><th>Sayı</th></tr>`); Object.entries(losDistribution).forEach(([k,v]) => w.document.write(`<tr><td>${k} gece</td><td>${v}</td></tr>`)); w.document.write('</table>');
    w.document.write(`<div class="footer">Oluşturma: ${new Date().toLocaleString('tr-TR')} | Syroce PMS</div></body></html>`);
    w.document.close();
    w.print();
  };

  const Metric = ({ label, value, suffix = '', trend }) => (
    <div className="text-center">
      <div className="text-2xl font-bold">{value}{suffix}</div>
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
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5" /> Müdür Günlük Raporu
        </h2>
        <div className="flex items-center gap-2">
          <Input type="date" value={reportDate} onChange={e => setReportDate(e.target.value)} className="w-40" />
          <Button onClick={printReport}><Printer className="h-4 w-4 mr-1" /> Yazdır</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <Card><CardContent className="p-3"><Metric label="Doluluk" value={occupancy} suffix="%" /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label="Dolu Oda" value={occupiedRooms} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label="Boş Oda" value={availableRooms - occupiedRooms} /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label="ADR" value={adr} suffix=" TL" /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label="RevPAR" value={revpar} suffix=" TL" /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label="Toplam Gelir" value={totalRevenue.toLocaleString()} suffix=" TL" /></CardContent></Card>
        <Card><CardContent className="p-3"><Metric label="OOO/OOS" value={oooRooms} /></CardContent></Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Users className="h-4 w-4" /> Misafir Hareketi</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm"><span>Girişler</span><Badge variant="outline">{todayArrivals}</Badge></div>
            <div className="flex justify-between text-sm"><span>Çıkışlar</span><Badge variant="outline">{todayDepartures}</Badge></div>
            <div className="flex justify-between text-sm"><span>Otelde</span><Badge>{inhouseGuests}</Badge></div>
            <div className="flex justify-between text-sm"><span>VIP</span><Badge className="bg-purple-100 text-purple-800">{vipGuests}</Badge></div>
            <div className="flex justify-between text-sm"><span>Grup</span><Badge variant="outline">{groupBookings}</Badge></div>
            <div className="flex justify-between text-sm"><span>Walk-In</span><Badge variant="outline">{walkIns}</Badge></div>
            <div className="flex justify-between text-sm"><span>No-Show</span><Badge variant="destructive">{noShows}</Badge></div>
            <div className="flex justify-between text-sm"><span>İptal</span><Badge variant="secondary">{cancellations}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Calendar className="h-4 w-4" /> Milliyet Dağılımı</CardTitle></CardHeader>
          <CardContent>
            {topNationalities.length > 0 ? topNationalities.map(([nat, count]) => (
              <div key={nat} className="flex justify-between text-sm py-1 border-b last:border-0">
                <span>{nat}</span><Badge variant="outline">{count}</Badge>
              </div>
            )) : <p className="text-sm text-muted-foreground text-center py-4">Veri yok</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><BedDouble className="h-4 w-4" /> Konaklama Süresi</CardTitle></CardHeader>
          <CardContent>
            {Object.entries(losDistribution).map(([key, val]) => (
              <div key={key} className="flex justify-between text-sm py-1 border-b last:border-0">
                <span>{key} gece</span>
                <div className="flex items-center gap-2">
                  <div className="w-20 bg-gray-200 rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${bookings.length > 0 ? (val / bookings.length * 100) : 0}%` }} />
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
