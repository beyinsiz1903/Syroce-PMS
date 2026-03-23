import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Pencil, Check, Globe, Phone, Star, Building2, Users } from 'lucide-react';
import { API, fmtDate, InfoField, Avatar, EmptyState, statusLabel } from './helpers';

export function GeneralInfoTab({ booking, guest, room, company, onGuestUpdate }) {
  const [editing, setEditing] = useState(false);
  const [guestForm, setGuestForm] = useState({});
  useEffect(() => { if (guest) setGuestForm({ ...guest }); }, [guest]);

  const handleSave = async () => {
    try {
      await axios.put(`${API}/api/pms/reservations/${booking.id}/update-guest`, guestForm);
      toast.success('Misafir bilgileri guncellendi');
      setEditing(false);
      onGuestUpdate?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="general-info-tab">
      <div className="lg:col-span-2 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <InfoField label="Giris Tarihi" value={fmtDate(booking?.check_in)} />
          <InfoField label="Giris Saati" value="14:00" />
          <InfoField label="Cikis Tarihi" value={fmtDate(booking?.check_out)} />
          <InfoField label="Cikis Saati" value="12:00" />
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
          <InfoField label="Iptal Kurali" value={booking?.cancellation_policy || 'Esnek'} />
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
              <Pencil className="w-3 h-3 mr-1" /> {editing ? 'Iptal' : 'Duzenle'}
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

export function GuestsTab({ guests, booking }) {
  return (
    <div data-testid="guests-tab" className="space-y-3">
      {(!guests || guests.length === 0) ? <EmptyState icon={Users} text="Kayitli misafir bulunamadi" /> : (
        guests.map((g, i) => (
          <div key={g.id || i} className="border rounded-lg p-4 flex items-center gap-4">
            <Avatar name={g.name} size="lg" />
            <div className="flex-1">
              <div className="text-sm font-semibold">{g.name}</div>
              <div className="text-xs text-gray-500">{g.email || '-'} {g.phone ? `| ${g.phone}` : ''}</div>
            </div>
            {g.vip_status && <Badge className="bg-amber-100 text-amber-700">VIP</Badge>}
            {i === 0 && <Badge className="bg-blue-100 text-blue-700">Ana Misafir</Badge>}
          </div>
        ))
      )}
    </div>
  );
}
