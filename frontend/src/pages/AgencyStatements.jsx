import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { FileText, Loader2, Plus, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const STATUS = {
  issued: ['Acente onayı bekliyor', 'bg-amber-100 text-amber-800'],
  agreed: ['Mutabık', 'bg-emerald-100 text-emerald-800'],
  disputed: ['İtiraz var', 'bg-red-100 text-red-800'],
  resolved: ['İtiraz yanıtlandı', 'bg-sky-100 text-sky-800'],
  settled: ['Kapandı', 'bg-slate-200 text-slate-700'],
  void: ['İptal', 'bg-slate-100 text-slate-500'],
};
const NOTICE_STATUS = {
  pending: ['Doğrulama bekliyor', 'text-amber-700'],
  verified: ['Doğrulandı', 'text-emerald-700'],
  rejected: ['Reddedildi', 'text-red-700'],
};
const pendingNotices = statement => (statement.payment_notices || []).filter(n => n.status === 'pending');
const money = (value, currency) => `${Number(value || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || ''}`;
// Local calendar date; toISOString() would shift to UTC (01.09 00:00 +03 -> 31.08).
const localDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const monthStart = (now = new Date()) => localDate(new Date(now.getFullYear(), now.getMonth() - 1, 1));
export const monthEnd = (now = new Date()) => localDate(new Date(now.getFullYear(), now.getMonth(), 0));
const LINE_STATUS = { confirmed: 'Onaylı', guaranteed: 'Garantili', checked_in: 'Konaklıyor', checked_out: 'Çıkış yaptı', cancelled: 'İptal', no_show: 'Gelmedi', pending: 'Beklemede' };
const TERMS = { prepaid: 'Ön ödemeli', on_arrival: 'Girişte', net_7: '7 gün vadeli', net_15: '15 gün vadeli', net_30: '30 gün vadeli' };
export const ADJUSTABLE = ['issued', 'disputed', 'resolved'];

// Statement lines; with `edits` a checkbox per line opens a signed correction
// (+ the agency owes more, − less) that needs a reason.
export function StatementLines({ lines, currency, highlight = [], edits, onEdit }) {
  const editing = Boolean(edits);
  return (
    <div className="max-h-80 overflow-y-auto rounded border text-xs">
      <table className="w-full">
        <thead className="bg-slate-50 text-left"><tr>{editing && <th className="w-8 p-2" aria-label="Düzelt" />}<th className="p-2">Rezervasyon</th><th>Durum</th><th>Ödeme</th><th className="text-right">Brüt/Ceza</th><th className="text-right">Komisyon</th><th className="text-right p-2">Otel→Acente / Acente→Otel</th></tr></thead>
        <tbody>
          {lines.map(line => {
            const edit = edits?.[line.booking_id];
            return [
              <tr key={line.booking_id} className={`border-t ${highlight.includes(line.booking_id) ? 'bg-red-50' : ''}`}>
                {editing && <td className="p-2"><input type="checkbox" aria-label={`${line.confirmation_code} satırını düzelt`} checked={Boolean(edit)} onChange={e => onEdit(line.booking_id, e.target.checked ? { amount: line.adjustment?.amount ?? '', reason: line.adjustment?.reason ?? '' } : null)} /></td>}
                <td className="p-2">{line.confirmation_code}<div className="text-slate-400">{line.check_in} · {line.guest_name}</div></td>
                <td>{LINE_STATUS[line.status] || line.status}</td><td>{TERMS[line.payment_terms] || line.payment_terms}</td>
                <td className="text-right">{money(line.gross, currency)}</td>
                <td className="text-right">{money(line.commission, currency)}</td>
                <td className="p-2 text-right">{money(line.hotel_owes_agency, '')} / {money(line.agency_owes_hotel, '')}
                  {line.adjustment && <div className="text-amber-700" data-testid={`adjustment-${line.booking_id}`}>Düzeltme {line.adjustment.amount > 0 ? '+' : '−'}{money(Math.abs(line.adjustment.amount), '')} · {line.adjustment.reason}</div>}</td>
              </tr>,
              edit && <tr key={`${line.booking_id}-edit`} className="bg-amber-50">
                <td colSpan={7} className="p-2"><div className="grid gap-2 sm:grid-cols-[180px_1fr]">
                  <Input type="number" step="0.01" aria-label="Düzeltme tutarı" placeholder="+ fazla / − az" value={edit.amount} onChange={e => onEdit(line.booking_id, { ...edit, amount: e.target.value })} />
                  <Input aria-label="Düzeltme gerekçesi" placeholder="Gerekçe (en az 5 karakter)" maxLength={300} value={edit.reason} onChange={e => onEdit(line.booking_id, { ...edit, reason: e.target.value })} />
                </div><p className="mt-1 text-[11px] text-slate-500">Artı: acente otele daha fazla öder · Eksi: daha az öder. 0 düzeltmeyi kaldırır. PMS'teki rezervasyon tutarı değişmez.</p></td>
              </tr>,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

const editsToAdjustments = edits => Object.entries(edits || {}).map(([booking_id, edit]) => ({ booking_id, amount: Number(edit.amount || 0), reason: (edit.reason || '').trim() }));
const invalidEdit = edits => editsToAdjustments(edits).some(item => Number.isNaN(item.amount) || (Math.abs(item.amount) >= 0.01 && item.reason.length < 5));

const balanceText = (value, currency) => {
  if (Math.abs(Number(value || 0)) < 0.01) return 'Bakiye yok';
  return Number(value) > 0 ? `Acente ödeyecek: ${money(value, currency)}` : `Otel ödeyecek: ${money(-value, currency)}`;
};

export default function AgencyStatements() {
  const [items, setItems] = useState([]);
  const [agencies, setAgencies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ agency_id: '', period_start: monthStart(), period_end: monthEnd(), currency: 'TRY' });
  const [issuing, setIssuing] = useState(false);
  const [detail, setDetail] = useState(null);
  const [payment, setPayment] = useState({ amount: '', paid_at: localDate(new Date()), method: 'bank_transfer', reference: '' });
  const [note, setNote] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewEdits, setPreviewEdits] = useState({});
  // A correction typed after the last calculation is not what the preview shows.
  const [previewStale, setPreviewStale] = useState(false);
  const [lineEdits, setLineEdits] = useState({});
  const [noticeNote, setNoticeNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: list }, { data: agencyData }] = await Promise.all([
        axios.get('/marketplace/hotel/statements'),
        axios.get('/marketplace/hotel/statements/agencies'),
      ]);
      setItems(list.items || []);
      setAgencies(agencyData.agencies || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ekstreler yüklenemedi.');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const runPreview = async (edits = previewEdits) => {
    if (!form.agency_id) return toast.error('Acente seçin.');
    if (invalidEdit(edits)) return toast.error('Her düzeltme için tutar ve en az 5 karakter gerekçe girin.');
    setIssuing(true);
    try {
      const { data } = await axios.post('/marketplace/hotel/statements/preview', { ...form, adjustments: editsToAdjustments(edits) });
      setPreview(data);
      setPreviewStale(false);
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre hesaplanamadı.'); }
    finally { setIssuing(false); }
  };
  const openPreview = () => { setPreviewEdits({}); runPreview({}); };
  const issue = async () => {
    if (invalidEdit(previewEdits)) return toast.error('Her düzeltme için tutar ve en az 5 karakter gerekçe girin.');
    setIssuing(true);
    try {
      if (previewStale) return toast.error('Düzeltmeler değişti; göndermeden önce yeniden hesaplayın.');
      const { data } = await axios.post('/marketplace/hotel/statements', {
        ...form, adjustments: editsToAdjustments(previewEdits), expected_net_balance: preview?.totals?.net_balance ?? null,
      });
      toast.success(`${data.number} düzenlendi ve acenteye iletildi.`);
      setPreview(null);
      setPreviewEdits({});
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre düzenlenemedi.'); }
    finally { setIssuing(false); }
  };
  const editPreviewLine = (bookingId, edit) => {
    setPreviewStale(true);
    setPreviewEdits(current => {
      const next = { ...current };
      if (edit) next[bookingId] = edit; else delete next[bookingId];
      return next;
    });
  };
  const editDetailLine = (bookingId, edit) => setLineEdits(current => {
    const next = { ...current };
    if (edit) next[bookingId] = edit; else delete next[bookingId];
    return next;
  });
  const saveLineEdits = async () => {
    if (invalidEdit(lineEdits)) return toast.error('Her düzeltme için tutar ve en az 5 karakter gerekçe girin.');
    setBusy(true);
    try {
      let data = null;
      for (const item of editsToAdjustments(lineEdits)) {
        ({ data } = await axios.post(`/marketplace/hotel/statements/${detail.id}/adjust`, item));
      }
      if (data) setDetail(data);
      setLineEdits({});
      toast.success('Düzeltme kaydedildi ve acenteye bildirildi.');
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Düzeltme kaydedilemedi.'); }
    finally { setBusy(false); }
  };
  const open = async statement => {
    try {
      setDetail((await axios.get(`/marketplace/hotel/statements/${statement.id}`)).data);
      setNote('');
      setNoticeNote('');
      setLineEdits({});
      setPayment(current => ({ ...current, amount: '' }));
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre açılamadı.'); }
  };
  const act = async (path, body, success) => {
    setBusy(true);
    try {
      const { data } = await axios.post(`/marketplace/hotel/statements/${detail.id}/${path}`, body);
      setDetail(data);
      toast.success(success);
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'İşlem tamamlanamadı.'); }
    finally { setBusy(false); }
  };
  const decideNotice = async (notice, verify) => {
    await act(`payment-notices/${notice.id}/${verify ? 'verify' : 'reject'}`, { note: noticeNote.trim() },
      verify ? 'Ödeme doğrulandı ve ekstreye işlendi.' : 'Ödeme bildirimi reddedildi; acenteye iletildi.');
    setNoticeNote('');
  };
  const openProof = async notice => {
    try {
      const { data } = await axios.get(`/marketplace/hotel/statements/${detail.id}/payment-notices/${notice.id}/proof`, { responseType: 'blob' });
      window.open(URL.createObjectURL(data), '_blank', 'noopener');
    } catch { toast.error('Dekont açılamadı.'); }
  };
  const recordPayment = () => {
    const amount = Number(payment.amount);
    if (!(amount > 0)) return toast.error('Geçerli bir tutar girin.');
    return act('payments', { ...payment, amount, direction: detail.outstanding > 0 ? 'agency_to_hotel' : 'hotel_to_agency' }, 'Ödeme kaydedildi.');
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><FileText size={22} /> Acente Ekstreleri</h1>
          <p className="text-sm text-slate-500">Marketplace acenteleriyle dönem mutabakatı: ekstre, onay/itiraz ve ödeme kaydı.</p>
        </div>
        <Button variant="outline" onClick={load}><RefreshCw size={14} className="mr-2" />Yenile</Button>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Yeni ekstre</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-5">
          <div className="sm:col-span-2"><Label htmlFor="st-agency">Acente</Label>
            <select id="st-agency" className="h-10 w-full rounded-md border px-3 text-sm" value={form.agency_id} onChange={e => setForm(f => ({ ...f, agency_id: e.target.value }))}>
              <option value="">Seçin</option>
              {agencies.map(agency => <option key={agency.id} value={agency.id}>{agency.name}</option>)}
            </select>
          </div>
          <div><Label htmlFor="st-start">Başlangıç</Label><Input id="st-start" type="date" value={form.period_start} onChange={e => setForm(f => ({ ...f, period_start: e.target.value }))} /></div>
          <div><Label htmlFor="st-end">Bitiş</Label><Input id="st-end" type="date" value={form.period_end} onChange={e => setForm(f => ({ ...f, period_end: e.target.value }))} /></div>
          <div><Label htmlFor="st-cur">Para birimi</Label><Input id="st-cur" maxLength={3} value={form.currency} onChange={e => setForm(f => ({ ...f, currency: e.target.value.toUpperCase() }))} /></div>
          <div className="sm:col-span-5"><Button onClick={openPreview} disabled={issuing}>{issuing ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Plus size={14} className="mr-2" />}Ekstreyi önizle</Button><p className="mt-1 text-xs text-slate-500">Önizlemede satırları kontrol edip gerekirse düzeltin; ekstre ancak "Acenteye gönder" ile oluşur.</p></div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? <div className="py-10 text-center"><Loader2 className="mx-auto animate-spin" /></div> : items.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-400">Henüz ekstre yok.</p>
          ) : (
            <div className="divide-y">
              {items.map(statement => (
                <button type="button" key={statement.id} onClick={() => open(statement)} className="flex w-full flex-wrap items-center justify-between gap-3 p-4 text-left hover:bg-slate-50">
                  <div>
                    <div className="font-medium">{statement.number} · {statement.agency_name}</div>
                    <div className="text-xs text-slate-500">{statement.period_start} – {statement.period_end} · {statement.totals?.bookings} konaklama · {statement.totals?.cancelled + statement.totals?.no_show} iptal/no-show</div>
                  </div>
                  <div className="flex items-center gap-3">
                    {pendingNotices(statement).length > 0 && <Badge className="bg-amber-100 text-amber-800">{pendingNotices(statement).length} ödeme bildirimi</Badge>}
                    <span className="text-sm">{balanceText(statement.outstanding, statement.currency)}</span>
                    <Badge className={STATUS[statement.status]?.[1]}>{STATUS[statement.status]?.[0] || statement.status}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(preview)} onOpenChange={value => !value && !issuing && setPreview(null)}>
        <DialogContent className="max-w-3xl">
          {preview && <div data-testid="statement-preview" className="space-y-3">
            <DialogHeader>
              <DialogTitle>Önizleme · {preview.agency_name}</DialogTitle>
              <p className="text-sm text-slate-500">{preview.period_start} – {preview.period_end} · {balanceText(preview.outstanding, preview.currency)}{preview.totals?.adjustments ? ` · düzeltmeler ${money(preview.totals.adjustments, preview.currency)}` : ''}</p>
              <p className="text-xs text-slate-500">Henüz kaydedilmedi; acente bilgilendirilmedi. Düzeltmek istediğiniz satırın kutucuğunu işaretleyin.</p>
            </DialogHeader>
            <StatementLines lines={preview.lines} currency={preview.currency} edits={previewEdits} onEdit={editPreviewLine} />
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => runPreview()} disabled={issuing}>Yeniden hesapla</Button>
              {previewStale && <span className="self-center text-xs text-amber-700">Düzeltmeler değişti; göndermeden önce yeniden hesaplayın.</span>}
              <Button onClick={issue} disabled={issuing || previewStale}>{issuing ? <Loader2 size={14} className="mr-2 animate-spin" /> : null}Acenteye gönder</Button>
            </DialogFooter>
          </div>}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(detail)} onOpenChange={value => !value && setDetail(null)}>
        <DialogContent className="max-w-3xl">
          {detail && <>
            <DialogHeader>
              <DialogTitle>{detail.number} · {detail.agency_name}</DialogTitle>
              <p className="text-sm text-slate-500">{detail.period_start} – {detail.period_end} · {STATUS[detail.status]?.[0]} · {balanceText(detail.outstanding, detail.currency)}</p>
            </DialogHeader>
            <StatementLines lines={detail.lines} currency={detail.currency} highlight={detail.dispute?.booking_ids || []}
              edits={ADJUSTABLE.includes(detail.status) && !detail.payments?.length ? lineEdits : undefined} onEdit={editDetailLine} />
            {Object.keys(lineEdits).length > 0 && <div className="flex justify-end"><Button size="sm" onClick={saveLineEdits} disabled={busy}>Düzeltmeyi kaydet ve acenteye bildir</Button></div>}
            {detail.dispute && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm"><strong>İtiraz:</strong> {detail.dispute.reason}</div>}
            {detail.payments?.length > 0 && <div className="text-xs text-slate-600">Ödemeler: {detail.payments.map(p => `${p.paid_at} ${money(p.amount, detail.currency)} (${p.direction === 'agency_to_hotel' ? 'acente→otel' : 'otel→acente'})`).join(' · ')}</div>}
            {detail.payment_notices?.length > 0 && <div className="space-y-2 rounded border p-3" data-testid="hotel-payment-notices">
              <div className="text-sm font-medium">Acentenin ödeme bildirimleri</div>
              <p className="text-xs text-slate-500">Bildirim, siz doğrulayana kadar bakiyeyi ve acente kredisini değiştirmez. Doğrulanınca aynı banka referansıyla ekstreye ödeme olarak işlenir.</p>
              {detail.payment_notices.map(notice => <div key={notice.id} className="flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs">
                <span>{notice.paid_at} · {money(notice.amount, detail.currency)} · ref {notice.reference} · {notice.reported_by}</span>
                <span className="flex items-center gap-2">
                  {notice.has_proof && <button type="button" className="underline" onClick={() => openProof(notice)}>Dekont</button>}
                  <span className={NOTICE_STATUS[notice.status]?.[1]}>{NOTICE_STATUS[notice.status]?.[0] || notice.status}{notice.note ? `: ${notice.note}` : ''}</span>
                  {notice.status === 'pending' && <>
                    <Button size="sm" onClick={() => decideNotice(notice, true)} disabled={busy}>Doğrula</Button>
                    <Button size="sm" variant="outline" className="text-red-700" onClick={() => decideNotice(notice, false)} disabled={busy || noticeNote.trim().length < 5}>Reddet</Button>
                  </>}
                </span>
              </div>)}
              {pendingNotices(detail).length > 0 && <Input placeholder="Not (reddederken zorunlu, en az 5 karakter)" value={noticeNote} onChange={e => setNoticeNote(e.target.value)} />}
            </div>}
            {['agreed', 'resolved'].includes(detail.status) && Math.abs(detail.outstanding) >= 0.01 && (
              <div className="grid gap-2 sm:grid-cols-4">
                <Input type="number" min="0" step="0.01" placeholder="Tutar" value={payment.amount} onChange={e => setPayment(p => ({ ...p, amount: e.target.value }))} />
                <Input type="date" value={payment.paid_at} onChange={e => setPayment(p => ({ ...p, paid_at: e.target.value }))} />
                <Input placeholder="Referans / dekont no" value={payment.reference} onChange={e => setPayment(p => ({ ...p, reference: e.target.value }))} />
                <Button onClick={recordPayment} disabled={busy}>Ödeme kaydet</Button>
              </div>
            )}
            {['issued', 'disputed', 'resolved', 'agreed'].includes(detail.status) && !detail.payments?.length && (
              <textarea className="min-h-16 w-full rounded-md border p-2 text-sm" placeholder={detail.status === 'disputed' ? 'İtiraza yanıtınız (en az 5 karakter)' : 'İptal gerekçesi (en az 5 karakter)'} value={note} onChange={e => setNote(e.target.value)} />
            )}
            <DialogFooter className="gap-2">
              {detail.status === 'disputed' && <Button onClick={() => act('resolve', { note }, 'İtiraz yanıtlandı.')} disabled={busy || note.trim().length < 5}>İtirazı yanıtla</Button>}
              {['issued', 'disputed', 'resolved', 'agreed'].includes(detail.status) && !detail.payments?.length && (
                <Button variant="destructive" onClick={() => act('void', { note }, 'Ekstre iptal edildi; yeniden düzenleyebilirsiniz.')} disabled={busy || note.trim().length < 5}>Ekstreyi iptal et</Button>
              )}
            </DialogFooter>
          </>}
        </DialogContent>
      </Dialog>
    </div>
  );
}
