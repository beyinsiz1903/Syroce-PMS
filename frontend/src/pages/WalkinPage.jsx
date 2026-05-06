import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/api/axios';
import Layout from '@/components/Layout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, UserPlus, Bed, CheckCircle2, ChevronRight, ChevronLeft, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'sonner';

const STEPS = [
  { n: 1, label: 'Misafir' },
  { n: 2, label: 'Oda & Süre' },
  { n: 3, label: 'Tutar & Onay' },
];

function Stepper({ step }) {
  return (
    <div className="flex items-center gap-2 md:gap-4">
      {STEPS.map((s, i) => {
        const active = step === s.n;
        const done = step > s.n;
        return (
          <div key={s.n} className="flex items-center gap-2">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border transition
              ${active ? 'bg-amber-600 text-white border-amber-600'
                : done ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-white text-slate-500 border-slate-200'}`}>
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold
                ${active ? 'bg-white text-amber-700'
                  : done ? 'bg-emerald-600 text-white'
                  : 'bg-slate-100 text-slate-500'}`}>
                {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : s.n}
              </span>
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && <div className="w-4 md:w-8 h-px bg-slate-300" />}
          </div>
        );
      })}
    </div>
  );
}

function RoomGroup({ type, rooms, selectedId, onSelect, nights, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between p-3 bg-slate-50 hover:bg-slate-100 transition"
      >
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-800">{type || 'Standart'}</span>
          <span className="text-xs text-slate-500">{rooms.length} oda</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
      </button>
      {open && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3">
          {rooms.map(r => {
            const sel = selectedId === r.id;
            const rate = r.rate || 0;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => onSelect(r)}
                className={`border rounded-lg p-2.5 text-left transition
                  ${sel ? 'border-amber-500 bg-amber-50 ring-1 ring-amber-300' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                data-testid={`walkin-room-${r.room_number}`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-slate-900">Oda {r.room_number}</div>
                  {sel && <CheckCircle2 className="w-4 h-4 text-amber-600" />}
                </div>
                <div className="text-[11px] text-slate-500">{r.room_type || '-'}</div>
                {rate > 0 ? (
                  <div className="text-sm mt-1.5 text-slate-700">
                    <span className="font-semibold text-slate-900">{rate.toLocaleString('tr-TR')} ₺</span>
                    <span className="text-xs text-slate-500"> / gece</span>
                  </div>
                ) : (
                  <div className="text-[11px] text-amber-700 mt-1.5">Tarife belirleyin</div>
                )}
                {sel && nights > 1 && rate > 0 && (
                  <div className="text-[11px] text-slate-500 mt-0.5">Toplam: {(rate * nights).toLocaleString('tr-TR')} ₺</div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function WalkinPage({ user, tenant, onLogout }) {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [done, setDone] = useState(false);
  const [nights, setNights] = useState(1);
  const [rooms, setRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(false);
  const [form, setForm] = useState({
    guest_name: '', phone: '', id_number: '', email: '',
    room_id: '', adults: 1, children: 0, total_amount: 0,
    payment_amount: 0, payment_method: 'cash', note: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const loadRooms = useCallback(async (n = nights) => {
    setLoadingRooms(true);
    try {
      const { data } = await api.get('/pms/walkin/available-rooms', { params: { nights: n } });
      setRooms(data.rooms || []);
    } catch (e) { toast.error('Oda yükleme hatası'); }
    finally { setLoadingRooms(false); }
  }, [nights]);

  // LAZY: sadece Adım 2'ye geçildiğinde + nights değiştiğinde yükle (Adım 1'de gereksiz fetch yok)
  useEffect(() => {
    if (step >= 2) loadRooms(nights);
    /* eslint-disable-next-line */
  }, [step, nights]);

  const selectedRoom = useMemo(() => rooms.find(r => r.id === form.room_id), [rooms, form.room_id]);

  // Oda gruplama (oda tipine göre)
  const groupedRooms = useMemo(() => {
    const grp = {};
    rooms.forEach(r => {
      const k = r.room_type || 'Standart';
      (grp[k] = grp[k] || []).push(r);
    });
    return grp;
  }, [rooms]);

  const submit = async () => {
    if (!form.guest_name.trim()) return toast.error('Misafir adı gerekli');
    if (!form.room_id) return toast.error('Oda seçin');
    if (!(form.total_amount > 0)) return toast.error('Tutar gerekli');
    setSubmitting(true);
    try {
      const { data } = await api.post('/pms/walkin/checkin', { ...form, nights });
      toast.success(`Check-in tamam — Oda ${data.room_number}`);
      setDone(true);
      setTimeout(() => nav(`/reservations/${data.booking_id}`), 1200);
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    finally { setSubmitting(false); }
  };

  const goNext = () => {
    if (step === 1) {
      if (!form.guest_name.trim()) return toast.error('Misafir adı gerekli');
    }
    if (step === 2) {
      if (!form.room_id) return toast.error('Oda seçin');
    }
    setStep(s => Math.min(3, s + 1));
  };

  const goBack = () => setStep(s => Math.max(1, s - 1));

  // Sticky özet metni
  const summaryText = (() => {
    const parts = [];
    if (form.guest_name) parts.push(form.guest_name);
    if (selectedRoom) parts.push(`Oda ${selectedRoom.room_number}`);
    if (selectedRoom) parts.push(`${nights} gece`);
    if (form.total_amount > 0) parts.push(`${form.total_amount.toLocaleString('tr-TR')} ₺`);
    return parts.join(' · ') || 'Henüz seçim yok';
  })();

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="dashboard">
      <div className="p-4 md:p-6 max-w-5xl mx-auto pb-28" data-testid="walkin-page">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
              <UserPlus className="w-6 h-6 text-amber-600" /> Walk-in Check-in
            </h1>
            <p className="text-sm text-slate-500 mt-1">Yeni misafir kaydı + oda atama + check-in</p>
          </div>
          <Stepper step={done ? 4 : step} />
        </div>

        {/* Sticky özet */}
        <div className="sticky top-0 z-10 bg-white/95 backdrop-blur border border-slate-200 rounded-lg px-3 py-2 mb-4 text-sm flex items-center gap-2 flex-wrap">
          <span className="text-xs uppercase tracking-wide text-slate-500">Özet:</span>
          <span className="text-slate-800">{summaryText}</span>
        </div>

        {done ? (
          <Card className="p-8 text-center border-emerald-200 bg-emerald-50/40">
            <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
            <div className="mt-3 text-lg font-semibold text-slate-900">Check-in tamamlandı</div>
            <div className="text-sm text-slate-600 mt-1">Rezervasyon detayına yönlendiriliyorsunuz…</div>
          </Card>
        ) : (
          <div className="space-y-4">
            {/* ADIM 1 — Misafir */}
            {step === 1 && (
              <Card className="p-5 space-y-3 border-slate-200">
                <h2 className="font-semibold text-slate-900">1. Misafir Bilgileri</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Ad Soyad <span className="text-rose-500">*</span></Label>
                    <Input value={form.guest_name} onChange={e => setForm({ ...form, guest_name: e.target.value })} className="h-9" data-testid="walkin-name" />
                  </div>
                  <div>
                    <Label className="text-xs">Telefon</Label>
                    <Input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className="h-9" />
                  </div>
                  <div>
                    <Label className="text-xs">TC / Pasaport</Label>
                    <Input value={form.id_number} onChange={e => setForm({ ...form, id_number: e.target.value })} className="h-9" />
                  </div>
                  <div>
                    <Label className="text-xs">E-posta</Label>
                    <Input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className="h-9" />
                  </div>
                  <div>
                    <Label className="text-xs">Yetişkin</Label>
                    <Input type="number" min={1} value={form.adults} onChange={e => setForm({ ...form, adults: parseInt(e.target.value || '1') })} className="h-9" />
                  </div>
                  <div>
                    <Label className="text-xs">Çocuk</Label>
                    <Input type="number" min={0} value={form.children} onChange={e => setForm({ ...form, children: parseInt(e.target.value || '0') })} className="h-9" />
                  </div>
                </div>
              </Card>
            )}

            {/* ADIM 2 — Oda */}
            {step === 2 && (
              <Card className="p-5 space-y-3 border-slate-200">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <h2 className="font-semibold flex items-center gap-2 text-slate-900">
                    <Bed className="w-4 h-4 text-amber-600" /> 2. Oda & Süre
                  </h2>
                  <div className="flex items-center gap-2">
                    <Label className="text-xs">Gece sayısı</Label>
                    <Input type="number" min={1} max={14} value={nights}
                      onChange={e => setNights(Math.max(1, parseInt(e.target.value || '1')))}
                      className="h-8 w-20" />
                    <Button size="sm" variant="outline" onClick={() => loadRooms(nights)} disabled={loadingRooms} className="border-slate-300">
                      {loadingRooms ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Yenile'}
                    </Button>
                  </div>
                </div>
                {loadingRooms ? (
                  <div className="text-center py-6"><Loader2 className="inline w-5 h-5 animate-spin text-slate-400" /></div>
                ) : rooms.length === 0 ? (
                  <div className="text-center py-8 border-2 border-dashed border-slate-200 rounded-lg text-slate-500 text-sm">
                    Müsait oda bulunamadı
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[480px] overflow-auto">
                    {Object.entries(groupedRooms).map(([type, rs], idx) => (
                      <RoomGroup
                        key={type}
                        type={type}
                        rooms={rs}
                        selectedId={form.room_id}
                        onSelect={(r) => setForm({ ...form, room_id: r.id, total_amount: (r.rate || 0) * nights })}
                        nights={nights}
                        defaultOpen={idx === 0}
                      />
                    ))}
                  </div>
                )}
              </Card>
            )}

            {/* ADIM 3 — Tutar & Onay */}
            {step === 3 && (
              <Card className="p-5 space-y-3 border-slate-200">
                <h2 className="font-semibold text-slate-900">3. Tutar & Ödeme</h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <Label className="text-xs">Toplam Tutar (₺) <span className="text-rose-500">*</span></Label>
                    <Input type="number" value={form.total_amount} onChange={e => setForm({ ...form, total_amount: parseFloat(e.target.value || '0') })} className="h-9" />
                  </div>
                  <div>
                    <Label className="text-xs">Şimdi Ödenen (₺)</Label>
                    <Input type="number" value={form.payment_amount} onChange={e => setForm({ ...form, payment_amount: parseFloat(e.target.value || '0') })} className="h-9" />
                  </div>
                  <div className="md:col-span-2">
                    <Label className="text-xs">Ödeme Türü</Label>
                    <select value={form.payment_method} onChange={e => setForm({ ...form, payment_method: e.target.value })}
                      className="h-9 w-full border border-slate-200 rounded-md px-2 text-sm bg-white">
                      <option value="cash">Nakit</option>
                      <option value="credit_card">Kredi Kartı</option>
                      <option value="bank_transfer">Havale</option>
                      <option value="none">Sonra</option>
                    </select>
                  </div>
                  <div className="md:col-span-4">
                    <Label className="text-xs">Not</Label>
                    <Input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} className="h-9" />
                  </div>
                </div>
                {selectedRoom && (
                  <div className="bg-amber-50/60 border border-amber-200 rounded-lg p-3 text-sm text-amber-900">
                    <div className="font-semibold">Onay</div>
                    <div className="mt-1 text-amber-800">
                      {form.guest_name} · Oda {selectedRoom.room_number} ({selectedRoom.room_type || '-'}) · {nights} gece · {form.adults}+{form.children} kişi
                    </div>
                    <div className="mt-1 font-semibold text-amber-900">Toplam: {form.total_amount.toLocaleString('tr-TR')} ₺</div>
                  </div>
                )}
              </Card>
            )}
          </div>
        )}

        {/* Sticky footer CTA */}
        {!done && (
          <div className="fixed bottom-0 left-0 right-0 z-20 bg-white border-t border-slate-200 px-4 py-3 md:pl-64">
            <div className="max-w-5xl mx-auto flex items-center justify-between gap-2">
              <Button variant="outline" onClick={step === 1 ? () => nav('/pms') : goBack} className="border-slate-300">
                {step === 1 ? 'İptal' : (<><ChevronLeft className="w-4 h-4 mr-1" /> Geri</>)}
              </Button>
              {step < 3 ? (
                <Button onClick={goNext} className="bg-amber-600 hover:bg-amber-700 text-white">
                  Devam <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              ) : (
                <Button onClick={submit} disabled={submitting} className="bg-amber-600 hover:bg-amber-700 text-white" data-testid="walkin-submit">
                  {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                  Check-in Tamamla {form.total_amount > 0 && `(${form.total_amount.toLocaleString('tr-TR')} ₺)`}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
