import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Info, Modal } from '../_shared';

const BeoModal = ({ beoData, markPaid, onClose }) => (
  <Modal title={`BEO — ${beoData.event.name}`} onClose={onClose} wide>
    <div className="space-y-3 text-sm">
      <Card><CardContent className="p-3 grid grid-cols-2 gap-2 text-xs">
        <Info l="Müşteri" v={beoData.event.client_name} />
        <Info l="Tip" v={beoData.event.event_type} />
        <Info l="Pax" v={beoData.event.expected_pax} />
        <Info l="Tarih" v={`${beoData.event.start_date} → ${beoData.event.end_date}`} />
        <Info l="E-posta" v={beoData.event.client_email} />
        <Info l="Telefon" v={beoData.event.client_phone} />
        {beoData.event.lost_reason && (
          <Info l="Lost/Cancel Sebebi" v={beoData.event.lost_reason} cls="text-red-600" />
        )}
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
            {beoData.spaces.map((s, i) => (
              <tr key={i}>
                <td className="border p-1">{s.space_name}</td>
                <td className="border p-1 text-center">{s.setup_style}</td>
                <td className="border p-1 text-center">{s.expected_pax}</td>
                <td className="border p-1 font-mono">{s.starts_at?.slice(0, 16)}</td>
                <td className="border p-1 font-mono">{s.ends_at?.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {beoData.agenda?.length > 0 && (
        <div>
          <h4 className="font-semibold text-sm mb-1">Fonksiyon Sheet</h4>
          <table className="w-full text-xs border-collapse">
            <thead className="bg-slate-50"><tr>
              <th className="border p-1">Saat</th>
              <th className="border p-1 text-left">Başlık</th>
              <th className="border p-1">Tip</th>
              <th className="border p-1">Sorumlu</th>
            </tr></thead>
            <tbody>
              {beoData.agenda.map((a, i) => (
                <tr key={i}>
                  <td className="border p-1 font-mono">
                    {a.starts_at?.slice(11, 16)}–{a.ends_at?.slice(11, 16)}
                  </td>
                  <td className="border p-1">{a.title}</td>
                  <td className="border p-1 text-center">{a.kind}</td>
                  <td className="border p-1">{a.owner || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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
            {beoData.resources.map((r, i) => (
              <tr key={i}>
                <td className="border p-1">{r.name}</td>
                <td className="border p-1 text-center">{r.type}</td>
                <td className="border p-1 text-center">{r.quantity}</td>
                <td className="border p-1 text-right">{r.unit_price?.toLocaleString('tr-TR')}</td>
                <td className="border p-1 text-right">
                  ₺{(r.quantity * r.unit_price).toLocaleString('tr-TR')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {beoData.payment_schedule?.length > 0 && (
        <div>
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
              {beoData.payment_schedule.map((p, i) => (
                <tr key={i}>
                  <td className="border p-1 font-mono">{p.due_date}</td>
                  <td className="border p-1">{p.label}</td>
                  <td className="border p-1 text-right">₺{p.amount?.toLocaleString('tr-TR')}</td>
                  <td className="border p-1 text-center">
                    {p.paid ? <Badge className="bg-emerald-100 text-emerald-800 border-0">Ödendi</Badge>
                            : <Badge className="bg-amber-100 text-amber-800 border-0">Bekliyor</Badge>}
                    {p.reference && <div className="text-[10px] text-gray-500 mt-0.5">Ref: {p.reference}</div>}
                  </td>
                  <td className="border p-1 text-center">
                    {!p.paid && (
                      <Button size="sm" variant="ghost"
                              onClick={() => markPaid(beoData.event.id, i)}>
                        Öde
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
        <Info l="Mekan Toplamı" v={`₺${(beoData.event.totals?.space_total || 0).toLocaleString('tr-TR')}`} />
        <Info l="Kaynak Toplamı" v={`₺${(beoData.event.totals?.resources_total || 0).toLocaleString('tr-TR')}`} />
        <Info l="GRAND TOTAL" v={`₺${(beoData.event.totals?.grand_total || 0).toLocaleString('tr-TR')}`}
              cls="text-lg text-indigo-600 font-bold" />
      </CardContent></Card>

      <div className="text-right">
        <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
        <Button variant="ghost" onClick={onClose}>Kapat</Button>
      </div>
    </div>
  </Modal>
);

export default BeoModal;
