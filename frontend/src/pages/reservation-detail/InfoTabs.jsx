import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Pencil, Check, Globe, Phone, Star, Building2, Users, X, Mail, CreditCard, Calendar as CalendarIcon, MapPin, Loader2, ScanLine, Crown, AlertTriangle, ShieldAlert, Cake, Repeat, BedDouble, CalendarDays, UserCircle2 } from 'lucide-react';
import { API, fmtDate, InfoField, Avatar, EmptyState, statusLabel, translateValue, SectionHeader } from './helpers';
import QuickIdScanDialog from '@/components/QuickIdScanDialog';
import api from '@/api/axios';

const ALERT_LEVEL_BG = {
  danger: 'bg-red-50 border-red-300 text-red-800',
  warning: 'bg-amber-50 border-amber-300 text-amber-800',
  gold: 'bg-yellow-50 border-yellow-300 text-yellow-900',
  info: 'bg-blue-50 border-blue-300 text-blue-800',
};
const ALERT_ICON = { vip: Crown, repeat: Repeat, blacklist: ShieldAlert, allergy: AlertTriangle, note: AlertTriangle, special_date: Cake };

export function GeneralInfoTab({ booking, guest, room, company, onGuestUpdate }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [guestForm, setGuestForm] = useState({});
  const [highlights, setHighlights] = useState(null);
  const [risk, setRisk] = useState(null);
  useEffect(() => { if (guest) setGuestForm({ ...guest }); }, [guest]);
  useEffect(() => {
    const gid = guest?.id || booking?.guest_id;
    if (!gid) return;
    api.get(`/pms/guests/${gid}/highlights`).then(r => setHighlights(r.data)).catch(() => setHighlights(null));
  }, [guest?.id, booking?.guest_id]);
  useEffect(() => {
    if (!booking?.id) return;
    const st = (booking.status || '').toLowerCase();
    if (['checked_in', 'in_house', 'checked_out', 'cancelled', 'no_show'].includes(st)) { setRisk(null); return; }
    api.get(`/pms/no-show-risk/${booking.id}`).then(r => setRisk(r.data)).catch(() => setRisk(null));
  }, [booking?.id, booking?.status]);

  const handleSave = async () => {
    try {
      await axios.put(`/pms/reservations/${booking.id}/update-guest`, guestForm);
      toast.success('Misafir bilgileri güncellendi');
      setEditing(false);
      onGuestUpdate?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const nights = booking?.check_in && booking?.check_out
    ? Math.max(1, Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24)))
    : 1;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="general-info-tab">
      <div className="lg:col-span-2 space-y-5">
        {risk && (
          <div className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-sm ${
            risk.level === 'high' ? 'bg-red-50 border-red-300 text-red-800'
            : risk.level === 'medium' ? 'bg-amber-50 border-amber-300 text-amber-800'
            : 'bg-emerald-50 border-emerald-200 text-emerald-800'
          }`} data-testid="no-show-risk-banner">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="font-semibold">No-Show Risk Skoru: {risk.score}/100 — {risk.level === 'high' ? 'Yüksek' : risk.level === 'medium' ? 'Orta' : 'Düşük'}</div>
              {risk.factors?.length > 0 && (
                <div className="text-xs mt-1 opacity-90">
                  {risk.factors.slice(0, 4).map((f, i) => (
                    <span key={i} className="mr-2">· {f.label} ({f.delta > 0 ? '+' : ''}{f.delta})</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        {highlights?.has_alerts && (
          <div className="space-y-1.5" data-testid="guest-highlights-banner">
            {highlights.alerts.map((a, i) => {
              const Icon = ALERT_ICON[a.type] || AlertTriangle;
              return (
                <div key={i} className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-sm ${ALERT_LEVEL_BG[a.level] || ALERT_LEVEL_BG.info}`}>
                  <Icon className="w-4 h-4 mt-0.5 shrink-0" />
                  <span className="font-medium">{a.message}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Bölüm 1: Tarih & Süre */}
        <section className="space-y-3">
          <SectionHeader icon={CalendarDays} title="Tarih & Süre" />
          <div className="grid grid-cols-2 gap-4">
            <InfoField label="Giriş Tarihi" value={fmtDate(booking?.check_in)} />
            <InfoField label="Giriş Saati" value={booking?.check_in_time || booking?.checkin_time || '14:00'} />
            <InfoField label="Çıkış Tarihi" value={fmtDate(booking?.check_out)} />
            <InfoField label="Çıkış Saati" value={booking?.check_out_time || booking?.checkout_time || '12:00'} />
            {booking?.checked_in_at && (
              <InfoField label="Gerçekleşen Giriş" value={new Date(booking.checked_in_at).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })} />
            )}
            {booking?.checked_out_at && (
              <InfoField label="Gerçekleşen Çıkış" value={new Date(booking.checked_out_at).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })} />
            )}
            <InfoField label="Konaklama Süresi" value={`${nights} gece`} />
          </div>
        </section>

        {/* Bölüm 2: Konuk Sayısı */}
        <section className="space-y-3">
          <SectionHeader icon={UserCircle2} title="Konuk Sayısı" />
          <div className="grid grid-cols-2 gap-4">
            <InfoField label="Yetişkin" value={booking?.adults || booking?.guests_count || 1} />
            <InfoField label="Çocuk" value={booking?.children || 0} />
          </div>
        </section>

        {/* Bölüm 3: Oda & Tarife */}
        <section className="space-y-3">
          <SectionHeader icon={BedDouble} title="Oda & Tarife" />
          <div className="grid grid-cols-2 gap-4">
            <InfoField label="Oda Tipi" value={room?.room_type || '-'} />
            <InfoField label="Oda No" value={booking?.room_number || room?.room_number || '-'} />
            <InfoField label="Konaklama Türü" value={translateValue(booking?.rate_plan) || 'Standart'} />
            <InfoField label={t('common.cancellationPolicy')} value={translateValue(booking?.cancellation_policy) || t('common.flexible')} />
          </div>
        </section>

        {booking?.special_requests && (
          <InfoField label="Özel İstekler" value={booking.special_requests} className="bg-amber-50 border-amber-200" />
        )}
      </div>
      <div className="space-y-4">
        <div className="border border-slate-200 rounded-xl bg-white p-4 space-y-3 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Ana Kontak</span>
            <Button variant="ghost" size="sm" onClick={() => setEditing(!editing)} className="h-7 px-2">
              <Pencil className="w-3 h-3 mr-1" /> {editing ? 'İptal' : 'Düzenle'}
            </Button>
          </div>
          {editing ? (
            <div className="space-y-2">
              <Input value={guestForm.name || ''} onChange={e => setGuestForm(p => ({ ...p, name: e.target.value }))} placeholder="Ad Soyad" className="h-8 text-sm" />
              <Input value={guestForm.email || ''} onChange={e => setGuestForm(p => ({ ...p, email: e.target.value }))} placeholder="E-posta" className="h-8 text-sm" />
              <Input value={guestForm.phone || ''} onChange={e => setGuestForm(p => ({ ...p, phone: e.target.value }))} placeholder="Telefon" className="h-8 text-sm" />
              <div className="border-t pt-2 mt-2 space-y-1.5">
                <Label className="text-[10px] uppercase text-gray-500 tracking-wide">VIP / Tercihler</Label>
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox" checked={!!guestForm.vip_status} onChange={e => setGuestForm(p => ({ ...p, vip_status: e.target.checked }))} />
                  <span>VIP misafir</span>
                </label>
                <Input value={guestForm.allergies || ''} onChange={e => setGuestForm(p => ({ ...p, allergies: e.target.value }))} placeholder="Alerjiler (Ananas, fındık)" className="h-8 text-xs" />
                <Input value={guestForm.dietary_restrictions || ''} onChange={e => setGuestForm(p => ({ ...p, dietary_restrictions: e.target.value }))} placeholder="Beslenme tercihi (Vejeteryan)" className="h-8 text-xs" />
                <Input value={guestForm.pillow_preference || ''} onChange={e => setGuestForm(p => ({ ...p, pillow_preference: e.target.value }))} placeholder="Yastık tercihi" className="h-8 text-xs" />
                <Input value={guestForm.room_preference || ''} onChange={e => setGuestForm(p => ({ ...p, room_preference: e.target.value }))} placeholder="Oda tercihi" className="h-8 text-xs" />
                <Input value={guestForm.important_notes || ''} onChange={e => setGuestForm(p => ({ ...p, important_notes: e.target.value }))} placeholder="Resepsiyon önemli notu" className="h-8 text-xs" />
                <div className="border-t pt-2 mt-2 space-y-1.5 bg-red-50 -mx-1 px-1 py-1.5 rounded">
                  <Label className="text-[10px] uppercase text-red-700 tracking-wide">Kara Liste</Label>
                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" checked={!!guestForm.blacklisted} onChange={e => setGuestForm(p => ({ ...p, blacklisted: e.target.checked }))} />
                    <span className="text-red-700 font-medium">Misafiri kara listeye al</span>
                  </label>
                  {guestForm.blacklisted && (
                    <Input value={guestForm.blacklist_reason || ''} onChange={e => setGuestForm(p => ({ ...p, blacklist_reason: e.target.value }))} placeholder="Sebep (zorunlu)" className="h-8 text-xs border-red-300" />
                  )}
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  <Input value={guestForm.birthday || ''} onChange={e => setGuestForm(p => ({ ...p, birthday: e.target.value }))} placeholder="Doğum (MM-DD)" className="h-8 text-xs" />
                  <Input value={guestForm.anniversary_date || ''} onChange={e => setGuestForm(p => ({ ...p, anniversary_date: e.target.value }))} placeholder="Yıldönümü (MM-DD)" className="h-8 text-xs" />
                </div>
              </div>
              <Button size="sm" onClick={async () => { await handleSave(); /* highlights refresh */ const gid = guest?.id || booking?.guest_id; if (gid) api.get(`/pms/guests/${gid}/highlights`).then(r => setHighlights(r.data)).catch(() => {}); }} className="w-full h-8"><Check className="w-3 h-3 mr-1" /> Kaydet</Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Avatar name={guest?.name || booking?.guest_name} size="lg" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-slate-800 truncate">{guest?.name || booking?.guest_name || '—'}</div>
                  {guest?.vip_status && (
                    <Badge className="mt-0.5 bg-amber-100 text-amber-700 border-amber-200 text-[10px] h-4 px-1.5"><Star className="w-2.5 h-2.5 mr-0.5" /> VIP</Badge>
                  )}
                </div>
              </div>
              <div className="space-y-1.5 pt-1 border-t border-slate-100">
                {guest?.email ? (
                  <a href={`mailto:${guest.email}`} className="flex items-center gap-2 text-xs text-slate-700 hover:text-amber-700 transition-colors group">
                    <Mail className="w-3.5 h-3.5 text-slate-400 group-hover:text-amber-600 shrink-0" />
                    <span className="truncate">{guest.email}</span>
                  </a>
                ) : (
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Mail className="w-3.5 h-3.5 shrink-0" /> E-posta yok
                  </div>
                )}
                {guest?.phone ? (
                  <a href={`tel:${guest.phone}`} className="flex items-center gap-2 text-xs text-slate-700 hover:text-amber-700 transition-colors group">
                    <Phone className="w-3.5 h-3.5 text-slate-400 group-hover:text-amber-600 shrink-0" />
                    <span className="truncate">{guest.phone}</span>
                  </a>
                ) : (
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Phone className="w-3.5 h-3.5 shrink-0" /> Telefon yok
                  </div>
                )}
                {guest?.nationality && (
                  <div className="flex items-center gap-2 text-xs text-slate-700">
                    <Globe className="w-3.5 h-3.5 text-slate-400 shrink-0" /> {guest.nationality}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
        {company && (
          <div className="border border-slate-200 rounded-xl bg-white p-4 space-y-2 shadow-sm">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Şirket</span>
            <div className="flex items-center gap-2"><Building2 className="w-4 h-4 text-slate-500" /><span className="text-sm text-slate-800">{company.name}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}

const ID_TYPES = [
  { code: 'tc_kimlik', label: 'TC Kimlik' },
  { code: 'passport', label: 'Pasaport' },
  { code: 'driving_license', label: 'Ehliyet' },
  { code: 'other', label: 'Diğer' },
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
                    <span className="ml-1 text-xs">{isEditing ? 'İptal' : 'Düzenle'}</span>
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
                    <div><Label className="text-xs">Doğum Tarihi</Label><Input type="date" value={form.date_of_birth} onChange={e => setForm(p => ({ ...p, date_of_birth: e.target.value }))} className="h-8 text-sm" /></div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <Label className="text-xs">Cinsiyet</Label>
                      <Select value={form.gender || ''} onValueChange={v => setForm(p => ({ ...p, gender: v }))}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Seçiniz" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="male">Erkek</SelectItem>
                          <SelectItem value="female">Kadın</SelectItem>
                          <SelectItem value="other">Diğer</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div><Label className="text-xs">Şehir</Label><Input value={form.city} onChange={e => setForm(p => ({ ...p, city: e.target.value }))} className="h-8 text-sm" /></div>
                    <div><Label className="text-xs">Ülke</Label><Input value={form.country} onChange={e => setForm(p => ({ ...p, country: e.target.value }))} className="h-8 text-sm" /></div>
                  </div>

                  <div><Label className="text-xs">Adres</Label><Input value={form.address} onChange={e => setForm(p => ({ ...p, address: e.target.value }))} className="h-8 text-sm" /></div>
                  <div><Label className="text-xs">Notlar</Label><Input value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} className="h-8 text-sm" /></div>

                  <div className="flex gap-2 pt-1">
                    <Button size="sm" onClick={() => handleSave(g.id, isPrimary)} disabled={saving} className="h-8">
                      {saving ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Check className="w-3 h-3 mr-1" />} Kaydet
                    </Button>
                    <Button size="sm" variant="outline" onClick={cancelEdit} className="h-8">Vazgeç</Button>
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
