import { useState, useEffect } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Loader2, FileText, Send, Download, Calendar, X as XIcon, AlertTriangle, CheckCircle2, TrendingUp, DollarSign, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
const today = () => new Date().toISOString().slice(0, 10);
function KpiCard({
  label,
  value,
  sub,
  accent = 'slate',
  icon: Icon,
  onClick
}) {
  const {
    t
  } = useTranslation();
  const tone = {
    slate: 'border-slate-200 bg-white',
    amber: 'border-amber-300 bg-amber-50/60',
    emerald: 'border-emerald-200 bg-emerald-50/40',
    rose: 'border-rose-200 bg-rose-50/40',
    sky: 'border-sky-200 bg-sky-50/40'
  }[accent];
  const valueColor = {
    slate: 'text-slate-900',
    amber: 'text-amber-700',
    emerald: 'text-emerald-700',
    rose: 'text-rose-700',
    sky: 'text-sky-700'
  }[accent];
  const interactive = onClick ? 'cursor-pointer hover:shadow-md hover:border-amber-400 transition-all' : '';
  const Tag = onClick ? 'button' : 'div';
  return <Tag type={onClick ? 'button' : undefined} onClick={onClick} className={`border rounded-lg p-3 text-left w-full ${tone} ${interactive}`}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase text-slate-500 tracking-wide">{label}</div>
        <div className="flex items-center gap-1">
          {onClick && <ExternalLink className="w-3 h-3 text-slate-400" />}
          {Icon && <Icon className={`w-3.5 h-3.5 ${valueColor} opacity-60`} />}
        </div>
      </div>
      <div className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </Tag>;
}
function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('tr-TR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });
  } catch {
    return iso;
  }
}
function OpenFoliosDialog({
  open,
  onClose,
  businessDate
}) {
  const {
    t
  } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [folios, setFolios] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(null);
    setFolios([]);
    setTotal(0);
    (async () => {
      try {
        const {
          data
        } = await api.get('/folio/list', {
          params: {
            status: 'open',
            limit: 500
          },
          signal: controller.signal
        });
        if (!active) return;
        setFolios(data.folios || []);
        setTotal(data.total || 0);
      } catch (e) {
        if (!active || controller.signal.aborted) return;
        const msg = e.response?.data?.detail || e.message || 'Bilinmeyen hata';
        setError(msg);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [open, reloadTick]);

  // Çıkışı geçmiş ama folyo açık → kritik
  const overdue = folios.filter(f => f.check_out && f.check_out < businessDate);
  const inHouse = folios.filter(f => !(f.check_out && f.check_out < businessDate));
  return <Dialog open={open} onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
            {t('cm.pages_EodReportPage.acik_folyolar')}
          </DialogTitle>
          <DialogDescription>
            {t('cm.pages_EodReportPage.toplam')} {total} {t('cm.pages_EodReportPage.acik_folyo_cikisi_gecmis_olanlar_gun_son')}
          </DialogDescription>
        </DialogHeader>

        {loading ? <div className="py-12 text-center">
            <Loader2 className="inline w-6 h-6 animate-spin text-slate-400" />
          </div> : error ? <div className="py-8 text-center">
            <AlertTriangle className="inline w-8 h-8 text-rose-500 mb-2" />
            <div className="text-sm text-rose-700 mb-3">{t('cm.pages_EodReportPage.folyolar_yuklenemedi')} {error}</div>
            <Button variant="outline" size="sm" onClick={() => setReloadTick(t => t + 1)} className="border-amber-300 text-amber-700 hover:bg-amber-50">
              Tekrar Dene
            </Button>
          </div> : folios.length === 0 ? <div className="py-12 text-center text-slate-500">
            <CheckCircle2 className="inline w-8 h-8 text-emerald-500 mb-2" /><br />
            {t('cm.pages_EodReportPage.acik_folyo_yok')}
          </div> : <div className="max-h-[60vh] overflow-auto">
            {overdue.length > 0 && <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <Badge className="bg-rose-100 text-rose-800 border-rose-200">
                    {t('cm.pages_EodReportPage.cikisi_gecmis')} {overdue.length}
                  </Badge>
                  <span className="text-xs text-slate-500">{t('cm.pages_EodReportPage.oncelikli_inceleme')}</span>
                </div>
                <FolioTable rows={overdue} highlight />
              </div>}
            {inHouse.length > 0 && <div>
                <div className="flex items-center gap-2 mb-2">
                  <Badge className="bg-sky-100 text-sky-800 border-sky-200">
                    Tesiste — {inHouse.length}
                  </Badge>
                  <span className="text-xs text-slate-500">{t('cm.pages_EodReportPage.cikista_otomatik_kapanir')}</span>
                </div>
                <FolioTable rows={inHouse} />
              </div>}
          </div>}
      </DialogContent>
    </Dialog>;
}
function FolioTable({
  rows,
  highlight = false
}) {
  const {
    t
  } = useTranslation();
  return <div className="border border-slate-200 rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-600 text-xs">
          <tr>
            <th className="text-left px-3 py-2 font-medium">{t('cm.pages_EodReportPage.oda')}</th>
            <th className="text-left px-3 py-2 font-medium">{t('cm.pages_EodReportPage.misafir')}</th>
            <th className="text-left px-3 py-2 font-medium">{t('cm.pages_EodReportPage.giris')}</th>
            <th className="text-left px-3 py-2 font-medium">{t('cm.pages_EodReportPage.cikis')}</th>
            <th className="text-right px-3 py-2 font-medium">{t('cm.pages_EodReportPage.bakiye')}</th>
            <th className="text-left px-3 py-2 font-medium">Folyo</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(f => <tr key={f.id} className={`border-t border-slate-100 ${highlight ? 'bg-rose-50/40' : 'hover:bg-slate-50'}`}>
              <td className="px-3 py-2 font-medium text-slate-900">{f.room_number || '—'}</td>
              <td className="px-3 py-2 text-slate-700">{f.guest_name || '—'}</td>
              <td className="px-3 py-2 text-slate-600">{fmtDate(f.check_in)}</td>
              <td className="px-3 py-2 text-slate-600">{fmtDate(f.check_out)}</td>
              <td className="px-3 py-2 text-right font-semibold text-slate-900">
                {(f.balance ?? 0).toLocaleString('tr-TR')} ₺
              </td>
              <td className="px-3 py-2 text-xs text-slate-400 font-mono">
                #{(f.id || '').slice(0, 8)}
              </td>
            </tr>)}
        </tbody>
      </table>
    </div>;
}
function ProgressKpi({
  label,
  actual,
  expected,
  accent = 'sky'
}) {
  const {
    t
  } = useTranslation();
  const pct = expected > 0 ? Math.min(100, Math.round(actual / expected * 100)) : 0;
  const barColor = pct >= 100 ? 'bg-emerald-500' : pct >= 70 ? 'bg-sky-500' : 'bg-amber-500';
  return <div className="border border-slate-200 bg-white rounded-lg p-3">
      <div className="text-[10px] uppercase text-slate-500 tracking-wide">{label}</div>
      <div className="flex items-baseline gap-1.5 mt-1">
        <span className="text-2xl font-bold text-slate-900">{actual}</span>
        <span className="text-sm text-slate-500">/ {expected}</span>
      </div>
      <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`${barColor} h-full transition-all`} style={{
        width: `${pct}%`
      }} />
      </div>
      <div className="text-[11px] text-slate-500 mt-1">{pct}{t('cm.pages_EodReportPage.tamamlandi')}</div>
    </div>;
}
export default function EodReportPage({
  user,
  tenant,
  onLogout
}) {
  const {
    t
  } = useTranslation();
  const [businessDate, setBusinessDate] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recipients, setRecipients] = useState([]);
  const [recipientInput, setRecipientInput] = useState('');
  const [sending, setSending] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [showOpenFolios, setShowOpenFolios] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const {
        data
      } = await api.get('/pms/eod-report/preview', {
        params: {
          business_date: businessDate
        }
      });
      setData(data);
    } catch (e) {
      toast.error('Yükleme hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => {
    load();
  }, [businessDate]);
  const downloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const r = await api.get('/pms/eod-report/pdf', {
        params: {
          business_date: businessDate
        },
        responseType: 'blob'
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gun-sonu-${businessDate}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('Hata: ' + e.message);
    } finally {
      setDownloadingPdf(false);
    }
  };
  const addRecipient = raw => {
    const list = (raw || recipientInput).split(/[,\s;]+/).map(s => s.trim()).filter(Boolean);
    const valid = list.filter(e => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));
    if (valid.length === 0 && (raw || recipientInput).trim()) {
      toast.error('Geçerli e-posta adresi girin');
      return;
    }
    setRecipients(prev => [...new Set([...prev, ...valid])]);
    setRecipientInput('');
  };
  const removeRecipient = email => setRecipients(prev => prev.filter(e => e !== email));
  const send = async () => {
    if (recipients.length === 0) {
      toast.error('En az bir alıcı ekleyin');
      return;
    }
    setSending(true);
    try {
      const {
        data: res
      } = await api.post('/pms/eod-report/send', {
        business_date: businessDate,
        recipients
      });
      setLastResult(res);
      toast.success(`${res.sent}/${res.total} alıcıya gönderildi`);
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSending(false);
    }
  };
  const isAuditPending = data && (data.open_folios > 0 || data.open_handovers > 0);
  return <>
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4" data-testid="eod-report-page">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
              <FileText className="w-6 h-6 text-amber-600" /> {t('cm.pages_EodReportPage.gun_sonu_raporu')}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {new Date(businessDate).toLocaleDateString('tr-TR', {
              day: '2-digit',
              month: 'long',
              year: 'numeric',
              weekday: 'long'
            })}
              {' · '}
              {data?.audit_status === 'completed' ? <span className="text-emerald-700 font-medium">{t('cm.pages_EodReportPage.audit_tamamlandi')}</span> : <span className="text-amber-700 font-medium">{t('cm.pages_EodReportPage.audit_henuz_yapilmadi')}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-500" />
            <Input type="date" value={businessDate} onChange={e => setBusinessDate(e.target.value)} className="h-9 w-40" />
          </div>
        </div>

        {/* Risk banner */}
        {isAuditPending && <div className="flex items-start gap-3 bg-amber-50 border border-amber-300 rounded-lg p-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-sm text-amber-900">
              <div className="font-semibold">{t('cm.pages_EodReportPage.kapanmamis_kalem_var')}</div>
              <div className="text-amber-800 mt-0.5">
                {data.open_folios > 0 && <span>{data.open_folios} {t('cm.pages_EodReportPage.acik_folyo')}</span>}
                {data.open_folios > 0 && data.open_handovers > 0 && <span> · </span>}
                {data.open_handovers > 0 && <span>{data.open_handovers} {t('cm.pages_EodReportPage.onaylanmamis_vardiya_devri')}</span>}
                {t('cm.pages_EodReportPage.gun_sonu_kapatilmadan_once_tamamlanmalid')}
              </div>
            </div>
          </div>}

        {loading && <div className="text-center py-8"><Loader2 className="inline w-5 h-5 animate-spin text-slate-400" /></div>}

        {data && <>
            {/* Finansal blok — büyük */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <KpiCard label="Doluluk" value={`${data.occupancy_rate}%`} sub={`${data.occupied} / ${data.rooms_total} oda dolu`} accent="sky" icon={TrendingUp} />
              <KpiCard label={t('cm.pages_EodReportPage.toplam_gelir')} value={`${(data.revenue_total || 0).toLocaleString('tr-TR')} ₺`} sub={`Ödeme ${(data.payments_total || 0).toLocaleString('tr-TR')} ₺ · Ekstra ${(data.extras_total || 0).toLocaleString('tr-TR')} ₺`} accent="emerald" icon={DollarSign} />
            </div>

            {/* Operasyonel blok — yatay küçük */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <ProgressKpi label={t('cm.pages_EodReportPage.giris_1ffbd')} actual={data.actual_checkins} expected={data.arrivals} />
              <ProgressKpi label={t('cm.pages_EodReportPage.cikis_b9015')} actual={data.actual_checkouts} expected={data.departures} />
              <KpiCard label="No-Show" value={data.no_shows} accent={data.no_shows > 0 ? 'rose' : 'slate'} />
              <KpiCard label={t('cm.pages_EodReportPage.iptal')} value={data.cancels} accent="slate" />
            </div>

            {/* Risk blok — vurgulu */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <KpiCard label={t('cm.pages_EodReportPage.acik_folyo_fa529')} value={data.open_folios} sub={data.open_folios > 0 ? 'Detayları görmek için tıklayın' : 'Tüm folyolar kapalı'} accent={data.open_folios > 0 ? 'amber' : 'emerald'} icon={data.open_folios > 0 ? AlertTriangle : CheckCircle2} onClick={data.open_folios > 0 ? () => setShowOpenFolios(true) : undefined} />
              <KpiCard label={t('cm.pages_EodReportPage.onaylanmamis_devir')} value={data.open_handovers} sub={data.open_handovers > 0 ? 'Vardiya notu beklemede' : 'Tüm devirler onaylı'} accent={data.open_handovers > 0 ? 'amber' : 'emerald'} icon={data.open_handovers > 0 ? AlertTriangle : CheckCircle2} />
            </div>
          </>}

        {/* Gönderim bloğu */}
        <Card className="p-4 space-y-3 border-slate-200">
          <h2 className="font-semibold flex items-center gap-2 text-slate-900">
            <Send className="w-4 h-4 text-amber-600" /> {t('cm.pages_EodReportPage.yoneticilere_gonder')}
          </h2>

          {/* Chips */}
          <div>
            <Label className="text-xs text-slate-700">{t('cm.pages_EodReportPage.alicilar')}</Label>
            <div className="mt-1.5 border border-slate-200 rounded-md p-2 bg-white min-h-[42px] flex flex-wrap gap-1.5 items-center focus-within:border-amber-400 focus-within:ring-1 focus-within:ring-amber-400">
              {recipients.map(email => <span key={email} className="inline-flex items-center gap-1 bg-amber-50 border border-amber-200 text-amber-900 text-xs px-2 py-1 rounded-md">
                  {email}
                  <button onClick={() => removeRecipient(email)} className="hover:text-amber-700" aria-label={t('cm.pages_EodReportPage.sil')}>
                    <XIcon className="w-3 h-3" />
                  </button>
                </span>)}
              <input value={recipientInput} onChange={e => setRecipientInput(e.target.value)} onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
                e.preventDefault();
                addRecipient();
              } else if (e.key === 'Backspace' && !recipientInput && recipients.length) {
                removeRecipient(recipients[recipients.length - 1]);
              }
            }} onBlur={() => recipientInput && addRecipient()} placeholder={recipients.length === 0 ? 'ornek@otel.com — Enter ile ekle' : ''} className="flex-1 min-w-[160px] outline-none text-sm bg-transparent" data-testid="eod-recipient-input" />
            </div>
            <div className="text-[11px] text-slate-500 mt-1">{t('cm.pages_EodReportPage.birden_fazla_adres_icin_her_birini_enter')}</div>
          </div>

          <div className="flex gap-2 flex-wrap">
            <Button onClick={send} disabled={sending || recipients.length === 0} className="bg-amber-600 hover:bg-amber-700 text-white">
              {sending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
              {t('cm.pages_EodReportPage.e_posta_gonder')}
            </Button>
            <Button onClick={downloadPdf} disabled={downloadingPdf} variant="outline" className="border-slate-300">
              {downloadingPdf ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> {t('cm.pages_EodReportPage.hazirlaniyor')}</> : <><Download className="w-4 h-4 mr-2" /> {t('cm.pages_EodReportPage.pdf_indir')}</>}
            </Button>
          </div>

          {lastResult && <div className="border-t border-slate-200 pt-3 space-y-1.5">
              <div className="text-sm font-medium text-slate-900">
                {t('cm.pages_EodReportPage.son_gonderim')} {lastResult.sent}/{lastResult.total} {t('cm.pages_EodReportPage.basarili')}
              </div>
              {(lastResult.results || []).map((r, i) => <div key={r.id || i} className="flex items-center gap-2 text-xs">
                  <Badge className={r.sent ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-rose-100 text-rose-700 border-rose-200'}>
                    {r.sent ? 'Gönderildi' : 'Hata'}
                  </Badge>
                  <span className="text-slate-700">{r.to}</span>
                  {r.id && <span className="text-slate-400">#{r.id.slice(0, 8)}</span>}
                  {r.error && <span className="text-rose-600">{r.error}</span>}
                </div>)}
            </div>}
        </Card>
      </div>

      <OpenFoliosDialog open={showOpenFolios} onClose={() => setShowOpenFolios(false)} businessDate={businessDate} />
    </>;
}