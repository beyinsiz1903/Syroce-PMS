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
const money = (value, currency) => `${Number(value || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || ''}`;
// Local calendar date; toISOString() would shift to UTC (01.09 00:00 +03 -> 31.08).
const localDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const monthStart = (now = new Date()) => localDate(new Date(now.getFullYear(), now.getMonth() - 1, 1));
export const monthEnd = (now = new Date()) => localDate(new Date(now.getFullYear(), now.getMonth(), 0));
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

  const issue = async () => {
    if (!form.agency_id) return toast.error('Acente seçin.');
    setIssuing(true);
    try {
      const { data } = await axios.post('/marketplace/hotel/statements', form);
      toast.success(`${data.number} düzenlendi ve acenteye iletildi.`);
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre düzenlenemedi.'); }
    finally { setIssuing(false); }
  };
  const open = async statement => {
    try {
      setDetail((await axios.get(`/marketplace/hotel/statements/${statement.id}`)).data);
      setNote('');
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
          <div className="sm:col-span-5"><Button onClick={issue} disabled={issuing}>{issuing ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Plus size={14} className="mr-2" />}Ekstre düzenle ve acenteye gönder</Button></div>
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
                    <span className="text-sm">{balanceText(statement.outstanding, statement.currency)}</span>
                    <Badge className={STATUS[statement.status]?.[1]}>{STATUS[statement.status]?.[0] || statement.status}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(detail)} onOpenChange={value => !value && setDetail(null)}>
        <DialogContent className="max-w-3xl">
          {detail && <>
            <DialogHeader>
              <DialogTitle>{detail.number} · {detail.agency_name}</DialogTitle>
              <p className="text-sm text-slate-500">{detail.period_start} – {detail.period_end} · {STATUS[detail.status]?.[0]} · {balanceText(detail.outstanding, detail.currency)}</p>
            </DialogHeader>
            <div className="max-h-72 overflow-y-auto rounded border text-xs">
              <table className="w-full">
                <thead className="bg-slate-50 text-left"><tr><th className="p-2">Rezervasyon</th><th>Durum</th><th>Ödeme</th><th className="text-right">Brüt/Ceza</th><th className="text-right">Komisyon</th><th className="text-right p-2">Otel→Acente / Acente→Otel</th></tr></thead>
                <tbody>
                  {detail.lines.map(line => (
                    <tr key={line.booking_id} className={`border-t ${detail.dispute?.booking_ids?.includes(line.booking_id) ? 'bg-red-50' : ''}`}>
                      <td className="p-2">{line.confirmation_code}<div className="text-slate-400">{line.check_in} · {line.guest_name}</div></td>
                      <td>{line.status}</td><td>{line.payment_terms}</td>
                      <td className="text-right">{money(line.gross, detail.currency)}</td>
                      <td className="text-right">{money(line.commission, detail.currency)}</td>
                      <td className="p-2 text-right">{money(line.hotel_owes_agency, '')} / {money(line.agency_owes_hotel, '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {detail.dispute && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm"><strong>İtiraz:</strong> {detail.dispute.reason}</div>}
            {detail.payments?.length > 0 && <div className="text-xs text-slate-600">Ödemeler: {detail.payments.map(p => `${p.paid_at} ${money(p.amount, detail.currency)} (${p.direction === 'agency_to_hotel' ? 'acente→otel' : 'otel→acente'})`).join(' · ')}</div>}
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
