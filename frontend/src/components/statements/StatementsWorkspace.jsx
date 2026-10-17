import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, Plus, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

// One statement workflow for both parties (hotel in the PMS, agency in its
// portal). Either party issues; both agree to the same revision; the party
// that owes reports a payment, the party owed verifies it or records money
// it received. The backend enforces every rule; this only shows the actions
// open to `side`.

export const money = (value, currency) => `${Number(value || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || ''}`;
// Local calendar date; toISOString() would shift to UTC (01.09 00:00 +03 -> 31.08).
const localDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const monthStart = (now = new Date()) => localDate(new Date(now.getFullYear(), now.getMonth() - 1, 1));
export const monthEnd = (now = new Date()) => localDate(new Date(now.getFullYear(), now.getMonth(), 0));

const STATUS = {
  issued: ['Onay bekliyor', 'bg-amber-100 text-amber-800'],
  agreed: ['Mutabık', 'bg-emerald-100 text-emerald-800'],
  disputed: ['İtiraz var', 'bg-red-100 text-red-800'],
  resolved: ['İtiraz yanıtlandı', 'bg-sky-100 text-sky-800'],
  settled: ['Kapandı', 'bg-slate-200 text-slate-700'],
  void: ['İptal', 'bg-slate-100 text-slate-500'],
};
const LINE_STATUS = { confirmed: 'Onaylı', guaranteed: 'Garantili', checked_in: 'Konaklıyor', checked_out: 'Çıkış yaptı', cancelled: 'İptal', no_show: 'Gelmedi', pending: 'Beklemede' };
const TERMS = { prepaid: 'Ön ödemeli', on_arrival: 'Girişte', net_7: '7 gün vadeli', net_15: '15 gün vadeli', net_30: '30 gün vadeli' };
const NOTICE_STATUS = { pending: ['Doğrulama bekliyor', 'text-amber-700'], verified: ['Doğrulandı', 'text-emerald-700'], rejected: ['Reddedildi', 'text-red-700'] };
const PARTY = { hotel: 'otel', agency: 'acente', system: 'sistem' };
export const ADJUSTABLE = ['issued', 'disputed', 'resolved'];
const PAYABLE = ['agreed', 'resolved'];
const OPEN = ['issued', 'agreed', 'disputed', 'resolved'];

const other = side => (side === 'hotel' ? 'agency' : 'hotel');
const receiverOf = direction => ((direction || 'agency_to_hotel') === 'agency_to_hotel' ? 'hotel' : 'agency');
const debtorOf = statement => {
  const balance = Number(statement.outstanding || 0);
  if (Math.abs(balance) < 0.01) return null;
  return balance > 0 ? 'agency' : 'hotel';
};
export const balanceText = (value, currency) => {
  if (Math.abs(Number(value || 0)) < 0.01) return 'Bakiye yok';
  return Number(value) > 0 ? `Acente ödeyecek: ${money(value, currency)}` : `Otel ödeyecek: ${money(-value, currency)}`;
};
const issuerText = (statement, side) => {
  const issuer = statement.issuer || 'hotel';
  if (issuer === 'system') return 'Otomatik (aylık)';
  return issuer === side ? 'Sizin düzenlediğiniz' : `${PARTY[issuer] === 'otel' ? 'Otel' : 'Acente'} düzenledi`;
};
const waitingText = (statement, side) => {
  if (!['issued', 'resolved'].includes(statement.status)) return null;
  const agreed = statement.agreements || {};
  const revision = statement.revision || 1;
  return agreed[side] === revision ? `${PARTY[other(side)] === 'otel' ? 'Otelin' : 'Acentenin'} onayı bekleniyor` : 'Onayınız bekleniyor';
};

const editsToAdjustments = edits => Object.entries(edits || {}).map(([booking_id, edit]) => ({ booking_id, amount: Number(edit.amount || 0), reason: (edit.reason || '').trim() }));
const invalidEdit = edits => editsToAdjustments(edits).some(item => Number.isNaN(item.amount) || (Math.abs(item.amount) >= 0.01 && item.reason.length < 5));
const withEdit = (current, bookingId, edit) => {
  const next = { ...current };
  if (edit) next[bookingId] = edit; else delete next[bookingId];
  return next;
};

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
                  {line.adjustment && <div className="text-amber-700" data-testid={`adjustment-${line.booking_id}`}>{line.adjustment.side === 'agency' ? 'Acente' : 'Otel'} düzeltmesi {line.adjustment.amount > 0 ? '+' : '−'}{money(Math.abs(line.adjustment.amount), '')} · {line.adjustment.reason}</div>}</td>
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

const emptyPayment = () => ({ amount: '', paid_at: localDate(new Date()), method: 'bank_transfer', reference: '', file: null });

export default function StatementsWorkspace({ side, api, base, partiesPath, title, description }) {
  const counterpart = PARTY[other(side)];
  const sendLabel = side === 'hotel' ? 'Acenteye gönder' : 'Otele gönder';
  const partyKey = side === 'hotel' ? 'agency_id' : 'tenant_id';
  const [items, setItems] = useState([]);
  const [parties, setParties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ party: '', period_start: monthStart(), period_end: monthEnd(), currency: 'TRY' });
  const [issuing, setIssuing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewEdits, setPreviewEdits] = useState({});
  // A correction typed after the last calculation is not what the preview shows.
  const [previewStale, setPreviewStale] = useState(false);
  const [detail, setDetail] = useState(null);
  const [lineEdits, setLineEdits] = useState({});
  const [note, setNote] = useState('');
  const [noticeNote, setNoticeNote] = useState('');
  const [payment, setPayment] = useState(emptyPayment());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: list }, { data: partyData }] = await Promise.all([api.get(base), api.get(partiesPath)]);
      setItems(list.items || []);
      const rows = side === 'hotel'
        ? (partyData.agencies || []).map(row => ({ id: row.id, name: row.name }))
        : (partyData.hotels || []).map(row => ({ id: row.tenant_id, name: row.name, currency: row.currency }));
      setParties(rows);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ekstreler yüklenemedi.');
    } finally {
      setLoading(false);
    }
  }, [api, base, partiesPath, side]);
  useEffect(() => { load(); }, [load]);

  const body = edits => ({ [partyKey]: form.party, period_start: form.period_start, period_end: form.period_end, currency: form.currency, adjustments: editsToAdjustments(edits) });
  const runPreview = async (edits = previewEdits) => {
    if (!form.party) return toast.error(side === 'hotel' ? 'Acente seçin.' : 'Otel seçin.');
    if (invalidEdit(edits)) return toast.error('Her düzeltme için tutar ve en az 5 karakter gerekçe girin.');
    setIssuing(true);
    try {
      const { data } = await api.post(`${base}/preview`, body(edits));
      setPreview(data);
      setPreviewStale(false);
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre hesaplanamadı.'); }
    finally { setIssuing(false); }
  };
  const openPreview = () => { setPreviewEdits({}); runPreview({}); };
  const issue = async () => {
    if (previewStale) return toast.error('Düzeltmeler değişti; göndermeden önce yeniden hesaplayın.');
    if (invalidEdit(previewEdits)) return toast.error('Her düzeltme için tutar ve en az 5 karakter gerekçe girin.');
    setIssuing(true);
    try {
      const { data } = await api.post(base, { ...body(previewEdits), expected_signature: preview?.signature ?? null, expected_net_balance: preview?.totals?.net_balance ?? null });
      toast.success(`${data.number} düzenlendi ve ${counterpart === 'otel' ? 'otele' : 'acenteye'} iletildi.`);
      setPreview(null);
      setPreviewEdits({});
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre düzenlenemedi.'); }
    finally { setIssuing(false); }
  };
  const editPreviewLine = (bookingId, edit) => { setPreviewStale(true); setPreviewEdits(current => withEdit(current, bookingId, edit)); };

  const open = async statement => {
    try {
      setDetail((await api.get(`${base}/${statement.id}`)).data);
      setNote('');
      setNoticeNote('');
      setLineEdits({});
      setPayment(emptyPayment());
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre açılamadı.'); }
  };
  const act = async (path, payload, success) => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/${detail.id}/${path}`, payload);
      setDetail(data);
      toast.success(success);
      await load();
      return true;
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem tamamlanamadı.');
      if (err.response?.status === 409) {
        try { setDetail((await api.get(`${base}/${detail.id}`)).data); } catch { /* keep the dialog */ }
      }
      return false;
    } finally { setBusy(false); }
  };
  const saveLineEdits = async () => {
    if (invalidEdit(lineEdits)) return toast.error('Her düzeltme için tutar ve en az 5 karakter gerekçe girin.');
    for (const item of editsToAdjustments(lineEdits)) {
      const ok = await act('adjust', item, `Düzeltme kaydedildi ve ${counterpart === 'otel' ? 'otele' : 'acenteye'} bildirildi.`);
      if (!ok) return;
    }
    setLineEdits({});
  };
  const reportPayment = async event => {
    event.preventDefault();
    const data = new FormData();
    data.append('amount', payment.amount);
    data.append('paid_at', payment.paid_at);
    data.append('reference', payment.reference.trim());
    data.append('method', payment.method);
    if (payment.file) data.append('proof', payment.file);
    if (await act('payment-notices', data, `Ödeme bildiriminiz ${counterpart === 'otel' ? 'otele' : 'acenteye'} iletildi; doğrulanınca bakiyeye işlenir.`)) setPayment(emptyPayment());
  };
  const recordReceived = async event => {
    event.preventDefault();
    const amount = Number(payment.amount);
    if (!(amount > 0)) return toast.error('Geçerli bir tutar girin.');
    const direction = side === 'hotel' ? 'agency_to_hotel' : 'hotel_to_agency';
    if (await act('payments', { amount, paid_at: payment.paid_at, method: payment.method, reference: payment.reference.trim(), direction }, 'Ödeme kaydedildi.')) setPayment(emptyPayment());
  };
  const decideNotice = async (notice, verify) => {
    await act(`payment-notices/${notice.id}/${verify ? 'verify' : 'reject'}`, { note: noticeNote.trim() },
      verify ? 'Ödeme doğrulandı ve ekstreye işlendi.' : `Ödeme bildirimi reddedildi; ${counterpart === 'otel' ? 'otele' : 'acenteye'} iletildi.`);
    setNoticeNote('');
  };
  const openProof = async notice => {
    try {
      const { data } = await api.get(`${base}/${detail.id}/payment-notices/${notice.id}/proof`, { responseType: 'blob' });
      window.open(URL.createObjectURL(data), '_blank', 'noopener');
    } catch { toast.error('Dekont açılamadı.'); }
  };

  const pendingForMe = statement => (statement.payment_notices || []).filter(n => n.status === 'pending' && receiverOf(n.direction) === side);
  const revision = detail?.revision || 1;
  const canAgree = detail && ['issued', 'resolved'].includes(detail.status) && (detail.agreements || {})[side] !== revision;
  const canDispute = detail && (detail.issuer || 'hotel') !== side && ['issued', 'resolved'].includes(detail.status);
  const canResolve = detail && detail.status === 'disputed' && (detail.dispute?.by_side || 'agency') !== side;
  const canVoid = detail && [side, 'system'].includes(detail.issuer || 'hotel') && OPEN.includes(detail.status) && !detail.payments?.length;
  const canEditLines = detail && ADJUSTABLE.includes(detail.status) && !detail.payments?.length;
  const payable = detail && PAYABLE.includes(detail.status) && debtorOf(detail);
  const iOwe = payable && debtorOf(detail) === side;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">{title || 'Yeni ekstre'}</CardTitle>
            <Button variant="outline" size="sm" onClick={load}><RefreshCw size={14} className="mr-2" />Yenile</Button>
          </div>
          {description && <p className="text-xs text-slate-500">{description}</p>}
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-5">
          <div className="sm:col-span-2"><Label htmlFor={`st-party-${side}`}>{side === 'hotel' ? 'Acente' : 'Otel'}</Label>
            <select id={`st-party-${side}`} className="h-10 w-full rounded-md border px-3 text-sm" value={form.party} onChange={e => {
              const chosen = parties.find(row => row.id === e.target.value);
              setForm(f => ({ ...f, party: e.target.value, currency: chosen?.currency || f.currency }));
            }}>
              <option value="">Seçin</option>
              {parties.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </div>
          <div><Label htmlFor={`st-start-${side}`}>Başlangıç</Label><Input id={`st-start-${side}`} type="date" value={form.period_start} onChange={e => setForm(f => ({ ...f, period_start: e.target.value }))} /></div>
          <div><Label htmlFor={`st-end-${side}`}>Bitiş</Label><Input id={`st-end-${side}`} type="date" value={form.period_end} onChange={e => setForm(f => ({ ...f, period_end: e.target.value }))} /></div>
          <div><Label htmlFor={`st-cur-${side}`}>Para birimi</Label><Input id={`st-cur-${side}`} maxLength={3} value={form.currency} onChange={e => setForm(f => ({ ...f, currency: e.target.value.toUpperCase() }))} /></div>
          <div className="sm:col-span-5"><Button onClick={openPreview} disabled={issuing}>{issuing ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Plus size={14} className="mr-2" />}Ekstreyi önizle</Button>
            <p className="mt-1 text-xs text-slate-500">Önizlemede satırları kontrol edip gerekirse düzeltin; ekstre ancak "{sendLabel}" ile oluşur. Her ayın 1'inde önceki ayın ekstresi otomatik de düzenlenir.</p></div>
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
                    <div className="font-medium">{statement.number} · {side === 'hotel' ? statement.agency_name : statement.hotel_name}</div>
                    <div className="text-xs text-slate-500">{statement.period_start} – {statement.period_end} · {issuerText(statement, side)}{statement.totals ? ` · ${statement.totals.bookings} konaklama · ${(statement.totals.cancelled || 0) + (statement.totals.no_show || 0)} iptal/no-show` : ''}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {pendingForMe(statement).length > 0 && <Badge className="bg-amber-100 text-amber-800">{pendingForMe(statement).length} ödeme bildirimi</Badge>}
                    <span className="text-sm">{balanceText(statement.outstanding, statement.currency)}</span>
                    <Badge className={STATUS[statement.status]?.[1]}>{STATUS[statement.status]?.[0] || statement.status}</Badge>
                    {waitingText(statement, side) && <span className="text-xs text-slate-500">{waitingText(statement, side)}</span>}
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
              <DialogTitle>Önizleme · {side === 'hotel' ? preview.agency_name : preview.hotel_name}</DialogTitle>
              <p className="text-sm text-slate-500">{preview.period_start} – {preview.period_end} · {balanceText(preview.outstanding, preview.currency)}{preview.totals?.adjustments ? ` · düzeltmeler ${money(preview.totals.adjustments, preview.currency)}` : ''}</p>
              <p className="text-xs text-slate-500">Henüz kaydedilmedi; {counterpart} bilgilendirilmedi. Düzeltmek istediğiniz satırın kutucuğunu işaretleyin.</p>
            </DialogHeader>
            <StatementLines lines={preview.lines} currency={preview.currency} edits={previewEdits} onEdit={editPreviewLine} />
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => runPreview()} disabled={issuing}>Yeniden hesapla</Button>
              {previewStale && <span className="self-center text-xs text-amber-700">Düzeltmeler değişti; göndermeden önce yeniden hesaplayın.</span>}
              <Button onClick={issue} disabled={issuing || previewStale}>{issuing ? <Loader2 size={14} className="mr-2 animate-spin" /> : null}{sendLabel}</Button>
            </DialogFooter>
          </div>}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(detail)} onOpenChange={value => !value && setDetail(null)}>
        <DialogContent className="max-w-3xl">
          {detail && <>
            <DialogHeader>
              <DialogTitle>{detail.number} · {side === 'hotel' ? detail.agency_name : detail.hotel_name}</DialogTitle>
              <p className="text-sm text-slate-500">{detail.period_start} – {detail.period_end} · {STATUS[detail.status]?.[0]} · {balanceText(detail.outstanding, detail.currency)} · {issuerText(detail, side)}</p>
              {['issued', 'resolved'].includes(detail.status) && <p className="text-xs text-slate-500" data-testid="agreement-state">
                Otel: {(detail.agreements || {}).hotel === revision ? 'onayladı' : 'onay bekleniyor'} · Acente: {(detail.agreements || {}).agency === revision ? 'onayladı' : 'onay bekleniyor'}
              </p>}
            </DialogHeader>
            <StatementLines lines={detail.lines || []} currency={detail.currency} highlight={detail.dispute?.booking_ids || []}
              edits={canEditLines ? lineEdits : undefined} onEdit={(id, edit) => setLineEdits(current => withEdit(current, id, edit))} />
            {Object.keys(lineEdits).length > 0 && <div className="flex justify-end"><Button size="sm" onClick={saveLineEdits} disabled={busy}>Düzeltmeyi kaydet ve {counterpart === 'otel' ? 'otele' : 'acenteye'} bildir</Button></div>}
            {detail.dispute && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm"><strong>İtiraz ({PARTY[detail.dispute.by_side || 'agency']}):</strong> {detail.dispute.reason}</div>}
            {detail.payments?.length > 0 && <div className="text-xs text-slate-600">Ödemeler: {detail.payments.map(p => `${p.paid_at} ${money(p.amount, detail.currency)} (${p.direction === 'agency_to_hotel' ? 'acente→otel' : 'otel→acente'})`).join(' · ')}</div>}

            {detail.payment_notices?.length > 0 && <div className="space-y-2 rounded border p-3" data-testid="payment-notices">
              <div className="text-sm font-medium">Ödeme bildirimleri</div>
              <p className="text-xs text-slate-500">Bildirim, ödemeyi alan taraf doğrulayana kadar bakiyeyi ve kredi limitini değiştirmez.</p>
              {detail.payment_notices.map(notice => {
                const mine = receiverOf(notice.direction) === side;
                return <div key={notice.id} className="flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs">
                  <span>{notice.paid_at} · {money(notice.amount, detail.currency)} · ref {notice.reference} · {notice.direction === 'hotel_to_agency' ? 'otel→acente' : 'acente→otel'}</span>
                  <span className="flex items-center gap-2">
                    {notice.has_proof && <button type="button" className="underline" onClick={() => openProof(notice)}>Dekont</button>}
                    <span className={NOTICE_STATUS[notice.status]?.[1]}>{NOTICE_STATUS[notice.status]?.[0] || notice.status}{notice.note ? `: ${notice.note}` : ''}</span>
                    {notice.status === 'pending' && mine && <>
                      <Button size="sm" onClick={() => decideNotice(notice, true)} disabled={busy}>Doğrula</Button>
                      <Button size="sm" variant="outline" className="text-red-700" onClick={() => decideNotice(notice, false)} disabled={busy || noticeNote.trim().length < 5}>Reddet</Button>
                    </>}
                  </span>
                </div>;
              })}
              {pendingForMe(detail).length > 0 && <Input placeholder="Not (reddederken zorunlu, en az 5 karakter)" value={noticeNote} onChange={e => setNoticeNote(e.target.value)} />}
            </div>}

            {payable && (iOwe ? (
              <form onSubmit={reportPayment} className="grid gap-2 rounded border p-3 sm:grid-cols-4" data-testid="report-payment-form">
                <div className="text-sm font-medium sm:col-span-4">Ödeme bildir <span className="text-xs font-normal text-slate-500">({counterpart} doğruladığında bakiyeye işlenir)</span></div>
                <Input type="number" min="0.01" step="0.01" required placeholder="Tutar" aria-label="Bildirilen tutar" value={payment.amount} onChange={e => setPayment(p => ({ ...p, amount: e.target.value }))} />
                <Input type="date" required aria-label="Ödeme tarihi" max={localDate(new Date())} value={payment.paid_at} onChange={e => setPayment(p => ({ ...p, paid_at: e.target.value }))} />
                <Input required minLength={3} maxLength={120} placeholder="Banka referansı" aria-label="Banka referansı" value={payment.reference} onChange={e => setPayment(p => ({ ...p, reference: e.target.value }))} />
                <Input type="file" aria-label="Dekont" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={e => setPayment(p => ({ ...p, file: e.target.files?.[0] || null }))} />
                <div className="sm:col-span-4"><Button type="submit" size="sm" disabled={busy}>Bildir</Button></div>
              </form>
            ) : (
              <form onSubmit={recordReceived} className="grid gap-2 rounded border p-3 sm:grid-cols-4" data-testid="record-payment-form">
                <div className="text-sm font-medium sm:col-span-4">Ödeme alındı <span className="text-xs font-normal text-slate-500">(hesabınıza geçen tutarı kaydedin)</span></div>
                <Input type="number" min="0" step="0.01" placeholder="Tutar" aria-label="Alınan tutar" value={payment.amount} onChange={e => setPayment(p => ({ ...p, amount: e.target.value }))} />
                <Input type="date" aria-label="Alındığı tarih" value={payment.paid_at} onChange={e => setPayment(p => ({ ...p, paid_at: e.target.value }))} />
                <Input placeholder="Referans / dekont no" aria-label="Alınan ödeme referansı" value={payment.reference} onChange={e => setPayment(p => ({ ...p, reference: e.target.value }))} />
                <Button type="submit" disabled={busy}>Ödeme kaydet</Button>
              </form>
            ))}

            {canDispute && <p className="text-xs text-slate-500">İtiraz ettiğiniz satırları kutucukla işaretleyebilirsiniz; işaretli satırlar itirazla birlikte iletilir.</p>}
            {(canDispute || canResolve || canVoid) && (
              <textarea className="min-h-16 w-full rounded-md border p-2 text-sm" placeholder={canResolve ? 'İtiraza yanıtınız (en az 5 karakter)' : canDispute ? 'İtiraz gerekçesi veya iptal notu (en az 5 karakter)' : 'İptal gerekçesi (en az 5 karakter)'} value={note} onChange={e => setNote(e.target.value)} />
            )}
            <DialogFooter className="gap-2">
              {canResolve && <Button onClick={() => act('resolve', { note }, 'İtiraz yanıtlandı.')} disabled={busy || note.trim().length < 5}>İtirazı yanıtla</Button>}
              {canDispute && <Button variant="outline" onClick={() => act('dispute', { reason: note.trim(), booking_ids: Object.keys(lineEdits) }, 'İtirazınız iletildi.')} disabled={busy || note.trim().length < 5}>İtiraz et</Button>}
              {canVoid && <Button variant="destructive" onClick={() => act('void', { note }, 'Ekstre iptal edildi; yeniden düzenleyebilirsiniz.')} disabled={busy || note.trim().length < 5}>Ekstreyi iptal et</Button>}
              {canAgree && <Button onClick={() => act('agree', { revision }, 'Onayınız kaydedildi.')} disabled={busy}>Mutabıkız</Button>}
            </DialogFooter>
          </>}
        </DialogContent>
      </Dialog>
    </div>
  );
}
