import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, UserPlus, Bed, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

export default function WalkinPage() {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [nights, setNights] = useState(1);
  const [rooms, setRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(false);
  const [form, setForm] = useState({
    guest_name: '', phone: '', id_number: '', email: '',
    room_id: '', adults: 1, children: 0, total_amount: 0,
    payment_amount: 0, payment_method: 'cash', note: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const loadRooms = async (n = nights) => {
    setLoadingRooms(true);
    try {
      const { data } = await api.get('/pms/walkin/available-rooms', { params: { nights: n } });
      setRooms(data.rooms || []);
    } catch (e) { toast.error('Oda yükleme hatası'); }
    finally { setLoadingRooms(false); }
  };

  useEffect(() => { loadRooms(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { loadRooms(nights); /* eslint-disable-next-line */ }, [nights]);

  const selectedRoom = useMemo(() => rooms.find(r => r.id === form.room_id), [rooms, form.room_id]);
  useEffect(() => {
    if (selectedRoom && !form.total_amount) {
      setForm(f => ({ ...f, total_amount: (selectedRoom.rate || 0) * nights }));
    }
    // eslint-disable-next-line
  }, [selectedRoom, nights]);

  const submit = async () => {
    if (!form.guest_name.trim()) return toast.error('Misafir adı gerekli');
    if (!form.room_id) return toast.error('Oda seçin');
    if (!(form.total_amount > 0)) return toast.error('Tutar gerekli');
    setSubmitting(true);
    try {
      const { data } = await api.post('/pms/walkin/checkin', { ...form, nights });
      toast.success(`Check-in tamam — Oda ${data.room_number}`);
      setStep(3);
      setTimeout(() => nav(`/reservations/${data.booking_id}`), 1200);
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4" data-testid="walkin-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <UserPlus className="w-6 h-6 text-emerald-600" /> Walk-in Check-in
        </h1>
        <p className="text-sm text-gray-500 mt-1">30 saniyede yeni misafir kaydı + oda + check-in</p>
      </div>

      {step === 3 ? (
        <Card className="p-8 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
          <div className="mt-3 text-lg font-semibold">Check-in tamamlandı</div>
          <div className="text-sm text-gray-500 mt-1">Rezervasyon detayına yönlendiriliyorsunuz...</div>
        </Card>
      ) : (
        <>
          <Card className="p-4 space-y-3">
            <h2 className="font-semibold">1. Misafir</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div><Label className="text-xs">Ad Soyad *</Label>
                <Input value={form.guest_name} onChange={e => setForm({ ...form, guest_name: e.target.value })} className="h-9" data-testid="walkin-name" /></div>
              <div><Label className="text-xs">Telefon</Label>
                <Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className="h-9" /></div>
              <div><Label className="text-xs">TC / Pasaport</Label>
                <Input value={form.id_number} onChange={e => setForm({ ...form, id_number: e.target.value })} className="h-9" /></div>
              <div><Label className="text-xs">E-posta</Label>
                <Input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className="h-9" /></div>
            </div>
          </Card>

          <Card className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold flex items-center gap-2"><Bed className="w-4 h-4" /> 2. Oda & Süre</h2>
              <div className="flex items-center gap-2">
                <Label className="text-xs">Gece</Label>
                <Input type="number" min={1} max={14} value={nights} onChange={e => setNights(Math.max(1, parseInt(e.target.value || '1')))} className="h-8 w-20" />
                <Button size="sm" variant="outline" onClick={() => loadRooms(nights)} disabled={loadingRooms}>
                  {loadingRooms ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Yenile'}
                </Button>
              </div>
            </div>
            {loadingRooms ? (
              <div className="text-center py-4"><Loader2 className="inline w-5 h-5 animate-spin" /></div>
            ) : rooms.length === 0 ? (
              <div className="text-center py-4 text-gray-500 text-sm">Müsait oda bulunamadı</div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 max-h-72 overflow-auto">
                {rooms.map(r => (
                  <button key={r.id} onClick={() => setForm({ ...form, room_id: r.id, total_amount: (r.rate || 0) * nights })}
                    className={`border rounded-lg p-2 text-left hover:bg-gray-50 ${form.room_id === r.id ? 'border-emerald-500 bg-emerald-50' : 'border-gray-200'}`}
                    data-testid={`walkin-room-${r.room_number}`}>
                    <div className="font-semibold">Oda {r.room_number}</div>
                    <div className="text-xs text-gray-500">{r.room_type || '-'}</div>
                    <div className="text-sm mt-1">{(r.rate || 0).toLocaleString('tr-TR')} TL/gece</div>
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-4 space-y-3">
            <h2 className="font-semibold">3. Tutar & Ödeme</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div><Label className="text-xs">Yetişkin</Label>
                <Input type="number" min={1} value={form.adults} onChange={e => setForm({ ...form, adults: parseInt(e.target.value || '1') })} className="h-9" /></div>
              <div><Label className="text-xs">Çocuk</Label>
                <Input type="number" min={0} value={form.children} onChange={e => setForm({ ...form, children: parseInt(e.target.value || '0') })} className="h-9" /></div>
              <div><Label className="text-xs">Toplam Tutar (TL) *</Label>
                <Input type="number" value={form.total_amount} onChange={e => setForm({ ...form, total_amount: parseFloat(e.target.value || '0') })} className="h-9" /></div>
              <div><Label className="text-xs">Şimdi Ödenen</Label>
                <Input type="number" value={form.payment_amount} onChange={e => setForm({ ...form, payment_amount: parseFloat(e.target.value || '0') })} className="h-9" /></div>
              <div className="md:col-span-2"><Label className="text-xs">Ödeme Türü</Label>
                <select value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value })}
                  className="h-9 w-full border rounded-md px-2 text-sm">
                  <option value="cash">Nakit</option>
                  <option value="credit_card">Kredi Kartı</option>
                  <option value="bank_transfer">Havale</option>
                  <option value="none">Sonra</option>
                </select></div>
              <div className="md:col-span-2"><Label className="text-xs">Not</Label>
                <Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} className="h-9" /></div>
            </div>
          </Card>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => nav('/pms')}>İptal</Button>
            <Button onClick={submit} disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700" data-testid="walkin-submit">
              {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
              Check-in Yap
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
