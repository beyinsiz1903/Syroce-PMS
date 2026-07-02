import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Download, Send } from 'lucide-react';
import { promptDialog } from '@/lib/dialogs';
import { Info, Modal } from '../_shared';
const downloadBeoPdf = async (eventId, eventName) => {
  try {
    const res = await axios.get(`/mice/events/${eventId}/beo.pdf`, {
      responseType: 'blob'
    });
    const blob = new Blob([res.data], {
      type: 'application/pdf'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const safe = (eventName || 'beo').replace(/[^a-zA-Z0-9_-]+/g, '_');
    a.download = `${safe}_${eventId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    toast.error(err?.response?.data?.detail || 'PDF indirilemedi');
  }
};
const emailBeoPdf = async (eventId, eventEmail, setSending) => {
  const defaultRecipients = eventEmail || '';
  const raw = await promptDialog({
    title: 'BEO PDF Gönder',
    message: 'Alıcı e-posta adreslerini virgül ile ayırarak girin.',
    defaultValue: defaultRecipients,
    placeholder: 'mutfak@otel.com, av@otel.com',
    confirmText: 'Devam'
  });
  if (raw === null || raw === undefined) return;
  const recipients = String(raw).split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);
  if (recipients.length === 0) {
    toast.error('En az bir e-posta adresi girin');
    return;
  }
  const note = await promptDialog({
    title: 'Not (opsiyonel)',
    message: 'Mesaja eklenecek kısa bir not yazabilirsiniz.',
    defaultValue: '',
    placeholder: 'Yarın saat 10:00 itibariyle son hâli ektedir.',
    confirmText: 'Gönder'
  });
  if (note === null) return;
  try {
    setSending(true);
    const res = await axios.post(`/mice/events/${eventId}/beo/email`, {
      recipients,
      note: note ? String(note) : null
    });
    const {
      sent = 0,
      total = 0,
      failures = []
    } = res.data || {};
    if (failures.length > 0) {
      toast.warning(`${sent}/${total} alıcıya gönderildi · ${failures.length} hata`);
    } else {
      toast.success(`${sent}/${total} alıcıya gönderildi`);
    }
  } catch (err) {
    toast.error(err?.response?.data?.detail || 'PDF gönderilemedi');
  } finally {
    setSending(false);
  }
};
const BeoModal = ({
  beoData,
  markPaid,
  onClose
}) => {
  const [sending, setSending] = useState(false);
  return <Modal title={`BEO — ${beoData.event.name}`} onClose={onClose} wide>
    <div className="space-y-3 text-sm">
      <Card><CardContent className="p-3 grid grid-cols-2 gap-2 text-xs">
        <Info l="Müşteri" v={beoData.event.client_name} />
        <Info l="Tip" v={beoData.event.event_type} />
        <Info l="Pax" v={beoData.event.expected_pax} />
        <Info l="Tarih" v={`${beoData.event.start_date} → ${beoData.event.end_date}`} />
        <Info l="E-posta" v={beoData.event.client_email} />
        <Info l="Telefon" v={beoData.event.client_phone} />
        {beoData.event.lost_reason && <Info l="Lost/Cancel Sebebi" v={beoData.event.lost_reason} cls="text-red-600" />}
      </CardContent></Card>

      <div>
        <h4 className="font-semibold text-sm mb-1">Mekanlar</h4>
        <table className="w-full text-xs border-collapse">
          <thead className="bg-slate-50"><tr>
            <th className="border p-1 text-left">Mekan</th>
            <th className="border p-1">Düzen</th>
            <th className="border p-1">Pax</th>
            <th className="border p-1">Başla</th>
            <th className="border p-1">Bitir</th>
          </tr></thead>
          <tbody>
            {beoData.spaces.map((s, i) => <tr key={s.id || i}>
                <td className="border p-1">{s.space_name}</td>
                <td className="border p-1 text-center">{s.setup_style}</td>
                <td className="border p-1 text-center">{s.expected_pax}</td>
                <td className="border p-1 font-mono">{s.starts_at?.slice(0, 16)}</td>
                <td className="border p-1 font-mono">{s.ends_at?.slice(0, 16)}</td>
              </tr>)}
          </tbody>
        </table>
      </div>

      {beoData.agenda?.length > 0 && <div>
          <h4 className="font-semibold text-sm mb-1">Fonksiyon Sheet</h4>
          <table className="w-full text-xs border-collapse">
            <thead className="bg-slate-50"><tr>
              <th className="border p-1">Saat</th>
              <th className="border p-1 text-left">Başlık</th>
              <th className="border p-1">Tip</th>
              <th className="border p-1">Sorumlu</th>
            </tr></thead>
            <tbody>
              {beoData.agenda.map((a, i) => <tr key={a.id || i}>
                  <td className="border p-1 font-mono">
                    {a.starts_at?.slice(11, 16)}–{a.ends_at?.slice(11, 16)}
                  </td>
                  <td className="border p-1">{a.title}</td>
                  <td className="border p-1 text-center">{a.kind}</td>
                  <td className="border p-1">{a.owner || '—'}</td>
                </tr>)}
            </tbody>
          </table>
        </div>}

      <div>
        <h4 className="font-semibold text-sm mb-1">Kaynaklar</h4>
        <table className="w-full text-xs border-collapse">
          <thead className="bg-slate-50"><tr>
            <th className="border p-1 text-left">Hat</th>
            <th className="border p-1">Tip</th>
            <th className="border p-1">Adet</th>
            <th className="border p-1">Birim ₺</th>
            <th className="border p-1 text-right">Toplam ₺</th>
          </tr></thead>
          <tbody>
            {beoData.resources.map((r, i) => <tr key={r.id || i}>
                <td className="border p-1">{r.name}</td>
                <td className="border p-1 text-center">{r.type}</td>
                <td className="border p-1 text-center">{r.quantity}</td>
                <td className="border p-1 text-right">{r.unit_price?.toLocaleString('tr-TR')}</td>
                <td className="border p-1 text-right">
                  ₺{(r.quantity * r.unit_price).toLocaleString('tr-TR')}
                </td>
              </tr>)}
          </tbody>
        </table>
      </div>

      {beoData.payment_schedule?.length > 0 && <div>
          <h4 className="font-semibold text-sm mb-1">Ödeme Takvimi</h4>
          <table className="w-full text-xs border-collapse">
            <thead className="bg-slate-50"><tr>
              <th className="border p-1">Vade</th>
              <th className="border p-1 text-left">Etiket</th>
              <th className="border p-1 text-right">Tutar</th>
              <th className="border p-1">Durum</th>
              <th className="border p-1">Aksiyon</th>
            </tr></thead>
            <tbody>
              {beoData.payment_schedule.map((p, i) => <tr key={p.id || i}>
                  <td className="border p-1 font-mono">{p.due_date}</td>
                  <td className="border p-1">{p.label}</td>
                  <td className="border p-1 text-right">₺{p.amount?.toLocaleString('tr-TR')}</td>
                  <td className="border p-1 text-center">
                    {p.paid ? <Badge className="bg-emerald-100 text-emerald-800 border-0">Ödendi</Badge> : <Badge className="bg-amber-100 text-amber-800 border-0">Bekliyor</Badge>}
                    {p.reference && <div className="text-[10px] text-gray-500 mt-0.5">Ref: {p.reference}</div>}
                  </td>
                  <td className="border p-1 text-center">
                    {!p.paid && <Button size="sm" variant="ghost" onClick={() => markPaid(beoData.event.id, i)}>
                        Öde
                      </Button>}
                  </td>
                </tr>)}
            </tbody>
          </table>
        </div>}

      <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
        <Info l="Mekan Toplamı" v={`₺${(beoData.event.totals?.space_total || 0).toLocaleString('tr-TR')}`} />
        <Info l="Kaynak Toplamı" v={`₺${(beoData.event.totals?.resources_total || 0).toLocaleString('tr-TR')}`} />
        <Info l="GRAND TOTAL" v={`₺${(beoData.event.totals?.grand_total || 0).toLocaleString('tr-TR')}`} cls="text-lg text-indigo-600 font-bold" />
      </CardContent></Card>

      <div className="text-right flex justify-end gap-2">
        <Button variant="outline" onClick={() => downloadBeoPdf(beoData.event.id, beoData.event.name)}>
          <Download className="w-4 h-4 mr-1" /> PDF İndir
        </Button>
        <Button variant="outline" disabled={sending} onClick={() => emailBeoPdf(beoData.event.id, beoData.event.client_email, setSending)}>
          <Send className="w-4 h-4 mr-1" />
          {sending ? 'Gönderiliyor…' : 'PDF Gönder'}
        </Button>
        <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
        <Button variant="ghost" onClick={onClose}>Kapat</Button>
      </div>
    </div>
  </Modal>;
};
export default BeoModal;