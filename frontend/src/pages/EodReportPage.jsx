import { useState, useEffect } from 'react';
import api from '@/api/axios';
import Layout from '@/components/Layout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Loader2, FileText, Send, Download, Calendar, X as XIcon,
  AlertTriangle, CheckCircle2, TrendingUp, DollarSign,
} from 'lucide-react';
import { toast } from 'sonner';

const today = () => new Date().toISOString().slice(0, 10);

function KpiCard({ label, value, sub, accent = 'slate', icon: Icon }) {
  const tone = {
    slate: 'border-slate-200 bg-white',
    amber: 'border-amber-300 bg-amber-50/60',
    emerald: 'border-emerald-200 bg-emerald-50/40',
    rose: 'border-rose-200 bg-rose-50/40',
    sky: 'border-sky-200 bg-sky-50/40',
  }[accent];
  const valueColor = {
    slate: 'text-slate-900',
    amber: 'text-amber-700',
    emerald: 'text-emerald-700',
    rose: 'text-rose-700',
    sky: 'text-sky-700',
  }[accent];
  return (
    <div className={`border rounded-lg p-3 ${tone}`}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase text-slate-500 tracking-wide">{label}</div>
        {Icon && <Icon className={`w-3.5 h-3.5 ${valueColor} opacity-60`} />}
      </div>
      <div className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

function ProgressKpi({ label, actual, expected, accent = 'sky' }) {
  const pct = expected > 0 ? Math.min(100, Math.round((actual / expected) * 100)) : 0;
  const barColor = pct >= 100 ? 'bg-emerald-500' : pct >= 70 ? 'bg-sky-500' : 'bg-amber-500';
  return (
    <div className="border border-slate-200 bg-white rounded-lg p-3">
      <div className="text-[10px] uppercase text-slate-500 tracking-wide">{label}</div>
      <div className="flex items-baseline gap-1.5 mt-1">
        <span className="text-2xl font-bold text-slate-900">{actual}</span>
        <span className="text-sm text-slate-500">/ {expected}</span>
      </div>
      <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`${barColor} h-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[11px] text-slate-500 mt-1">{pct}% tamamlandı</div>
    </div>
  );
}

export default function EodReportPage({ user, tenant, onLogout }) {
  const [businessDate, setBusinessDate] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recipients, setRecipients] = useState([]);
  const [recipientInput, setRecipientInput] = useState('');
  const [sending, setSending] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
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
    setDownloadingPdf(true);
    try {
      const r = await api.get('/pms/eod-report/pdf', { params: { business_date: businessDate }, responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url; a.download = `gun-sonu-${businessDate}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error('Hata: ' + e.message); }
    finally { setDownloadingPdf(false); }
  };

  const addRecipient = (raw) => {
    const list = (raw || recipientInput).split(/[,\s;]+/).map(s => s.trim()).filter(Boolean);
    const valid = list.filter(e => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));
    if (valid.length === 0 && (raw || recipientInput).trim()) {
      toast.error('Geçerli e-posta adresi girin');
      return;
    }
    setRecipients(prev => [...new Set([...prev, ...valid])]);
    setRecipientInput('');
  };

  const removeRecipient = (email) => setRecipients(prev => prev.filter(e => e !== email));

  const send = async () => {
    if (recipients.length === 0) {
      toast.error('En az bir alıcı ekleyin');
      return;
    }
    setSending(true);
    try {
      const { data: res } = await api.post('/pms/eod-report/send', { business_date: businessDate, recipients });
      setLastResult(res);
      toast.success(`${res.sent}/${res.total} alıcıya gönderildi`);
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    finally { setSending(false); }
  };

  const isAuditPending = data && (data.open_folios > 0 || data.open_handovers > 0);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="dashboard">
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4" data-testid="eod-report-page">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
              <FileText className="w-6 h-6 text-amber-600" /> Gün Sonu Raporu
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {new Date(businessDate).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric', weekday: 'long' })}
              {' · '}
              {data?.audit_status === 'completed'
                ? <span className="text-emerald-700 font-medium">Audit Tamamlandı</span>
                : <span className="text-amber-700 font-medium">Audit Henüz Yapılmadı</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-500" />
            <Input type="date" value={businessDate} onChange={e => setBusinessDate(e.target.value)} className="h-9 w-40" />
          </div>
        </div>

        {/* Risk banner */}
        {isAuditPending && (
          <div className="flex items-start gap-3 bg-amber-50 border border-amber-300 rounded-lg p-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-sm text-amber-900">
              <div className="font-semibold">Kapanmamış kalem var.</div>
              <div className="text-amber-800 mt-0.5">
                {data.open_folios > 0 && <span>{data.open_folios} açık folyo</span>}
                {data.open_folios > 0 && data.open_handovers > 0 && <span> · </span>}
                {data.open_handovers > 0 && <span>{data.open_handovers} onaylanmamış vardiya devri</span>}
                . Gün sonu kapatılmadan önce tamamlanmalıdır.
              </div>
            </div>
          </div>
        )}

        {loading && <div className="text-center py-8"><Loader2 className="inline w-5 h-5 animate-spin text-slate-400" /></div>}

        {data && (
          <>
            {/* Finansal blok — büyük */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <KpiCard
                label="Doluluk"
                value={`${data.occupancy_rate}%`}
                sub={`${data.occupied} / ${data.rooms_total} oda dolu`}
                accent="sky"
                icon={TrendingUp}
              />
              <KpiCard
                label="Toplam Gelir"
                value={`${(data.revenue_total || 0).toLocaleString('tr-TR')} ₺`}
                sub={`Ödeme ${(data.payments_total || 0).toLocaleString('tr-TR')} ₺ · Ekstra ${(data.extras_total || 0).toLocaleString('tr-TR')} ₺`}
                accent="emerald"
                icon={DollarSign}
              />
            </div>

            {/* Operasyonel blok — yatay küçük */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <ProgressKpi label="Giriş" actual={data.actual_checkins} expected={data.arrivals} />
              <ProgressKpi label="Çıkış" actual={data.actual_checkouts} expected={data.departures} />
              <KpiCard label="No-Show" value={data.no_shows} accent={data.no_shows > 0 ? 'rose' : 'slate'} />
              <KpiCard label="İptal" value={data.cancels} accent="slate" />
            </div>

            {/* Risk blok — vurgulu */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <KpiCard
                label="Açık Folyo"
                value={data.open_folios}
                sub={data.open_folios > 0 ? 'Hesap kapatılmadı — kontrol edin' : 'Tüm folyolar kapalı'}
                accent={data.open_folios > 0 ? 'amber' : 'emerald'}
                icon={data.open_folios > 0 ? AlertTriangle : CheckCircle2}
              />
              <KpiCard
                label="Onaylanmamış Devir"
                value={data.open_handovers}
                sub={data.open_handovers > 0 ? 'Vardiya notu beklemede' : 'Tüm devirler onaylı'}
                accent={data.open_handovers > 0 ? 'amber' : 'emerald'}
                icon={data.open_handovers > 0 ? AlertTriangle : CheckCircle2}
              />
            </div>
          </>
        )}

        {/* Gönderim bloğu */}
        <Card className="p-4 space-y-3 border-slate-200">
          <h2 className="font-semibold flex items-center gap-2 text-slate-900">
            <Send className="w-4 h-4 text-amber-600" /> Yöneticilere Gönder
          </h2>

          {/* Chips */}
          <div>
            <Label className="text-xs text-slate-700">Alıcılar</Label>
            <div className="mt-1.5 border border-slate-200 rounded-md p-2 bg-white min-h-[42px] flex flex-wrap gap-1.5 items-center focus-within:border-amber-400 focus-within:ring-1 focus-within:ring-amber-400">
              {recipients.map(email => (
                <span key={email} className="inline-flex items-center gap-1 bg-amber-50 border border-amber-200 text-amber-900 text-xs px-2 py-1 rounded-md">
                  {email}
                  <button onClick={() => removeRecipient(email)} className="hover:text-amber-700" aria-label="Sil">
                    <XIcon className="w-3 h-3" />
                  </button>
                </span>
              ))}
              <input
                value={recipientInput}
                onChange={e => setRecipientInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
                    e.preventDefault();
                    addRecipient();
                  } else if (e.key === 'Backspace' && !recipientInput && recipients.length) {
                    removeRecipient(recipients[recipients.length - 1]);
                  }
                }}
                onBlur={() => recipientInput && addRecipient()}
                placeholder={recipients.length === 0 ? 'ornek@otel.com — Enter ile ekle' : ''}
                className="flex-1 min-w-[160px] outline-none text-sm bg-transparent"
                data-testid="eod-recipient-input"
              />
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Birden fazla adres için her birini Enter veya virgül ile ayırın.</div>
          </div>

          <div className="flex gap-2 flex-wrap">
            <Button onClick={send} disabled={sending || recipients.length === 0} className="bg-amber-600 hover:bg-amber-700 text-white">
              {sending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
              E-posta Gönder
            </Button>
            <Button onClick={downloadPdf} disabled={downloadingPdf} variant="outline" className="border-slate-300">
              {downloadingPdf
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Hazırlanıyor…</>
                : <><Download className="w-4 h-4 mr-2" /> PDF İndir</>}
            </Button>
          </div>

          {lastResult && (
            <div className="border-t border-slate-200 pt-3 space-y-1.5">
              <div className="text-sm font-medium text-slate-900">
                Son Gönderim: {lastResult.sent}/{lastResult.total} başarılı
              </div>
              {(lastResult.results || []).map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <Badge className={r.sent
                    ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                    : 'bg-rose-100 text-rose-700 border-rose-200'}>
                    {r.sent ? 'Gönderildi' : 'Hata'}
                  </Badge>
                  <span className="text-slate-700">{r.to}</span>
                  {r.id && <span className="text-slate-400">#{r.id.slice(0, 8)}</span>}
                  {r.error && <span className="text-rose-600">{r.error}</span>}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </Layout>
  );
}
