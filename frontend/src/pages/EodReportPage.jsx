import { useState, useEffect } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Loader2, FileText, Send, Download, Calendar } from 'lucide-react';
import { toast } from 'sonner';

const today = () => new Date().toISOString().slice(0, 10);

function Metric({ label, value, sub }) {
  return (
    <div className="border rounded-lg p-3 bg-gray-50">
      <div className="text-[10px] uppercase text-gray-500 tracking-wide">{label}</div>
      <div className="text-2xl font-bold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

export default function EodReportPage() {
  const [businessDate, setBusinessDate] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recipients, setRecipients] = useState('');
  const [sending, setSending] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/pms/eod-report/preview', { params: { business_date: businessDate } });
      setData(data);
    } catch (e) { toast.error('Yükleme hatası: ' + (e.response?.data?.detail || e.message)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [businessDate]);

  const downloadPdf = async () => {
    try {
      const r = await api.get('/pms/eod-report/pdf', { params: { business_date: businessDate }, responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url; a.download = `eod-${businessDate}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error('Hata: ' + e.message); }
  };

  const send = async () => {
    const list = recipients.split(/[,\s;]+/).map(s => s.trim()).filter(Boolean);
    if (!list.length) { toast.error('En az bir alıcı e-postası girin'); return; }
    setSending(true);
    try {
      const { data } = await api.post('/pms/eod-report/send', { business_date: businessDate, recipients: list });
      setLastResult(data);
      toast.success(`${data.sent}/${data.total} alıcıya gönderildi`);
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    finally { setSending(false); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4" data-testid="eod-report-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-orange-600" /> Gün Sonu Raporu
          </h1>
          <p className="text-sm text-gray-500 mt-1">Tek tıkla PDF üretin ya da yöneticilere e-posta gönderin</p>
        </div>
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-gray-500" />
          <Input type="date" value={businessDate} onChange={e => setBusinessDate(e.target.value)} className="h-9 w-40" />
        </div>
      </div>

      {loading && <div className="text-center py-8"><Loader2 className="inline w-5 h-5 animate-spin" /></div>}

      {data && (
        <Card className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Metric label="Doluluk" value={`${data.occupancy_rate}%`} sub={`${data.occupied} / ${data.rooms_total} oda`} />
            <Metric label="Toplam Gelir" value={`${data.revenue_total.toLocaleString('tr-TR')} TL`} sub={`Ödeme ${data.payments_total} · Ekstra ${data.extras_total}`} />
            <Metric label="Beklenen / Gerçek Giriş" value={`${data.actual_checkins} / ${data.arrivals}`} />
            <Metric label="Beklenen / Gerçek Çıkış" value={`${data.actual_checkouts} / ${data.departures}`} />
            <Metric label="No-Show" value={data.no_shows} />
            <Metric label="İptal" value={data.cancels} />
            <Metric label="Açık Folyo" value={data.open_folios} />
            <Metric label="Onaylanmamış Devir" value={data.open_handovers} />
          </div>
        </Card>
      )}

      <Card className="p-4 space-y-3">
        <h2 className="font-semibold flex items-center gap-2"><Send className="w-4 h-4" /> Yöneticilere Gönder</h2>
        <div>
          <Label className="text-xs">Alıcılar (virgül veya boşlukla ayır)</Label>
          <Input value={recipients} onChange={e => setRecipients(e.target.value)}
            placeholder="gm@otel.com, cfo@otel.com" className="h-9" />
        </div>
        <div className="flex gap-2">
          <Button onClick={send} disabled={sending} className="bg-orange-600 hover:bg-orange-700">
            {sending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />} E-posta Gönder
          </Button>
          <Button onClick={downloadPdf} variant="outline">
            <Download className="w-4 h-4 mr-2" /> PDF İndir
          </Button>
        </div>
        {lastResult && (
          <div className="border-t pt-3 space-y-1.5">
            <div className="text-sm font-medium">Son Gönderim: {lastResult.sent}/{lastResult.total}</div>
            {lastResult.results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <Badge className={r.sent ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-red-100 text-red-700 border-red-200'}>
                  {r.sent ? 'OK' : 'HATA'}
                </Badge>
                <span>{r.to}</span>
                {r.id && <span className="text-gray-400">#{r.id.slice(0, 8)}</span>}
                {r.error && <span className="text-red-600">{r.error}</span>}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
