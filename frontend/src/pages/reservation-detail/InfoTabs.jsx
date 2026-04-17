import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Pencil, Check, Globe, Phone, Star, Building2, Users, X, Mail, CreditCard, Calendar as CalendarIcon, MapPin, Loader2, ScanLine } from 'lucide-react';
import { API, fmtDate, fmtDateTime, InfoField, Avatar, EmptyState, statusLabel } from './helpers';
import QuickIdScanDialog from '@/components/QuickIdScanDialog';

export function GeneralInfoTab({ booking, guest, room, company, onGuestUpdate }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [guestForm, setGuestForm] = useState({});
  useEffect(() => { if (guest) setGuestForm({ ...guest }); }, [guest]);

  const handleSave = async () => {
    try {
      await axios.put(`/pms/reservations/${booking.id}/update-guest`, guestForm);
      toast.success('Misafir bilgileri güncellendi');
      setEditing(false);
      onGuestUpdate?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="general-info-tab">
      <div className="lg:col-span-2 space-y-4">
        {/* Sisteme dusme / olusturulma zamani */}
        {booking?.created_at && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm text-blue-800">
            Sisteme dusme zamani: <span className="font-semibold">{fmtDateTime(booking.created_at)}</span>
          </div>
        )}
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Giris Tarihi" value={fmtDate(booking?.check_in)} />
          <InfoField label="Giris Saati" value={booking?.check_in_time || booking?.checkin_time || '14:00'} />
          <InfoField label="Cikis Tarihi" value={fmtDate(booking?.check_out)} />
          <InfoField label="Cikis Saati" value={booking?.check_out_time || booking?.checkout_time || '12:00'} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Yetiskin" value={booking?.adults || booking?.guests_count || 1} />
          <InfoField label="Cocuk" value={booking?.children || 0} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Oda Tipi" value={room?.room_type || '-'} />
          <InfoField label="Oda No" value={booking?.room_number || room?.room_number || '-'} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Konaklama Turu" value={booking?.rate_plan || 'Standart'} />
          <InfoField label={t('common.cancellationPolicy')} value={booking?.cancellation_policy || t('common.flexible')} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Durum</Label>
            <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">{statusLabel(booking?.status)}</Badge>
          </div>
          <InfoField label="Kaynak" value={booking?.source_channel || booking?.channel || 'Direkt'} />
        </div>
        {booking?.special_requests && <InfoField label="Ozel Istekler" value={booking.special_requests} className="bg-amber-50 border-amber-200" />}
      </div>
      <div className="space-y-4">
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase">Ana Kontak</span>
            <Button variant="ghost" size="sm" onClick={() => setEditing(!editing)} className="h-7 px-2">
              <Pencil className="w-3 h-3 mr-1" /> {editing ? 'İptal' : 'Duzenle'}
            </Button>
          </div>
          {editing ? (
            <div className="space-y-2">
              <Input value={guestForm.name || ''} onChange={e => setGuestForm(p => ({ ...p, name: e.target.value }))} placeholder="Ad Soyad" className="h-8 text-sm" />
              <Input value={guestForm.email || ''} onChange={e => setGuestForm(p => ({ ...p, email: e.target.value }))} placeholder="E-posta" className="h-8 text-sm" />
              <Input value={guestForm.phone || ''} onChange={e => setGuestForm(p => ({ ...p, phone: e.target.value }))} placeholder="Telefon" className="h-8 text-sm" />
              <Button size="sm" onClick={handleSave} className="w-full h-8"><Check className="w-3 h-3 mr-1" /> Kaydet</Button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2 bg-teal-50 rounded-lg p-2">
                <Avatar name={guest?.name || booking?.guest_name} />
                <div>
                  <div className="text-sm font-semibold text-gray-800">{guest?.name || booking?.guest_name}</div>
                  <div className="text-xs text-gray-500">{guest?.email || '-'}</div>
                </div>
              </div>
              {guest?.phone && <div className="flex items-center gap-2 text-xs text-gray-600"><Phone className="w-3 h-3" /> {guest.phone}</div>}
              {guest?.nationality && <div className="flex items-center gap-2 text-xs text-gray-600"><Globe className="w-3 h-3" /> {guest.nationality}</div>}
              {guest?.vip_status && <Badge className="bg-amber-100 text-amber-700 border-amber-200"><Star className="w-3 h-3 mr-1" /> VIP</Badge>}
            </div>
          )}
        </div>
        <div className="border rounded-lg p-4 space-y-2">
          <span className="text-xs font-semibold text-gray-500 uppercase">Kanal</span>
          <div className="flex items-center gap-2"><Globe className="w-4 h-4 text-blue-600" /><span className="text-sm font-medium">{booking?.source_channel || 'Direkt'}</span></div>
        </div>
        {company && <div className="border rounded-lg p-4 space-y-2"><span className="text-xs font-semibold text-gray-500 uppercase">Sirket</span><div className="flex items-center gap-2"><Building2 className="w-4 h-4 text-gray-500" /><span className="text-sm">{company.name}</span></div></div>}
      </div>
    </div>
  );
}

const ID_TYPES = [
  { code: 'tc_kimlik', label: 'TC Kimlik' },
  { code: 'passport', label: 'Pasaport' },
  { code: 'driving_license', label: 'Ehliyet' },
  { code: 'other', label: 'Diger' },
];

function isQuickIdEnabled() {
  try {
    const m = JSON.parse(localStorage.getItem("modules") || "null");
    return !m || m.quick_id !== false;
  } catch { return true; }
}

export function GuestsTab({ guests, booking, onRefresh }) {
  const quickIdOn = isQuickIdEnabled();
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [scanGuestId, setScanGuestId] = useState(null);

  const startEdit = (g) => {
    setEditingId(g.id);
    setForm({
      name: g.name || '',
      email: g.email || '',
      phone: g.phone || '',
      id_type: g.id_type || 'tc_kimlik',
      id_number: g.id_number || '',
      nationality: g.nationality || '',
      date_of_birth: g.date_of_birth || '',
      gender: g.gender || '',
      address: g.address || '',
      city: g.city || '',
      country: g.country || '',
      notes: g.notes || '',
    });
  };

  const cancelEdit = () => { setEditingId(null); setForm({}); };

  const mapIdType = (dt) => {
    if (!dt) return 'tc_kimlik';
    const s = String(dt).toLowerCase();
    if (s.includes('passport') || s.includes('pasaport')) return 'passport';
    if (s.includes('driv') || s.includes('ehliyet')) return 'driving_license';
    if (s.includes('tc') || s.includes('kimlik') || s.includes('national')) return 'tc_kimlik';
    return 'other';
  };

  const applyExtractedData = (g, doc) => {
    const fullName = [doc.first_name, doc.last_name].filter(Boolean).join(' ').trim();
    const prev = editingId === g.id ? form : {
      name: g.name || '', email: g.email || '', phone: g.phone || '',
      id_type: g.id_type || 'tc_kimlik', id_number: g.id_number || '',
      nationality: g.nationality || '', date_of_birth: g.date_of_birth || '',
      gender: g.gender || '', address: g.address || '', city: g.city || '',
      country: g.country || '', notes: g.notes || '',
    };
    const next = {
      ...prev,
      name: fullName || prev.name,
      id_number: doc.id_number || doc.document_number || prev.id_number,
      id_type: mapIdType(doc.document_type) || prev.id_type,
      nationality: doc.nationality || prev.nationality,
      date_of_birth: doc.birth_date || prev.date_of_birth,
      gender: doc.gender || prev.gender,
    };
    setEditingId(g.id);
    setForm(next);
    setScanGuestId(null);
  };

  const handleSave = async (guestId, isPrimary) => {
    setSaving(true);
    try {
      if (isPrimary && booking?.id) {
        await axios.put(`/pms/reservations/${booking.id}/update-guest`, {
          name: form.name || undefined,
          email: form.email || undefined,
          phone: form.phone || undefined,
          id_number: form.id_number || undefined,
          nationality: form.nationality || undefined,
        });
      }
      await axios.put(`/pms/guests/${guestId}`, form);
      toast.success('Misafir bilgileri güncellendi');
      cancelEdit();
      onRefresh?.();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  };

  return (
    <div data-testid="guests-tab" className="space-y-3">
      {(!guests || guests.length === 0) ? <EmptyState icon={Users} text="Kayıtlı misafir bulunamadı" /> : (
        guests.map((g, i) => {
          const isPrimary = i === 0;
          const isEditing = editingId === g.id;

          return (
            <div key={g.id || i} className="border rounded-lg overflow-hidden">
              <div className="p-4 flex items-center gap-4">
                <Avatar name={g.name} size="lg" />
                <div className="flex-1">
                  <div className="text-sm font-semibold">{g.name}</div>
                  <div className="text-xs text-gray-500 flex items-center gap-3 mt-0.5">
                    {g.email && <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{g.email}</span>}
                    {g.phone && <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{g.phone}</span>}
                    {g.nationality && <span className="flex items-center gap-1"><Globe className="w-3 h-3" />{g.nationality}</span>}
                    {g.id_number && <span className="flex items-center gap-1"><CreditCard className="w-3 h-3" />{g.id_type === 'passport' ? 'Pasaport' : 'Kimlik'}: {g.id_number}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {g.vip_status && <Badge className="bg-amber-100 text-amber-700">VIP</Badge>}
                  {isPrimary && <Badge className="bg-blue-100 text-blue-700">Ana Misafir</Badge>}
                  {quickIdOn && (
                    <Button variant="outline" size="sm" className="h-8 px-2 bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100" onClick={() => setScanGuestId(g.id)} data-testid={`btn-scan-id-${g.id}`}>
                      <ScanLine className="w-3.5 h-3.5" />
                      <span className="ml-1 text-xs">Kimlik Tara</span>
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" className="h-8 px-2" onClick={() => isEditing ? cancelEdit() : startEdit(g)}>
                    {isEditing ? <X className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
                    <span className="ml-1 text-xs">{isEditing ? 'İptal' : 'Duzenle'}</span>
                  </Button>
                </div>
              </div>

              {isEditing && (
                <div className="border-t bg-gray-50 p-4 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div><Label className="text-xs">Ad Soyad</Label><Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} className="h-8 text-sm" /></div>
                    <div><Label className="text-xs">E-posta</Label><Input type="email" value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} className="h-8 text-sm" /></div>
                    <div><Label className="text-xs">Telefon</Label><Input value={form.phone} onChange={e => setForm(p => ({ ...p, phone: e.target.value }))} className="h-8 text-sm" /></div>
                    <div><Label className="text-xs">Uyruk</Label><Input value={form.nationality} onChange={e => setForm(p => ({ ...p, nationality: e.target.value }))} placeholder="TR" className="h-8 text-sm" /></div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <Label className="text-xs">Kimlik Tipi</Label>
                      <Select value={form.id_type} onValueChange={v => setForm(p => ({ ...p, id_type: v }))}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                        <SelectContent>{ID_TYPES.map(t => <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div><Label className="text-xs">Kimlik / Pasaport No</Label><Input value={form.id_number} onChange={e => setForm(p => ({ ...p, id_number: e.target.value }))} className="h-8 text-sm" /></div>
                    <div><Label className="text-xs">Dogum Tarihi</Label><Input type="date" value={form.date_of_birth} onChange={e => setForm(p => ({ ...p, date_of_birth: e.target.value }))} className="h-8 text-sm" /></div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <Label className="text-xs">Cinsiyet</Label>
                      <Select value={form.gender || ''} onValueChange={v => setForm(p => ({ ...p, gender: v }))}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Seciniz" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="male">Erkek</SelectItem>
                          <SelectItem value="female">Kadin</SelectItem>
                          <SelectItem value="other">Diger</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div><Label className="text-xs">Sehir</Label><Input value={form.city} onChange={e => setForm(p => ({ ...p, city: e.target.value }))} className="h-8 text-sm" /></div>
                    <div><Label className="text-xs">Ulke</Label><Input value={form.country} onChange={e => setForm(p => ({ ...p, country: e.target.value }))} className="h-8 text-sm" /></div>
                  </div>

                  <div><Label className="text-xs">Adres</Label><Input value={form.address} onChange={e => setForm(p => ({ ...p, address: e.target.value }))} className="h-8 text-sm" /></div>
                  <div><Label className="text-xs">Notlar</Label><Input value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} className="h-8 text-sm" /></div>

                  <div className="flex gap-2 pt-1">
                    <Button size="sm" onClick={() => handleSave(g.id, isPrimary)} disabled={saving} className="h-8">
                      {saving ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Check className="w-3 h-3 mr-1" />} Kaydet
                    </Button>
                    <Button size="sm" variant="outline" onClick={cancelEdit} className="h-8">Vazgec</Button>
                  </div>
                </div>
              )}
            </div>
          );
        })
      )}
      <QuickIdScanDialog
        open={!!scanGuestId}
        onClose={() => setScanGuestId(null)}
        onExtracted={(doc) => {
          const g = guests?.find(x => x.id === scanGuestId);
          if (g) applyExtractedData(g, doc);
        }}
      />
    </div>
  );
}
